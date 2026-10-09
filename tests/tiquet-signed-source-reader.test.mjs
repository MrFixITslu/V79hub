import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, sign as signEd25519 } from "node:crypto";
import { readSignedTiquetMetrics } from "../server/tiquet-signed-source-reader.mjs";
import { canonicalSourceMetricPayload } from "../server/source-metric-signature.mjs";
import { signPlatformRequest } from "../server/platform-contract.mjs";

const pair = generateKeyPairSync("ed25519");
const unrelated = generateKeyPairSync("ed25519");
const publicKey = pair.publicKey.export({ format: "pem", type: "spki" });
const organizationId = "synthetic-owner-org";
const requestId = "01234567-89ab-4cde-8000-0123456789ab";
const frozen = new Date("2026-10-09T12:00:00.000Z");
const platformSecret = "synthetic-platform-signing-key-0123456789012345";
const initialMetrics = [
  { key: "clients", value: 3 }, { key: "jobs", value: 4 },
  { key: "teamMembers", value: 2 }, { key: "unreadNotifications", value: 0 },
  { key: "jobValueTotal", value: 1250 },
];

function signedEnvelope(changes = {}, secretKey = pair.privateKey) {
  const payload = {
    schema: "v79-source-metrics-v1", source: "tiquet",
    organizationId, requestId,
    observedAt: "2026-10-09T11:59:30.000Z",
    expiresAt: "2026-10-09T12:01:00.000Z",
    metrics: initialMetrics, ...changes,
  };
  const canonical = canonicalSourceMetricPayload(payload);
  if (!canonical) throw Error("Synthetic payload does not meet strict source contract.");
  return {
    payload,
    signature: signEd25519(null, Buffer.from(canonical), secretKey).toString("base64url"),
  };
}

const config = {
  enabled: true, organizationId, publicKey, platformSecret,
  baseUrl: "http://synthetic-tiquet.internal:3050",
  signPlatformRequest,
  uuid: () => requestId,
  now: () => frozen,
};

function fetcherFor(value, capture) {
  return async (url, options) => {
    capture?.push({ url, options });
    return new Response(JSON.stringify(value), {
      status: 200, headers: { "content-type": "application/json" },
    });
  };
}

test("verified Tiquet signature exposes only fresh bounded numerical evidence", async () => {
  const calls = [];
  const answer = await readSignedTiquetMetrics({
    ...config, fetcher: fetcherFor(signedEnvelope(), calls),
  });
  assert.deepEqual(answer, {
    status: "available", source: "tiquet", provenance: "source_signed",
    observedAt: "2026-10-09T11:59:30.000Z",
    expiresAt: "2026-10-09T12:01:00.000Z",
    metrics: [...initialMetrics].sort((a,b)=>a.key.localeCompare(b.key)),
    executionEnabled: false,
  });
  assert.equal("organizationId" in answer, false);
  assert.equal("requestId" in answer, false);
  assert.equal("signature" in answer, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url.pathname,
    `/api/platform/agent/signed-metrics/${organizationId}/${requestId}`);
  assert.equal(calls[0].options.method,"GET");
  assert.equal(calls[0].options.redirect,"manual");
  const sent = calls[0].options.headers;
  assert.equal(sent["x-v79-service-id"],"v79-hub");
  assert.equal(sent["x-v79-signature"],signPlatformRequest({
    method:"GET", pathname:calls[0].url.pathname, timestamp:sent["x-v79-timestamp"],
    body:"", secret:platformSecret,
  }));
});

test("disabled or unconfigured signed sources fail closed without any network request", async () => {
  let requests = 0;
  const fetcher = async () => { requests++; throw Error("Network request should not happen"); };
  for (const changes of [
    { enabled:false }, { publicKey:"" }, { platformSecret:"short" },
    { organizationId:"../../other-org" }, { signPlatformRequest:null },
    { baseUrl:"file:///etc/passwd" }, { uuid:()=> "not-a-uuid" },
  ]) {
    const result = await readSignedTiquetMetrics({ ...config, fetcher, ...changes });
    assert.deepEqual(result, { status:"unavailable", source:"tiquet", executionEnabled:false });
  }
  assert.equal(requests,0);
});

test("forged signatures, wrong tenant, wrong nonce, foreign keys and stale snapshots stay unavailable", async () => {
  const valid = signedEnvelope();
  const badCases = [
    { ...valid, signature:"forged" },
    signedEnvelope({ organizationId:"other-tenant" }),
    signedEnvelope({ requestId:"12345678-89ab-4cde-8000-0123456789ab" }),
    signedEnvelope({ observedAt:"2026-10-09T11:52:00.000Z", expiresAt:"2026-10-09T11:53:00.000Z" }),
    signedEnvelope({ expiresAt:"2026-10-09T11:59:59.000Z" }),
    signedEnvelope({ metrics: [{ key:"clients",value:9 }] }),
    signedEnvelope({}, unrelated.privateKey),
    { ...valid, payload:{...valid.payload, metrics:[{key:"clients",value:999}]} },
    { ...valid, extra:"unexpected metadata" },
  ];
  for (const candidate of badCases) {
    const result = await readSignedTiquetMetrics({
      ...config, fetcher: fetcherFor(candidate),
    });
    assert.equal(result.status,"unavailable");
    assert.equal(result.executionEnabled,false);
    assert.equal("metrics" in result,false);
  }
});

test("bad upstream status, redirects, non-JSON, oversized text and exceptions never become zero-valued metrics", async () => {
  const valid = signedEnvelope();
  const responses = [
    new Response(JSON.stringify(valid),{status:503,headers:{"content-type":"application/json"}}),
    new Response("",{status:302,headers:{location:"https://evil.invalid"}}),
    new Response("<html>bad</html>",{status:200,headers:{"content-type":"text/html"}}),
    new Response("x".repeat(9000),{status:200,headers:{"content-type":"application/json"}}),
    new Response("{broken",{status:200,headers:{"content-type":"application/json"}}),
  ];
  for (const response of responses) {
    const result=await readSignedTiquetMetrics({ ...config, fetcher:async()=>response });
    assert.deepEqual(result,{status:"unavailable",source:"tiquet",executionEnabled:false});
  }
  const errored = await readSignedTiquetMetrics({
    ...config, fetcher:async()=>{ throw Error("synthetic network down"); },
  });
  assert.equal(errored.status,"unavailable");
});

test("signed Tiquet data that expires during an HTTP response is not delivered as verified", async () => {
  let observedClock = 0;
  const fetcher = async () => new Response(JSON.stringify(signedEnvelope()), {
    status:200, headers:{"content-type":"application/json"},
  });
  const result = await readSignedTiquetMetrics({
    ...config,
    now: () => {
      observedClock++;
      return observedClock === 1 ? frozen : new Date("2026-10-09T12:01:01.000Z");
    },
    fetcher,
  });
  assert.equal(observedClock, 2, "check the clock again after receiving source data");
  assert.deepEqual(result,{status:"unavailable",source:"tiquet",executionEnabled:false});
});
