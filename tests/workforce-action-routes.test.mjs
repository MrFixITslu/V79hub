import test from "node:test";
import assert from "node:assert/strict";
import express from "express";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { createServer } from "node:http";
import { createWorkActionStore } from "../server/workforce-action-store.mjs";
import { workforceActionRouters } from "../server/workforce-action-routes.mjs";

test("HTTP owner approval flow and separate worker boundary fail closed", async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "v79-work-api-"));
  const ledger = createWorkActionStore({ file: path.join(dir, "ledger.json"), secret: "SYNTHETIC-AUDIT-KEY-NOT-A-REAL-SECRET" });
  const now = Date.now(), token = "SYNTHETIC-SEPARATE-WORKER-TOKEN-123456";
  let active = true;
  const app = express(); app.use(express.json());
  app.use((req, _res, next) => { req.user = { mfaVerifiedAt: req.get("x-test-stale") ? now - 300001 : now }; next(); });
  const routers = workforceActionRouters({ ledger, enabled: () => active,
    ownerContext: req => req.get("x-test-owner") === "owner" ? { userId: "founder", organizationId: "owner-org" } : null,
    sameOrigin: req => req.get("origin") === "https://hub.synthetic.test", workerToken: () => token,
    ownerOrganizationId: () => "owner-org", ownerReady: () => true, now: () => now });
  app.use("/owner", routers.owner); app.use("/worker", routers.worker);
  const server = createServer(app); await new Promise(r => server.listen(0, "127.0.0.1", r));
  t.after(async () => { await new Promise(r => server.close(r)); await fs.rm(dir, { recursive: true, force: true }); });
  const base = "http://127.0.0.1:" + server.address().port;
  const call = (route, body, headers = {}) => fetch(base + route, { method: body === undefined ? "GET" : "POST", headers: { "content-type": "application/json", ...headers }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const owner = { "x-test-owner": "owner", origin: "https://hub.synthetic.test" }, worker = { "x-v79-workforce-token": token };
  const input = { operation: "create_work_item", system: "hub", summary: "Build approved Hub enhancement", payload: { detail: "Implement and test the requested Hub enhancement." }, idempotencyKey: "synthetic-api-task-key-1234" };
  assert.equal((await call("/owner")).status, 403);
  assert.equal((await call("/owner", input, { ...owner, "x-test-stale": "1" })).status, 403);
  assert.equal((await call("/owner", input, { ...owner, origin: "https://attacker.test" })).status, 403);
  const j = (await (await call("/owner", input, owner)).json()).job;
  const decision = { decision: "approve", expectedRevision: 1, digest: j.digest };
  assert.equal((await call("/owner/" + j.id + "/decision", { ...decision, digest: "0".repeat(64) }, owner)).status, 409);
  const approved = (await (await call("/owner/" + j.id + "/decision", decision, owner)).json()).job;
  assert.equal(approved.status, "approved");
  assert.equal((await call("/owner/" + j.id + "/execute", { expectedRevision: 2 }, owner)).status, 200);
  assert.equal((await call("/owner/" + j.id + "/execute", { expectedRevision: 3 }, owner)).status, 409);
  assert.equal((await (await call("/owner", undefined, owner)).json()).tasks.length, 1);
  const scope = { worker: "v79-release-worker", operations: ["validate_release"], systems: ["hub"] };
  assert.equal((await call("/worker/claim", scope, { "x-v79-agent-token": token })).status, 403);
  assert.equal((await call("/worker/claim", scope, { ...worker, origin: "https://hub.synthetic.test" })).status, 403);
  assert.equal((await call("/worker/claim", scope, { ...worker, cookie: "founder" })).status, 403);
  assert.equal((await call("/worker/claim", { ...scope, operations: ["shell"] }, worker)).status, 400);
  const release = { ...input, operation: "validate_release", idempotencyKey: "synthetic-release-key-1234", payload: { commitSha: "a".repeat(40), manifestSha256: "b".repeat(64) } };
  const proposed = (await (await call("/worker/propose", release, worker)).json()).job;
  assert.equal(proposed.status, "pending");
  assert.equal((await (await call("/worker/claim", scope, worker)).json()).job, null);
  await call("/owner/" + proposed.id + "/decision", { decision: "approve", expectedRevision: 1, digest: proposed.digest }, owner);
  const claim = (await (await call("/worker/claim", scope, worker)).json()).job;
  assert.equal(claim.status, "running");
  assert.equal((await call("/worker/" + claim.id + "/authorization", undefined, { ...worker, "x-v79-workforce-claim": claim.claim.token })).status, 200);
  await call("/owner/pause", { paused: true }, owner);
  assert.equal((await call("/worker/" + claim.id + "/authorization", undefined, { ...worker, "x-v79-workforce-claim": claim.claim.token })).status, 403);
  // Pausing blocks dispatch but permits the worker to report an already-started effect.
  const receipt = { claimToken: claim.claim.token, digest: claim.digest, status: "uncertain", receiptSha256: "c".repeat(64) };
  assert.equal((await call("/worker/" + claim.id + "/receipt", receipt, worker)).status, 200);
  assert.equal((await call("/worker/" + claim.id + "/receipt", receipt, worker)).status, 409);
  active = false; assert.equal((await call("/worker/claim", scope, worker)).status, 503);
});
