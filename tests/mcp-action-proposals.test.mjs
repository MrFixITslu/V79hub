import test from "node:test";
import assert from "node:assert/strict";
import express from "express";
import { randomBytes } from "node:crypto";
import { createMcpProposalRouter, MCP_PROPOSAL_PATH, signMcpProposal, verifyMcpProposal } from "../server/mcp-action-proposals.mjs";
import { initialWorkState } from "../server/workforce-actions.mjs";

const key = "V79_TEST_ONLY_" + "m".repeat(45);
const payload = (suffix = "one") => ({
  operation: "create_work_item", system: "hub",
  summary: "Review customer onboarding readiness",
  payload: { detail: "Inspect the current customer onboarding journey and document gaps." },
  idempotencyKey: "MCP_Source_ValidKey_" + suffix,
});
function signed(input = payload(), options = {}) {
  const body = JSON.stringify(input), at = options.at ?? Date.now();
  const nonce = randomBytes(32).toString("base64url");
  return {
    body,
    headers: {
      "content-type": "application/json",
      "x-v79-mcp-timestamp": String(at),
      "x-v79-mcp-nonce": nonce,
      "x-v79-mcp-signature": signMcpProposal({
        key: options.secret ?? key, timestamp: at, nonce, body,
      }),
      ...(options.headers || {}),
    },
  };
}
async function host(t, opts = {}) {
  const state = initialWorkState();
  const ledger = { transact: async fn => fn(state) };
  const app = express();
  app.use(express.json({ limit: "2mb", verify: (req, _res, body) => { req.rawBody = Buffer.from(body); } }));
  app.use(MCP_PROPOSAL_PATH, createMcpProposalRouter({
    ledger, enabled: opts.enabled || (() => true),
    secret: opts.secret || (() => key),
    ownerReady: opts.ownerReady || (() => true),
    ownerOrganizationId: () => "owner-organization-verified",
    now: opts.now || Date.now,
  }));
  const server = await new Promise(resolve => {
    const running = app.listen(0, "127.0.0.1", () => resolve(running));
  });
  t.after(() => new Promise(resolve => server.close(resolve)));
  const endpoint = "http://127.0.0.1:" + server.address().port + MCP_PROPOSAL_PATH;
  async function post(input, options) {
    const r = signed(input, options);
    const response = await fetch(endpoint, {
      method: "POST", headers: r.headers, body: r.body, redirect: "manual",
    });
    return { status: response.status, body: await response.json() };
  }
  return { state, post, endpoint };
}

test("signed MCP proposal queues a pending owner-reviewed Hub work item, never creates it", async t => {
  const h = await host(t);
  const { status, body } = await h.post(payload());
  assert.equal(status, 201);
  assert.equal(body.proposal.status, "pending");
  assert.equal(body.proposal.system, "hub");
  assert.match(body.approval, /Founder review required/);
  assert.equal(h.state.jobs.length, 1);
  assert.equal(h.state.tasks.length, 0, "MCP never executes work items");
  assert.equal(h.state.jobs[0].createdBy, "mcp-action-broker");
  assert.equal(h.state.jobs[0].organizationId, "owner-organization-verified");
});

test("idempotent replay returns same pending proposal", async t => {
  const h = await host(t);
  const first = await h.post(payload("duplicate"));
  const second = await h.post(payload("duplicate"));
  assert.equal(first.status, 201); assert.equal(second.status, 201);
  assert.equal(first.body.proposal.id, second.body.proposal.id);
  assert.equal(h.state.jobs.length, 1);
  assert.equal(h.state.tasks.length, 0);
});
test("idempotency conflict denies a different payload", async t => {
  const h = await host(t);
  assert.equal((await h.post(payload("same-key"))).status, 201);
  const changed = payload("same-key");
  changed.payload.detail = "A different action with the same idempotency key.";
  const response = await h.post(changed);
  assert.equal(response.status, 409);
  assert.equal(response.body.code, "MCP_IDEMPOTENCY_CONFLICT");
  assert.equal(h.state.jobs.length, 1);
});
test("rejects execution, deployment and other app operations", async t => {
  const h = await host(t);
  for (const [i, change] of [
    { operation: "deploy_release" }, { operation: "rollback_release" },
    { system: "pos" }, { system: "ffpro" }, { operation: "delete_user" },
  ].entries()) {
    assert.ok([400,403].includes((await h.post({ ...payload("denied"+i), ...change })).status));
  }
  assert.equal(h.state.jobs.length, 0);
});
test("Tiquet and Marketing proposals create internal Hub triage jobs only, not app writes", async t => {
  const h = await host(t);
  for (const system of ["tiquet", "marketing"]) {
    const input = { ...payload("triage_"+system), system,
      summary: system==="tiquet" ? "Review a Tiquet customer support issue" : "Review a V79 Marketing content brief" };
    const answer = await h.post(input);
    assert.equal(answer.status, 201);
    assert.equal(answer.body.proposal.status, "pending");
    assert.equal(answer.body.proposal.system, system);
  }
  assert.deepEqual(h.state.jobs.map(j=>j.system), ["tiquet", "marketing"]);
  assert.deepEqual(h.state.jobs.map(j=>j.status), ["pending", "pending"]);
  assert.equal(h.state.tasks.length, 0, "No internal task or external app action until Hub owner approval");
});
test("signature is bound to exact bytes, method, fixed endpoint and time", () => {
  const r = signed();
  const fields = {
    method: "POST", path: MCP_PROPOSAL_PATH, contentType: "application/json",
    rawBody: Buffer.from(r.body), key,
    timestamp: r.headers["x-v79-mcp-timestamp"],
    nonce: r.headers["x-v79-mcp-nonce"],
    signature: r.headers["x-v79-mcp-signature"],
  };
  assert.equal(verifyMcpProposal(fields), true);
  assert.equal(verifyMcpProposal({ ...fields, path: "/internal/mcp/v1/execute" }), false);
  assert.equal(verifyMcpProposal({ ...fields, rawBody: Buffer.from(r.body + " ") }), false);
  assert.equal(verifyMcpProposal({ ...fields, timestamp: String(Date.now()-300000) }), false);
});
test("expired requests, cookies, origins, bearer tokens and forged signatures fail", async t => {
  const h = await host(t);
  const cases = [
    { at: Date.now() - 200000 },
    { headers: { origin: "https://untrusted.example" } },
    { headers: { cookie: "session=no" } },
    { headers: { authorization: "Bearer do-not-forward" } },
    { headers: { "x-v79-mcp-signature": "f".repeat(64) } },
  ];
  for (const [i, options] of cases.entries()) {
    assert.equal((await h.post(payload("blocked"+i),options)).status, 403);
  }
  assert.equal(h.state.jobs.length, 0);
  const missing = await host(t,{secret:()=>""});
  assert.equal((await missing.post(payload("missing-secret"))).status,403);
});
test("disabled flag or inactive Hub owner fail closed", async t => {
  const disabled = await host(t,{enabled:()=>false});
  const ownerOff = await host(t,{ownerReady:()=>false});
  assert.equal((await disabled.post(payload("off"))).status,503);
  assert.equal((await ownerOff.post(payload("owner-off"))).status,503);
  assert.equal(disabled.state.jobs.length,0);assert.equal(ownerOff.state.jobs.length,0);
});
test("rejects model-supplied tenancy and malformed work", async t => {
  const h = await host(t);
  assert.equal((await h.post({ ...payload(), organizationId:"injected-tenant"})).status,400);
  assert.equal((await h.post({ ...payload(),payload:{detail:"short"} })).status,400);
  assert.equal(h.state.jobs.length,0);
});
test("GET never reveals private proposals", async t => {
  const h=await host(t);
  const r=await fetch(h.endpoint);
  assert.equal(r.status,405);
  assert.equal(h.state.jobs.length,0);
});
