import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createSyntheticSignedSentinelGet } from "../../agent-service/src/sentinel-read-request-prototype.ts";
import { createSyntheticSentinelResponseVerifier } from "../../agent-service/src/sentinel-signed-response-prototype.ts";

const fixture = fileURLToPath(new URL("./emit_authenticated_fixture.py", import.meta.url));
const time = Date.parse("2026-10-10T23:40:00.000Z");
const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const privateKeyPem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const publicKeyPem = publicKey.export({ type: "spki", format: "pem" }).toString();
const hmacKey = randomBytes(32);

const verifier = () => createSyntheticSentinelResponseVerifier({
  publicKeyPem, keyId: "sentinel-g2-test", organizationId: "v79founder",
}, () => time);
const rawSnapshot = () => ({
  source: "local-mission-control",
  monitorMode: "staging",
  lastCheck: "2026-10-10T23:39:42Z",
  services: [
    { name: "Private company 172.20.5.8", state: "up", http: 200, latencyMs: 25 },
    { name: "classified internal system", state: "down", http: 503, latencyMs: 900 },
  ],
  qa: { results: [{ name: "bob@example.invalid", state: "fail" }] },
});
function issue(v) {
  return createSyntheticSignedSentinelGet(v.issueChallenge(), hmacKey, time);
}
function send(readRequest) {
  const r = spawnSync("python3", [fixture], {
    input: JSON.stringify({
      privateKeyPem,
      readHmacKey: hmacKey.toString("base64url"),
      readRequest,
      missionSnapshot: rawSnapshot(),
      now: "2026-10-10T23:40:00.000Z",
    }),
    encoding: "utf8", timeout: 6000, maxBuffer: 90_000,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
  });
  assert.equal(r.status, 0, "Offline Python HMAC fixture failed");
  return JSON.parse(r.stdout);
}

test("Node signed GET -> Python scoped authorization and signing -> Node one-use verification", () => {
  const v = verifier();
  const result = send(issue(v));
  assert.equal(result.status, 200);
  const serialized = JSON.stringify(result);
  for (const secret of ["172.20.5.8", "Private company", "bob@example.invalid", "classified"]) {
    assert.ok(!serialized.includes(secret), "Unapproved source field entered transport");
  }
  const approved = v.verify(result.body);
  assert.equal(approved.state, "signature_valid_synthetic_only");
  assert.equal(approved.signatureVerified, true);
  assert.equal(approved.readyForExecutiveUse, false);
  assert.equal(approved.sourceVerified, false);
  assert.equal(approved.counts?.servicesObserved, 2);
  assert.equal(approved.counts?.down, 1);
  assert.equal(v.verify(result.body).state, "rejected", "Node verifier must reject replay");
});

test("Modified organization and unauthorized request MAC cannot fetch or sign anything", () => {
  const v = verifier();
  const original = issue(v);
  const wrongOrg = send({ ...original, headers: {
    ...original.headers, "X-V79-Read-Organization": "other_tenant",
  } });
  assert.equal(wrongOrg.status, 401);
  assert.equal(Object.hasOwn(wrongOrg.body, "payloadJson"), false);
  const tampered = send({ ...original, headers: {
    ...original.headers, "X-V79-Read-Signature": "A".repeat(43),
  } });
  assert.equal(tampered.status, 401);
  assert.equal(Object.hasOwn(tampered.body, "signature"), false);
});

test("Mutating methods and arbitrary query strings cannot reach Python source loader", () => {
  const v = verifier();
  const original = issue(v);
  for (const changed of [
    { ...original, method: "POST" },
    { ...original, path: original.path + "?url=http://evil.invalid" },
    { ...original, path: "/api/v1/incidents/ack" },
  ]) {
    const result = send(changed);
    assert.equal(result.status, 404);
    assert.equal(Object.hasOwn(result.body, "payloadJson"), false);
  }
});

test("Invalid signing input fails before any Python request is made", () => {
  const v = verifier();
  const challenge = v.issueChallenge();
  assert.throws(() => createSyntheticSignedSentinelGet(challenge, Buffer.from("short"), time));
  assert.throws(() => createSyntheticSignedSentinelGet({ ...challenge, keyId: "../evil" }, hmacKey, time));
});
