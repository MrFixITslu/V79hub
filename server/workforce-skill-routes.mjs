import express from "express";
import { validateSkillDraft } from "./workforce-skill-registry.mjs";

// A model instruction is never an authorization grant. Owner-only, no external
// tool execution, no model-supplied assignment IDs, no browser-supplied actor.
export function workforceSkillRouter({ registry, enabled, ownerContext, freshOwnerContext, sameOrigin }) {
  const router = express.Router();
  router.use((req, res, next) => {
    res.setHeader("Cache-Control", "no-store");
    if (!enabled() || !registry) return res.status(503).json({ error: "Skill Manager is not configured or enabled" });
    const owner = ownerContext(req);
    if (!owner) return res.status(403).json({ error: "Founder-only access required" });
    if (req.method !== "GET" && !sameOrigin(req))
      return res.status(403).json({ error: "Same-origin request required" });
    req.skillOwner = owner;
    next();
  });
  const wrap = fn => async (req, res) => {
    try { await fn(req, res); }
    catch (e) {
      const status = Number.isInteger(e?.status) && e.status >= 400 && e.status <= 503 ? e.status : 503;
      return res.status(status).json({ error: status === 503 ? "Skill registry unavailable or integrity gate failed" : e.message });
    }
  };
  const body = (input, names) => input && typeof input === "object" && !Array.isArray(input) &&
    Object.keys(input).sort().join("|") === [...names].sort().join("|");
  const mfa = (req, res) => {
    if (freshOwnerContext(req)) return true;
    res.status(403).json({ error: "A fresh founder MFA challenge (within 5 minutes) is required to change active assignments" });
    return false;
  };
  router.get("/", wrap(async (_req, res) => res.json(registry.list())));
  router.get("/:id", wrap(async (req, res) => res.json(registry.get(req.params.id))));
  router.post("/validate", wrap(async (req, res) => {
    if (!body(req.body, ["name", "content"])) return res.status(400).json({ error: "Invalid draft" });
    const checked = validateSkillDraft(req.body);
    res.json({ name: checked.name, bytes: checked.bytes, sha256: checked.sha256, warnings: checked.warnings,
      result: "format-only", note: "Validation is not model-quality testing or a security certification" });
  }));
  router.post("/", wrap(async (req, res) => {
    if (!body(req.body, ["name", "content"])) return res.status(400).json({ error: "Invalid draft" });
    res.status(201).json({ skill: await registry.create(req.body, req.skillOwner.userId) });
  }));
  router.post("/:id/revise", wrap(async (req, res) => {
    if (!body(req.body, ["name", "content", "expectedRevision"])) return res.status(400).json({ error: "Invalid revision" });
    res.json({ skill: await registry.revise(req.params.id, { name: req.body.name, content: req.body.content },
      req.body.expectedRevision, req.skillOwner.userId) });
  }));
  router.post("/:id/activate", wrap(async (req, res) => {
    if (!mfa(req, res)) return;
    if (!body(req.body, ["version", "workers", "expectedRevision"])) return res.status(400).json({ error: "Invalid assignment" });
    res.json({ skill: await registry.activate(req.params.id, req.body.version, req.body.workers,
      req.body.expectedRevision, req.skillOwner.userId) });
  }));
  router.post("/:id/pause", wrap(async (req, res) => {
    if (!mfa(req, res)) return;
    if (!body(req.body, ["expectedRevision"])) return res.status(400).json({ error: "Invalid pause request" });
    res.json({ skill: await registry.pause(req.params.id, req.body.expectedRevision, req.skillOwner.userId) });
  }));
  router.post("/:id/restore", wrap(async (req, res) => {
    if (!body(req.body, ["version", "expectedRevision"])) return res.status(400).json({ error: "Invalid restoration" });
    res.json({ skill: await registry.restore(req.params.id, req.body.version, req.body.expectedRevision,
      req.skillOwner.userId) });
  }));
  return router;
}
