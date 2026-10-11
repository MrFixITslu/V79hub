/**
 * G2: synthetic-only projection of the ACTUAL observed Sentinel
 * mission_control_snapshot() data fields.
 *
 * Acer source: noc/server.py GET /api/v1/mission-control requires an
 * operator session, while noc/sentinel_mission_bridge.py builds a bounded
 * local status. Nothing here authenticates a machine caller, verifies
 * the producer, signs records, invokes Sentinel, or exposes an API route.
 *
 * Crucially, even a syntactically valid status is UNVERIFIED. Never
 * promote these values to owner/COO/CEO evidence based on this parser.
 */
export type MissionHealthCounts = Readonly<{
  servicesObserved: number;
  up: number;
  down: number;
  degraded: number;
  unknown: number;
}>;

export type ProposedMissionHealth =
  | Readonly<{
      state: "candidate_unverified";
      readyForExecutiveUse: false;
      sourceVerified: false;
      monitorModeReported: "live" | "staging";
      observedAt: string;
      counts: MissionHealthCounts;
    }>
  | Readonly<{
      state: "invalid" | "unknown_time" | "stale" | "no_data";
      readyForExecutiveUse: false;
      sourceVerified: false;
      monitorModeReported: null;
      observedAt: null;
      counts: null;
    }>;

const OUTER_KEYS = ["source", "monitorMode", "lastCheck", "services", "qa"] as const;
const SERVICE_KEYS = ["name", "state", "http", "latencyMs"] as const;
const SERVICE_STATES = ["up", "down", "degraded", "unknown"] as const;
const MAX_JSON_LENGTH = 32_000;
const MAX_AGE_MS = 15 * 60_000;
const CLOCK_SKEW_MS = 120_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function exactKeys(obj: Record<string, unknown>, keys: readonly string[]) {
  const own = Object.keys(obj);
  return own.length === keys.length && keys.every(key => Object.hasOwn(obj, key));
}
function failed(state: "invalid" | "unknown_time" | "stale" | "no_data"): ProposedMissionHealth {
  return {
    state, readyForExecutiveUse: false, sourceVerified: false,
    monitorModeReported: null, observedAt: null, counts: null,
  };
}

/**
 * Shape-only, strictly bounded projection.
 * - Source strings and monitor mode are CLAIMS, never identity/provenance.
 * - Service names, HTTP details and entire QA results are discarded.
 * - No source requests, session cookies, secret tokens or ML tools.
 * - Missing/stale/future data never turns into a false "all healthy".
 */
export function parseProposedMissionHealth(
  payload: unknown,
  nowMs: number = Date.now(),
): ProposedMissionHealth {
  if (!isRecord(payload) || !exactKeys(payload, OUTER_KEYS) ||
      payload.source !== "local-mission-control" ||
      (payload.monitorMode !== "live" && payload.monitorMode !== "staging") ||
      !Array.isArray(payload.services) || payload.services.length > 24 ||
      !isRecord(payload.qa)) return failed("invalid");

  // Reject oversized or unencodable inputs rather than processing unknown
  // browser QA data, even though the QA payload is never returned.
  let serialized: string;
  try { serialized = JSON.stringify(payload); } catch { return failed("invalid"); }
  if (typeof serialized !== "string" || serialized.length > MAX_JSON_LENGTH) return failed("invalid");

  if (typeof payload.lastCheck !== "string" || payload.lastCheck.length > 48 ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(payload.lastCheck)) {
    return failed("unknown_time");
  }
  const observedMs = Date.parse(payload.lastCheck);
  if (!Number.isFinite(nowMs) || !Number.isFinite(observedMs)) return failed("unknown_time");
  const observedAt = new Date(observedMs).toISOString();
  // Some JavaScript runtimes normalize impossible calendar days (e.g. Feb 30)
  // rather than rejecting them. Never interpret a changed date as source truth.
  if (observedAt.slice(0, 19) !== payload.lastCheck.slice(0, 19)) return failed("unknown_time");
  if (observedMs - nowMs > CLOCK_SKEW_MS) return failed("unknown_time");
  if (nowMs - observedMs > MAX_AGE_MS) return failed("stale");

  const counts: Record<(typeof SERVICE_STATES)[number], number> = {
    up: 0, down: 0, degraded: 0, unknown: 0,
  };
  for (const item of payload.services) {
    if (!isRecord(item) || !exactKeys(item, SERVICE_KEYS) ||
        typeof item.name !== "string" || item.name.length > 65 ||
        typeof item.state !== "string" ||
        !(SERVICE_STATES as readonly string[]).includes(item.state) ||
        !(item.http === null || (
          typeof item.http === "number" && Number.isInteger(item.http) &&
          item.http >= 100 && item.http <= 599
        )) ||
        !(item.latencyMs === null || (
          typeof item.latencyMs === "number" && Number.isInteger(item.latencyMs) &&
          item.latencyMs >= 0 && item.latencyMs <= 120_000
        ))
    ) return failed("invalid");
    counts[item.state as keyof typeof counts] += 1;
  }
  if (payload.services.length === 0) return failed("no_data");

  return {
    state: "candidate_unverified",
    readyForExecutiveUse: false,
    sourceVerified: false,
    monitorModeReported: payload.monitorMode,
    observedAt,
    counts: {
      servicesObserved: payload.services.length,
      up: counts.up, down: counts.down,
      degraded: counts.degraded, unknown: counts.unknown,
    },
  };
}
