import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { createSyntheticSentinelResponseVerifier } from "../../agent-service/src/sentinel-signed-response-prototype.ts";
import { createSyntheticSignedSentinelGet, SENTINEL_READ_PATH } from "../../agent-service/src/sentinel-read-request-prototype.ts";

const fixture = fileURLToPath(new URL("./loopback_http_fixture.py", import.meta.url));
const fixedTime = Date.parse("2026-10-10T23:40:00.000Z");
const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const privateKeyPem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const publicKeyPem = publicKey.export({ type: "spki", format: "pem" }).toString();
const hmacKey = randomBytes(32); // ephemeral synthetic fixture only

function syntheticSnapshot(stale = false) {
  return {
    source: "local-mission-control",
    monitorMode: "staging",
    lastCheck: stale ? "2026-10-10T22:40:00Z" : "2026-10-10T23:39:45Z",
    services: [
      { name: "Private test organization 10.0.1.9", state: "up", http: 200, latencyMs: 10 },
      { name: "Childcare private site", state: "down", http: 503, latencyMs: 120 },
    ],
    qa: { results: [{ name: "private@example.invalid", state: "fail" }] },
  };
}

async function startLoopback(stale = false) {
  const child = spawn("python3", ["-B", fixture], {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
  });
  const setup = {
    privateKeyPem, readHmacKey: hmacKey.toString("base64url"),
    now: "2026-10-10T23:40:00.000Z",
    missionSnapshot: syntheticSnapshot(stale),
  };
  // Never send actual credentials or customer data. Only synthetic test keys.
  child.stdin.end(JSON.stringify(setup) + "\n");
  try {
    const port = await new Promise((resolve, reject) => {
      let text = "";
      const timer = setTimeout(() => reject(new Error("Loopback fixture startup timeout")), 5000);
      child.once("error", error => { clearTimeout(timer); reject(error); });
      child.once("exit", () => { clearTimeout(timer); reject(new Error("Loopback fixture stopped early")); });
      child.stdout.on("data", buffer => {
        text += buffer.toString("utf8");
        const firstLine = text.split("\n")[0];
        if (text.includes("\n")) {
          clearTimeout(timer);
          const parsed = Number(firstLine);
          if (!Number.isInteger(parsed) || parsed < 1024 || parsed > 65535) {
            reject(new Error("Invalid loopback fixture port")); return;
          }
          resolve(parsed);
        }
      });
    });
    return {
      child,
      base: `http://127.0.0.1:${port}`,
      stop: () => { child.kill("SIGTERM"); },
    };
  } catch (error) {
    child.kill("SIGTERM");
    throw error;
  }
}

const newVerifier = () => createSyntheticSentinelResponseVerifier({
  publicKeyPem, keyId: "sentinel-g2-test", organizationId: "v79founder",
}, () => fixedTime);

async function send(base, method, path, headers, body) {
  const response = await fetch(base + path, {
    method, headers, ...(body === undefined ? {} : { body }),
    signal: AbortSignal.timeout(3000),
  });
  return {
    status: response.status,
    cache: response.headers.get("cache-control"),
    contentType: response.headers.get("content-type"),
    body: await response.json(),
  };
}

test("isolated loopback HTTP: signed GET -> Python source -> Ed25519 response -> Node verifier", { timeout: 18000 }, async () => {
  const fixture = await startLoopback();
  try {
    const v = newVerifier();
    const req = createSyntheticSignedSentinelGet(v.issueChallenge(), hmacKey, fixedTime);
    const first = await send(fixture.base, req.method, req.path, req.headers);
    assert.equal(first.status, 200);
    assert.equal(first.cache, "no-store");
    assert.equal(first.contentType, "application/json");
    const serialized = JSON.stringify(first.body);
    for (const sensitive of ["10.0.1.9", "Private test organization", "Childcare", "private@example.invalid"]) {
      assert.ok(!serialized.includes(sensitive), "Raw source data crossed the HTTP boundary");
    }
    const verified = v.verify(first.body);
    assert.equal(verified.state, "signature_valid_synthetic_only");
    assert.deepEqual(verified.counts, {
      servicesObserved: 2, up: 1, down: 1, degraded: 0, unknown: 0,
    });
    assert.equal(verified.sourceVerified, false);
    assert.equal(verified.readyForExecutiveUse, false);
    assert.equal(v.verify(first.body).state, "rejected");
    const replay = await send(fixture.base, req.method, req.path, req.headers);
    assert.equal(replay.status, 409, "HTTP request replay must be rejected by Python");
  } finally {
    fixture.stop();
  }
});

test("isolated loopback HTTP: wrong tenant, tampered HMAC, cookies and mutation paths rejected", { timeout: 18000 }, async () => {
  const fixture = await startLoopback();
  try {
    const v = newVerifier();
    const req = createSyntheticSignedSentinelGet(v.issueChallenge(), hmacKey, fixedTime);
    const wrongTenant = await send(fixture.base, req.method, req.path, {
      ...req.headers, "X-V79-Read-Organization": "customer-other",
    });
    assert.equal(wrongTenant.status, 401);
    assert.ok(!Object.hasOwn(wrongTenant.body, "signature"));

    const alteredMac = await send(fixture.base, req.method, req.path, {
      ...req.headers, "X-V79-Read-Signature": "A".repeat(43),
    });
    assert.equal(alteredMac.status, 401);
    const withCookie = await send(fixture.base, req.method, req.path, {
      ...req.headers, Cookie: "session=unsafe",
    });
    assert.equal(withCookie.status, 401);
    const query = await send(fixture.base, req.method, SENTINEL_READ_PATH + "?customer=someone", req.headers);
    assert.equal(query.status, 404);
    const mutation = await send(fixture.base, "POST", "/api/v1/incidents/ack", req.headers);
    assert.equal(mutation.status, 404);
    const postSame = await send(fixture.base, "POST", SENTINEL_READ_PATH, req.headers);
    assert.equal(postSame.status, 404);
    const bodyAttempt = await send(fixture.base, "POST", SENTINEL_READ_PATH, req.headers,
      JSON.stringify({ grant: "admin", ackIncident: true }));
    assert.ok([401, 404].includes(bodyAttempt.status));
    for (const result of [wrongTenant, alteredMac, withCookie, query, mutation, postSame, bodyAttempt]) {
      assert.equal(Object.hasOwn(result.body, "payloadJson"), false);
    }
  } finally {
    fixture.stop();
  }
});

test("isolated loopback HTTP: stale synthetic monitor returns bounded 503 and no signing", { timeout: 18000 }, async () => {
  const fixture = await startLoopback(true);
  try {
    const v = newVerifier();
    const req = createSyntheticSignedSentinelGet(v.issueChallenge(), hmacKey, fixedTime);
    const result = await send(fixture.base, req.method, req.path, req.headers);
    assert.equal(result.status, 503);
    assert.equal(result.body.error, "Read temporarily unavailable");
    assert.equal(Object.hasOwn(result.body, "signature"), false);
  } finally {
    fixture.stop();
  }
});
