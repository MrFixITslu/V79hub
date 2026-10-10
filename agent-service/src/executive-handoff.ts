import type { EvidenceLedger } from "./evidence.js";
import { buildInvestigationBrief, type InvestigationFinding } from "./investigations.js";
import { executiveWorkforceStructure } from "./executive-workforce.js";
import { getWorkforceSpecialist } from "./workforce.js";

/**
 * G1 read-only COO -> CEO handoff.
 *
 * The source ledger must come from the existing owner-verified Hub snapshot
 * and narrow signed-product metrics pipeline, never from a model-generated
 * request body. This builds a deterministic *review brief*, not a task,
 * approval, model-to-model instruction, or application write.
 */
export function prepareExecutiveHandoff(ledger: EvidenceLedger) {
  if (ledger.mode !== "read-only" || ledger.specialist !== getWorkforceSpecialist("owner").name) {
    throw new Error("Executive handoff requires the verified owner-wide evidence view.");
  }
  const structure = executiveWorkforceStructure();
  if (structure.actionsEnabled || structure.applicationWriteAdaptersEnabled) {
    throw new Error("The G1 handoff cannot execute actions.");
  }

  const investigation = buildInvestigationBrief(ledger);
  // Only deterministic findings from fresh signed product summaries survive
  // this boundary; never forward arbitrary external ticket/customer text.
  const findings = investigation.findings.filter((finding: InvestigationFinding) =>
    finding.evidence.source === "signed_product_summary" &&
    typeof finding.evidence.reportedAt === "string" &&
    Number.isFinite(finding.evidence.value) &&
    ledger.records.some(record =>
      record.source === "signed_product_summary" &&
      record.state === "available" &&
      record.system === finding.system &&
      record.reportedAt === finding.evidence.reportedAt &&
      record.metrics.some(metric =>
        metric.key === finding.evidence.metric && metric.value === finding.evidence.value
      )
    )
  ).slice(0, 10).map(finding => ({
    id: finding.id,
    system: finding.system,
    severity: finding.severity,
    title: finding.title,
    source: finding.evidence.source,
    metric: finding.evidence.metric,
    value: finding.evidence.value,
    reportedAt: finding.evidence.reportedAt,
    nextStep: finding.nextStep,
  }));

  const attention = findings.filter(f => f.severity === "attention").length;
  const watch = findings.filter(f => f.severity === "watch").length;
  const priority = attention > 0 ? "attention" : watch > 0 ? "watch" : "routine";
  const incomplete = investigation.dataStatus !== "available";

  return {
    version: "1.0" as const,
    mode: "read-only" as const,
    state: "ceo-review-only" as const,
    from: "coo" as const,
    to: "ceo" as const,
    ownerApprovalGranted: false,
    approvalRequestCreated: false,
    executionEnabled: false,
    customerCommunicationSent: false,
    appRecordsChanged: false,
    source: {
      collectedAt: investigation.checkedAt,
      coverage: investigation.dataStatus,
      status: incomplete ? "incomplete" as const : "available" as const,
    },
    ceoReview: {
      priority,
      recommendation: attention
        ? "Review evidence-backed operational risks and prioritize investigation."
        : watch
          ? "Review the evidence-backed watch items and assign follow-up priorities."
          : "Review routine operations; no actionable verified exceptions in the current evidence.",
      requiresOwnerDecision: false,
      note: "A future restricted action must be proposed through the separate MFA-protected owner approval flow.",
    },
    cooReport: {
      findings,
      unavailableSources: investigation.missing.slice(0, 12).map(item => ({ ...item })),
      notice: "Read-only evidence and recommendations; no live action, approval or autonomous learning occurred.",
    },
  };
}
