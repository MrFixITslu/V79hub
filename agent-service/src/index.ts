import "dotenv/config";
import express from "express";
import fs from "node:fs";
import { run } from "@openai/agents";
import { managerAgent } from "./agents.js";
import { BUSINESS_SYSTEMS } from "./business.js";
import { checkApproval, type ActionRisk } from "./policy.js";
import { isValidOwnerContext, type AgentContext } from "./context.js";
import { agentModelRuntime } from "./model-runtime.js";
import { readBusinessSnapshot } from "./tools.js";
import { compactOwnerSnapshot, deterministicFactAnswer, formatPriorityBrief, isPriorityBriefRequest } from "./grounding.js";
import { prewarmOllamaOwnerAssistant, runOllamaOwnerAssistant } from "./ollama-native.js";
import { buildEvidenceLedger, compactFromEvidence } from "./evidence.js";
import { buildInvestigationBrief } from "./investigations.js";
import { getWorkforceSpecialist } from "./workforce.js";
import { routeWorkforceRequest, specialistInstructions, workforceRoster } from "./workforce.js";
import { executiveWorkforceStructure } from "./executive-workforce.js";
import { prepareExecutiveHandoff } from "./executive-handoff.js";
import { runReadOnlyExecutiveCycle } from "./executive-cycle.js";
import { createLocalExecutiveSelector } from "./ollama-executive.js";

const app = express();
const port = Number(process.env.PORT || 3055);
const tokenFile = process.env.V79_AGENT_TOKEN_FILE || "/run/secrets/v79-agent-token";
let modelWarmState: "pending" | "ready" | "failed" | "not_applicable" = agentModelRuntime.provider === "ollama" ? "pending" : "not_applicable";
function readApiToken() {
  const direct = String(process.env.V79_AGENT_API_TOKEN || "").trim();
  if (direct) return direct;
  try { return fs.readFileSync(tokenFile, "utf8").trim(); } catch { return ""; }
}

app.disable("x-powered-by");
app.use(express.json({ limit: "128kb" }));

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "v79-business-agent",
    mode: "read-only",
    systemsKnown: BUSINESS_SYSTEMS.length,
    modelProvider: agentModelRuntime.provider,
    model: agentModelRuntime.model,
    modelWarmState,
  });
});
app.use("/api", (req, res, next) => {
  const apiToken = readApiToken();
  if (!apiToken) {
    if (process.env.NODE_ENV === "production") {
      return res.status(503).json({ error: "Owner Assistant internal token is not configured." });
    }
    return next();
  }
  if (req.header("x-v79-agent-token") !== apiToken) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
});

app.get("/api/agent/specialists", (_req, res) => {
  res.setHeader("Cache-Control", "no-store");
  res.json({ mode: "read-only", specialists: workforceRoster() });
});

// G1 only: role mapping metadata. No write tools or policy bypass.
app.get("/api/agent/executive-structure", (_req, res) => {
  res.setHeader("Cache-Control", "no-store");
  res.json(executiveWorkforceStructure());
});

app.get("/api/agent/capabilities", (_req, res) => {
  res.json({
    mode: "read-only",
    ownerOnly: true,
    modelProvider: agentModelRuntime.provider,
    model: agentModelRuntime.model,
    routing: "deterministic-specialist",
    specialists: workforceRoster(),
    can: [
      "answer business questions",
      "route work to specialist agents",
      "check permitted application health",
      "prepare drafts and recommendations",
      "explain whether an action needs owner approval",
    ],
    cannotYet: [
      "send email",
      "change bookings",
      "charge or refund customers",
      "change production data",
      "deploy code",
      "change security settings",
    ],
  });
});
app.post("/api/policy/check", (req, res) => {
  const risk = String(req.body?.risk || "") as ActionRisk;
  const valid: ActionRisk[] = [
    "read",
    "draft",
    "external_communication",
    "booking_change",
    "financial",
    "deployment",
    "security",
  ];
  if (!valid.includes(risk)) {
    return res.status(400).json({ error: "Unknown risk category." });
  }
  return res.json(checkApproval(risk));
});

app.post("/api/agent/evidence", async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const context = req.body?.context as AgentContext | undefined;
  if (!context || !isValidOwnerContext(context)) {
    return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  }
  const id = String(req.body?.specialistId || "").trim();
  if (!workforceRoster().some(person => person.id === id)) {
    return res.status(400).json({ error: "Unknown specialist." });
  }
  try {
    const snapshot = await readBusinessSnapshot(context);
    const ledger = buildEvidenceLedger(snapshot, getWorkforceSpecialist(id as ReturnType<typeof workforceRoster>[number]["id"]));
    return res.json(ledger);
  } catch (error) {
    console.error("agent evidence read failed", error instanceof Error ? error.name : "error");
    return res.status(502).json({ error: "Evidence from V79 Hub is unavailable." });
  }
});

app.post("/api/agent/investigate", async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const context = req.body?.context as AgentContext | undefined;
  if (!context || !isValidOwnerContext(context)) {
    return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  }
  const id = String(req.body?.specialistId || "").trim();
  if (!workforceRoster().some(person => person.id === id)) {
    return res.status(400).json({ error: "Unknown specialist." });
  }
  try {
    const snapshot = await readBusinessSnapshot(context);
    const ledger = buildEvidenceLedger(snapshot, getWorkforceSpecialist(id as ReturnType<typeof workforceRoster>[number]["id"]));
    return res.json(buildInvestigationBrief(ledger));
  } catch (error) {
    console.error("agent investigation read failed", error instanceof Error ? error.name : "error");
    return res.status(502).json({ error: "Investigation data is unavailable." });
  }
});

// G1 COO -> CEO briefing. Uses the SAME token guard and verified owner snapshot
// as the existing read-only evidence APIs. Never dispatches an action.
app.post("/api/agent/executive-handoff", async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const context = req.body?.context as AgentContext | undefined;
  if (!context || !isValidOwnerContext(context)) {
    return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  }
  try {
    const snapshot = await readBusinessSnapshot(context);
    const evidence = buildEvidenceLedger(snapshot, getWorkforceSpecialist("owner"));
    return res.json(prepareExecutiveHandoff(evidence));
  } catch (error) {
    console.error("executive handoff read failed", error instanceof Error ? error.name : "error");
    return res.status(502).json({ error: "Verified V79 executive evidence is unavailable." });
  }
});

// Opt-in G1.1 model-assisted preview. OFF by default. No scheduler or writes.
// Two constrained local Ollama calls re-order existing signed evidence only.
app.post("/api/agent/executive-preview", async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (process.env.V79_EXECUTIVE_MODEL_CYCLE_ENABLED !== "1" ||
      agentModelRuntime.provider !== "ollama") {
    return res.status(404).json({ error: "Executive model preview is disabled." });
  }
  const context = req.body?.context as AgentContext | undefined;
  if (!context || !isValidOwnerContext(context)) {
    return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  }
  try {
    const snapshot = await readBusinessSnapshot(context);
    const evidence = buildEvidenceLedger(snapshot, getWorkforceSpecialist("owner"));
    const preview = await runReadOnlyExecutiveCycle(evidence, createLocalExecutiveSelector());
    return res.json(preview);
  } catch (error) {
    console.error("executive preview read failed", error instanceof Error ? error.name : "error");
    return res.status(502).json({ error: "Verified V79 executive preview is unavailable." });
  }
});

app.post("/api/agent/chat", async (req, res) => {
  const message = String(req.body?.message || "").trim();
  const context = req.body?.context as AgentContext | undefined;

  if (!message) return res.status(400).json({ error: "message is required" });
  if (message.length > 12000) return res.status(413).json({ error: "message is too long" });
  if (!context || !isValidOwnerContext(context)) {
    return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  }
  try {
    const snapshot = await readBusinessSnapshot(context);
    const localFastPath = agentModelRuntime.provider === "ollama";
    const chosenSpecialist = routeWorkforceRequest(message);
    const evidence = buildEvidenceLedger(snapshot, chosenSpecialist);
    const investigation = buildInvestigationBrief(evidence);
    const grounding = compactFromEvidence(evidence);
    // Both local and cloud model providers must receive only the same reviewed
    // aggregate evidence, never the raw Hub/product payload. Keep the local
    // model context short while preserving all provenance in the API response.
    const modelEvidence = evidence.records.map(record => ({
      system: record.system, source: record.source, state: record.state,
      reportedAt: record.reportedAt,
      metrics: record.state === "available" ? record.metrics : [],
    }));
    const snapshotText = JSON.stringify({
      collectedAt: evidence.collectedAt,
      evidence: modelEvidence,
      prioritySignals: grounding.prioritySignals,
    });
    const maxSnapshotChars = localFastPath ? 6000 : 12000;
    const trustedSnapshot = snapshotText.length > maxSnapshotChars
      ? snapshotText.slice(0, maxSnapshotChars) + "...[truncated]"
      : snapshotText;
    const groundedMessage = [
      "TRUSTED CURRENT V79 BUSINESS SNAPSHOT:",
      trustedSnapshot,
      "",
      "OWNER REQUEST:",
      message,
      "",
      "Use the trusted snapshot for current business facts. Do not invent missing values.",
      "If a requested fact is not present, say it is not available in the current snapshot.",
    ].join("\n");
    if (localFastPath) {
      if (isPriorityBriefRequest(message) && grounding.prioritySignals.length) {
        return res.json({
          output: formatPriorityBrief(grounding.prioritySignals, 5),
          evidence,
          investigation,
          specialist: chosenSpecialist.name,
          mode: "read-only",
          modelProvider: "ollama",
          model: agentModelRuntime.model,
          responseMode: "deterministic-priority",
        });
      }
      const factual = deterministicFactAnswer(message, grounding as ReturnType<typeof compactOwnerSnapshot>);
      if (factual) {
        return res.json({
          output: factual.output,
          evidence,
          investigation,
          specialist: chosenSpecialist.name,
          mode: "read-only",
          modelProvider: "ollama",
          model: agentModelRuntime.model,
          responseMode: "deterministic-facts",
          domain: factual.domain,
        });
      }
      const result = await runOllamaOwnerAssistant(groundedMessage, {
        specialistInstructions: specialistInstructions(chosenSpecialist),
      });
      return res.json({
        output: result.output,
        evidence,
        investigation,
        specialist: chosenSpecialist.name,
        mode: "read-only",
        modelProvider: result.provider,
        model: result.model,
        responseMode: "ollama",
      });
    }

    const result = await run(managerAgent, groundedMessage, { context });
    return res.json({
      evidence,
      investigation,
      output:
        typeof result.finalOutput === "string"
          ? result.finalOutput
          : JSON.stringify(result.finalOutput),
      specialist: result.lastAgent?.name || managerAgent.name,
      mode: "read-only",
      modelProvider: "openai",
      model: agentModelRuntime.model,
    });
  } catch (error) {
    console.error("agent run failed", error);
    return res.status(500).json({ error: "The agent could not complete this request." });
  }
});

app.listen(port, "0.0.0.0", () => {
  console.log(`Vision79 Owner Assistant listening on :${port} in read-only mode`);
  if (agentModelRuntime.provider === "ollama") {
    prewarmOllamaOwnerAssistant()
      .then(({ model, keepAlive }) => {
        modelWarmState = "ready";
        console.log(`Ollama model prewarmed: ${model} (keep_alive=${keepAlive})`);
      })
      .catch((error) => {
        modelWarmState = "failed";
        console.error("Ollama model prewarm failed", error);
      });
  }
});
