import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { createWorkActionStore } from "../server/workforce-action-store.mjs";
import { initialWorkState, proposeWork, decideWork, claimWork, finishWork, createApprovedWorkItem,
  cancelWork, pauseWork, publicWorkJob, validateWorkRequest } from "../server/workforce-actions.mjs";
const org = "synthetic-owner-org", actor = "synthetic-owner", now = Date.now();
const scope = { organizationId: org, actor, now };
const worker = { organizationId: org, worker: "v79-release-worker", operations: ["validate_release", "deploy_release", "rollback_release"], systems: ["hub"], now };
function input(operation = "create_work_item", key = "synthetic-work-key-1234") {
  return { operation, system: "hub", summary: "Review Hub operational readiness", idempotencyKey: key,
    payload: operation === "create_work_item" ? { detail: "Review the current backlog and prepare the next release." } : { commitSha: "a".repeat(40), manifestSha256: "b".repeat(64) } };
}
function approve(s, j) { return decideWork(s, j.id, "approve", { ...scope, expectedRevision: j.revision, digest: j.digest }); }
function finish(s, j, status = "succeeded") { return finishWork(s, j.id, { claimToken: j.claim.token, digest: j.digest, status, receiptSha256: "c".repeat(64) }, worker); }
test("exact approval is required; task creation is durable and cannot replay", () => {
  const s = initialWorkState(), j = proposeWork(s, input(), scope);
  assert.throws(() => createApprovedWorkItem(s, j.id, { ...scope, expectedRevision: 1 }));
  assert.throws(() => decideWork(s, j.id, "approve", { ...scope, expectedRevision: 1, digest: "0".repeat(64) }));
  approve(s, j);
  createApprovedWorkItem(s, j.id, { ...scope, expectedRevision: 2 });
  assert.equal(j.status, "succeeded"); assert.equal(s.tasks.length, 1); assert.equal(s.tasks[0].assignedTo, "coo");
  assert.throws(() => createApprovedWorkItem(s, j.id, { ...scope, expectedRevision: 3 }));
  assert.throws(() => approve(s, j));
});
test("unknown operations, shell fields, secrets and mismatched target are rejected", () => {
  for (const raw of [{ ...input(), operation: "shell" }, { ...input(), command: "docker rm" },
    { ...input(), system: "customer-system" }, { ...input(), payload: { detail: "secret=credential-data" } },
    { ...input("deploy_release"), payload: { commitSha: "main", manifestSha256: "b".repeat(64) } }]) assert.throws(() => validateWorkRequest(raw));
});
test("modified payload, revision races, rejected/expired/cross-tenant approvals cannot execute", () => {
  const s = initialWorkState(), j = proposeWork(s, input("validate_release"), scope);
  assert.equal(claimWork(s, worker), null);
  approve(s, j); j.payload.commitSha = "d".repeat(40);
  assert.equal(claimWork(s, worker), null);
  j.payload.commitSha = "a".repeat(40);
  assert.equal(claimWork(s, { ...worker, organizationId: "foreign-org" }), null);
  assert.equal(claimWork(s, { ...worker, now: now + 3600001 }), null);
  assert.throws(() => cancelWork(s, j.id, { ...scope, expectedRevision: 1 }));
  cancelWork(s, j.id, { ...scope, expectedRevision: 2 }); assert.equal(claimWork(s, worker), null);
});
test("deployment requires validation of same immutable manifest; rollback requires attempted deploy", () => {
  const s = initialWorkState(), deploy = proposeWork(s, input("deploy_release"), scope); approve(s, deploy);
  assert.equal(claimWork(s, worker), null);
  const validation = proposeWork(s, input("validate_release", "synthetic-check-key-1234"), scope); approve(s, validation);
  assert.equal(claimWork(s, worker).id, validation.id); finish(s, validation);
  assert.equal(claimWork(s, worker).id, deploy.id); finish(s, deploy, "uncertain");
  const rollback = proposeWork(s, input("rollback_release", "synthetic-rollback-key-1234"), scope); approve(s, rollback);
  assert.equal(claimWork(s, worker).id, rollback.id);
});
test("pause stops claims, receipts require exact worker and token, running jobs never replay", () => {
  const s = initialWorkState(), j = proposeWork(s, input("validate_release"), scope); approve(s, j);
  pauseWork(s, true, scope); assert.equal(claimWork(s, worker), null); pauseWork(s, false, scope);
  claimWork(s, worker); assert.equal(claimWork(s, worker), null); assert.equal(publicWorkJob(j).claim.token, undefined);
  assert.throws(() => finishWork(s, j.id, { claimToken: "forged", digest: j.digest, status: "succeeded", receiptSha256: "c".repeat(64) }, worker));
  finish(s, j); assert.throws(() => finish(s, j));
});
test("idempotency binds payload and actor cannot replace an existing action", () => {
  const s = initialWorkState(), j = proposeWork(s, input(), scope);
  assert.equal(proposeWork(s, input(), scope).id, j.id);
  assert.throws(() => proposeWork(s, { ...input(), summary: "Replace previously reviewed work" }, scope));
});
test("file ledger survives restart, rolls back failed mutation, detects payload tampering and refuses stolen locks", async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "v79-work-ledger-")); t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const opts = { file: path.join(dir, "actions.json"), secret: "SYNTHETIC-WORKFORCE-AUDIT-KEY-1234567890" };
  const a = createWorkActionStore(opts), j = await a.transact(s => proposeWork(s, input(), scope));
  const b = createWorkActionStore(opts); assert.equal((await b.read()).jobs[0].id, j.id);
  await assert.rejects(a.transact(s => { s.jobs.length = 0; throw new Error("disk failure"); }));
  assert.equal((await b.read()).jobs.length, 1);
  await fs.mkdir(opts.file + ".lock"); await assert.rejects(b.transact(s => proposeWork(s, input(), scope))); await fs.rmdir(opts.file + ".lock");
  const envelope = JSON.parse(await fs.readFile(opts.file, "utf8")); envelope.state.jobs[0].payload.detail = "Tampered release instructions";
  await fs.writeFile(opts.file, JSON.stringify(envelope)); await assert.rejects(b.read(), /integrity/);
});
