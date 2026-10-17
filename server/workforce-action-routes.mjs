import express from "express";
import { timingSafeEqual } from "node:crypto";
import { WORK_OPERATIONS, WORK_SYSTEMS, proposeWork, decideWork, cancelWork, claimWork,
  finishWork, createApprovedWorkItem, pauseWork, publicWorkJob } from "./workforce-actions.mjs";

const exact = (body, fields) => body && typeof body === "object" && !Array.isArray(body) &&
  Object.keys(body).sort().join(",") === fields.slice().sort().join(",");
export function workforceActionRouters({ ledger, enabled, ownerContext, sameOrigin, workerToken,
  ownerOrganizationId, ownerReady, now = Date.now }) {
  const owner = express.Router(), worker = express.Router();
  const wrap = fn => async (req, res) => {
    res.setHeader("Cache-Control", "no-store");
    try { return await fn(req, res); }
    catch { return res.status(409).json({ error: "Action rejected or storage unavailable. Refresh and verify the current state before retrying." }); }
  };
  owner.use((req, res, next) => {
    const context = ownerContext(req);
    if (!context) return res.status(403).json({ error: "MFA-verified founder required" });
    req.workOwner = context;
    if (req.method !== "GET") {
      if (!enabled()) return res.status(503).json({ error: "Approved actions are disabled" });
      if (!sameOrigin(req)) return res.status(403).json({ error: "Same-origin request required" });
      const at = req.user?.mfaVerifiedAt;
      if (!Number.isFinite(at) || now() - at < 0 || now() - at > 300000) return res.status(403).json({ error: "Confirm MFA again before approving or changing actions" });
    }
    if (!ledger) return res.status(503).json({ error: "Workforce ledger key is not configured" });
    next();
  });
  owner.get("/", wrap(async (req, res) => {
    const state = await ledger.read(), org = req.workOwner.organizationId;
    return res.json({ mode: "owner-approved-actions", enabled: enabled(), paused: state.paused,
      operations: WORK_OPERATIONS, systems: WORK_SYSTEMS,
      jobs: state.jobs.filter(j => j.organizationId === org).slice(-200).reverse().map(publicWorkJob),
      tasks: state.tasks.filter(j => j.organizationId === org).slice(-200).reverse() });
  }));
  owner.post("/", wrap(async (req, res) => {
    const job = await ledger.transact(s => proposeWork(s, req.body, {
      organizationId: req.workOwner.organizationId, actor: req.workOwner.userId, now: now() }));
    return res.status(201).json({ job: publicWorkJob(job) });
  }));
  owner.post("/pause", wrap(async (req, res) => {
    if (!exact(req.body, ["paused"])) return res.status(400).json({ error: "Invalid pause request" });
    await ledger.transact(s => pauseWork(s, req.body.paused, { actor: req.workOwner.userId, now: now() }));
    return res.json({ paused: req.body.paused });
  }));
  owner.post("/:id/decision", wrap(async (req, res) => {
    if (!exact(req.body, ["decision", "expectedRevision", "digest"])) return res.status(400).json({ error: "Invalid action decision" });
    const job = await ledger.transact(s => decideWork(s, req.params.id, req.body.decision, {
      organizationId: req.workOwner.organizationId, actor: req.workOwner.userId,
      expectedRevision: req.body.expectedRevision, digest: req.body.digest, now: now() }));
    return res.json({ job: publicWorkJob(job) });
  }));
  owner.post("/:id/cancel", wrap(async (req, res) => {
    if (!exact(req.body, ["expectedRevision"])) return res.status(400).json({ error: "Invalid cancellation" });
    const job = await ledger.transact(s => cancelWork(s, req.params.id, {
      organizationId: req.workOwner.organizationId, actor: req.workOwner.userId,
      expectedRevision: req.body.expectedRevision, now: now() }));
    return res.json({ job: publicWorkJob(job) });
  }));
  owner.post("/:id/execute", wrap(async (req, res) => {
    if (!exact(req.body, ["expectedRevision"])) return res.status(400).json({ error: "Invalid execution request" });
    const job = await ledger.transact(s => createApprovedWorkItem(s, req.params.id, {
      organizationId: req.workOwner.organizationId, actor: req.workOwner.userId,
      expectedRevision: req.body.expectedRevision, now: now() }));
    return res.json({ job: publicWorkJob(job) });
  }));
  worker.use((req, res, next) => {
    res.setHeader("Cache-Control", "no-store");
    if (!enabled() || !ledger || !ownerReady()) return res.status(503).json({ error: "Worker execution unavailable" });
    // Separate credential: the existing read-only agent token cannot claim jobs.
    const expected = String(workerToken() || ""), supplied = String(req.get("x-v79-workforce-token") || "");
    if (req.get("origin") || req.get("cookie") || expected.length < 32 ||
        Buffer.byteLength(expected) !== Buffer.byteLength(supplied) ||
        !timingSafeEqual(Buffer.from(expected), Buffer.from(supplied))) return res.status(403).json({ error: "Trusted worker required" });
    next();
  });
  worker.post("/propose", wrap(async (req, res) => {
    const job = await ledger.transact(s => proposeWork(s, req.body, {
      organizationId: ownerOrganizationId(), actor: "coo-worker", now: now() }));
    return res.status(201).json({ job: publicWorkJob(job) });
  }));
  worker.get("/work-items", wrap(async (_req, res) => {
    const state = await ledger.read();
    return res.json({ tasks: state.tasks.filter(t => t.organizationId === ownerOrganizationId()).slice(-200) });
  }));
  worker.post("/execute-work-item", wrap(async (req, res) => {
    if (!exact(req.body, [])) return res.status(400).json({ error: "No worker-supplied task payload accepted" });
    const job = await ledger.transact(s => {
      if (s.paused) return null;
      const j = s.jobs.find(j => j.organizationId === ownerOrganizationId() && j.operation === "create_work_item" &&
        j.status === "approved" && Date.parse(j.approval?.expiresAt) > now());
      if (!j) return null;
      return createApprovedWorkItem(s, j.id, { organizationId: ownerOrganizationId(), actor: "coo-worker",
        expectedRevision: j.revision, now: now() });
    });
    return res.json({ job: job ? publicWorkJob(job) : null });
  }));
  worker.post("/claim", wrap(async (req, res) => {
    if (!exact(req.body, ["worker", "operations", "systems"]) ||
        req.body.worker !== "v79-release-worker" ||
        !Array.isArray(req.body.operations) || !req.body.operations.every(x => ["validate_release", "deploy_release", "rollback_release"].includes(x)) ||
        !Array.isArray(req.body.systems) || !req.body.systems.every(x => WORK_SYSTEMS.includes(x))) return res.status(400).json({ error: "Invalid worker scope" });
    const job = await ledger.transact(s => claimWork(s, { ...req.body, organizationId: ownerOrganizationId(), now: now() }));
    return res.json({ job });
  }));
  worker.get("/:id/authorization", wrap(async (req, res) => {
    const state = await ledger.read();
    const job = state.jobs.find(j => j.id === req.params.id && j.organizationId === ownerOrganizationId());
    const authorized = !state.paused && job?.status === "running" && job.claim?.worker === "v79-release-worker" &&
      job.claim.token === req.get("x-v79-workforce-claim") && Date.parse(job.approval?.expiresAt) > now();
    return res.status(authorized ? 200 : 403).json({ authorized });
  }));
  worker.post("/:id/receipt", wrap(async (req, res) => {
    const job = await ledger.transact(s => finishWork(s, req.params.id, req.body, {
      organizationId: ownerOrganizationId(), worker: "v79-release-worker", now: now() }));
    return res.json({ job: publicWorkJob(job) });
  }));
  return { owner, worker };
}
