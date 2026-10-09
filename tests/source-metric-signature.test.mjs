import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, sign as signEd25519 } from "node:crypto";
import { canonicalSourceMetricPayload, verifySignedSourceMetrics } from "../server/source-metric-signature.mjs";

const original = {
  schema: "v79-source-metrics-v1",
  source: "pos",
  organizationId: "ci-owner-org",
  requestId: "01234567-89ab-4cde-8000-0123456789ab",
  observedAt: "2026-10-09T11:59:00.000Z",
  expiresAt: "2026-10-09T12:01:00.000Z",
  metrics: [
    { key: "criticalReplenishmentItems", value: 4 },
    { key: "delayedShipments", value: 1 },
  ],
};
const clock = new Date("2026-10-09T12:00:00.000Z");
const pair = generateKeyPairSync("ed25519");
const anotherPair = generateKeyPairSync("ed25519");
const trustedPublicKey = pair.publicKey.export({ format: "pem", type: "spki" });
const signed = payload => {
  const canonical = canonicalSourceMetricPayload(payload);
  if (!canonical) return "";
  return signEd25519(null, Buffer.from(canonical, "utf8"), pair.privateKey).toString("base64url");
};
const call = (payload = original, options = {}) => verifySignedSourceMetrics({
  payload,
  signature: signed(payload),
  publicKey: trustedPublicKey,
  expectedSource: "pos",
  expectedOrganizationId: "ci-owner-org",
  expectedRequestId: original.requestId,
  now: clock,
  ...options,
});

test("signed metric envelope verifies only trusted Ed25519 origin and exposes no tenant identifiers", () => {
  const proof = call();
  assert.equal(proof.valid, true);
  assert.equal(proof.provenance, "source_signed");
  assert.equal(proof.evidence.system, "pos");
  assert.equal(proof.evidence.expiresAt, original.expiresAt,
    "Trusted expiration is part of the verified source evidence");
  assert.equal(proof.evidence.metrics.length, 2);
  assert.equal("organizationId" in proof.evidence, false);
  assert.equal("requestId" in proof.evidence, false);
  assert.equal("signature" in proof.evidence, false);
  const reverse = { ...original, metrics: [...original.metrics].reverse() };
  assert.equal(canonicalSourceMetricPayload(reverse), canonicalSourceMetricPayload(original),
    "the same signed metric set has one canonical representation");
  assert.equal(call(reverse, { signature: signed(original) }).valid, true);
});

test("source, tenant and request binding block cross-workspace or replayed source evidence", () => {
  assert.equal(call(original, { expectedOrganizationId: "other-org" }).valid, false);
  assert.equal(call(original, { expectedSource: "tiquet" }).valid, false);
  assert.equal(call(original, { expectedRequestId: "12345678-89ab-4cde-8000-0123456789ab" }).valid, false);
  assert.equal(call(original, { publicKey: anotherPair.publicKey.export({ format: "pem", type: "spki" }) }).valid, false);
  const changed = { ...original, organizationId: "other-org" };
  assert.equal(call(changed, { signature: signed(original) }).valid, false);
  const unrelated = { ...original, metrics: [{ key: "criticalReplenishmentItems", value: 9 }] };
  assert.equal(call(unrelated, { signature: signed(original) }).valid, false);
  assert.equal(call(original, { signature: "forged-signature" }).valid, false);
  assert.equal(call(original, { publicKey: "not a valid trusted key" }).valid, false);
});

test("source freshness and bounded expiry are enforced independent of signature validity", () => {
  const stale = { ...original, observedAt: "2026-10-09T11:54:00.000Z", expiresAt: "2026-10-09T11:55:00.000Z" };
  assert.equal(call(stale).valid, false);
  const future = { ...original, observedAt: "2026-10-09T12:01:00.000Z", expiresAt: "2026-10-09T12:02:00.000Z" };
  assert.equal(call(future).valid, false);
  const longTtl = { ...original, expiresAt: "2026-10-09T12:05:00.000Z" };
  assert.equal(call(longTtl).valid, false);
  const expired = { ...original, expiresAt: "2026-10-09T11:59:30.000Z" };
  assert.equal(call(expired).valid, false);
  const invalidStamp = { ...original, observedAt: "2026-10-09" };
  assert.equal(call(invalidStamp).valid, false);
});

test("source contract rejects arbitrary upstream PII, schema drift, duplicate metrics and outliers", () => {
  const bad = [
    { ...original, metrics: [{ key: "customerEmail", value: 1 }] },
    { ...original, metrics: [{ key: "criticalReplenishmentItems", value: "4" }] },
    { ...original, metrics: [{ key: "criticalReplenishmentItems", value: NaN }] },
    { ...original, metrics: [{ key: "criticalReplenishmentItems", value: 1e14 }] },
    { ...original, metrics: [{ key: "criticalReplenishmentItems", value: 4, customerName: "Someone" }] },
    { ...original, metrics: [original.metrics[0], original.metrics[0]] },
    { ...original, metrics: [] },
    { ...original, arbitraryRequestUrl: "https://example.invalid" },
    { ...original, requestId: "unscoped-request" },
    { ...original, source: "other_application" },
    { ...original, organizationId: "owner@unsafe.example" },
    { ...original, schema: "v79-unsafe-write-v1" },
  ];
  for (const envelope of bad) {
    assert.equal(canonicalSourceMetricPayload(envelope), null);
    assert.equal(call(envelope).valid, false);
  }
});

test("Hub rejects missing trusted verification configuration and non-Ed25519 keys", () => {
  assert.equal(call(original, { publicKey: "" }).valid, false);
  assert.equal(call(original, { expectedSource: "" }).valid, false);
  assert.equal(call(original, { expectedOrganizationId: "" }).valid, false);
  assert.equal(call(original, { expectedRequestId: "" }).valid, false);
  const rsa = generateKeyPairSync("rsa", { modulusLength: 2048 });
  assert.equal(call(original, {
    publicKey: rsa.publicKey.export({ format: "pem", type: "spki" }),
  }).valid, false);
});
