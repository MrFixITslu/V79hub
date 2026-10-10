/**
 * G2 PROPOSED contract only. NOT connected to Sentinel, Hub, or any model.
 *
 * The Acer Sentinel source has identified authenticated NOC GET routes but
 * their payload, organization scope, and machine-to-machine signing semantics
 * are not yet verified. This parser is a synthetic contract prototype.
 *
 * IMPORTANT: A structurally valid payload is NOT authenticated. Its output
 * must never be sent to CEO/COO or treated as signed product evidence.
 */
export type ProposedSentinelCounts = Readonly<{
  monitoredDevices: number;
  unreachableDevices: number;
  criticalOpenIncidents: number;
  warningOpenIncidents: number;
}>;

export type ProposedSentinelCandidate = Readonly<{
  state: "candidate_unverified";
  readyForExecutiveUse: false;
  observedAt: string;
  counts: ProposedSentinelCounts;
}>;

export type ProposedSentinelResult =
  | ProposedSentinelCandidate
  | Readonly<{
      state: "invalid" | "stale" | "unknown_time";
      readyForExecutiveUse: false;
      observedAt: null;
      counts: null;
    }>;

const countKeys = [
  "monitoredDevices", "unreachableDevices",
  "criticalOpenIncidents", "warningOpenIncidents",
] as const;
const outerKeys = ["schemaVersion", "organizationId", "observedAt", "counts"] as const;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasExactly(value: Record<string, unknown>, keys: readonly string[]) {
  const own = Object.keys(value);
  return own.length === keys.length && keys.every(key => Object.hasOwn(value, key));
}

const failed = (state: "invalid" | "stale" | "unknown_time"): ProposedSentinelResult => ({
  state, readyForExecutiveUse: false, observedAt: null, counts: null,
});

/**
 * Shape-only validation for the future signed adapter. Never call this with
 * a model-supplied organization ID; only a verified server-side owner binding.
 * The parser accepts no packet data, IP/device addresses, user identifiers,
 * raw incident descriptions, credentials or arbitrary text.
 *
 * An independently authenticated source envelope and protected request/nonce
 * remain mandatory before any data can be promoted to a business evidence
 * ledger. Nothing here implements or pretends to verify a signature.
 */
export function parseProposedSentinelSummary(
  payload: unknown,
  expectedOrganizationId: string,
  nowMs: number = Date.now(),
): ProposedSentinelResult {
  if (!record(payload) || !hasExactly(payload, outerKeys) ||
    payload.schemaVersion !== 1 ||
    typeof expectedOrganizationId !== "string" ||
    expectedOrganizationId.length < 6 || expectedOrganizationId.length > 96 ||
    !/^[a-zA-Z0-9_-]+$/.test(expectedOrganizationId) ||
    payload.organizationId !== expectedOrganizationId ||
    !record(payload.counts) || !hasExactly(payload.counts, countKeys)
  ) return failed("invalid");

  const counts = payload.counts;
  if (!countKeys.every(key =>
    typeof counts[key] === "number" &&
    Number.isSafeInteger(counts[key]) &&
    (counts[key] as number) >= 0 && (counts[key] as number) <= 1_000_000
  )) return failed("invalid");

  if ((counts.unreachableDevices as number) > (counts.monitoredDevices as number)) {
    return failed("invalid");
  }

  if (typeof payload.observedAt !== "string" || payload.observedAt.length > 40 ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(payload.observedAt)
  ) return failed("unknown_time");

  const observedMs = Date.parse(payload.observedAt);
  if (!Number.isFinite(nowMs) || !Number.isFinite(observedMs) ||
    new Date(observedMs).toISOString() !== new Date(Date.parse(payload.observedAt)).toISOString()
  ) return failed("unknown_time");

  const deltaMs = nowMs - observedMs;
  if (deltaMs < -120_000) return failed("unknown_time");
  if (deltaMs > 15 * 60_000) return failed("stale");

  return {
    state: "candidate_unverified",
    readyForExecutiveUse: false,
    observedAt: new Date(observedMs).toISOString(),
    counts: {
      monitoredDevices: counts.monitoredDevices as number,
      unreachableDevices: counts.unreachableDevices as number,
      criticalOpenIncidents: counts.criticalOpenIncidents as number,
      warningOpenIncidents: counts.warningOpenIncidents as number,
    },
  };
}
