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
import { routeWorkforceRequest, scopeSnapshotForSpecialist, specialistInstructions, workforceRoster } from "./workforce.js";

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
    const grounding = localFastPath
      ? scopeSnapshotForSpecialist(compactOwnerSnapshot(snapshot), chosenSpecialist)
      : snapshot;
    const snapshotText = JSON.stringify(grounding);
    const maxSnapshotChars = localFastPath ? 6000 : 50000;
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
        specialist: chosenSpecialist.name,
        mode: "read-only",
        modelProvider: result.provider,
        model: result.model,
        responseMode: "ollama",
      });
    }

    const result = await run(managerAgent, groundedMessage, { context });
    return res.json({
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