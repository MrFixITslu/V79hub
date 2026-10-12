import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createOwnerExecutiveProxy } from "../server/agent-executive-owner-proxy.mjs";

const owner = Object.freeze({
  userId: "synthetic-founder", email: "founder@example.invalid",
  organizationId: "synthetic-owner-org", ownerAgent: true, hubAdmin: true,
});

function response() {
  return {
    statusCode: 200, headers: {}, body: undefined,
    setHeader(name, value) { this.headers[name.toLowerCase()] = value; return this; },
    status(value) { this.statusCode = value; return this; },
    json(value) { this.body = value; return this; },
  };
}
function make(kind, overrides = {}) {
  const calls = [];
  const defaults = {
    ownerMfaContext: () => owner,
    readServiceToken: () => "synthetic-test-token",
    agentBaseUrl: "http://synthetic-agent.invalid:3055",
    fetchImpl: async (url, options) => {
      calls.push({ url: String(url), options });
      return new Response(JSON.stringify({ mode: "read-only", actionsEnabled: false,
        roles: [{ id: "ceo" }, { id: "coo" }] }),
        { status: 200, headers: { "content-type": "application/json" } });
    },
  };
  return { handler: createOwnerExecutiveProxy(kind, { ...defaults, ...overrides }), calls };
}

test("Hub routes wire all three fixed endpoints behind founder MFA", () => {
  const source = fs.readFileSync(new URL("../server.ts", import.meta.url), "utf8");
  for (const [verb, route, kind] of [
    ["get", "executive-structure", "structure"],
    ["post", "executive-handoff", "handoff"],
    ["post", "executive-preview", "preview"],
  ]) {
    assert.ok(source.includes(`app.${verb}("/api/agent/${route}"`));
    assert.ok(source.includes(`createOwnerExecutiveProxy("${kind}", executiveProxyDeps)`));
  }
  assert.match(source, /ownerMfaContext: ownerApprovalContext/);
  assert.match(source, /readServiceToken: readAgentApiToken/);
});

test("non-owner or non-MFA session is rejected before contacting agent", async () => {
  const {handler, calls} = make("structure", {ownerMfaContext: () => null});
  const res = response();
  await handler({body: {context: owner}}, res);
  assert.equal(res.statusCode, 403);
  assert.equal(res.headers["cache-control"], "no-store");
  assert.equal(calls.length, 0);
});

test("missing service token fails closed, never contacts agent", async () => {
  const {handler, calls} = make("handoff", {readServiceToken: () => ""});
  const res = response();
  await handler({}, res);
  assert.equal(res.statusCode, 503);
  assert.equal(calls.length, 0);
});

test("structure fetch sends only internal token, no browser-supplied context or headers", async () => {
  const {handler,calls} = make("structure");
  const res = response();
  await handler({body: {context: {ownerAgent: true, organizationId: "attacker"}},
    headers: {"x-v79-agent-token": "malicious"}},res);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.mode, "read-only");
  assert.equal(res.headers["cache-control"], "no-store");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://synthetic-agent.invalid:3055/api/agent/executive-structure");
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.body, undefined);
  assert.equal(calls[0].options.headers["x-v79-agent-token"], "synthetic-test-token");
  assert.equal(calls[0].options.redirect, "manual");
});

test("handoff POST uses server-attested founder context and fixed internal route", async () => {
  const {handler,calls} = make("handoff");
  const res = response();
  await handler({body: {context: {ownerAgent:false, email:"forged@example.invalid"}}},res);
  assert.equal(res.statusCode, 200);
  assert.equal(calls[0].url, "http://synthetic-agent.invalid:3055/api/agent/executive-handoff");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {context: owner});
});

test("disabled preview remains disabled and cannot be enabled by request body", async () => {
  const {handler,calls} = make("preview", {fetchImpl: async (url, options) => {
    calls.push({url: String(url), options});
    return new Response(JSON.stringify({error:"Executive model preview is disabled."}),
      {status:404,headers:{"content-type":"application/json"}});
  }});
  const res = response();
  await handler({body:{V79_EXECUTIVE_MODEL_CYCLE_ENABLED:"1"}}, res);
  assert.equal(res.statusCode,404);
  assert.deepEqual(JSON.parse(calls[0].options.body), {context: owner});
});

test("unexpected redirect, invalid JSON, excessive body and transport failure fail closed", async () => {
  const outcomes = [
    async () => new Response("", {status:302,headers:{location:"https://evil.invalid"}}),
    async () => new Response("not-json", {status:200}),
    async () => new Response(JSON.stringify({value:"x".repeat(140000)}), {status:200}),
    async () => { throw new Error("synthetic upstream outage"); },
  ];
  for (const fetchImpl of outcomes) {
    const {handler} = make("handoff", {fetchImpl});
    const res = response();
    await handler({}, res);
    assert.equal(res.statusCode,502);
    assert.equal(res.headers["cache-control"],"no-store");
  }
});

test("arbitrary agent paths, URL credentials and unsupported executive operations are rejected", () => {
  assert.throws(() => make("arbitrary-route"), /Unsupported executive endpoint/);
  assert.throws(() => make("structure", {agentBaseUrl:"http://user:secret@synthetic-agent.invalid"}), /Invalid internal agent service URL/);
  assert.throws(() => make("structure", {agentBaseUrl:"file:///etc/passwd"}), /Invalid internal agent service URL/);
});
