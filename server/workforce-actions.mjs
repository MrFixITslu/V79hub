import { createHash, randomUUID } from "node:crypto";
import { GOOGLE_OPERATIONS, validateGooglePayload } from './workforce-google.mjs';

export const WORK_SYSTEMS = Object.freeze(["hub", "tiquet", "marketing", "ffpro", "pos", "academy", "website", "games", "sentinel", "lasertag", "gmail", "calendar"]);
export const WORK_OPERATIONS = Object.freeze(["create_work_item", "validate_release", "deploy_release", "rollback_release", ...GOOGLE_OPERATIONS]);
export const WORK_SPECIALISTS = Object.freeze(["coo", "finance", "strategy", "marketing", "customer-service", "technical-security", "sales"]);
const SHA = /^[a-f0-9]{64}$/;
const COMMIT = /^[a-f0-9]{40}$/;
const MAX = 2000;
function exact(value, fields) {
  return value && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).sort().join(",") === fields.slice().sort().join(",");
}
function text(value, max) {
  return typeof value === "string" && value === value.trim() && value.length >= 8 && value.length <= max &&
    !/[\u0000-\u001f\u007f]/.test(value) &&
    !/\b(password|secret|token|api[_ -]?key|private\s*key)\s*[:=]/i.test(value.normalize("NFKC"));
}
export function validateWorkRequest(input) {
  if (!exact(input, ["operation", "system", "summary", "payload", "idempotencyKey"]) ||
      !WORK_OPERATIONS.includes(input.operation) || !WORK_SYSTEMS.includes(input.system) ||
      !text(input.summary, 180) || !/^[A-Za-z0-9_-]{16,96}$/.test(input.idempotencyKey)) throw new Error("Invalid action request");
  if (GOOGLE_OPERATIONS.includes(input.operation)) {
    validateGooglePayload(input.operation, input.system, input.payload);
  } else if (["gmail", "calendar"].includes(input.system)) {
    throw new Error("Google systems require a bounded Google operation");
  } else if (input.operation === "create_work_item") {
    if (!(exact(input.payload, ["detail"]) ||
      (exact(input.payload, ["detail", "specialist"]) && WORK_SPECIALISTS.includes(input.payload.specialist))) || !text(input.payload.detail, 2000)) throw new Error("Invalid work item");
  } else if (!exact(input.payload, ["commitSha", "manifestSha256"]) ||
      !COMMIT.test(input.payload.commitSha) || !SHA.test(input.payload.manifestSha256)) throw new Error("Immutable release manifest required");
  return structuredClone(input);
}
export function workDigest(input) {
  const request = validateWorkRequest(input);
  return createHash("sha256").update(JSON.stringify([
    request.operation, request.system, request.summary,
    GOOGLE_OPERATIONS.includes(request.operation) ? Object.keys(request.payload).sort().map(k=>[k,request.payload[k]]) :
      request.operation === "create_work_item" ? (Object.hasOwn(request.payload, "specialist")
        ? [request.payload.detail, request.payload.specialist] : request.payload.detail) : [request.payload.commitSha, request.payload.manifestSha256],
    request.idempotencyKey,
  ])).digest("hex");
}
export function initialWorkState() { return { version: 1, paused: false, jobs: [], tasks: [], events: [] }; }
function fail(message) { throw new Error(message); }
function event(state, job, actor, type, now) {
  if (state.events.length >= MAX * 8) fail("Audit capacity reached");
  state.events.push({ id: randomUUID(), jobId: job?.id ?? null, actor, type,
    at: new Date(now).toISOString(), revision: job?.revision ?? null, digest: job?.digest ?? null });
}
function find(state, id, organizationId) {
  const job = state.jobs.find(item => item.id === id && item.organizationId === organizationId);
  if (!job) fail("Action not found");
  return job;
}
function revision(job, expected) {
  if (!Number.isSafeInteger(expected) || expected !== job.revision) fail("Action revision conflict");
}
export function proposeWork(state, input, { organizationId, actor, now = Date.now() }) {
  if (!organizationId || !actor || !Number.isFinite(now)) fail("Trusted identity required");
  const request = validateWorkRequest(input), digest = workDigest(request);
  const prior = state.jobs.find(j => j.organizationId === organizationId && j.idempotencyKey === request.idempotencyKey);
  if (prior) { if (prior.digest !== digest) fail("Idempotency conflict"); return prior; }
  if (state.jobs.length >= MAX) fail("Action capacity reached");
  const job = { ...request, id: randomUUID(), organizationId, createdBy: actor, digest,
    status: "pending", revision: 1, createdAt: new Date(now).toISOString(),
    expiresAt: new Date(now + 24 * 3600000).toISOString(), approval: null, claim: null, result: null };
  state.jobs.push(job); event(state, job, actor, "proposed", now); return job;
}
export function decideWork(state, id, decision, { organizationId, actor, expectedRevision, digest, now = Date.now() }) {
  const job = find(state, id, organizationId); revision(job, expectedRevision);
  if (!actor || job.status !== "pending" || !["approve", "reject"].includes(decision) ||
      digest !== job.digest || digest !== workDigest(jobRequest(job)) || !(Date.parse(job.expiresAt) > now)) fail("Action cannot be approved");
  job.status = decision === "approve" ? "approved" : "rejected"; job.revision++;
  if (decision === "approve") job.approval = { by: actor, digest, at: new Date(now).toISOString(),
    expiresAt: new Date(now + (job.operation.includes("deploy") || job.operation.includes("rollback") ? 15 : 60) * 60000).toISOString() };
  event(state, job, actor, job.status, now); return job;
}
function jobRequest(job) { return Object.fromEntries(["operation", "system", "summary", "payload", "idempotencyKey"].map(k => [k, job[k]])); }
function approved(job, now) {
  return job.status === "approved" && job.approval?.digest === job.digest &&
    job.digest === workDigest(jobRequest(job)) && Date.parse(job.approval.expiresAt) > now;
}
export function claimWork(state, { organizationId, worker, operations, systems, jobId = null, now = Date.now() }) {
  if (state.paused) return null;
  if (!worker || !Array.isArray(operations) || !Array.isArray(systems)) fail("Trusted worker required");
  const job = state.jobs.find(j => (!jobId || j.id === jobId) && j.organizationId === organizationId && operations.includes(j.operation) &&
    systems.includes(j.system) && approved(j, now) &&
    (j.operation !== "deploy_release" || state.jobs.some(v => v.organizationId === organizationId &&
      v.operation === "validate_release" && v.status === "succeeded" && v.system === j.system &&
      v.payload.commitSha === j.payload.commitSha && v.payload.manifestSha256 === j.payload.manifestSha256)) &&
    (j.operation !== "rollback_release" || state.jobs.some(v => v.organizationId === organizationId &&
      v.operation === "deploy_release" && ["succeeded", "uncertain"].includes(v.status) && v.system === j.system &&
      v.payload.commitSha === j.payload.commitSha && v.payload.manifestSha256 === j.payload.manifestSha256)));
  if (!job) return null;
  // Never automatically reclaim a running job. A crash can leave an uncertain
  // external effect; manual reconciliation and a new approval are required.
  job.status = "running"; job.revision++;
  job.claim = { worker, token: randomUUID(), at: new Date(now).toISOString() };
  event(state, job, worker, "claimed", now); return job;
}
export function cancelWork(state, id, { organizationId, actor, expectedRevision, now = Date.now() }) {
  const job = find(state, id, organizationId); revision(job, expectedRevision);
  if (!actor || !["pending", "approved"].includes(job.status)) fail("Running or completed actions cannot be cancelled");
  job.status = "cancelled"; job.revision++; event(state, job, actor, "cancelled", now); return job;
}
export function finishWork(state, id, receipt, { organizationId, worker, now = Date.now() }) {
  const job = find(state, id, organizationId);
  if (!exact(receipt, ["claimToken", "digest", "status", "receiptSha256"]) ||
      !["succeeded", "failed", "uncertain"].includes(receipt.status) || !SHA.test(receipt.receiptSha256) ||
      job.status !== "running" || job.claim?.worker !== worker || job.claim?.token !== receipt.claimToken ||
      receipt.digest !== job.digest || workDigest(jobRequest(job)) !== job.digest) fail("Invalid worker receipt");
  job.status = receipt.status; job.revision++;
  job.result = { receiptSha256: receipt.receiptSha256, at: new Date(now).toISOString() };
  event(state, job, worker, receipt.status, now); return job;
}
export function createApprovedWorkItem(state, id, { organizationId, actor, expectedRevision, now = Date.now() }) {
  const job = find(state, id, organizationId); revision(job, expectedRevision);
  if (state.paused || !actor || job.operation !== "create_work_item" || !approved(job, now)) fail("Work item requires current approval");
  if (state.tasks.length >= MAX) fail("Task capacity reached");
  const task = { id: randomUUID(), jobId: job.id, organizationId, system: job.system,
    title: job.summary, detail: job.payload.detail, status: "open", assignedTo: "coo", createdAt: new Date(now).toISOString() };
  if (job.payload.specialist) task.specialist = job.payload.specialist;
  state.tasks.push(task); job.status = "succeeded"; job.revision++;
  job.result = { taskId: task.id, at: new Date(now).toISOString() };
  event(state, job, actor, "work_item_created", now); return job;
}
export function pauseWork(state, paused, { actor, now = Date.now() }) {
  if (typeof paused !== "boolean" || !actor) fail("Invalid pause request");
  state.paused = paused; event(state, null, actor, paused ? "paused" : "resumed", now);
}
export function publicWorkJob(job) {
  const copy = structuredClone(job);
  if (copy.claim) delete copy.claim.token;
  return copy;
}

