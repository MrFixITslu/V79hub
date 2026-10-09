import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

async function freeOrigin() {
  const server = createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return `http://127.0.0.1:${port}`;
}

test("Owner Assistant snapshot is service-authenticated and locked to Vision79 owner identity", { timeout: 30000 }, async t => {
  const dir = await mkdtemp(join(tmpdir(), "v79-owner-agent-"));
  const origin = await freeOrigin();
  const agentToken = "agent-test-token-123456789012345678901234";
  const dead = "http://127.0.0.1:9";

  const server = spawn(process.execPath, ["--import", "tsx", "server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      DATA_DIR: dir,
      PORT: new URL(origin).port,
      APP_URL: origin,
      V79_HUB_ADMIN_PASSWORD: "owner-password-123456789",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_PLATFORM_SHARED_SECRET: "platform-test-secret-12345678901234567890",
      V79_AGENT_API_TOKEN: agentToken,
      POS_BASE_URL: dead,
      FFPRO_INTERNAL_URL: dead,
      TIQUET_INTERNAL_URL: dead,
      MARKETING_INTERNAL_URL: dead,
      ACADEMY_INTERNAL_URL: dead,
      LASERTAG_INTERNAL_URL: dead,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let logs = "";
  server.stdout.on("data", chunk => logs += chunk);
  server.stderr.on("data", chunk => logs += chunk);
  t.after(async () => {
    if (server.exitCode === null) {
      const exited = new Promise(resolve => server.once("exit", resolve));
      server.kill();
      await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 1500))]);
    }
    await rm(dir, { recursive: true, force: true });
  });

  const request = (url, options = {}) => fetch(origin + url, { redirect: "manual", ...options });
  let ready = false;
  for (let i = 0; i < 300; i++) {
    try {
      if ((await request("/api/health")).ok) {
        ready = true;
        break;
      }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.equal(ready, true, logs || "Hub test server did not become ready.");

  const login = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "owner-password-123456789" }),
  });
  assert.equal(login.status, 200, logs);
  const identity = await login.json();
  const organizationId = identity.organization.id;
  assert.equal(identity.user.ownerAgent, true);

  // Phase 3: the real Hub owner session records decisions, never executes them.
  assert.equal((await request("/api/agent/proposals")).status, 401);
  const cookie = String(login.headers.get("set-cookie") || "").split(";")[0];
  const draft = {
    operation: "draft_inventory_review", targetSystem: "pos",
    summary: "Review replenishment requirements",
    rationale: "Examine the current POS stock count before preparing a purchase request.",
    evidenceRef: "pos:criticalReplenishmentItems", idempotencyKey: "isolated-owner-ledger-test-0001",
  };
  const headers = { "content-type": "application/json", origin, cookie };
  assert.equal((await request("/api/agent/proposals", {
    method: "POST", headers: { ...headers, origin: "https://invalid.invalid" },
    body: JSON.stringify(draft),
  })).status, 403);
  const created = await request("/api/agent/proposals", {
    method: "POST", headers, body: JSON.stringify(draft),
  });
  assert.equal(created.status, 201);
  const createdBody = await created.json();
  assert.equal(createdBody.executionEnabled, false);
  assert.equal(createdBody.proposal.status, "pending");
  assert.equal((await request("/api/agent/proposals", {
    method: "POST", headers, body: JSON.stringify(draft),
  })).status, 200);
  const approval = await request("/api/agent/proposals/" + createdBody.proposal.id + "/decision", {
    method: "POST", headers, body: JSON.stringify({ decision: "approve", expectedRevision: 1 }),
  });
  assert.equal(approval.status, 200);
  const decision = await approval.json();
  assert.equal(decision.executionEnabled, false);
  assert.equal(decision.proposal.status, "approved");
  assert.equal(decision.proposal.executionStatus, "disabled");
  assert.equal((await request("/api/agent/proposals/" + createdBody.proposal.id + "/decision", {
    method: "POST", headers, body: JSON.stringify({ decision: "approve", expectedRevision: 1 }),
  })).status, 409);
  const proposalsResponse = await request("/api/agent/proposals", { headers: { cookie } });
  assert.equal(proposalsResponse.status, 200);
  const proposals = await proposalsResponse.json();
  assert.equal(proposals.proposals.length, 1);
  assert.equal(proposals.proposals[0].executionStatus, "disabled");

  assert.equal((await request("/internal/agent/snapshot")).status, 403);
  assert.equal((await request("/internal/agent/snapshot", {
    headers: {
      "x-v79-agent-token": agentToken,
      "x-v79-owner-email": "someone@example.com",
      "x-v79-organization-id": organizationId,
    },
  })).status, 403);

  const snapshotResponse = await request("/internal/agent/snapshot", {
    headers: {
      "x-v79-agent-token": agentToken,
      "x-v79-owner-email": "vision79slu@gmail.com",
      "x-v79-organization-id": organizationId,
    },
  });
  assert.equal(snapshotResponse.status, 200, logs);
  const snapshot = await snapshotResponse.json();
  assert.equal(snapshot.owner.email, "vision79slu@gmail.com");
  assert.equal(snapshot.owner.organizationId, organizationId);
  assert.equal(snapshot.hubAdmin.enabledApps.includes("app-lasertag"), true);
  assert.equal(typeof snapshot.hubAdmin.users, "number");
  assert.equal(typeof snapshot.connections.lasertag.status, "string");
  assert.equal(typeof snapshot.business.lasertag.status, "string");
  assert.equal(typeof snapshot.platform.lasertag.status, "string");
});