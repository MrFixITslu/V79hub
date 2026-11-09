import express from "express";
import {builtinSkillCatalog,builtinSkillDetail} from "./workforce-builtins.mjs";
import { validateSkillDraft } from "./workforce-skill-registry.mjs";

// A model instruction is never an authorization grant. Owner-only, no external
// tool execution, no model-supplied assignment IDs, no browser-supplied actor.
export function workforceSkillRouter({ registry, packages, enabled, ownerContext, freshOwnerContext, sameOrigin }) {
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
  // Founder-only read endpoints; built-in files are verified against the exact
  // pinned Git blob IDs before disclosure. No route may modify a built-in skill.
  router.get("/builtins", wrap(async (_req,res) => res.json({skills:builtinSkillCatalog()})));
  router.get("/builtins/:role", wrap(async (req,res) => res.json({skill:builtinSkillDetail(req.params.role)})));
  // Executable assets are never evaluated inside Hub. Import quarantines a
  // content-addressed ZIP; approval and assignments demand fresh founder MFA.
  router.get("/packages", wrap(async (_req,res) => {
    if(!packages) return res.status(503).json({error:"Package quarantine unavailable"});
    return res.json(packages.list());
  }));
  router.get("/packages/scheduled/:job", wrap(async (req,res) => {
    if(!packages) return res.status(503).json({error:"Package quarantine unavailable"});
    return res.json(packages.scheduledSnapshot(req.params.job));
  }));
  router.get("/packages/:id", wrap(async (req,res) => {
    if(!packages) return res.status(503).json({error:"Package quarantine unavailable"});
    return res.json({package:packages.read(req.params.id)});
  }));
  router.post("/packages/import", wrap(async (req,res) => {
    if(!packages) return res.status(503).json({error:"Package quarantine unavailable"});
    if(!body(req.body,["name","archive"]))return res.status(400).json({error:"Invalid ZIP upload"});
    return res.status(201).json({package:await packages.import(req.body,req.skillOwner.userId)});
  }));
  router.get("/packages/:id/download", wrap(async (req,res) => {
    if(!packages)return res.status(503).json({error:"Package quarantine unavailable"});
    const detail=packages.read(req.params.id);
    const bytes=packages.download(req.params.id);
    res.setHeader("Content-Type","application/zip");
    res.setHeader("Content-Length",String(bytes.length));
    res.setHeader("Content-Disposition",`attachment; filename="${detail.name}-v${detail.version||1}.zip"`);
    res.setHeader("X-Content-Type-Options","nosniff");
    return res.end(bytes);
  }));
  router.post("/packages/:id/stage-revision",wrap(async(req,res)=>{
    if(!packages)return res.status(503).json({error:"Package quarantine unavailable"});
    if(!body(req.body,["archive","expectedRevision"]))return res.status(400).json({error:"Invalid revision upload"});
    return res.status(201).json({package:await packages.stageRevision(req.params.id,req.body,req.skillOwner.userId)});
  }));
  for(const [action,method,fields] of [
    ["promote","promote",["expectedRevision","expectedParentRevision"]],
    ["archive","archive",["expectedRevision"]],
    ["unarchive","unarchive",["expectedRevision"]],
  ]){
    router.post(`/packages/:id/${action}`,wrap(async(req,res)=>{
      if(!mfa(req,res))return;
      if(!packages)return res.status(503).json({error:"Package quarantine unavailable"});
      if(!body(req.body,fields))return res.status(400).json({error:"Invalid package management request"});
      return res.json({package:await packages[method](req.params.id,req.body,req.skillOwner.userId)});
    }));
  }
  router.post("/packages/:id/approve", wrap(async (req,res) => {
    if(!mfa(req,res))return;
    if(!packages)return res.status(503).json({error:"Package quarantine unavailable"});
    if(!body(req.body,["sha256","expectedRevision"]))return res.status(400).json({error:"Invalid package approval"});
    return res.json({package:await packages.approve(req.params.id,req.body,req.skillOwner.userId)});
  }));
  router.post("/packages/:id/revoke", wrap(async (req,res) => {
    if(!mfa(req,res))return;
    if(!packages)return res.status(503).json({error:"Package quarantine unavailable"});
    if(!body(req.body,["expectedRevision"]))return res.status(400).json({error:"Invalid revocation"});
    return res.json({package:await packages.revoke(req.params.id,req.body,req.skillOwner.userId)});
  }));
  router.post("/packages/:id/configure", wrap(async (req,res) => {
    if(!mfa(req,res))return;
    if(!packages)return res.status(503).json({error:"Package quarantine unavailable"});
    if(!body(req.body,["hooks","schedules","expectedRevision"]))return res.status(400).json({error:"Invalid package policy"});
    return res.json({package:await packages.configure(req.params.id,req.body,req.skillOwner.userId)});
  }));
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
  for(const action of ["archive","unarchive"]){
    router.post(`/:id/${action}`,wrap(async(req,res)=>{
      if(!mfa(req,res))return;
      if(!body(req.body,["expectedRevision"]))return res.status(400).json({error:"Invalid skill management request"});
      return res.json({skill:await registry[action](req.params.id,req.body.expectedRevision,req.skillOwner.userId)});
    }));
  }
  router.post("/:id/restore", wrap(async (req, res) => {
    if (!body(req.body, ["version", "expectedRevision"])) return res.status(400).json({ error: "Invalid restoration" });
    res.json({ skill: await registry.restore(req.params.id, req.body.version, req.body.expectedRevision,
      req.skillOwner.userId) });
  }));
  return router;
}
