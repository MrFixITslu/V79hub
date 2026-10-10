import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import net from "node:net";

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

    responsePayload = { ...successfulSnapshot, owner: { email: founder.email, organizationId: "customer-other" } };
    const wrongHub = await request(founder);
    assert.equal(wrongHub.status, 502);
    assert.equal(wrongHub.headers.get("cache-control"), "no-store");
  } finally {
    child.kill("SIGTERM");
    await new Promise<void>(resolve => hub.close(() => resolve()));
  }
});
