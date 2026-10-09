import { createPublicKey, verify as cryptoVerify } from "node:crypto";

// Phase 2C / Phase 3A development contract only. No production verification
// is enabled until each source application signs from its own private key.
// Hub MUST load trusted per-application public keys from server configuration,
// never a key supplied by the agent, a browser, or source JSON.
export const SIGNED_SOURCE_METRIC_KEYS = Object.freeze({
  pos: Object.freeze([
    "products", "locations", "sales", "sales30d", "revenue30d", "openPurchaseOrders",
    "criticalReplenishmentItems", "delayedShipments", "unresolvedInventoryExceptions",
  ]),
  ffpro: Object.freeze([
    "currentMonthIncome", "currentMonthExpenses", "currentMonthNet",
    "yearToDateIncome", "yearToDateExpenses", "yearToDateNet",
  ]),
  tiquet: Object.freeze(["clients", "jobs", "teamMembers", "jobValueTotal", "unreadNotifications"]),
  marketing: Object.freeze([
    "posts", "scheduledPosts", "publishedPosts", "campaigns", "activeCampaigns",
    "customers", "repeatCustomers", "connectedSocialAccounts", "aiCreditsRemaining",
  ]),
});
const EXPECTED_FIELDS = Object.freeze([
  "schema", "source", "organizationId", "requestId", "observedAt", "expiresAt", "metrics",
]);
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const MAX_METRICS = 24;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function epoch(value) {
  if (typeof value !== "string" || !ISO_UTC.test(value)) return NaN;
  const time = Date.parse(value);
  return Number.isFinite(time) && new Date(time).toISOString() === value ? time : NaN;
}

// This EXACT canonical encoding is shared with reviewed application signers.
// It deliberately binds the organisation and unique Hub request ID to the
// observed numeric metric values, without accepting raw customer records.
export function canonicalSourceMetricPayload(raw) {
  if (!isRecord(raw) ||
      Object.keys(raw).sort().join("|") !== [...EXPECTED_FIELDS].sort().join("|") ||
      raw.schema !== "v79-source-metrics-v1" ||
      typeof raw.source !== "string" ||
      !Object.hasOwn(SIGNED_SOURCE_METRIC_KEYS, raw.source) ||
      typeof raw.organizationId !== "string" ||
      !/^[A-Za-z0-9_-]{6,96}$/.test(raw.organizationId) ||
      typeof raw.requestId !== "string" || !UUID_V4.test(raw.requestId) ||
      !Number.isFinite(epoch(raw.observedAt)) ||
      !Number.isFinite(epoch(raw.expiresAt)) ||
      !Array.isArray(raw.metrics) || raw.metrics.length < 1 ||
      raw.metrics.length > MAX_METRICS) return null;
  const known = new Set(SIGNED_SOURCE_METRIC_KEYS[raw.source]);
  const keys = new Set();
  const metrics = [];
  for (const item of raw.metrics) {
    if (!isRecord(item) || Object.keys(item).sort().join("|") !== "key|value" ||
        typeof item.key !== "string" || !known.has(item.key) || keys.has(item.key) ||
        typeof item.value !== "number" || !Number.isFinite(item.value) ||
        Math.abs(item.value) > 1e12) return null;
    keys.add(item.key);
    metrics.push({ key: item.key, value: item.value });
  }
  metrics.sort((a, b) => a.key.localeCompare(b.key));
  return JSON.stringify({
    schema: raw.schema,
    source: raw.source,
    organizationId: raw.organizationId,
    requestId: raw.requestId.toLowerCase(),
    observedAt: raw.observedAt,
    expiresAt: raw.expiresAt,
    metrics,
  });
}

export function verifySignedSourceMetrics({
  payload, signature, expectedSource, expectedOrganizationId,
  expectedRequestId, publicKey, now = new Date(),
} = {}) {
  // Do not derive expected tenant, system, request ID, or trusted signer key
  // from this payload. All must come from authenticated server-side context.
  if (!expectedSource || !expectedOrganizationId || !expectedRequestId ||
      typeof publicKey !== "string" || !publicKey.trim()) return { valid: false };
  const canonical = canonicalSourceMetricPayload(payload);
  const nowMs = +now;
  if (!canonical || !Number.isFinite(nowMs) ||
      payload.source !== expectedSource ||
      payload.organizationId !== expectedOrganizationId ||
      payload.requestId.toLowerCase() !== String(expectedRequestId).toLowerCase()) {
    return { valid: false };
  }
  const observedAt = epoch(payload.observedAt);
  const expiresAt = epoch(payload.expiresAt);
  if (observedAt > nowMs + 30_000 || nowMs - observedAt > 300_000 ||
      expiresAt <= nowMs || expiresAt <= observedAt ||
      expiresAt - observedAt > 120_000) return { valid: false };
  if (typeof signature !== "string" || !/^[A-Za-z0-9_-]{85,88}$/.test(signature)) {
    return { valid: false };
  }
  try {
    const key = createPublicKey(publicKey);
    const value = Buffer.from(signature, "base64url");
    if (key.asymmetricKeyType !== "ed25519" || value.length !== 64 ||
        !cryptoVerify(null, Buffer.from(canonical, "utf8"), key, value)) return { valid: false };
  } catch {
    return { valid: false };
  }
  return {
    valid: true,
    provenance: "source_signed",
    // Explicitly do not return organisation ID, signature or request IDs to
    // model context. The caller retains tenant binding on its server.
    evidence: {
      system: payload.source,
      observedAt: payload.observedAt,
      // From the independently signed source envelope. The preview MUST
      // discard figures at expiration instead of implying everlasting trust.
      expiresAt: payload.expiresAt,
      metrics: JSON.parse(canonical).metrics,
    },
  };
}
