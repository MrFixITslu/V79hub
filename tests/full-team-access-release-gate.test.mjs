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

const tiquetPermissions = {
  manager: ["dashboard", "jobs", "clients", "invoices", "files", "new-request"],
  staff: ["dashboard", "jobs", "clients", "files", "new-request"],
  viewer: ["dashboard"],
};
const posRoles = { manager: "MANAGER", staff: "CASHIER", viewer: "AUDITOR" };
const marketingRoles = { manager: "MARKETING_MANAGER", staff: "MARKETING_STAFF", viewer: "MARKETING_VIEWER" };

async function startMock(product, secret, t) {
  const ownerProvisioned = new Map();
  const teamProvisioned = [];
  const teamDeprovisioned = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString("utf8");
    const pathname = new URL(req.url, "http://mock.test").pathname;
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

    const payload = body ? JSON.parse(body) : {};
    res.setHeader("content-type", "application/json");

    if (req.method === "POST" && pathname === "/api/platform/provision") {
      const organizationId = payload.organization.id;
      ownerProvisioned.set(organizationId, payload);
      if (product === "pos") {
        return res.end(JSON.stringify({ provisioned: true, organizationId, ownerUserId: payload.user.id }));
      }
      if (product === "ffpro") {
        return res.end(JSON.stringify({
          provisioned: true,
          organizationId,
          ownerHubUserId: payload.user.id,
          financeUserId: `finance-${organizationId}`,
        }));
      }
      if (product === "tiquet") {
        return res.end(JSON.stringify({
          provisioned: true,
          organizationId,
          ownerHubUserId: payload.user.id,
          accountId: `account-${organizationId}`,
          userId: `tiquet-owner-${organizationId}`,
        }));
      }
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId,
        ownerHubUserId: payload.user.id,
        businessId: `business-${organizationId}`,
        userId: `marketing-owner-${organizationId}`,
      }));
    }

    if (req.method === "POST" && pathname === "/api/platform/members/provision") {
      teamProvisioned.push(payload);
      if (product === "pos") {
        return res.end(JSON.stringify({
          provisioned: true,
          organizationId: payload.organizationId,
          userId: payload.user.id,
          roleKey: posRoles[payload.role],
          locationIds: [`main-${payload.organizationId}`],
        }));
      }
      if (product === "tiquet") {
        return res.end(JSON.stringify({
          provisioned: true,
          organizationId: payload.organization.id,
          hubUserId: payload.user.id,
          accountId: `account-${payload.organization.id}`,
          userId: `tiquet-${payload.user.id}`,
          localRole: "Member",
          permissions: tiquetPermissions[payload.role],
        }));
      }
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organization.id,
        hubUserId: payload.user.id,
        businessId: `business-${payload.organization.id}`,
        userId: `marketing-${payload.user.id}`,
        localRole: marketingRoles[payload.role],
      }));
    }

    if (req.method === "POST" && pathname === "/api/platform/members/deprovision") {
      teamDeprovisioned.push(payload);
      if (product === "pos") {
        return res.end(JSON.stringify({
          deprovisioned: true,
          organizationId: payload.organizationId,
          userId: payload.user.id,
        }));
      }
      if (product === "tiquet") {
        return res.end(JSON.stringify({
          deprovisioned: true,
          organizationId: payload.organizationId,
          hubUserId: payload.user.id,
        }));
      }
      return res.end(JSON.stringify({
        deprovisioned: true,
        organizationId: payload.organizationId,
        hubUserId: payload.user.id,
        businessId: `business-${payload.organizationId}`,
      }));
    }

    if (req.method === "GET" && pathname.startsWith("/api/platform/summary/")) {
      const organizationId = decodeURIComponent(pathname.slice("/api/platform/summary/".length));
      if (!ownerProvisioned.has(organizationId)) {
        res.writeHead(404);
        return res.end(JSON.stringify({ error: "not provisioned" }));
      }
      return res.end(JSON.stringify({
        generatedAt: new Date().toISOString(),
        metrics: { organizationMarker: organizationId, productMarker: product },
      }));
    }

    res.writeHead(404);
    res.end(JSON.stringify({ error: "not found" }));
  });

  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  return {
    origin: `http://127.0.0.1:${server.address().port}`,
    ownerProvisioned,
    teamProvisioned,
    teamDeprovisioned,
  };
}

test("team access release gate provisions, scopes and revokes POS Tiquet and Marketing", { timeout: 70000 }, async t => {
  const platformSecret = "platform-test-secret-12345678901234567890";
  const launchSecrets = {
    ffpro: "ffpro-launch-secret-12345678901234567890",
    tiquet: "tiquet-launch-secret-12345678901234567890",
    marketing: "marketing-launch-secret-12345678901234567890",
  };
  const mocks = {
    pos: await startMock("pos", platformSecret, t),
    ffpro: await startMock("ffpro", platformSecret, t),
    tiquet: await startMock("tiquet", platformSecret, t),
    marketing: await startMock("marketing", platformSecret, t),
  };

  const dir = await mkdtemp(join(tmpdir(), "v79-team-release-gate-"));
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
      V79_HUB_ADMIN_PASSWORD: "owner-password-123456789",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_PLATFORM_SHARED_SECRET: platformSecret,
      POS_BASE_URL: mocks.pos.origin,
      POS_PUBLIC_URL: "https://pos.v79sl.com",
      FFPRO_INTERNAL_URL: mocks.ffpro.origin,
      FFPRO_PUBLIC_URL: "https://ffpro.v79sl.com",
      V79_FFPRO_LAUNCH_SECRET: launchSecrets.ffpro,
      TIQUET_INTERNAL_URL: mocks.tiquet.origin,
      TIQUET_PUBLIC_URL: "https://tiquet.v79sl.com",
      V79_TIQUET_LAUNCH_SECRET: launchSecrets.tiquet,
      MARKETING_INTERNAL_URL: mocks.marketing.origin,
      MARKETING_PUBLIC_URL: "https://marketing.v79sl.com",
      V79_MARKETING_LAUNCH_SECRET: launchSecrets.marketing,
      ACADEMY_INTERNAL_URL: dead,
      LASERTAG_INTERNAL_URL: dead,
      WEBSITE_INTERNAL_URL: dead,
      GAMES_INTERNAL_URL: dead,
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

  const operatorLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "owner-password-123456789" }),
  });
  assert.equal(operatorLogin.status, 200, logs);
  const operatorCookie = operatorLogin.headers.get("set-cookie").split(";")[0];
  const operatorHeaders = { Cookie: operatorCookie, Origin: origin, "content-type": "application/json" };

  const ownerInvite = await request("/api/admin/onboarding/invitations", {
    method: "POST",
    headers: operatorHeaders,
    body: JSON.stringify({
      organizationName: "Team Release Ltd",
      email: "release.owner@example.test",
      appIds: ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"],
      expiresInHours: 24,
    }),
  });
  assert.equal(ownerInvite.status, 201, await ownerInvite.clone().text());
  const ownerInviteBody = await ownerInvite.json();
  const ownerToken = new URLSearchParams(new URL(ownerInviteBody.inviteUrl).hash.slice(1)).get("invite");
  const ownerAccepted = await request("/api/onboarding/invitation/accept", {
    method: "POST",
    headers: { Origin: origin, "content-type": "application/json", "x-v79-invite-token": ownerToken },
    body: JSON.stringify({ fullName: "Release Owner", password: "release-owner-password-12345" }),
  });
  assert.equal(ownerAccepted.status, 201, await ownerAccepted.clone().text());
  const ownerBody = await ownerAccepted.clone().json();
  const ownerCookie = ownerAccepted.headers.get("set-cookie").split(";")[0];
  const organizationId = ownerBody.organization.id;

  for (const product of ["pos", "ffpro", "tiquet", "marketing"]) {
    const provisioned = await request(
      `/api/admin/onboarding/organizations/${organizationId}/apps/${product}/provision`,
      { method: "POST", headers: operatorHeaders, body: "{}" },
    );
    assert.equal(provisioned.status, 200, `${product}: ${await provisioned.clone().text()}`);
  }

  const teamInvite = await request("/api/team/invitations", {
    method: "POST",
    headers: { Cookie: ownerCookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({
      email: "release.manager@example.test",
      role: "manager",
      appIds: ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"],
      expiresInHours: 24,
    }),
  });
  assert.equal(teamInvite.status, 201, await teamInvite.clone().text());
  const teamInviteBody = await teamInvite.json();
  const teamToken = new URLSearchParams(new URL(teamInviteBody.inviteUrl).hash.slice(1)).get("teamInvite");
  const teamAccepted = await request("/api/team-invitation/accept", {
    method: "POST",
    headers: { Origin: origin, "content-type": "application/json", "x-v79-team-invite-token": teamToken },
    body: JSON.stringify({ fullName: "Release Manager", password: "release-manager-password-12345" }),
  });
  assert.equal(teamAccepted.status, 201, await teamAccepted.clone().text());
  const teamBody = await teamAccepted.clone().json();
  const managerCookie = teamAccepted.headers.get("set-cookie").split(";")[0];
  const managerId = teamBody.user.id;
  assert.equal(teamBody.user.platformOperator, false);
  assert.deepEqual(new Set(teamBody.user.appIds), new Set(["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"]));

  const apps = await (await request("/api/ecosystem/apps", { headers: { Cookie: managerCookie } })).json();
  assert.deepEqual(new Set(apps.map(app => app.id)), new Set(["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"]));
  assert.equal((await request("/api/admin/platform/overview", { headers: { Cookie: managerCookie } })).status, 403);

  async function launch(product, cookie) {
    const response = await request(`/api/apps/${product}/launch`, { headers: { Cookie: cookie } });
    assert.equal(response.status, 302, `${product}: ${await response.clone().text()}`);
    const url = new URL(response.headers.get("location"));
    const ticket = product === "pos"
      ? new URLSearchParams(url.hash.slice(1)).get("ticket")
      : url.searchParams.get("ticket");
    assert.ok(ticket);
    const body = JSON.stringify({ product, ticket });
    const timestamp = String(Date.now());
    const serviceId = product === "pos" ? "v79-pos" : `v79-${product}`;
    const secret = product === "pos" ? platformSecret : launchSecrets[product];
    const headers = {
      "content-type": "application/json",
      "x-v79-service-id": serviceId,
      "x-v79-timestamp": timestamp,
      "x-v79-signature": signPlatformRequest({
        method: "POST",
        pathname: "/api/platform/session/consume",
        timestamp,
        body,
        secret,
      }),
    };
    const consumed = await request("/api/platform/session/consume", { method: "POST", headers, body });
    assert.equal(consumed.status, 200, `${product}: ${await consumed.clone().text()}`);
    return consumed.json();
  }

  const posIdentity = await launch("pos", managerCookie);
  assert.equal(posIdentity.tenantId, organizationId);
  const ffproIdentity = await launch("ffpro", managerCookie);
  assert.equal(ffproIdentity.organization.id, organizationId);
  assert.equal(ffproIdentity.role, "manager");
  assert.equal(ffproIdentity.entitlement.access, "team");
  const tiquetIdentity = await launch("tiquet", managerCookie);
  assert.equal(tiquetIdentity.organization.id, organizationId);
  assert.equal(tiquetIdentity.role, "manager");
  assert.equal(tiquetIdentity.entitlement.access, "team");
  const marketingIdentity = await launch("marketing", managerCookie);
  assert.equal(marketingIdentity.organization.id, organizationId);
  assert.equal(marketingIdentity.role, "manager");
  assert.equal(marketingIdentity.entitlement.access, "team");

  assert.equal(mocks.pos.teamProvisioned.at(-1).role, "manager");
  assert.equal(mocks.ffpro.teamProvisioned.length, 0, "FFPRO team identity is provisioned by signed launch consumption, not a duplicate Hub service call");
  assert.equal(mocks.tiquet.teamProvisioned.at(-1).role, "manager");
  assert.equal(mocks.marketing.teamProvisioned.at(-1).role, "manager");

  const removeTwoApps = await request(`/api/users/${managerId}`, {
    method: "PUT",
    headers: { Cookie: ownerCookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ appIds: ["app-v79pos"] }),
  });
  assert.equal(removeTwoApps.status, 200, await removeTwoApps.clone().text());
  assert.equal(mocks.tiquet.teamDeprovisioned.length, 1);
  assert.equal(mocks.marketing.teamDeprovisioned.length, 1);
  assert.equal(mocks.pos.teamDeprovisioned.length, 0);
  assert.equal((await request("/api/apps/pos/launch", { headers: { Cookie: managerCookie } })).status, 401);

  const relogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "release.manager@example.test",
      password: "release-manager-password-12345",
      organizationId,
    }),
  });
  assert.equal(relogin.status, 200);
  let memberCookie = relogin.headers.get("set-cookie").split(";")[0];
  assert.equal((await request("/api/apps/ffpro/launch", { headers: { Cookie: memberCookie } })).status, 403);
  assert.equal((await request("/api/apps/tiquet/launch", { headers: { Cookie: memberCookie } })).status, 403);
  assert.equal((await request("/api/apps/marketing/launch", { headers: { Cookie: memberCookie } })).status, 403);
  await launch("pos", memberCookie);

  const roleChange = await request(`/api/users/${managerId}`, {
    method: "PUT",
    headers: { Cookie: ownerCookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ role: "viewer" }),
  });
  assert.equal(roleChange.status, 200, await roleChange.clone().text());
  assert.equal(mocks.pos.teamDeprovisioned.length, 1);

  const viewerLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "release.manager@example.test",
      password: "release-manager-password-12345",
      organizationId,
    }),
  });
  assert.equal(viewerLogin.status, 200);
  memberCookie = viewerLogin.headers.get("set-cookie").split(";")[0];
  await launch("pos", memberCookie);
  assert.equal(mocks.pos.teamProvisioned.at(-1).role, "viewer");

  const deleted = await request(`/api/users/${managerId}`, {
    method: "DELETE",
    headers: { Cookie: ownerCookie, Origin: origin, "content-type": "application/json" },
  });
  assert.equal(deleted.status, 200, await deleted.clone().text());
  assert.equal(mocks.pos.teamDeprovisioned.length, 2);
  assert.equal((await request("/api/apps/pos/launch", { headers: { Cookie: memberCookie } })).status, 401);

  const ffproOnlyInvite = await request("/api/team/invitations", {
    method: "POST",
    headers: { Cookie: ownerCookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({
      email: "finance.member@example.test",
      role: "viewer",
      appIds: ["app-ffpro"],
      expiresInHours: 24,
    }),
  });
  assert.equal(ffproOnlyInvite.status, 201, await ffproOnlyInvite.clone().text());
  assert.deepEqual((await ffproOnlyInvite.json()).invitation.appIds, ["app-ffpro"]);
});
