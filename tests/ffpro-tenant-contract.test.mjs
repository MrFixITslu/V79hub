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

test("FFPRO provisioning activates exact SMB tenants and keeps finance launches isolated", { timeout: 50000 }, async t => {
  const platformSecret = "platform-test-secret-12345678901234567890";
  const launchSecret = "ffpro-launch-secret-12345678901234567890";
  const provisioned = new Map();

  const ffproServer = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString("utf8");
    const pathname = new URL(req.url, "http://localhost").pathname;

    if (req.method === "POST" && pathname === "/api/platform/provision") {
      const valid = verifyPlatformRequest({
        method: req.method,
        pathname,
        timestamp: String(req.headers["x-v79-timestamp"] || ""),
        signature: String(req.headers["x-v79-signature"] || ""),
        body,
        secret: platformSecret,
      });
      if (req.headers["x-v79-service-id"] !== "v79-hub" || !valid) {
        res.writeHead(401, { "content-type": "application/json" });
        return res.end(JSON.stringify({ error: "bad signature" }));
      }
      const payload = JSON.parse(body);
      const financeUserId = `finance-${payload.organization.id}`;
      provisioned.set(payload.organization.id, { ...payload, financeUserId });
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organization.id,
        ownerHubUserId: payload.user.id,
        financeUserId,
      }));
    }

    if (req.method === "GET" && pathname.startsWith("/api/platform/summary/")) {
      const valid = verifyPlatformRequest({
        method: req.method,
        pathname,
        timestamp: String(req.headers["x-v79-timestamp"] || ""),
        signature: String(req.headers["x-v79-signature"] || ""),
        body: "",
        secret: platformSecret,
      });
      if (req.headers["x-v79-service-id"] !== "v79-hub" || !valid) {
        res.writeHead(401, { "content-type": "application/json" });
        return res.end(JSON.stringify({ error: "bad signature" }));
      }
      const organizationId = decodeURIComponent(pathname.slice("/api/platform/summary/".length));
      if (!provisioned.has(organizationId)) {
        res.writeHead(404, { "content-type": "application/json" });
        return res.end(JSON.stringify({ error: "not provisioned" }));
      }
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        generatedAt: new Date().toISOString(),
        metrics: { transactionCount: 1, organizationMarker: organizationId },
      }));
    }

    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "not found" }));
  });

  await new Promise(resolve => ffproServer.listen(0, "127.0.0.1", resolve));
  const ffproAddress = ffproServer.address();
  const ffproOrigin = `http://127.0.0.1:${ffproAddress.port}`;
  t.after(() => new Promise(resolve => ffproServer.close(resolve)));

  const dir = await mkdtemp(join(tmpdir(), "v79-ffpro-tenant-contract-"));
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
      POS_BASE_URL: dead,
      FFPRO_INTERNAL_URL: ffproOrigin,
      FFPRO_PUBLIC_URL: "https://ffpro.v79sl.com",
      V79_HUB_ADMIN_PASSWORD: "owner-password-123456789",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_PLATFORM_SHARED_SECRET: platformSecret,
      V79_FFPRO_LAUNCH_SECRET: launchSecret,
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
      body: JSON.stringify({ organizationName: name, email, appIds: ["app-ffpro"], expiresInHours: 24 }),
    });
    assert.equal(created.status, 201, await created.clone().text());
    const invite = await created.json();
    const token = new URLSearchParams(new URL(invite.inviteUrl).hash.slice(1)).get("invite");
    const accepted = await request("/api/onboarding/invitation/accept", {
      method: "POST",
      headers: { Origin: origin, "content-type": "application/json", "x-v79-invite-token": token },
      body: JSON.stringify({ fullName: `${name} Owner`, password }),
    });
    assert.equal(accepted.status, 201, await accepted.clone().text());
    const body = await accepted.clone().json();
    return { organization: body.organization, cookie: accepted.headers.get("set-cookie").split(";")[0], email };
  }

  const a = await onboard("Finance A", "a@example.test", "finance-a-password-123");
  const b = await onboard("Finance B", "b@example.test", "finance-b-password-123");
  assert.notEqual(a.organization.id, b.organization.id);

  assert.equal((await request("/api/apps/ffpro/launch", { headers: { Cookie: a.cookie } })).status, 409);
  assert.equal((await request(
    `/api/admin/onboarding/organizations/${a.organization.id}/apps/ffpro/provision`,
    { method: "POST", headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" }, body: "{}" },
  )).status, 403);

  for (const customer of [a, b]) {
    const response = await request(
      `/api/admin/onboarding/organizations/${customer.organization.id}/apps/ffpro/provision`,
      { method: "POST", headers: operatorHeaders, body: "{}" },
    );
    assert.equal(response.status, 200, await response.clone().text());
    const body = await response.json();
    assert.equal(body.mapping.status, "active");
    assert.equal(body.mapping.externalTenantId, customer.organization.id);
    assert.equal(body.mapping.externalOwnerId, `finance-${customer.organization.id}`);
    assert.equal(body.financeUserId, `finance-${customer.organization.id}`);
  }

  assert.equal(provisioned.size, 2);
  assert.notEqual(provisioned.get(a.organization.id).user.id, provisioned.get(b.organization.id).user.id);

  async function launchAndConsume(customer) {
    const launch = await request("/api/apps/ffpro/launch", { headers: { Cookie: customer.cookie } });
    assert.equal(launch.status, 302, await launch.clone().text());
    const location = new URL(launch.headers.get("location"));
    assert.equal(location.origin, "https://ffpro.v79sl.com");
    const ticket = location.searchParams.get("ticket");
    assert.ok(ticket);

    const payload = JSON.stringify({ product: "ffpro", ticket });
    const timestamp = String(Date.now());
    const headers = {
      "content-type": "application/json",
      "x-v79-service-id": "v79-ffpro",
      "x-v79-timestamp": timestamp,
      "x-v79-signature": signPlatformRequest({
        method: "POST",
        pathname: "/api/platform/session/consume",
        timestamp,
        body: payload,
        secret: launchSecret,
      }),
    };
    const consumed = await request("/api/platform/session/consume", { method: "POST", headers, body: payload });
    assert.equal(consumed.status, 200, await consumed.clone().text());
    const result = await consumed.json();
    assert.equal(result.organization.id, customer.organization.id);
    assert.equal(result.user.email, customer.email);
    assert.equal(result.entitlement.product, "ffpro");
    assert.equal((await request("/api/platform/session/consume", { method: "POST", headers, body: payload })).status, 401);
    return result;
  }

  const sessionA = await launchAndConsume(a);
  const sessionB = await launchAndConsume(b);
  assert.notEqual(sessionA.user.id, sessionB.user.id);

  const dashA = await (await request("/api/dashboard/summary", { headers: { Cookie: a.cookie } })).json();
  const dashB = await (await request("/api/dashboard/summary", { headers: { Cookie: b.cookie } })).json();
  assert.equal(dashA.apps.ffpro.status, "ok");
  assert.equal(dashB.apps.ffpro.status, "ok");
  assert.equal(dashA.apps.ffpro.metrics.organizationMarker, a.organization.id);
  assert.equal(dashB.apps.ffpro.metrics.organizationMarker, b.organization.id);
  assert.notEqual(dashA.apps.ffpro.metrics.organizationMarker, dashB.apps.ffpro.metrics.organizationMarker);
});
