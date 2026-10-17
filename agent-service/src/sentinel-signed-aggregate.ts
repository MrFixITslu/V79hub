import type { MissionHealthCounts } from "./sentinel-proposed-contract.js";

/**
 * Only this narrow, PRE-AGGREGATED schema may cross the eventual NOC -> Hub
 * signed service boundary. It is NOT the browser Mission Control payload.
 *
 * There is no code connecting this to actual Sentinel, and successful shape
 * checks alone are never proof of the real source or owner tenant.
 */
const FIELDS = ["schemaVersion", "source", "observedAt", "monitorMode", "counts"];
const COUNTS = ["servicesObserved", "up", "down", "degraded", "unknown"];
const MAX_AGE_MS = 15 * 60_000;
const MAX_FUTURE_MS = 120_000;
type RecordUnknown = Record<string, unknown>;

export type SignedMissionAggregateCandidate =
  | Readonly<{
      state: "candidate_unverified";
      observedAt: string;
      counts: MissionHealthCounts;
      sourceVerified: false;
      readyForExecutiveUse: false;
    }>
  | Readonly<{
      state: "invalid" | "stale" | "unknown_time" | "no_data";
      observedAt: null;
      counts: null;
      sourceVerified: false;
      readyForExecutiveUse: false;
    }>;

const isRecord = (x: unknown): x is RecordUnknown => typeof x === "object" && x !== null && !Array.isArray(x);
const exactly = (value: RecordUnknown, fields: readonly string[]) =>
  Object.keys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));

function reject(state: "invalid" | "stale" | "unknown_time" | "no_data"): SignedMissionAggregateCandidate {
  return { state, observedAt: null, counts: null, sourceVerified: false, readyForExecutiveUse: false };
}

/** Data can be emitted only after the producer aggregates status values
 * locally, discarding QA results, names, IP/MAC data, incident text and other
 * raw records before serialization and signing.
 */
export function parseSignedMissionAggregateCandidate(
  value: unknown,
  nowMs: number = Date.now(),
): SignedMissionAggregateCandidate {
  if (!isRecord(value) || !exactly(value, FIELDS) ||
      value.schemaVersion !== 1 || value.source !== "local-mission-control" ||
      (value.monitorMode !== "live" && value.monitorMode !== "staging") ||
      !isRecord(value.counts) || !exactly(value.counts, COUNTS)) return reject("invalid");
  const counts = value.counts;
  if (!COUNTS.every(k => typeof counts[k] === "number" &&
      Number.isSafeInteger(counts[k]) && (counts[k] as number) >= 0 &&
      (counts[k] as number) <= 24)) return reject("invalid");
  const total = counts.servicesObserved as number;
  if (total !== (counts.up as number) + (counts.down as number) +
      (counts.degraded as number) + (counts.unknown as number)) return reject("invalid");
  if (total === 0) return reject("no_data");

  if (typeof value.observedAt !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value.observedAt)) return reject("unknown_time");
  const time = Date.parse(value.observedAt);
  if (!Number.isFinite(nowMs) || !Number.isFinite(time) ||
      new Date(time).toISOString() !== value.observedAt) return reject("unknown_time");
  if (time > nowMs + MAX_FUTURE_MS) return reject("unknown_time");
  if (nowMs - time > MAX_AGE_MS) return reject("stale");

  return {
    state: "candidate_unverified",
    observedAt: value.observedAt,
    counts: {
      servicesObserved: total,
      up: counts.up as number,
      down: counts.down as number,
      degraded: counts.degraded as number,
      unknown: counts.unknown as number,
    },
    sourceVerified: false,
    readyForExecutiveUse: false,
  };
}
