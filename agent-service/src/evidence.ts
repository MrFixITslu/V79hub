import type { AgentContext } from "./context.js";
import { normalizeEmail } from "./context.js";
import { BUSINESS_SYSTEMS } from "./business.js";
import type { WorkforceSpecialist } from "./workforce.js";
import { compactOwnerSnapshot } from "./grounding.js";

/**
 * Only counters/amounts the Hub already obtains through its signed, read-only
 * product summary and admin-stats contracts are allowed into model context.
 * Arbitrary upstream strings, personal details, and newly added fields are
 * deliberately excluded until a reviewed contract exists.
 */
const ALLOWED_METRICS: Record<string, readonly string[]> = {
  pos: ["products", "locations", "sales", "sales30d", "revenue30d", "openPurchaseOrders",
    "criticalReplenishmentItems", "delayedShipments", "unresolvedInventoryExceptions"],
  ffpro: ["currentMonthIncome", "currentMonthExpenses", "currentMonthNet",
    "yearToDateIncome", "yearToDateExpenses", "yearToDateNet"],
  tiquet: ["clients", "jobs", "teamMembers", "jobValueTotal", "unreadNotifications"],
  marketing: ["posts", "scheduledPosts", "publishedPosts", "campaigns", "activeCampaigns",
    "customers", "repeatCustomers", "connectedSocialAccounts", "aiCreditsRemaining"],
  academy: ["publishedCourses", "enrolledCourses", "totalLessons", "totalLearners", "totalEnrolments"],
  lasertag: ["totalBookings", "upcomingBookings", "upcomingPlayers", "bookingsNext30Days", "playersNext30Days"],
  website: ["totalLeads", "newLeads", "qualifiedLeads", "contactedLeads", "lostLeads",
    "followUpsDue", "totalVisitors"],
  games: ["portalViews", "sessions", "players", "spellingCompletions", "wordsMastered"],
};

export type EvidenceMetric = { key: string; value: number };
export type EvidenceRecord = {
  system: string;
  name: string;
  source: "signed_product_summary" | "signed_platform_admin_stats" | "hub_owner_summary";
  state: "available" | "stale" | "unavailable" | "unknown";
  connection: "online" | "unavailable" | "unknown";
  collectedAt: string | null;
  reportedAt: string | null;
  ageSeconds: number | null;
  metrics: EvidenceMetric[];
};

export type EvidenceLedger = {
  mode: "read-only";
  specialist: string;
  collectedAt: string | null;
  records: EvidenceRecord[];
  note: string;
};

type UntrustedRecord = Record<string, unknown>;
const isRecord = (value: unknown): value is UntrustedRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function safeRecord(value: unknown): UntrustedRecord {
  return isRecord(value) ? value : {};
}

function parseTimestamp(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 40) return null;
  const epoch = Date.parse(value);
  return Number.isFinite(epoch) ? new Date(epoch).toISOString() : null;
}

function safeConnection(value: unknown): EvidenceRecord["connection"] {
  return value === "online" ? "online" : value === "unavailable" ? "unavailable" : "unknown";
}

function metricsFor(system: string, raw: unknown): EvidenceMetric[] {
  const entries = safeRecord(raw);
  return (ALLOWED_METRICS[system] || [])
    .flatMap(key => {
      const value = entries[key];
      // Values may be decimal amounts, but never strings or arbitrarily large numbers.
      if (typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > 1e12) return [];
      return [{ key, value }];
    });
}

function statusFor(
  rawStatus: unknown, observedAt: string | null, metricCount: number, nowMs: number,
) : Pick<EvidenceRecord, "state" | "ageSeconds"> {
  if (rawStatus !== "ok") return { state: rawStatus === "unavailable" || rawStatus === "misconfigured" ||
    rawStatus === "needs_setup" || rawStatus === "not_configured" ? "unavailable" : "unknown", ageSeconds: null };
  if (!observedAt) return { state: "unknown", ageSeconds: null };
  const age = Math.round((nowMs - Date.parse(observedAt)) / 1000);
  if (!Number.isFinite(age) || age < -120) return { state: "unknown", ageSeconds: null };
  if (!metricCount) return { state: "unknown", ageSeconds: Math.max(0, age) };
  return { state: age > 900 ? "stale" : "available", ageSeconds: Math.max(0, age) };
}

/** Called AFTER the service token has been verified by Hub and owner scoped by Agent. */
export function verifySignedOwnerSnapshot(snapshot: unknown, context: AgentContext): asserts snapshot is UntrustedRecord {
  if (!isRecord(snapshot)) throw new Error("Missing signed owner evidence.");
  const owner = safeRecord(snapshot.owner);
  if (!context.ownerAgent || !context.hubAdmin ||
    normalizeEmail(context.email) !== normalizeEmail(owner.email) ||
    context.organizationId !== owner.organizationId ||
    !context.organizationId || !context.userId
  ) throw new Error("Signed evidence owner scope mismatch.");
  if (!parseTimestamp(snapshot.generatedAt)) throw new Error("Signed evidence collection time is invalid.");
}

export function buildEvidenceLedger(
  snapshot: UntrustedRecord,
  specialist: WorkforceSpecialist,
  nowMs: number = Date.now(),
): EvidenceLedger {
  const collectedAt = parseTimestamp(snapshot.generatedAt);
  const business = safeRecord(snapshot.business);
  const platform = safeRecord(snapshot.platform);
  const connections = safeRecord(snapshot.connections);
  const records: EvidenceRecord[] = [];

  for (const system of specialist.systems) {
    if (!ALLOWED_METRICS[system]) continue;
    const productName = BUSINESS_SYSTEMS.find(p => p.key === system)?.name || system;
    const connection = safeConnection(safeRecord(connections[system]).status);
    const summary = safeRecord(business[system]);
    const status = summary.status;
    const reportedAt = parseTimestamp(summary.sourceReportedAt);
    const summaryMetrics = status === "ok" ? metricsFor(system, summary.metrics) : [];
    records.push({
      system, name: productName, source: "signed_product_summary", connection, collectedAt, reportedAt,
      ...statusFor(status, reportedAt, summaryMetrics.length, nowMs),
      metrics: summaryMetrics,
    });

    // Admin stats have no product-provided observation timestamp. Never represent
    // the Hub request timestamp as the source system's metric freshness.
    const stats = safeRecord(platform[system]);
    const adminMetrics = stats.status === "ok" ? metricsFor(system, stats.metrics) : [];
    records.push({
      system, name: productName, source: "signed_platform_admin_stats", connection,
      collectedAt, reportedAt: null, ageSeconds: null,
      state: stats.status === "ok" ? "unknown" :
        stats.status === "unavailable" ? "unavailable" : "unknown",
      metrics: adminMetrics,
    });
  }

  if (specialist.id === "technology" || specialist.id === "owner") {
    const hub = safeRecord(snapshot.hubAdmin);
    const metrics = ["users", "activeSessions"].flatMap(key => {
      const value = hub[key];
      return typeof value === "number" && Number.isFinite(value) &&
        value >= 0 && value <= 1e12 ? [{ key, value }] : [];
    });
    records.push({
      system: "hub", name: "V79 Hub Admin", source: "hub_owner_summary",
      connection: "online", collectedAt, reportedAt: collectedAt, ageSeconds: collectedAt
        ? Math.max(0, Math.round((nowMs - Date.parse(collectedAt)) / 1000)) : null,
      state: metrics.length && collectedAt && nowMs - Date.parse(collectedAt) <= 900000 ? "available" : "unknown",
      metrics,
    });
  }

  return {
    mode: "read-only", specialist: specialist.name, collectedAt,
    records,
    note: "Only allowlisted aggregate metrics from Hub's signed, read-only application integrations. Unavailable, undated and stale evidence must not be treated as current facts.",
  };
}


/** Build model/KPI context from verified, fresh, bounded aggregate evidence only. */
export function compactFromEvidence(ledger: EvidenceLedger) {
  const business: Record<string, unknown> = {};
  const connections: Record<string, unknown> = {};
  let hubAdmin: Record<string, number> = {};
  for (const record of ledger.records) {
    if (record.source === "hub_owner_summary") {
      if (record.state === "available") hubAdmin = Object.fromEntries(record.metrics.map(m => [m.key, m.value]));
      continue;
    }
    if (record.source !== "signed_product_summary") continue;
    // An offline HTTP health URL is only an alert; never turn it into evidence that
    // the live business metric has vanished or its numeric value is zero.
    connections[record.system] = { status: record.connection };
    const trustworthy = record.state === "available";
    business[record.system] = {
      status: trustworthy ? "ok" : record.state,
      metrics: trustworthy ? Object.fromEntries(record.metrics.map(m => [m.key, m.value])) : {},
    };
  }
  return compactOwnerSnapshot({
    generatedAt: ledger.collectedAt,
    hubAdmin,
    connections,
    business,
    platform: {},
  });
}
