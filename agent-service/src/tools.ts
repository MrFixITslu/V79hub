import { tool, type RunContext } from "@openai/agents";
import { z } from "zod";
import fs from "node:fs";
import { BUSINESS_SYSTEMS, getBusinessSystem } from "./business.js";
import { checkApproval } from "./policy.js";
import { canUseSystem, type AgentContext } from "./context.js";
import { buildEvidenceLedger, compactFromEvidence, verifySignedOwnerSnapshot } from "./evidence.js";
import { getWorkforceSpecialist } from "./workforce.js";

type HealthResult = {
  key: string;
  name: string;
  status: "healthy" | "unhealthy" | "not_configured" | "forbidden";
  httpStatus?: number;
  latencyMs?: number;
  detail?: string;
};

async function checkOne(key: string): Promise<HealthResult> {
  const system = getBusinessSystem(key);
  if (!system) return { key, name: key, status: "unhealthy", detail: "Unknown system." };
  if (!system.healthUrl) {
    return { key: system.key, name: system.name, status: "not_configured", detail: "No health URL is configured yet." };
  }

  const started = Date.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(system.healthUrl, {
      signal: controller.signal,
      headers: { "user-agent": "v79-business-agent/0.2" },
    });
    return {
      key: system.key,
      name: system.name,
      status: response.ok ? "healthy" : "unhealthy",
      httpStatus: response.status,
      latencyMs: Date.now() - started,
      detail: response.ok ? "Health check succeeded." : "Health check returned an error status.",
    };
  } catch (error) {
    return {
      key: system.key,
      name: system.name,
      status: "unhealthy",
      latencyMs: Date.now() - started,
      detail: error instanceof Error ? error.message : "Health check failed.",
    };
  } finally {
    clearTimeout(timeout);
  }
}

function contextFrom(runContext?: RunContext<AgentContext>) {
  if (!runContext?.context) throw new Error("Agent identity context is missing.");
  return runContext.context;
}

export const listBusinessSystemsTool = tool<z.ZodObject<{}>, AgentContext>({
  name: "list_business_systems",
  description: "List only the V79 systems this signed-in Hub account is allowed to use.",
  parameters: z.object({}),
  async execute(_input, runContext) {
    const context = contextFrom(runContext);
    return BUSINESS_SYSTEMS
      .filter((system) => canUseSystem(context, system.key))
      .map(({ key, name, purpose, healthUrl }) => ({
        key,
        name,
        purpose,
        healthConfigured: Boolean(healthUrl),
      }));
  },
});

export const checkAppHealthTool = tool({
  name: "check_app_health",
  description: "Check one permitted V79 system or all permitted systems. This is read-only.",
  parameters: z.object({
    system: z.string().default("all").describe("A system key such as hub, lasertag, marketing, pos, or all."),
  }),
  async execute({ system }, runContext: RunContext<AgentContext> | undefined) {
    const context = contextFrom(runContext);
    if (system.toLowerCase() === "all") {
      const permitted = BUSINESS_SYSTEMS.filter((item) => canUseSystem(context, item.key));
      return Promise.all(permitted.map((item) => checkOne(item.key)));
    }
    if (!canUseSystem(context, system)) {
      return { key: system, name: system, status: "forbidden", detail: "This Hub account does not have access to that system." };
    }
    return checkOne(system);
  },
});

const snapshotUrl = process.env.V79_HUB_AGENT_SNAPSHOT_URL || "http://v79-hub:3040/internal/agent/snapshot";
const tokenFile = process.env.V79_AGENT_TOKEN_FILE || "/run/secrets/v79-agent-token";
function readInternalToken() {
  const direct = String(process.env.V79_AGENT_API_TOKEN || "").trim();
  if (direct) return direct;
  try { return fs.readFileSync(tokenFile, "utf8").trim(); } catch { return ""; }
}

export async function readBusinessSnapshot(context: AgentContext) {
  if (!context.ownerAgent) throw new Error("Business-wide snapshot is restricted to the Vision79 Owner Assistant.");
  const internalToken = readInternalToken();
  if (!internalToken) throw new Error("Owner Assistant internal token is not configured.");

  const response = await fetch(snapshotUrl, {
    headers: {
      "x-v79-agent-token": internalToken,
      "x-v79-owner-email": context.email,
      "x-v79-organization-id": context.organizationId,
      "user-agent": "v79-business-agent/0.2",
    },
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`Hub business snapshot returned HTTP ${response.status}.`);
  const payload: unknown = await response.json();
  verifySignedOwnerSnapshot(payload, context);
  return payload as Record<string, any>;
}

export const getBusinessSnapshotTool = tool({
  name: "get_business_snapshot",
  description:
    "Read the trusted live Vision79 business snapshot from Hub Admin and connected apps. Use this before answering questions about current business performance.",
  parameters: z.object({
    section: z.enum([
      "all",
      "platform",
      "finance",
      "sales_inventory",
      "customers_support",
      "growth",
      "learning",
      "combat_zone",
    ]).default("all"),
  }),
  async execute({ section }, runContext: RunContext<AgentContext> | undefined) {
    const context = contextFrom(runContext);
    const snapshot = await readBusinessSnapshot(context);
    const evidence = buildEvidenceLedger(snapshot, getWorkforceSpecialist("owner"));
    const domainSystems: Record<string, string[]> = {
      finance: ["ffpro", "pos"],
      sales_inventory: ["pos"],
      customers_support: ["tiquet"],
      growth: ["marketing", "website"],
      learning: ["academy", "games"],
      combat_zone: ["lasertag"],
    };
    const systems = domainSystems[section];
    const records = !systems ? evidence.records : evidence.records.filter(
      record => systems.includes(record.system),
    );
    return {
      mode: "read-only",
      collectedAt: evidence.collectedAt,
      records,
      prioritySignals: compactFromEvidence(evidence).prioritySignals.filter(signal =>
        !systems || systems.some(system =>
          signal.code.startsWith(system + "_") ||
          (system === "ffpro" && signal.code.startsWith("finance_")) ||
          (system === "website" && signal.code.startsWith("website_"))
        )
      ),
      note: evidence.note,
    };
  },
});

export const approvalPolicyTool = tool({
  name: "check_action_approval",
  description: "Check whether a proposed business action requires owner approval before it can happen.",
  parameters: z.object({
    risk: z.enum(["read", "draft", "external_communication", "booking_change", "financial", "deployment", "security"]),
  }),
  async execute({ risk }) {
    return checkApproval(risk);
  },
});
