import { createHmac } from "node:crypto";

/**
 * G2.4 SYNTHETIC-ONLY request signer. Pure request data; no network access.
 * The caller must already possess a verified, owner-scoped Hub context and
 * secure service identity. Never share the HMAC secret with agents/browsers.
 */
export const SENTINEL_READ_PATH = "/internal/sentinel/g2/mission-aggregate";
const DOMAIN = "V79-SENTINEL-G2-GET-v1\n";
const UUID_V4 = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
const IDENTIFIER = /^[A-Za-z0-9_-]+$/;

export function createSyntheticSignedSentinelGet(
  challenge: { requestId: string; organizationId: string; keyId: string },
  sharedSecret: Buffer,
  nowMs: number = Date.now(),
) {
  if (!UUID_V4.test(challenge.requestId) ||
      typeof challenge.organizationId !== "string" ||
      !IDENTIFIER.test(challenge.organizationId) ||
      challenge.organizationId.length < 6 || challenge.organizationId.length > 96 ||
      typeof challenge.keyId !== "string" ||
      !IDENTIFIER.test(challenge.keyId) ||
      challenge.keyId.length < 1 || challenge.keyId.length > 64 ||
      !Buffer.isBuffer(sharedSecret) || sharedSecret.length < 32 ||
      !Number.isFinite(nowMs)) {
    throw new Error("Invalid trusted synthetic Sentinel read scope");
  }
  const issuedAt = new Date(nowMs).toISOString();
  const message = DOMAIN + [
    "GET", SENTINEL_READ_PATH,
    challenge.organizationId, challenge.keyId, challenge.requestId, issuedAt,
  ].join("\n");
  const signature = createHmac("sha256", sharedSecret)
    .update(message, "utf8").digest("base64url");
  return {
    method: "GET" as const,
    path: SENTINEL_READ_PATH,
    headers: {
      "X-V79-Read-Organization": challenge.organizationId,
      "X-V79-Read-Key-Id": challenge.keyId,
      "X-V79-Read-Request-Id": challenge.requestId,
      "X-V79-Read-Issued-At": issuedAt,
      "X-V79-Read-Signature": signature,
    },
  };
}
