import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import net from "node:net";
import { buildEvidenceLedger, compactFromEvidence } from "../src/evidence.js";
import { getWorkforceSpecialist } from "../src/workforce.js";

const founder = {
  userId: "owner-agent-api-test", email: "vision79slu@gmail.com",
  organizationId: "founder-test", organizationName: "V79 Digital",
  ownerAgent: true, hubAdmin: true, allowedSystems: [],
};
const token = "test_only_randomish_service_token_do_not_use_production";
const successfulSnapshot = {
  owner: { email: founder.email, organizationId: founder.organizationId },
  generatedAt: new Date().toISOString(),
  business: { ffpro: {
    status: "ok",
    sourceReportedAt: new Date().toISOString(),
    metrics: { currentMonthIncome: 100, currentMonthExpenses: 120, currentMonthNet: -20, customerEmails: ["private@example.invalid"], apiKey: "never-return-this" },
  } },
  connections: { ffpro: { status: "online" }, pos: { status: "online" } },
  platform: {},
};

async function freePort() {
  const socket = net.createServer();
  socket.listen(0, "127.0.0.1");
  await once(socket, "listening");
  const address = socket.address();
  const port = typeof address === "object" && address ? address.port : 0;
  await new Promise<void>(resolve => socket.close(() => resolve()));
  return port;
}

test("read-only evidence endpoint enforces service token, founder scope and Hub provenance", { timeout: 25000 }, async () => {
  let responsePayload: unknown = successfulSnapshot;
  let mockCalls = 0;
  const hub = createServer((req, res) => {
    mockCalls += 1;
    assert.equal(req.method, "GET");
    assert.equal(req.url, "/internal/agent/snapshot");
    assert.equal(req.headers["x-v79-agent-token"], token);
    assert.equal(req.headers["x-v79-owner-email"], founder.email);
    assert.equal(typeof req.headers["x-v79-organization-id"], "string");
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(responsePayload));
  });
  hub.listen(0, "127.0.0.1");
  await once(hub, "listening");
  const bind = hub.address();
  assert.ok(bind && typeof bind === "object");
  const port = await freePort();
  const child = spawn(process.execPath, ["--import", "tsx", "src/index.ts"], {
    cwd: new URL("../", import.meta.url).pathname,
    env: {
      ...process.env, PORT: String(port), NODE_ENV: "production",
      V79_AGENT_API_TOKEN: token,
      V79_HUB_AGENT_SNAPSHOT_URL: `http://127.0.0.1:${bind.port}/internal/agent/snapshot`,
      V79_AGENT_MODEL_PROVIDER: "openai",
      OPENAI_API_KEY: "test_not_a_real_key",
    },
    stdio: "ignore",
  });
  const base = `http://127.0.0.1:${port}`;
  async function request(context: object, auth: string | null = token, id = "finance", endpoint = "/api/agent/evidence") {
    return fetch(base + endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", ...(auth ? { "x-v79-agent-token": auth } : {}) },
      body: JSON.stringify({ context, specialistId: id }),
      signal: AbortSignal.timeout(3000),
    });
  }
  try {
    let ready = false;
    for (let i = 0; i < 90; i += 1) {
      if (child.exitCode !== null) throw new Error("Agent service terminated during integration test");
      try {
        const status = await fetch(base + "/health", { signal: AbortSignal.timeout(250) });
        if (status.ok) { ready = true; break; }
      } catch { /* service warming */ }
      await new Promise(resolve => setTimeout(resolve, 80));
    }
    assert.ok(ready, "Agent test service did not become ready");

    const prior = mockCalls;
    assert.equal((await request(founder, null)).status, 401);
    assert.equal((await request({ ...founder, ownerAgent: false })).status, 403);
    assert.equal((await request({ ...founder, organizationId: "customer-other" })).status, 502);
    assert.equal((await request(founder, token, "not-a-real-specialist")).status, 400);
    assert.equal(mockCalls, prior + 1, "Only forged owner-with-token request should reach Hub, then fail source scope validation");

    const accepted = await request(founder);
    assert.equal(accepted.status, 200);
    const ledger = await accepted.json();
    assert.equal(ledger.mode, "read-only");
    assert.ok(ledger.records.some((record: {system:string})=>record.system==="ffpro"));
    assert.ok(!JSON.stringify(ledger).includes("never-return-this"));
    assert.ok(!JSON.stringify(ledger).includes("private@example.invalid"));
    assert.ok(!ledger.records.some((record: {system:string})=>record.system==="website"));

    assert.equal((await request(founder, null, "finance", "/api/agent/investigate")).status, 401);
    assert.equal((await request({ ...founder, ownerAgent: false }, token, "finance", "/api/agent/investigate")).status, 403);
    assert.equal((await request(founder, token, "invalid", "/api/agent/investigate")).status, 400);
    const reportResponse = await request(founder, token, "finance", "/api/agent/investigate");
    assert.equal(reportResponse.status, 200);
    const report = await reportResponse.json();
    assert.equal(report.mode, "read-only");
    assert.ok(report.findings.some((f: {id:string}) => f.id === "ffpro:currentMonthNet"));
    assert.ok(report.findings.every((f: {system:string}) => ["ffpro", "pos"].includes(f.system)));
    assert.ok(!JSON.stringify(report).includes("never-return-this"));
    assert.ok(!JSON.stringify(report).includes("private@example.invalid"));
    assert.equal(reportResponse.headers.get("cache-control"), "no-store");

    // G1: actual owner-verified Hub read -> bounded COO-to-CEO briefing.
    const route = "/api/agent/executive-handoff";
    assert.equal((await request(founder, null, "owner", route)).status, 401);
    assert.equal((await request({ ...founder, ownerAgent: false }, token, "owner", route)).status, 403);
    assert.equal((await request({ ...founder, organizationId: "customer-other" }, token, "owner", route)).status, 502);
    const handoffResponse = await request(founder, token, "owner", route);
    assert.equal(handoffResponse.status, 200);
    assert.equal(handoffResponse.headers.get("cache-control"), "no-store");
    const handoff = await handoffResponse.json();
    assert.equal(handoff.mode, "read-only");
    assert.equal(handoff.from, "coo");
    assert.equal(handoff.to, "ceo");
    assert.equal(handoff.ceoReview.priority, "attention");
    assert.ok(handoff.cooReport.findings.some((item: { id: string }) => item.id === "ffpro:currentMonthNet"));
    assert.equal(handoff.ownerApprovalGranted, false);
    assert.equal(handoff.executionEnabled, false);
    assert.ok(!JSON.stringify(handoff).includes("private@example.invalid"));
    assert.ok(!JSON.stringify(handoff).includes("never-return-this"));

    responsePayload = { ...successfulSnapshot, owner: { email: founder.email, organizationId: "customer-other" } };
    const wrongHub = await request(founder);
    assert.equal(wrongHub.status, 502);
    assert.equal(wrongHub.headers.get("cache-control"), "no-store");
  } finally {
    child.kill("SIGTERM");
    await new Promise<void>(resolve => hub.close(() => resolve()));
  }
});


test("G1 owner Hub counters reject future, stale or missing evidence time", () => {
  // Explicit synthetic clock prevents test flakiness and requires NO Hub process.
  const now = Date.parse("2026-10-11T22:00:00.000Z");
  const at = (offsetSeconds: number) => new Date(now + offsetSeconds * 1000).toISOString();
  const ownerSnapshot = (generatedAt: string | null) => ({
    generatedAt,
    business: {},
    platform: {},
    connections: {},
    hubAdmin: { users: 2, activeSessions: 1, customerEmail: "private@example.invalid" },
  });
  function hubRecord(atTime: string | null) {
    const ledger = buildEvidenceLedger(
      ownerSnapshot(atTime), getWorkforceSpecialist("owner"), now);
    const record = ledger.records.find(row => row.system === "hub");
    assert.ok(record, "Hub owner evidence record must remain present");
    return { record, compact: compactFromEvidence(ledger) };
  }
  const current = hubRecord(at(-45));
  assert.equal(current.record.state, "available", "Current owner counters must remain usable");
  assert.equal(current.record.ageSeconds, 45);
  assert.deepEqual(current.record.metrics.map(metric => metric.key).sort(), ["activeSessions", "users"]);
  assert.ok(!JSON.stringify(current.compact).includes("private@example.invalid"));
  const nearFuture = hubRecord(at(90));
  assert.equal(nearFuture.record.state, "available", "Existing two-minute source skew remains allowed");
  assert.equal(nearFuture.record.ageSeconds, 0);
  const farFuture = hubRecord(at(3600));
  assert.equal(farFuture.record.state, "unknown", "Future-dated Hub counts are not current");
  assert.equal(farFuture.record.ageSeconds, null, "Do not show fake age zero for future evidence");
  const stale = hubRecord(at(-901));
  assert.equal(stale.record.state, "unknown", "Hub counters older than 15 minutes are not current");
  const undated = hubRecord(null);
  assert.equal(undated.record.state, "unknown", "Missing owner observation time is not current");
  assert.equal(undated.record.ageSeconds, null);
});

test("G1 product aggregate far-future and undated reports remain non-current", () => {
  const now = Date.parse("2026-10-11T22:00:00.000Z");
  const snapshot = (sourceReportedAt: string | null) => ({
    generatedAt: new Date(now).toISOString(),
    business: { ffpro: {
      status: "ok", sourceReportedAt,
      metrics: { currentMonthNet: -42, customerEmail: "not-model-evidence@example.invalid" },
    } },
    connections: { ffpro: { status: "online" } },
    platform: {},
    hubAdmin: {},
  });
  for (const reportedAt of [new Date(now + 3600_000).toISOString(), null]) {
    const ledger = buildEvidenceLedger(snapshot(reportedAt), getWorkforceSpecialist("owner"), now);
    const ffpro = ledger.records.find(row =>
      row.system === "ffpro" && row.source === "signed_product_summary");
    assert.ok(ffpro);
    assert.equal(ffpro.state, "unknown");
    assert.ok(!JSON.stringify(compactFromEvidence(ledger)).includes("not-model-evidence@example.invalid"));
  }
});
