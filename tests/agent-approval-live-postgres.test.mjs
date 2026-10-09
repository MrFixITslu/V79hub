import test from "node:test";
import assert from "node:assert/strict";
import { fork } from "node:child_process";
import { fileURLToPath } from "node:url";
import { Pool } from "pg";
import { PostgresStoreRepository } from "../server/postgres-store.mjs";
import { createHubStorePersistence } from "../server/runtime-store.mjs";
import { createAgentProposal, appendAgentProposalAudit, decideAgentProposal } from "../server/agent-approval-ledger.mjs";
import { createAgentApprovalAuditChain, verifyAgentApprovalAuditLinkage } from "../server/agent-approval-audit-chain.mjs";

const connection = String(process.env.V79_APPROVAL_TEST_PG_URL || "");
const workerPath = fileURLToPath(new URL("./helpers/agent-approval-pg-worker.mjs", import.meta.url));
const owner = { organizationId: "ci-owner-org", actorUserId: "ci-founder" };
const hmac = createAgentApprovalAuditChain("ci-only-owner-approval-hmac-key-1234567890");

function assertIsolatedDatabase() {
  const target = new URL(connection);
  assert.equal(target.hostname, "127.0.0.1", "never target a remote or production PostgreSQL instance");
  assert.equal(target.port, "5432");
  assert.equal(target.pathname, "/v79_ci_approval");
  assert.equal(target.username, "v79_ci_agent");
}

function startWorker(t, task) {
  const child = fork(workerPath, [], {
    stdio: ["ignore", "ignore", "pipe", "ipc"],
    env: { ...process.env, V79_APPROVAL_TEST_PG_URL: connection },
  });
  let readyOk = false;
  let finished = false;
  let resolveReady, rejectReady, resolveDone, rejectDone;
  const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
  const complete = new Promise((resolve, reject) => { resolveDone = resolve; rejectDone = reject; });
  // Prevent unhandled rejection before a slow child reaches the test's result barrier.
  ready.catch(() => {});
  complete.catch(() => {});
  let safeError = "";
  child.stderr?.on("data", value => { safeError = (safeError + String(value)).slice(-350); });
  const timer = setTimeout(() => {
    child.kill("SIGKILL");
    const error = Error("Isolated PostgreSQL worker timed out");
    if (!readyOk) rejectReady(error);
    if (!finished) rejectDone(error);
  }, 25000);
  timer.unref();
  child.on("message", message => {
    if (message?.type === "ready") {
      readyOk = true;
      resolveReady(message);
    } else if (message?.type === "result") {
      finished = true;
      clearTimeout(timer);
      resolveDone(message);
    } else if (message?.type === "fatal") {
      const error = Error("Isolated PostgreSQL worker fatal: " + String(message.errorName));
      if (!readyOk) rejectReady(error);
      if (!finished) rejectDone(error);
    }
  });
  child.on("exit", code => {
    if (!readyOk) rejectReady(Error("Worker exited before barrier: " + code + " " + safeError));
    if (!finished) rejectDone(Error("Worker exited without a result: " + code + " " + safeError));
    clearTimeout(timer);
  });
  child.on("error", error => {
    if (!readyOk) rejectReady(error);
    if (!finished) rejectDone(error);
    clearTimeout(timer);
  });
  t.after(() => { if (child.exitCode === null && !child.killed) child.kill(); });
  return {
    ready,
    complete,
    go() { child.send({ type: "go", task }); },
  };
}

async function pairRace(t, tasks, expectedRevision) {
  const workers = tasks.map(task => startWorker(t, task));
  const ready = await Promise.all(workers.map(worker => worker.ready));
  assert.deepEqual(ready.map(item => item.revision), [expectedRevision, expectedRevision],
    "both independent processes must load the same pre-write snapshot");
  for (const worker of workers) worker.go();
  const results = await Promise.all(workers.map(worker => worker.complete));
  assert.deepEqual(results.map(item => item.outcome).sort(), ["saved", "stale"],
    "exactly one concurrent PostgreSQL CAS writer must commit");
  return results;
}

test("real PostgreSQL rejects independent process races and preserves signed approval history", {
  skip: !connection && "No isolated CI PostgreSQL configured; never use the live Hub DB",
  timeout: 90000,
}, async t => {
  assertIsolatedDatabase();
  const pool = new Pool({ connectionString: connection, max: 5, connectionTimeoutMillis: 10000 });
  t.after(async () => { await pool.end(); });
  const repository = new PostgresStoreRepository(pool);
  await repository.ensureSchema();
  const initial = { users: [], agentActionProposals: [], agentProposalAuditTrail: [], auditEvents: [] };
  const init = await repository.initialize(initial);
  assert.equal(init.initialized, true, "the CI test database must be fresh and empty");

  const firstTasks = [
    { type: "create", summary: "Review inventory health this week", key: "real-pg-race-inventory-0001" },
    { type: "create", summary: "Review operational demand trend", key: "real-pg-race-demand-0002" },
  ];
  const firstRace = await pairRace(t, firstTasks, 1);
  const savedIndex = firstRace.findIndex(item => item.outcome === "saved");
  const failedIndex = 1 - savedIndex;
  let persisted = await repository.load();
  assert.equal(persisted.revision, 2);
  assert.equal(persisted.state.agentActionProposals.length, 1);
  assert.equal(persisted.state.agentProposalAuditTrail.length, 1);
  assert.equal(hmac.verify(persisted.state.agentProposalAuditTrail), true);
  assert.equal(verifyAgentApprovalAuditLinkage(
    persisted.state.agentProposalAuditTrail, persisted.state.agentActionProposals), true);

  // Replay the losing work only after reloading current state. No silent drop.
  const writer = createHubStorePersistence({
    backend: "postgres", databaseUrl: connection, storeFile: "/tmp/unused-v79-approval-test.json",
  });
  t.after(async () => writer.close());
  const state = await writer.load(value => value, () => { throw Error("do not seed"); });
  const retry = firstTasks[failedIndex];
  const created = createAgentProposal(state.agentActionProposals, {
    operation: "draft_operational_report", targetSystem: "hub",
    summary: retry.summary,
    rationale: "Examine safe aggregate indicators before preparing a human-only plan.",
    idempotencyKey: retry.key,
  }, owner);
  assert.equal(created.kind, "created");
  appendAgentProposalAudit(state.auditEvents, created.proposal, "agent.proposal.created", owner.actorUserId);
  hmac.append(state.agentProposalAuditTrail, created.proposal, owner.actorUserId);
  await writer.save(state);
  assert.equal(writer.revision(), 3);
  persisted = await repository.load();
  assert.equal(persisted.state.agentActionProposals.length, 2);
  assert.equal(new Set(persisted.state.agentActionProposals.map(item => item.id)).size, 2);
  assert.equal(hmac.verify(persisted.state.agentProposalAuditTrail), true);
  assert.equal(verifyAgentApprovalAuditLinkage(
    persisted.state.agentProposalAuditTrail, persisted.state.agentActionProposals), true);

  // Competing decisions on the same pending plan must never both commit.
  const targetId = persisted.state.agentActionProposals[0].id;
  const decisions = await pairRace(t, [
    { type: "decision", id: targetId, decision: "approve" },
    { type: "decision", id: targetId, decision: "reject" },
  ], 3);
  const winningDecision = ["approve", "reject"][decisions.findIndex(item => item.outcome === "saved")];
  persisted = await repository.load();
  assert.equal(persisted.revision, 4);
  const approvedOrRejected = persisted.state.agentActionProposals.find(item => item.id === targetId);
  assert.equal(approvedOrRejected.status, winningDecision === "approve" ? "approved" : "rejected");
  assert.equal(approvedOrRejected.revision, 2);
  assert.equal(approvedOrRejected.executionStatus, "disabled");
  assert.equal(persisted.state.agentProposalAuditTrail.length, 3);
  assert.equal(hmac.verify(persisted.state.agentProposalAuditTrail), true);
  assert.equal(verifyAgentApprovalAuditLinkage(
    persisted.state.agentProposalAuditTrail, persisted.state.agentActionProposals), true);

  const replay = decideAgentProposal(persisted.state.agentActionProposals, {
    id: targetId, ...owner, expectedRevision: 1, decision: winningDecision === "approve" ? "reject" : "approve",
  });
  assert.equal(replay.kind, "conflict", "a stale independent decision cannot supersede the winner");
  assert.equal(persisted.state.agentActionProposals.every(item => item.executionStatus === "disabled"), true);
});
