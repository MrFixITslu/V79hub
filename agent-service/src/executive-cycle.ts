import type { EvidenceLedger } from "./evidence.js";
import { prepareExecutiveHandoff } from "./executive-handoff.js";

/**
 * G1.1: narrow, read-only, two-role reasoning preview.
 * Both roles may REORDER a fixed set of trusted, evidence-backed findings.
 * They cannot create tasks, add facts, authorize actions or execute tools.
 */
export type ExecutiveStage = "coo" | "ceo";
export type ExecutiveCandidate = Readonly<{
  id: string;
  system: string;
  severity: "attention" | "watch" | "information";
  metric: string;
  value: number;
  reportedAt: string;
}>;
export type ExecutiveRankingRequest = Readonly<{
  stage: ExecutiveStage;
  candidates: readonly ExecutiveCandidate[];
  cooOrder?: readonly string[];
}>;

export type ExecutiveSelector =
  (request: ExecutiveRankingRequest) => Promise<unknown>;

const severityRank: Record<ExecutiveCandidate["severity"], number> = {
  attention: 0, watch: 1, information: 2,
};

function safeRanking(response: unknown, permitted: readonly string[]): string[] | null {
  let object: unknown = response;
  if (typeof response === "string") {
    if (response.length > 4096) return null;
    try { object = JSON.parse(response); } catch { return null; }
  }
  if (typeof object !== "object" || object === null || Array.isArray(object)) return null;
  const raw = object as Record<string, unknown>;
  if (Object.keys(raw).length !== 1 || !Object.hasOwn(raw, "findingIds") ||
      !Array.isArray(raw.findingIds) || raw.findingIds.length > 10) return null;
  const allowed = new Set(permitted);
  const seen = new Set<string>();
  for (const id of raw.findingIds) {
    if (typeof id !== "string" || !allowed.has(id) || seen.has(id)) return null;
    seen.add(id);
  }
  // Omitted verified findings can never disappear due to a model response.
  return [...seen, ...permitted.filter(id => !seen.has(id))];
}

function enforceSeverity(candidates: readonly ExecutiveCandidate[], requested: readonly string[]) {
  const indexed = new Map(requested.map((id, index) => [id, index]));
  return [...candidates].sort((a, b) =>
    severityRank[a.severity] - severityRank[b.severity] ||
    (indexed.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (indexed.get(b.id) ?? Number.MAX_SAFE_INTEGER) ||
    a.id.localeCompare(b.id)).map(finding => finding.id);
}

/** A disabled or failed model is harmless; known facts still yield a deterministic briefing. */
export async function runReadOnlyExecutiveCycle(
  ledger: EvidenceLedger,
  selector: ExecutiveSelector | null,
) {
  const handoff = prepareExecutiveHandoff(ledger);
  const candidates: ExecutiveCandidate[] = handoff.cooReport.findings.map(finding => ({
    id: finding.id, system: finding.system,
    severity: finding.severity, metric: finding.metric, value: finding.value,
    reportedAt: finding.reportedAt,
  }));
  const permitted = candidates.map(candidate => candidate.id);
  const fallback = enforceSeverity(candidates, permitted);
  const outcomes: Array<{ role: ExecutiveStage; result: "accepted" | "fallback" | "skipped" }> = [];
  let cooOrder = fallback;
  let ceoOrder = fallback;

  if (selector !== null && candidates.length > 0) {
    try {
      const raw = await selector({ stage: "coo", candidates });
      const ranking = safeRanking(raw, permitted);
      cooOrder = ranking ? enforceSeverity(candidates, ranking) : fallback;
      outcomes.push({ role: "coo", result: ranking ? "accepted" : "fallback" });
    } catch {
      outcomes.push({ role: "coo", result: "fallback" });
    }
    try {
      // COO free text must never be forwarded as trusted CEO instructions.
      const raw = await selector({ stage: "ceo", candidates, cooOrder });
      const ranking = safeRanking(raw, permitted);
      ceoOrder = ranking ? enforceSeverity(candidates, ranking) : cooOrder;
      outcomes.push({ role: "ceo", result: ranking ? "accepted" : "fallback" });
    } catch {
      ceoOrder = cooOrder;
      outcomes.push({ role: "ceo", result: "fallback" });
    }
  } else {
    outcomes.push({ role: "coo", result: "skipped" }, { role: "ceo", result: "skipped" });
  }

  const evidenceById = new Map(handoff.cooReport.findings.map(finding => [finding.id, finding]));
  // Return only existing fixed suggested next steps and verified evidence.
  const reviewItems = ceoOrder.map(id => {
    const evidence = evidenceById.get(id);
    if (!evidence) throw new Error("Executive preview lost verified source evidence");
    return { ...evidence, decision: "review" as const };
  });
  return {
    version: "1.0" as const,
    mode: "read-only" as const,
    state: "preview-only" as const,
    ownerScope: "v79-digital-only" as const,
    modelAssistance: outcomes.every(o => o.result === "accepted") ? "both-roles" as const :
      outcomes.some(o => o.result === "accepted") ? "partial" as const : "none" as const,
    stages: outcomes,
    source: handoff.source,
    reviewItems,
    missingSources: handoff.cooReport.unavailableSources,
    ownerApprovalGranted: false as const,
    approvalRequestCreated: false as const,
    executionEnabled: false as const,
    actionsExecuted: 0 as const,
    externalMessagesSent: 0 as const,
    note: "CEO/COO re-ordered existing verified findings for a read-only review. No task execution, approval, user contact or self-modification occurred.",
  };
}
