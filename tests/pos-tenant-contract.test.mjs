import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { signPlatformRequest, verifyPlatformRequest } from "../server/platform-contract.mjs";

async function freeOrigin() {
  const server = createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return `http://127.0.0.1:${port}`;
}

test("POS customer provisioning activates only the exact Hub tenant and enables tenant-bound launch", { timeout: 45000 }, async t => {
  const secret = "platform-test-secret-12345678901234567890";
  const provisioned = [];

  const posServer = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString("utf8");
    const pathname = new URL(req.url, "http://localhost").pathname;
    const valid = verifyPlatformRequest({
      method: req.method,
      pathname,
      timestamp: String(req.headers["x-v79-timestamp"] || ""),
      signature: String(req.headers["x-v79-signature"] || ""),
      body: req.method === "GET" ? "" : body,
      secret,
    });
    if (req.headers["x-v79-service-id"] !== "v79-hub" || !valid) {
      res.writeHead(401, { "content-type": "application/json" });
      return res.end(JSON.stringify({ error: "bad signature" }));
    }

    if (req.method === "POST" && pathname === "/api/platform/provision") {
      const payload = JSON.parse(body);
      provisioned.push(payload);
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        organizationId: payload.organization.id,
        ownerUserId: payload.user.id,
        provisioned: true,
      }));
    }

    if (req.method === "GET" && pathname.startsWith("/api/platform/summary/")) {
      const organizationId = decodeURIComponent(pathname.slice("/api/platform/summary/".length));
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        organizationId,
        generatedAt: new Date().toISOString(),
        metrics: { products: 22, locations: 1, organizationMarker: organizationId },
      }));
    }

    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "not found" }));
  });
  await new Promise(resolve => posServer.listen(0, "127.0.0.1", resolve));
  const posAddress = posServer.address();
  const posOrigin = `http://127.0.0.1:${posAddress.port}`;
  t.after(() => new Promise(resolve => posServer.close(resolve)));

  const dir = await mkdtemp(join(tmpdir(), "v79-pos-tenant-contract-"));
  const origin = await freeOrigin();
  const dead = "http://127.0.0.1:9";
  const hub = spawn(process.execPath, ["--import", "tsx", "server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      DATA_DIR: dir,
      PORT: new URL(origin).port,
      APP_URL: origin,
      POS_BASE_URL: posOrigin,
      POS_PUBLIC_URL: "https://pos.example.test",
      V79_HUB_ADMIN_PASSWORD: "owner-password-123456789",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_PLATFORM_SHARED_SECRET: secret,
      FFPRO_INTERNAL_URL: dead,
      TIQUET_INTERNAL_URL: dead,
      MARKETING_INTERNAL_URL: dead,
      ACADEMY_INTERNAL_URL: dead,
      LASERTAG_INTERNAL_URL: dead,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let logs = "";
  hub.stdout.on("data", chunk => logs += chunk);
  hub.stderr.on("data", chunk => logs += chunk);
  t.after(async () => {
    if (hub.exitCode === null) {
      const exited = new Promise(resolve => hub.once("exit", resolve));
      hub.kill();
      await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 1500))]);
    }
    await rm(dir, { recursive: true, force: true });
  });

  const request = (path, options = {}) => fetch(origin + path, { redirect: "manual", ...options });
  for (let i = 0; i < 300; i++) {
    try { if ((await request("/api/health")).ok) break; } catch {}
    if (i === 299) assert.fail(logs || "Hub did not start");
    await new Promise(resolve => setTimeout(resolve, 50));
  }

  const login = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "owner-password-123456789" }),
  });
  assert.equal(login.status, 200);
  const operatorCookie = login.headers.get("set-cookie").split(";")[0];
  const operatorHeaders = { Cookie: operatorCookie, Origin: origin, "content-type": "application/json" };

  async function onboard(name, email, password) {
    const created = await request("/api/admin/onboarding/invitations", {
      method: "POST",
      headers: operatorHeaders,
      body: JSON.stringify({ organizationName: name, email, appIds: ["app-v79pos", "app-academy"], expiresInHours: 24 }),
    });
    assert.equal(created.status, 201);
    const invite = await created.json();
    const token = new URLSearchParams(new URL(invite.inviteUrl).hash.slice(1)).get("invite");
    const accepted = await request("/api/onboarding/invitation/accept", {
      method: "POST",
      headers: { Origin: origin, "content-type": "application/json", "x-v79-invite-token": token },
      body: JSON.stringify({ fullName: `${name} Owner`, password }),
    });
    assert.equal(accepted.status, 201, await accepted.clone().text());
    return {
      organization: (await accepted.clone().json()).organization,
      cookie: accepted.headers.get("set-cookie").split(";")[0],
    };
  }

  const a = await onboard("Business A", "a@example.test", "business-a-password-123");
  const b = await onboard("Business B", "b@example.test", "business-b-password-123");
  assert.notEqual(a.organization.id, b.organization.id);

  assert.equal((await request("/api/apps/pos/launch", { headers: { Cookie: a.cookie } })).status, 409);
  assert.equal((await request(
    `/api/admin/onboarding/organizations/${a.organization.id}/apps/pos/provision`,
    { method: "POST", headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" }, body: "{}" },
  )).status, 403);

  for (const customer of [a, b]) {
    const response = await request(
      `/api/admin/onboarding/organizations/${customer.organization.id}/apps/pos/provision`,
      { method: "POST", headers: operatorHeaders, body: "{}" },
    );
    assert.equal(response.status, 200, await response.clone().text());
    const body = await response.json();
    assert.equal(body.mapping.status, "active");
    assert.equal(body.mapping.externalTenantId, customer.organization.id);
  }

  assert.equal(provisioned.length, 2);
  assert.deepEqual(new Set(provisioned.map(row => row.organization.id)), new Set([a.organization.id, b.organization.id]));
  assert.notEqual(provisioned[0].user.id, provisioned[1].user.id);

  async function launchAndConsume(customer) {
    const launch = await request("/api/apps/pos/launch", { headers: { Cookie: customer.cookie } });
    assert.equal(launch.status, 302, await launch.clone().text());
    const location = new URL(launch.headers.get("location"));
    assert.equal(location.origin, "https://pos.example.test");
    const ticket = new URLSearchParams(location.hash.slice(1)).get("ticket");
    assert.ok(ticket);

    const payload = JSON.stringify({ product: "pos", ticket });
    const timestamp = String(Date.now());
    const headers = {
      "content-type": "application/json",
      "x-v79-service-id": "v79-pos",
      "x-v79-timestamp": timestamp,
      "x-v79-signature": signPlatformRequest({
        method: "POST",
        pathname: "/api/platform/session/consume",
        timestamp,
        body: payload,
        secret,
      }),
    };
    const consumed = await request("/api/platform/session/consume", { method: "POST", headers, body: payload });
    assert.equal(consumed.status, 200);
    const result = await consumed.json();
    assert.equal(result.tenantId, customer.organization.id);
    const claims = JSON.parse(Buffer.from(result.token.split(".")[1], "base64url").toString("utf8"));
    assert.equal(claims.tenant_id, customer.organization.id);
    assert.equal((await request("/api/platform/session/consume", { method: "POST", headers, body: payload })).status, 401);
    return claims;
  }

  const claimsA = await launchAndConsume(a);
  const claimsB = await launchAndConsume(b);
  assert.notEqual(claimsA.sub, claimsB.sub);

  const dashA = await (await request("/api/dashboard/summary", { headers: { Cookie: a.cookie } })).json();
  const dashB = await (await request("/api/dashboard/summary", { headers: { Cookie: b.cookie } })).json();
  assert.equal(dashA.apps.pos.status, "ok");
  assert.equal(dashB.apps.pos.status, "ok");
  assert.equal(dashA.apps.pos.metrics.organizationMarker, a.organization.id);
  assert.equal(dashB.apps.pos.metrics.organizationMarker, b.organization.id);
  assert.notEqual(dashA.apps.pos.metrics.organizationMarker, dashB.apps.pos.metrics.organizationMarker);
  assert.equal(dashA.apps.academy.status, "not_configured");
  assert.equal(dashB.apps.academy.status, "not_configured");
  assert.match(dashA.apps.academy.accessMessage, /separate learner account/i);
  assert.equal(dashA.apps.lasertag.status, "not_enabled");
  assert.equal(dashB.apps.lasertag.status, "not_enabled");
  assert.equal(dashA.apps.website.status, "not_enabled");
  assert.equal(dashB.apps.website.status, "not_enabled");
  assert.equal(dashA.apps.games.status, "not_enabled");
  assert.equal(dashB.apps.games.status, "not_enabled");
});
