import { createPublicKey, randomUUID, verify as cryptoVerify, type KeyObject } from "node:crypto";
import { parseProposedMissionHealth, type MissionHealthCounts } from "./sentinel-proposed-contract.js";

/**
 * G2 security experiment ONLY: verifies a locally supplied, signed response
 * against a trusted, injected Ed25519 public key and a single-use request ID.
 *
 * This code makes NO HTTP requests; it is NOT mounted on Hub, Sentinel or
 * an agent route, and a valid fixture signature is NOT a claim that the
 * actual Sentinel service owns the trusted key.
 */
export const SENTINEL_G2_SIGNING_DOMAIN = "V79-SENTINEL-READ-G2-v1\n";
const ENVELOPE_KEYS = [
  "schemaVersion", "keyId", "organizationId", "requestId",
  "issuedAt", "expiresAt", "payloadJson", "signature",
] as const;
const MAX_ENVELOPE_CHARS = 40_000;
const MAX_PAYLOAD_CHARS = 32_000;
const MAX_CHALLENGE_AGE_MS = 60_000;
const MAX_CLOCK_SKEW_MS = 30_000;
const MAX_PENDING_CHALLENGES = 32;

type SignedEnvelope = {
  schemaVersion: 1;
  keyId: string;
  organizationId: string;
  requestId: string;
  issuedAt: string;
  expiresAt: string;
  payloadJson: string;
  signature: string;
};

export type SentinelG2Verification =
  | Readonly<{
      state: "signature_valid_synthetic_only";
      signatureVerified: true;
      sourceVerified: false;
      readyForExecutiveUse: false;
      observedAt: string;
      counts: MissionHealthCounts;
    }>
  | Readonly<{
      state: "rejected";
      signatureVerified: false;
      sourceVerified: false;
      readyForExecutiveUse: false;
      observedAt: null;
      counts: null;
    }>;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function exactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const names = Object.keys(value);
  return names.length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function parsedUtcMs(value: unknown): number | null {
  if (typeof value !== "string" || value.length > 30 ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value)) return null;
  const time = Date.parse(value);
  if (!Number.isFinite(time) || new Date(time).toISOString() !== value) return null;
  return time;
}
function rejected(): SentinelG2Verification {
  return {
    state: "rejected",
    signatureVerified: false,
    sourceVerified: false,
    readyForExecutiveUse: false,
    observedAt: null,
    counts: null,
  };
}

/** Signing input is fixed as a domain-separated UTF-8 serialization.
 * Sender must sign these exact fields, in this exact order. No JSON
 * canonicalization of arbitrary maps, signature-over-an-untrusted-object,
 * arbitrary URL, or model-authored input.
 */
function signedInput(value: SignedEnvelope) {
  return Buffer.from(SENTINEL_G2_SIGNING_DOMAIN + JSON.stringify([
    value.schemaVersion, value.keyId, value.organizationId, value.requestId,
    value.issuedAt, value.expiresAt, value.payloadJson,
  ]), "utf8");
}

export function createSyntheticSentinelResponseVerifier(config: {
  publicKeyPem: string;
  keyId: string;
  organizationId: string;
}, clock: () => number = () => Date.now()) {
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(config.keyId) ||
      !/^[A-Za-z0-9_-]{6,96}$/.test(config.organizationId)) {
    throw new Error("Invalid trusted Sentinel test verifier scope");
  }
  // Trusted key must be injected by the operator from a reviewed publisher;
  // test fixtures are NOT real production Sentinel public keys.
  const key: KeyObject = createPublicKey(config.publicKeyPem);
  if (key.asymmetricKeyType !== "ed25519") throw new Error("Expected Ed25519 signing key");

  const pending = new Map<string, number>();
  const prune = (nowMs: number) => {
    for (const [id, issuedMs] of pending) {
      if (!Number.isFinite(nowMs) || nowMs - issuedMs > MAX_CHALLENGE_AGE_MS ||
          nowMs < issuedMs - MAX_CLOCK_SKEW_MS) pending.delete(id);
    }
  };

  return {
    issueChallenge() {
      const nowMs = clock();
      if (!Number.isFinite(nowMs)) throw new Error("Clock unavailable");
      prune(nowMs);
      if (pending.size >= MAX_PENDING_CHALLENGES) throw new Error("Too many pending Sentinel test challenges");
      const requestId = randomUUID();
      pending.set(requestId, nowMs);
      return { requestId, organizationId: config.organizationId, keyId: config.keyId };
    },

    /** Verification is one-shot even on failure. The request nonce must
     * be freshly obtained for each test fetch; distributed replay protection
     * and HTTPS peer identity are NOT implemented here.
     */
    verify(envelope: unknown): SentinelG2Verification {
      const nowMs = clock();
      if (!Number.isFinite(nowMs) || !isObject(envelope)) return rejected();

      // Consume a known outstanding request ID even when the rest of the
      // envelope is malformed or oversized. A failed attempt cannot be retried
      // with the same nonce in this prototype.
      const requestId = envelope.requestId;
      if (typeof requestId !== "string") return rejected();
      const challengeIssuedMs = pending.get(requestId);
      if (challengeIssuedMs === undefined) return rejected();
      pending.delete(requestId);
      prune(nowMs);
      if (nowMs - challengeIssuedMs > MAX_CHALLENGE_AGE_MS ||
          nowMs < challengeIssuedMs - MAX_CLOCK_SKEW_MS) return rejected();

      if (!exactKeys(envelope, ENVELOPE_KEYS)) return rejected();
      let bytes: string;
      try { bytes = JSON.stringify(envelope); } catch { return rejected(); }
      if (Buffer.byteLength(bytes, "utf8") > MAX_ENVELOPE_CHARS) return rejected();

      if (envelope.schemaVersion !== 1 || envelope.keyId !== config.keyId ||
          envelope.organizationId !== config.organizationId ||
          typeof envelope.payloadJson !== "string" ||
          envelope.payloadJson.length === 0 || Buffer.byteLength(envelope.payloadJson, "utf8") > MAX_PAYLOAD_CHARS ||
          typeof envelope.signature !== "string" ||
          !/^[A-Za-z0-9_-]{86}$/.test(envelope.signature)) return rejected();

      const issuedMs = parsedUtcMs(envelope.issuedAt);
      const expiresMs = parsedUtcMs(envelope.expiresAt);
      if (issuedMs === null || expiresMs === null ||
          issuedMs > nowMs + MAX_CLOCK_SKEW_MS ||
          nowMs - issuedMs > MAX_CHALLENGE_AGE_MS ||
          issuedMs < challengeIssuedMs - MAX_CLOCK_SKEW_MS ||
          expiresMs <= issuedMs || expiresMs > issuedMs + MAX_CHALLENGE_AGE_MS ||
          expiresMs <= nowMs) return rejected();

      const signature = Buffer.from(envelope.signature, "base64url");
      if (signature.length !== 64) return rejected();
      let valid = false;
      try {
        valid = cryptoVerify(null, signedInput(envelope as SignedEnvelope), key, signature);
      } catch { return rejected(); }
      if (!valid) return rejected();

      let payload: unknown;
      try { payload = JSON.parse(envelope.payloadJson); } catch { return rejected(); }
      const observation = parseProposedMissionHealth(payload, nowMs);
      if (observation.state !== "candidate_unverified") return rejected();

      // Cryptographic verification against the injected fixture key is
      // distinct from real-source attestation or tenancy authorization.
      return {
        state: "signature_valid_synthetic_only",
        signatureVerified: true,
        sourceVerified: false,
        readyForExecutiveUse: false,
        observedAt: observation.observedAt,
        counts: observation.counts,
      };
    },
  };
}
