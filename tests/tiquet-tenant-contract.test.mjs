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

test("Tiquet provisioning activates exact SMB tenants and keeps ticketing launches isolated", { timeout: 50000 }, async t => {
  const platformSecret = "platform-test-secret-12345678901234567890";
  const launchSecret = "tiquet-launch-secret-12345678901234567890";
  const provisioned = new Map();
  const teamProvisioned = [];
  const teamDeprovisioned = [];

  const tiquetServer = createServer(async (req, res) => {
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
      const accountId = `account-${payload.organization.id}`;
      const userId = `user-${payload.organization.id}`;
      provisioned.set(payload.organization.id, { ...payload, accountId, userId });
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organization.id,
        ownerHubUserId: payload.user.id,
        accountId,
        userId,
      }));
    }

    if (req.method === "POST" && pathname === "/api/platform/members/provision") {
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
      const permissionsByRole = {
        manager: ["dashboard", "jobs", "clients", "invoices", "files", "new-request"],
        staff: ["dashboard", "jobs", "clients", "files", "new-request"],
        viewer: ["dashboard"],
      };
      const permissions = permissionsByRole[payload.role];
      if (!permissions || !provisioned.has(payload.organization.id)) {
        res.writeHead(409, { "content-type": "application/json" });
        return res.end(JSON.stringify({ error: "not ready" }));
      }
      const accountId = `account-${payload.organization.id}`;
      const userId = `team-${payload.role}-${payload.user.id}`;
      teamProvisioned.push({ payload, accountId, userId, permissions });
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organization.id,
        hubUserId: payload.user.id,
        accountId,
        userId,
        localRole: "Member",
        permissions,
      }));
    }

    if (req.method === "POST" && pathname === "/api/platform/members/deprovision") {
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
      teamDeprovisioned.push(payload);
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        deprovisioned: true,
        organizationId: payload.organizationId,
        hubUserId: payload.user.id,
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

  await new Promise(resolve => tiquetServer.listen(0, "127.0.0.1", resolve));
  const tiquetAddress = tiquetServer.address();
  const tiquetOrigin = `http://127.0.0.1:${tiquetAddress.port}`;
  t.after(() => new Promise(resolve => tiquetServer.close(resolve)));

  const dir = await mkdtemp(join(tmpdir(), "v79-tiquet-tenant-contract-"));
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
      TIQUET_INTERNAL_URL: tiquetOrigin,
      TIQUET_PUBLIC_URL: "https://tiquet.v79sl.com",
      V79_HUB_ADMIN_PASSWORD: "owner-password-123456789",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_PLATFORM_SHARED_SECRET: platformSecret,
      V79_TIQUET_LAUNCH_SECRET: launchSecret,
      FFPRO_INTERNAL_URL: dead,
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
      body: JSON.stringify({ organizationName: name, email, appIds: ["app-tiquet"], expiresInHours: 24 }),
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

  async function addTeamMember(owner, email, role, password) {
    const invited = await request("/api/team/invitations", {
      method: "POST",
      headers: { Cookie: owner.cookie, Origin: origin, "content-type": "application/json" },
      body: JSON.stringify({ email, role, appIds: ["app-tiquet"], expiresInHours: 24 }),
    });
    assert.equal(invited.status, 201, await invited.clone().text());
    const invitation = await invited.json();
    const token = new URLSearchParams(new URL(invitation.inviteUrl).hash.slice(1)).get("teamInvite");
    assert.ok(token);
    const accepted = await request("/api/team-invitation/accept", {
      method: "POST",
      headers: { Origin: origin, "content-type": "application/json", "x-v79-team-invite-token": token },
      body: JSON.stringify({ fullName: `${role} User`, password }),
    });
    assert.equal(accepted.status, 201, await accepted.clone().text());
    return {
      cookie: accepted.headers.get("set-cookie").split(";")[0],
      body: await accepted.json(),
      email,
      role,
    };
  }

  const a = await onboard("Tickets A", "a@example.test", "tickets-a-password-123");
  const b = await onboard("Tickets B", "b@example.test", "tickets-b-password-123");
  assert.notEqual(a.organization.id, b.organization.id);

  assert.equal((await request("/api/apps/tiquet/launch", { headers: { Cookie: a.cookie } })).status, 409);
  assert.equal((await request(
    `/api/admin/onboarding/organizations/${a.organization.id}/apps/tiquet/provision`,
    { method: "POST", headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" }, body: "{}" },
  )).status, 403);

  for (const customer of [a, b]) {
    const response = await request(
      `/api/admin/onboarding/organizations/${customer.organization.id}/apps/tiquet/provision`,
      { method: "POST", headers: operatorHeaders, body: "{}" },
    );
    assert.equal(response.status, 200, await response.clone().text());
    const body = await response.json();
    assert.equal(body.mapping.status, "active");
    assert.equal(body.mapping.externalTenantId, `account-${customer.organization.id}`);
    assert.equal(body.mapping.externalOwnerId, `user-${customer.organization.id}`);
    assert.equal(body.accountId, `account-${customer.organization.id}`);
    assert.equal(body.userId, `user-${customer.organization.id}`);
  }

  assert.equal(provisioned.size, 2);
  assert.notEqual(provisioned.get(a.organization.id).user.id, provisioned.get(b.organization.id).user.id);

  async function launchAndConsume(cookie, expectedOrganizationId, expectedEmail, expectedRole = "owner") {
    const launch = await request("/api/apps/tiquet/launch", { headers: { Cookie: cookie } });
    assert.equal(launch.status, 302, await launch.clone().text());
    const location = new URL(launch.headers.get("location"));
    assert.equal(location.origin, "https://tiquet.v79sl.com");
    const ticket = location.searchParams.get("ticket");
    assert.ok(ticket);

    const payload = JSON.stringify({ product: "tiquet", ticket });
    const timestamp = String(Date.now());
    const headers = {
      "content-type": "application/json",
      "x-v79-service-id": "v79-tiquet",
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
    assert.equal(result.organization.id, expectedOrganizationId);
    assert.equal(result.user.email, expectedEmail);
    assert.equal(result.role, expectedRole);
    assert.equal(result.entitlement.product, "tiquet");
    assert.equal(result.entitlement.access, expectedRole === "owner" ? "owner" : "team");
    assert.equal((await request("/api/platform/session/consume", { method: "POST", headers, body: payload })).status, 401);
    return result;
  }

  const sessionA = await launchAndConsume(a.cookie, a.organization.id, a.email);
  const sessionB = await launchAndConsume(b.cookie, b.organization.id, b.email);
  assert.notEqual(sessionA.user.id, sessionB.user.id);

  const expectedPermissions = {
    manager: ["dashboard", "jobs", "clients", "invoices", "files", "new-request"],
    staff: ["dashboard", "jobs", "clients", "files", "new-request"],
    viewer: ["dashboard"],
  };
  const teamMembers = new Map();
  for (const role of ["manager", "staff", "viewer"]) {
    const email = `${role}.tiquet@example.test`;
    const member = await addTeamMember(a, email, role, `${role}-tiquet-password-12345`);
    assert.equal(member.body.user.workspaceOwner, false);
    assert.equal(member.body.user.platformOperator, false);
    assert.equal(member.body.teamOnboarding.managedProductAccess.tiquet, "role_mapped");
    const appsResponse = await request("/api/ecosystem/apps", { headers: { Cookie: member.cookie } });
    assert.equal(appsResponse.status, 200);
    const apps = await appsResponse.json();
    const tiquetApp = apps.find(app => app.id === "app-tiquet");
    assert.equal(tiquetApp.launchReady, true);
    assert.equal(tiquetApp.ssoSupported, true);
    const identity = await launchAndConsume(member.cookie, a.organization.id, email, role);
    assert.equal(identity.entitlement.access, "team");
    const provisionCall = teamProvisioned.at(-1);
    assert.equal(provisionCall.payload.organization.id, a.organization.id);
    assert.equal(provisionCall.payload.role, role);
    assert.deepEqual(provisionCall.permissions, expectedPermissions[role]);
    assert.equal(provisionCall.accountId, `account-${a.organization.id}`);
    assert.equal((await request("/api/apps/ffpro/launch", { headers: { Cookie: member.cookie } })).status, 403);
    assert.equal((await request("/api/apps/marketing/launch", { headers: { Cookie: member.cookie } })).status, 403);
    assert.equal((await request("/api/admin/platform/overview", { headers: { Cookie: member.cookie } })).status, 403);
    teamMembers.set(role, member);
  }
  assert.equal(teamProvisioned.length, 3);

  const managerMember = teamMembers.get("manager");
  const managerRoleSync = await request(`/api/users/${managerMember.body.user.id}`, {
    method: "PUT",
    headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ role: "viewer" }),
  });
  assert.equal(managerRoleSync.status, 200, await managerRoleSync.clone().text());
  assert.equal(teamProvisioned.length, 4);
  assert.equal(teamProvisioned.at(-1).payload.role, "viewer");
  assert.deepEqual(teamProvisioned.at(-1).permissions, expectedPermissions.viewer);

  const managerRemoveTiquet = await request(`/api/users/${managerMember.body.user.id}`, {
    method: "PUT",
    headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ appIds: [] }),
  });
  assert.equal(managerRemoveTiquet.status, 200, await managerRemoveTiquet.clone().text());
  assert.equal(teamDeprovisioned.length, 1);
  assert.equal(teamDeprovisioned[0].organizationId, a.organization.id);

  const managerRelogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "manager.tiquet@example.test",
      password: "manager-tiquet-password-12345",
      organizationId: a.organization.id,
    }),
  });
  assert.equal(managerRelogin.status, 200, await managerRelogin.clone().text());
  const managerFreshCookie = managerRelogin.headers.get("set-cookie").split(";")[0];
  assert.equal((await request("/api/apps/tiquet/launch", { headers: { Cookie: managerFreshCookie } })).status, 403);

  const staffMember = teamMembers.get("staff");
  const deleteStaff = await request(`/api/users/${staffMember.body.user.id}`, {
    method: "DELETE",
    headers: { Cookie: a.cookie, Origin: origin },
  });
  assert.equal(deleteStaff.status, 200, await deleteStaff.clone().text());
  assert.equal(teamDeprovisioned.length, 2);
  assert.equal(teamDeprovisioned[1].organizationId, a.organization.id);

  const dashA = await (await request("/api/dashboard/summary", { headers: { Cookie: a.cookie } })).json();
  const dashB = await (await request("/api/dashboard/summary", { headers: { Cookie: b.cookie } })).json();
  assert.equal(dashA.apps.tiquet.status, "ok");
  assert.equal(dashB.apps.tiquet.status, "ok");
  assert.equal(dashA.apps.tiquet.metrics.organizationMarker, a.organization.id);
  assert.equal(dashB.apps.tiquet.metrics.organizationMarker, b.organization.id);
  assert.notEqual(dashA.apps.tiquet.metrics.organizationMarker, dashB.apps.tiquet.metrics.organizationMarker);
});
