import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createSyntheticSentinelResponseVerifier } from "../../agent-service/src/sentinel-signed-response-prototype.ts";

const fixture = fileURLToPath(new URL("./emit_test_fixture.py", import.meta.url));
const now = Date.parse("2026-10-10T23:40:00.000Z");
const pairs = generateKeyPairSync("ed25519");
const publicKeyPem = pairs.publicKey.export({ type: "spki", format: "pem" }).toString();
const privateKeyPem = pairs.privateKey.export({ type: "pkcs8", format: "pem" }).toString();

const newVerifier = () => createSyntheticSentinelResponseVerifier({
  keyId: "sentinel-g2-test",
  organizationId: "v79founder",
  publicKeyPem,
}, () => now);

function snapshot() {
  return {
    source: "local-mission-control", monitorMode: "staging",
    lastCheck: "2026-10-10T23:39:40Z",
    services: [
      { name: "Private child school 10.44.3.2", state: "up", http: 200, latencyMs: 18 },
      { name: "V79 sample internal", state: "down", http: 503, latencyMs: 150 },
      { name: "secret booking", state: "degraded", http: null, latencyMs: null },
    ],
    qa: {
      results: [{ name: "Customer PII: sample@example.invalid", status: "fail" }],
      counts: { pass: 0, fail: 1 },
    },
  };
}

function runPython(challenge, missionSnapshot = snapshot()) {
  return spawnSync("python3", [fixture], {
    input: JSON.stringify({
      privateKeyPem, challenge, missionSnapshot,
      now: "2026-10-10T23:40:00.000Z",
    }),
    encoding: "utf8", timeout: 6000,
    maxBuffer: 70_000,
    env: {
      ...process.env,
      PYTHONDONTWRITEBYTECODE: "1",
    },
  });
}

test("cross-language: Python signs ONLY local aggregate; Node verifies Ed25519 and consumes nonce", () => {
  const verifier = newVerifier();
  const challenge = verifier.issueChallenge();
  const r = runPython(challenge);
  assert.equal(r.status, 0, "Python offline test source signer failed");
  assert.ok(r.stdout.length < 1500, "Unexpected sensitive or unbounded transport");
  const response = JSON.parse(r.stdout);
  for (const privateValue of ["Private child", "10.44.3.2", "sample@example.invalid", "secret booking"]) {
    assert.ok(!r.stdout.includes(privateValue), `Leaked ${privateValue}`);
  }
  const data = JSON.parse(response.payloadJson);
  assert.equal(data.counts.servicesObserved, 3);
  assert.equal(data.counts.down, 1);
  assert.ok(!Object.hasOwn(data, "services"));
  assert.ok(!Object.hasOwn(data, "qa"));
  const verified = verifier.verify(response);
  assert.equal(verified.state, "signature_valid_synthetic_only");
  assert.equal(verified.signatureVerified, true);
  assert.equal(verified.sourceVerified, false);
  assert.equal(verified.readyForExecutiveUse, false);
  assert.equal(verifier.verify(response).state, "rejected", "Replay must fail");
});

test("cross-language: Python source producer refuses forged organization before signing", () => {
  const v = newVerifier();
  const challenge = { ...v.issueChallenge(), organizationId: "unauthorized" };
  const r = runPython(challenge);
  assert.notEqual(r.status, 0);
  assert.equal(r.stdout, "", "No signed or partial response may be emitted");
});

test("cross-language: unsupported service packet and QA payload never get signed", () => {
  const v = newVerifier();
  const raw = snapshot();
  raw.services[0].packet = "private-raw-data";
  const result = runPython(v.issueChallenge(), raw);
  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, "");
});

test("cross-language: Node rejects modified Python signed response and burns request ID", () => {
  const v = newVerifier();
  const signed = runPython(v.issueChallenge());
  assert.equal(signed.status, 0);
  const e = JSON.parse(signed.stdout);
  assert.equal(v.verify({ ...e, organizationId: "someone_else" }).state, "rejected");
  assert.equal(v.verify(e).state, "rejected");
});
