import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import {
  createSyntheticSentinelResponseVerifier,
  SENTINEL_G2_SIGNING_DOMAIN,
} from "../src/sentinel-signed-response-prototype.js";

const now = Date.parse("2026-10-10T23:40:00.000Z");
const keys = generateKeyPairSync("ed25519"); // only ephemeral synthetic test keys
const publicKeyPem = keys.publicKey.export({ type: "spki", format: "pem" }).toString();
const verifier = () => createSyntheticSentinelResponseVerifier({
  keyId: "sentinel-fixture-v1",
  organizationId: "v79founder",
  publicKeyPem,
}, () => now);

function payload() {
  return {
    source: "local-mission-control",
    monitorMode: "staging",
    lastCheck: new Date(now - 20_000).toISOString(),
    services: [
      { name: "Sensitive site 10.0.1.2", state: "up", http: 200, latencyMs: 20 },
      { name: "Customer ACME Private", state: "down", http: 503, latencyMs: 150 },
    ],
    qa: {
      runId: "synthetic", checkedAt: new Date(now).toISOString(),
      results: [{ name: "sensitive@example.invalid", status: "fail" }],
    },
  };
}
type FixtureEnvelope = {
  schemaVersion: 1; keyId: string; organizationId: string;
  requestId: string; issuedAt: string; expiresAt: string;
  payloadJson: string; signature: string;
};
function signFixture(e: FixtureEnvelope) {
  const message = SENTINEL_G2_SIGNING_DOMAIN + JSON.stringify([
    e.schemaVersion, e.keyId, e.organizationId, e.requestId,
    e.issuedAt, e.expiresAt, e.payloadJson,
  ]);
  return { ...e, signature: sign(null, Buffer.from(message, "utf8"), keys.privateKey).toString("base64url") };
}
function makeEnvelope(v: ReturnType<typeof verifier>, overrides: Partial<FixtureEnvelope> = {}) {
  const challenge = v.issueChallenge();
  return signFixture({
    schemaVersion: 1, keyId: challenge.keyId,
    organizationId: challenge.organizationId,
    requestId: challenge.requestId,
    issuedAt: new Date(now).toISOString(),
    expiresAt: new Date(now + 30_000).toISOString(),
    payloadJson: JSON.stringify(payload()),
    signature: "",
    ...overrides,
  });
}

test("genuine synthetic Ed25519 signature and one-use request IDs verify but are NOT real Sentinel evidence", () => {
  const v = verifier();
  const e = makeEnvelope(v);
  const a = v.verify(e);
  assert.equal(a.state, "signature_valid_synthetic_only");
  assert.equal(a.signatureVerified, true);
  assert.equal(a.sourceVerified, false);
  assert.equal(a.readyForExecutiveUse, false);
  assert.deepEqual(a.counts, {
    servicesObserved: 2, up: 1, down: 1, degraded: 0, unknown: 0,
  });
  const serialized = JSON.stringify(a);
  for (const phrase of ["10.0.1.2", "ACME Private", "sensitive@example.invalid", "synthetic"]) {
    assert.ok(!serialized.includes(phrase), phrase);
  }
  assert.equal(v.verify(e).state, "rejected", "same signed response cannot be replayed");
});

test("invalid signature consumes the nonce and cannot be fixed or replayed", () => {
  const v = verifier();
  const valid = makeEnvelope(v);
  assert.equal(v.verify({ ...valid, payloadJson: "{}" }).state, "rejected");
  assert.equal(v.verify(valid).state, "rejected");
});

test("forged organization, key identifier, request ID and alternate signer all rejected", () => {
  for (const [field, value] of [
    ["organizationId", "different_tenant"],
    ["keyId", "unapproved_signer"],
    ["requestId", "e56cdd51-c327-4b77-9c84-2d85b711f566"],
  ] as const) {
    const v = verifier();
    assert.equal(v.verify(makeEnvelope(v, { [field]: value })).state, "rejected", field);
  }
  const wrongKeys = generateKeyPairSync("ed25519");
  const v = verifier();
  const original = makeEnvelope(v);
  const message = SENTINEL_G2_SIGNING_DOMAIN + JSON.stringify([
    original.schemaVersion, original.keyId, original.organizationId, original.requestId,
    original.issuedAt, original.expiresAt, original.payloadJson,
  ]);
  const wrongSignature = sign(null, Buffer.from(message), wrongKeys.privateKey).toString("base64url");
  assert.equal(v.verify({ ...original, signature: wrongSignature }).state, "rejected");
});

test("unsigned extra fields and modified signing domain are forbidden", () => {
  const v = verifier();
  const original = makeEnvelope(v);
  assert.equal(v.verify({ ...original, allowExternalWrites: true }).state, "rejected");
  const another = verifier();
  const unsigned = makeEnvelope(another);
  const invalidSig = sign(null, Buffer.from("OTHER-DOMAIN" + JSON.stringify([
    unsigned.schemaVersion, unsigned.keyId, unsigned.organizationId, unsigned.requestId,
    unsigned.issuedAt, unsigned.expiresAt, unsigned.payloadJson,
  ])), keys.privateKey).toString("base64url");
  assert.equal(another.verify({ ...unsigned, signature: invalidSig }).state, "rejected");
});

test("signed content still must pass strict Mission Control parser; source claim alone never authorizes", () => {
  const v = verifier();
  const bad = { ...payload(), packet: "private-customer-traffic" };
  const envelope = makeEnvelope(v, { payloadJson: JSON.stringify(bad) });
  assert.equal(v.verify(envelope).state, "rejected");
  const v2 = verifier();
  const stale = { ...payload(), lastCheck: "2026-10-10T23:00:00.000Z" };
  assert.equal(v2.verify(makeEnvelope(v2, { payloadJson: JSON.stringify(stale) })).state, "rejected");
  const v3 = verifier();
  const noServices = { ...payload(), services: [] };
  assert.equal(v3.verify(makeEnvelope(v3, { payloadJson: JSON.stringify(noServices) })).state, "rejected");
});

test("expired, future or invalid issuedAt and expiresAt fail closed", () => {
  const examples = [
    { issuedAt: new Date(now - 65_000).toISOString(), expiresAt: new Date(now - 5_000).toISOString() },
    { issuedAt: new Date(now + 100_000).toISOString(), expiresAt: new Date(now + 120_000).toISOString() },
    { issuedAt: new Date(now).toISOString(), expiresAt: new Date(now).toISOString() },
    { issuedAt: new Date(now).toISOString(), expiresAt: new Date(now + 120_000).toISOString() },
    { issuedAt: "2026-02-30T23:00:00.000Z", expiresAt: new Date(now + 30_000).toISOString() },
  ];
  for (const sample of examples) {
    const v = verifier();
    assert.equal(v.verify(makeEnvelope(v, sample)).state, "rejected", JSON.stringify(sample));
  }
});

test("too many outstanding challenges are refused and no public key substitution is possible", () => {
  const v = verifier();
  for (let i=0;i<32;i+=1) v.issueChallenge();
  assert.throws(() => v.issueChallenge(), /Too many pending/);
  const { publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  assert.throws(() => createSyntheticSentinelResponseVerifier({
    keyId: "sentinel-fixture-v1", organizationId: "v79founder",
    publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
  }), /Expected Ed25519/);
});

test("signature-verified status stays owner-review-disabled even for claimed 'live' monitor", () => {
  const v = verifier();
  const live = { ...payload(), monitorMode: "live" };
  const signed = makeEnvelope(v, { payloadJson: JSON.stringify(live) });
  const result = v.verify(signed);
  assert.equal(result.state, "signature_valid_synthetic_only");
  assert.equal(result.readyForExecutiveUse, false);
  assert.equal(result.sourceVerified, false);
});
