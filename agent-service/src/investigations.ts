import type { EvidenceLedger, EvidenceRecord } from "./evidence.js";
import type { WorkforceSpecialistId } from "./workforce.js";

export type InvestigationSeverity = "attention" | "watch" | "information";
export type InvestigationFinding = {
  id: string;
  system: string;
  severity: InvestigationSeverity;
  title: string;
  evidence: { source: "signed_product_summary"; metric: string; value: number; reportedAt: string };
  nextStep: string;
};
export type InvestigationBrief = {
  mode: "read-only";
  specialist: string;
  dataStatus: "available" | "partial" | "unavailable";
  checkedAt: string | null;
  findings: InvestigationFinding[];
  missing: Array<{ system: string; reason: "stale" | "unavailable" | "unknown" }>;
  notice: string;
};

/**
 * Stage 2B is an *aggregate* investigation, not ticket/customer/item-level access.
 * Rules never consume undated admin stats, stale product data, free-form strings,
 * or model-authored actions. Every finding is traceable to one fresh metric.
 */
export function buildInvestigationBrief(ledger: EvidenceLedger): InvestigationBrief {
  const latestBySystem = new Map<string, EvidenceRecord>();
  for (const record of ledger.records) {
    if (record.source === "signed_product_summary") latestBySystem.set(record.system, record);
  }
  const findings: InvestigationFinding[] = [];
  const missing: InvestigationBrief["missing"] = [];
  const seen = new Set<string>();

  const add = (
    record: EvidenceRecord, metric: string, predicate: (value: number) => boolean,
    severity: InvestigationSeverity, title: string, nextStep: string,
  ) => {
    if (record.state !== "available" || !record.reportedAt) return;
    const reading = record.metrics.find(m => m.key === metric);
    if (!reading || !Number.isFinite(reading.value) || !predicate(reading.value)) return;
    const id = record.system + ":" + metric;
    if (seen.has(id)) return;
    seen.add(id);
    findings.push({
      id, system: record.system, severity, title,
      evidence: { source: "signed_product_summary", metric, value: reading.value, reportedAt: record.reportedAt },
      nextStep,
    });
  };
  for (const [system, record] of latestBySystem) {
    if (record.state !== "available") {
      missing.push({ system, reason: record.state === "stale" ? "stale" : record.state === "unavailable" ? "unavailable" : "unknown" });
      continue;
    }
    if (system === "pos") {
      add(record, "criticalReplenishmentItems", x => x > 0, "attention",
        "Inventory replenishment needs review", "Inspect POS reorder recommendations and confirm stock before placing any orders.");
      add(record, "delayedShipments", x => x > 0, "attention",
        "Delayed shipments need investigation", "Review shipment ETAs and contact suppliers through an approved workflow.");
      add(record, "unresolvedInventoryExceptions", x => x > 0, "attention",
        "Open inventory exceptions", "Inspect the POS exception queue and reconcile the affected stock records.");
      add(record, "openPurchaseOrders", x => x > 0, "watch",
        "Purchase orders remain open", "Review open POs for expected deliveries and overdue approvals.");
      add(record, "sales30d", x => x === 0, "watch",
        "No completed sales recorded in the last 30 days", "Check whether this is expected for the beta and verify the POS sales setup.");
    }
    if (system === "ffpro") {
      add(record, "currentMonthNet", x => x < 0, "attention",
        "Negative current-month net cashflow", "Review expense categories and incoming receipts in FFPRO before making financial decisions.");
      add(record, "currentMonthExpenses", x => x > 0, "information",
        "Current-month expenses recorded", "Inspect FFPRO expense breakdowns for unusual categories or recurring charges.");
    }
    if (system === "tiquet") {
      add(record, "unreadNotifications", x => x > 0, "watch",
        "Unread support notifications", "Review Tiquet notifications and assign follow-up through the normal support workflow.");
      add(record, "jobs", x => x > 0, "information",
        "Tiquet jobs recorded", "Inspect ticket statuses and resolution timelines inside Tiquet.");
    }
    if (system === "marketing") {
      add(record, "activeCampaigns", x => x === 0, "watch",
        "No active marketing campaigns", "Review whether a campaign is scheduled or still awaiting founder approval.");
      add(record, "scheduledPosts", x => x > 0, "information",
        "Social posts scheduled", "Review draft and scheduled posts before publication.");
      add(record, "connectedSocialAccounts", x => x === 0, "watch",
        "No connected social accounts", "Review authorised platform connections in V79 Marketing.");
    }
  }
  const order: Record<InvestigationSeverity, number> = { attention: 0, watch: 1, information: 2 };
  findings.sort((a, b) => order[a.severity] - order[b.severity] || a.system.localeCompare(b.system));
  return {
    mode: "read-only",
    specialist: ledger.specialist,
    checkedAt: ledger.collectedAt,
    dataStatus: latestBySystem.size === 0 || missing.length === latestBySystem.size ? "unavailable" :
      missing.length > 0 ? "partial" : "available",
    findings: findings.slice(0, 20),
    missing,
    notice: "Derived only from fresh owner-workspace aggregate summaries. No individual tickets, customer records, purchases or campaigns were opened or changed. Confirm recommendations in the relevant application.",
  };
}

export function investigationDomainsForSpecialist(id: WorkforceSpecialistId): string[] {
  switch (id) {
    case "operations": return ["pos", "tiquet"];
    case "finance": return ["ffpro", "pos"];
    case "growth": return ["marketing", "website"];
    case "customer": return ["tiquet", "website"];
    case "technology": return ["pos", "ffpro", "tiquet", "marketing", "academy", "lasertag", "website", "games"];
    case "combatzone": return ["lasertag"];
    case "owner": return ["pos", "ffpro", "tiquet", "marketing", "academy", "lasertag", "website", "games"];
  }
}
