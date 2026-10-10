import { randomUUID } from "node:crypto";
import { verifySignedSourceMetrics } from "./source-metric-signature.mjs";

// Separate, disabled-by-default GET-only source reader for the first Tiquet
// Ed25519 proof-of-origin pilot. Never fetch arbitrary URLs or relay raw
// signed envelopes (tenant ID, request ID, signature) to a model/browser.
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const TENANT_ID = /^[A-Za-z0-9_-]{6,96}$/;
const MAX_RESPONSE_BYTES = 8192;
// This pilot requires the complete five-counter Tiquet schema. A valid Ed25519
// signature over an incomplete aggregate must not be presented as complete.
const REQUIRED_TIQUET_METRICS = Object.freeze([
  "clients", "jobs", "teamMembers", "unreadNotifications", "jobValueTotal",
]);

/**
 * @param {{
 *   enabled?: boolean, organizationId?: string, publicKey?: string,
 *   platformSecret?: string, baseUrl?: string,
 *   signPlatformRequest?: (input: {method:string, pathname:string, timestamp:string, body:string, secret:string}) => string,
 *   fetcher?: typeof fetch, now?: () => Date, uuid?: () => string, timeoutMs?: number,
 * }} options
 */
export async function readSignedTiquetMetrics({
  enabled = false, organizationId, publicKey, platformSecret, baseUrl,
  signPlatformRequest, fetcher = fetch, now = () => new Date(),
  uuid = randomUUID, timeoutMs = 3500,
} = {}) {
  const unavailable = { status: "unavailable", source: "tiquet", executionEnabled: false };
  if (!enabled || typeof organizationId !== "string" || !TENANT_ID.test(organizationId) ||
      typeof platformSecret !== "string" || platformSecret.length < 32 ||
      typeof publicKey !== "string" || !publicKey.trim() ||
      typeof signPlatformRequest !== "function" || typeof baseUrl !== "string") {
    return unavailable;
  }
  const requestId = uuid();
  const timestampDate = now();
  if (!UUID_V4.test(requestId) || !(timestampDate instanceof Date) ||
      !Number.isFinite(+timestampDate)) return unavailable;
  const pathname = `/api/platform/agent/signed-metrics/${organizationId}/${requestId}`;
  const timestamp = String(+timestampDate);
  let url;
  try {
    url = new URL(pathname, baseUrl);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
        !url.hostname || url.pathname !== pathname) return unavailable;
  } catch {
    return unavailable;
  }
  try {
    const signature = signPlatformRequest({
      method: "GET", pathname, timestamp, body: "", secret: platformSecret,
    });
    const response = await fetcher(url, {
      method: "GET", redirect: "manual",
      headers: {
        "accept": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signature,
      },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (response.status !== 200 ||
        !/^application\/json(?:\s*;|$)/i.test(response.headers.get("content-type") || "") ||
        Number(response.headers.get("content-length") || "0") > MAX_RESPONSE_BYTES) return unavailable;
    const text = await response.text();
    if (Buffer.byteLength(text, "utf8") > MAX_RESPONSE_BYTES) return unavailable;
    const body = JSON.parse(text);
    if (!body || typeof body !== "object" || Array.isArray(body) ||
        Object.keys(body).sort().join("|") !== "payload|signature") return unavailable;
    const verified = verifySignedSourceMetrics({
      payload: body.payload, signature: body.signature,
      expectedSource: "tiquet", expectedOrganizationId: organizationId,
      // Re-evaluate the clock after the HTTP read. A slow or noncompliant
      // fetcher must not make an expired signature look fresh.
      expectedRequestId: requestId, publicKey, now: now(),
    });
    if (!verified.valid) return unavailable;
    const received = verified.evidence.metrics;
    if (received.length !== REQUIRED_TIQUET_METRICS.length ||
        received.some(item => !REQUIRED_TIQUET_METRICS.includes(item.key) ||
          (item.key !== "jobValueTotal" &&
           (!Number.isSafeInteger(item.value) || item.value < 0)))) return unavailable;
    return {
      status: "available", source: "tiquet", provenance: "source_signed",
      observedAt: verified.evidence.observedAt,
      expiresAt: verified.evidence.expiresAt,
      metrics: verified.evidence.metrics,
      executionEnabled: false,
    };
  } catch {
    // Missing, stale, malformed or unverifiable is unknown, NEVER zero.
    return unavailable;
  }
}
