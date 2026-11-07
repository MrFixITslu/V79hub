import express from "express";
import { timingSafeEqual } from "node:crypto";
import { GOOGLE_OPERATIONS } from './workforce-google.mjs';
import { WORK_OPERATIONS, WORK_SYSTEMS, proposeWork, decideWork, cancelWork, claimWork,
  finishWork, createApprovedWorkItem, pauseWork, publicWorkJob } from "./workforce-actions.mjs";

const exact = (body, fields) => body && typeof body === "object" && !Array.isArray(body) &&
  Object.keys(body).sort().join(",") === fields.slice().sort().join(",");
export function workforceActionRouters({ ledger, enabled, ownerContext, sameOrigin, workerToken,
  ownerOrganizationId, ownerReady, googleEnabled = () => false, now = Date.now }) {
  const owner = express.Router(), worker = express.Router();
  const wrap = fn => async (req, res) => {
    res.setHeader("Cache-Control", "no-store");
    try { return await fn(req, res); }
    catch (e) {
      if (e?.code === "REVIEW_MFA_REQUIRED") {
        return res.status(403).json({ code: "RECENT_MFA_REQUIRED",
          error: "Recent owner MFA verification is required for this specialist review." });
      }
      // Return only explicit, non-sensitive state errors. Never expose storage,
      // secret, identity or database details to the browser.
      const conflicts = {
        "Action revision conflict": ["ACTION_CHANGED", "This action changed. Refresh and review its current details."],
        "Work item requires current approval": ["APPROVAL_REQUIRED", "This work item cannot run: the queue is paused or its approval expired. Refresh status."],
        "Queue paused": ["QUEUE_PAUSED", "The workforce queue is paused. Resume it only when ready to execute."],
        "Approval expired": ["APPROVAL_EXPIRED", "This approval has expired. Review and approve a fresh action."],
        "Action not found": ["ACTION_CHANGED", "This action is no longer available. Refresh status."],
        "Action cannot be approved": ["APPROVAL_REQUIRED", "This approval is no longer valid. Refresh and review the action again."],
        "Invalid worker receipt": ["RECEIPT_REPLAY_DENIED", "The worker receipt is invalid or already recorded. Do not retry the effect; reconcile the recorded result."],
      };
      const known = conflicts[e?.message];
      if (known) return res.status(409).json({ code: known[0], error: known[1] });
      // Log error type only; request payloads, credentials and ledger content stay private.
      console.error("workforce-action-store-failure", { kind: String(e?.name || "Error").slice(0, 50) });
      return res.status(503).json({ code: "ACTION_STORE_UNAVAILABLE",
        error: "The action could not be confirmed. Refresh status before retrying; do not create a duplicate." });
    }
  };
  owner.use((req, res, next) => {
    const context = ownerContext(req);
    if (!context) return res.status(403).json({ code: "MFA_SESSION_REQUIRED", error: "Sign in with your owner account and complete MFA." });
    req.workOwner = context;
    if (req.method !== "GET") {
      if (!enabled()) return res.status(503).json({ error: "Approved actions are disabled" });
      if (!sameOrigin(req)) return res.status(403).json({ error: "Same-origin request required" });
      const at = req.user?.mfaVerifiedAt;
      if (!Number.isFinite(at) || now() - at < 0) return res.status(403).json({ code: "MFA_SESSION_REQUIRED", error: "Your owner session requires MFA sign-in." });
    }
    if (!ledger) return res.status(503).json({ error: "Workforce ledger key is not configured" });
    next();
  });
  owner.get("/", wrap(async (req, res) => {
    const state = await ledger.read(), org = req.workOwner.organizationId;
    return res.json({ mode: "owner-approved-actions", enabled: enabled(), paused: state.paused,
      operations: WORK_OPERATIONS.filter(op=>googleEnabled() || !GOOGLE_OPERATIONS.includes(op)),
      systems: WORK_SYSTEMS.filter(system=>googleEnabled() || !['gmail','calendar'].includes(system)),
      jobs: state.jobs.filter(j => j.organizationId === org).slice(-200).reverse().map(publicWorkJob),
      tasks: state.tasks.filter(j => j.organizationId === org).slice(-200).reverse() });
  }));
  owner.post("/", wrap(async (req, res) => {
    if (GOOGLE_OPERATIONS.includes(req.body?.operation) && !googleEnabled()) return res.status(503).json({ error: "Google workforce integration is disabled" });
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
    const job = await ledger.transact(s => {
      const existing = s.jobs.find(j=>j.id===req.params.id && j.organizationId===req.workOwner.organizationId);
      if (req.body.decision === 'approve' && GOOGLE_OPERATIONS.includes(existing?.operation) && !googleEnabled()) throw new Error('Google integration disabled');
      return decideWork(s, req.params.id, req.body.decision, {
      organizationId: req.workOwner.organizationId, actor: req.workOwner.userId,
      expectedRevision: req.body.expectedRevision, digest: req.body.digest, now: now() });
    });
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
    const job = await ledger.transact(s => {
      if (s.paused) throw new Error("Queue paused");
      const candidate = s.jobs.find(j => j.id === req.params.id && j.organizationId === req.workOwner.organizationId);
      if (!candidate) throw new Error("Action not found");
      if (!candidate.approval || !(Date.parse(candidate.approval.expiresAt) > now())) throw new Error("Approval expired");
      return createApprovedWorkItem(s, req.params.id, {
      organizationId: req.workOwner.organizationId, actor: req.workOwner.userId,
      expectedRevision: req.body.expectedRevision, now: now() });
    });
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
    if (GOOGLE_OPERATIONS.includes(req.body?.operation)) return res.status(403).json({ error: "Google proposals require the owner session" });
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

