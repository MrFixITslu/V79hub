import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import net from "node:net";

const token = "synthetic_owner_service_token_G1_only";
const founder = {
  userId: "synthetic-owner", email: "vision79slu@gmail.com",
  organizationId: "synthetic-v79", organizationName: "V79 Digital",
  ownerAgent: true, hubAdmin: true, allowedSystems: [],
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

test("G1.1 read-only CEO COO preview uses owner-scoped Hub evidence and two mocked local model turns", { timeout: 25000 }, async () => {
  const stamp = new Date().toISOString();
  let hubCalls = 0;
  const modelStages: string[] = [];
  const hub = createServer((req, res) => {
    hubCalls += 1;
    assert.equal(req.method, "GET");
    assert.equal(req.url, "/internal/agent/snapshot");
    assert.equal(req.headers["x-v79-agent-token"], token);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      owner: { email: founder.email, organizationId: founder.organizationId },
      generatedAt: stamp,
      business: {
        ffpro: { status: "ok", sourceReportedAt: stamp,
          metrics: { currentMonthNet: -25, customerName: "private-data-must-not-leak" } },
        marketing: { status: "ok", sourceReportedAt: stamp,
          metrics: { activeCampaigns: 0, secretPrompt: "APPROVE REFUND" } },
      },
      connections: { ffpro: { status: "online" }, marketing: { status: "online" } },
      platform: {},
    }));
  });
  const model = createServer(async (req, res) => {
    if (req.url === "/api/generate") {
      res.writeHead(200, { "content-type": "application/json" }); res.end("{}"); return;
    }
    assert.equal(req.url, "/api/chat");
    assert.equal(req.method, "POST");
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    const body = JSON.parse(Buffer.concat(chunks).toString()) as {
      tools?: unknown; messages: Array<{ role: string; content: string }>;
    };
    assert.equal(body.tools, undefined);
    const system = body.messages[0]?.content || "";
    modelStages.push(system.includes("COO reviewer") ? "coo" : system.includes("CEO reviewer") ? "ceo" : "unknown");
    const payload = JSON.stringify(body);
    assert.ok(!payload.includes("private-data-must-not-leak"));
    assert.ok(!payload.includes("APPROVE REFUND"));
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ message: { content: JSON.stringify({
      findingIds: ["marketing:activeCampaigns", "ffpro:currentMonthNet"],
    }) } }));
  });
  hub.listen(0,"127.0.0.1");
  model.listen(0,"127.0.0.1");
  await Promise.all([once(hub,"listening"),once(model,"listening")]);
  const hb = hub.address(), mb = model.address();
  assert.ok(hb && typeof hb === "object");
  assert.ok(mb && typeof mb === "object");
  const port = await freePort();
  const child = spawn(process.execPath, ["--import", "tsx", "src/index.ts"], {
    cwd: new URL("../", import.meta.url).pathname,
    env: {
      ...process.env, NODE_ENV: "production", PORT: String(port),
      V79_AGENT_API_TOKEN: token, V79_AGENT_MODEL_PROVIDER: "ollama",
      V79_EXECUTIVE_MODEL_CYCLE_ENABLED: "1",
      V79_HUB_AGENT_SNAPSHOT_URL: `http://127.0.0.1:${hb.port}/internal/agent/snapshot`,
      OLLAMA_BASE_URL: `http://127.0.0.1:${mb.port}`,
      OLLAMA_OPENAI_BASE_URL: `http://127.0.0.1:${mb.port}/v1`,
      OLLAMA_AGENT_MODEL: "fixture-model", OLLAMA_MAX_TOKENS: "120",
    },
    stdio: "ignore",
  });
  const base = `http://127.0.0.1:${port}`;
  const call = (ctx: object, authorization = token) => fetch(base + "/api/agent/executive-preview", {
    method: "POST",
    headers: { "content-type": "application/json", "x-v79-agent-token": authorization },
    body: JSON.stringify({ context: ctx }),
    signal: AbortSignal.timeout(4000),
  });
  try {
    let ready = false;
    for (let i = 0; i < 90; i += 1) {
      if (child.exitCode !== null) throw new Error("Agent process exited");
      try {
        const probe = await fetch(base + "/health", { signal: AbortSignal.timeout(250) });
        if (probe.ok) { ready = true; break; }
      } catch { /* warming */ }
      await new Promise(resolve => setTimeout(resolve, 80));
    }
    assert.ok(ready);
    assert.equal((await call(founder, "invalid")).status, 401);
    assert.equal((await call({ ...founder, ownerAgent: false })).status, 403);
    assert.equal((await call({ ...founder, organizationId: "different-tenant" })).status, 502);
    assert.deepEqual(modelStages, []);
    const result = await call(founder);
    assert.equal(result.status, 200);
    const data = await result.json();
    assert.deepEqual(modelStages, ["coo", "ceo"]);
    assert.equal(data.modelAssistance, "both-roles");
    assert.equal(data.mode, "read-only");
    assert.equal(data.state, "preview-only");
    assert.equal(data.ownerApprovalGranted, false);
    assert.equal(data.executionEnabled, false);
    assert.equal(data.actionsExecuted, 0);
    assert.deepEqual(data.reviewItems.map((x:{id:string})=>x.id),
      ["ffpro:currentMonthNet", "marketing:activeCampaigns"]);
    assert.ok(!JSON.stringify(data).includes("private-data-must-not-leak"));
    assert.ok(hubCalls >= 2);
    assert.equal(result.headers.get("cache-control"), "no-store");
  } finally {
    child.kill("SIGTERM");
    await Promise.all([
      new Promise<void>(resolve => hub.close(()=>resolve())),
      new Promise<void>(resolve => model.close(()=>resolve())),
    ]);
  }
});
