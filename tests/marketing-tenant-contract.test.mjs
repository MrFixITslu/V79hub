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

test("Marketing provisioning activates exact SMB tenants and keeps marketing launches isolated", { timeout: 50000 }, async t => {
  const platformSecret = "platform-test-secret-12345678901234567890";
  const launchSecret = "marketing-launch-secret-12345678901234567890";
  const provisioned = new Map();
  const teamProvisioned = [];
  const teamDeprovisioned = [];

  const marketingServer = createServer(async (req, res) => {
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
      const businessId = `business-${payload.organization.id}`;
      const userId = `user-${payload.organization.id}`;
      provisioned.set(payload.organization.id, { ...payload, businessId, userId });
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organization.id,
        ownerHubUserId: payload.user.id,
        businessId,
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
      const localRoleByRole = {
        manager: "MARKETING_MANAGER",
        staff: "MARKETING_STAFF",
        viewer: "MARKETING_VIEWER",
      };
      const localRole = localRoleByRole[payload.role];
      if (!localRole || !provisioned.has(payload.organization.id)) {
        res.writeHead(409, { "content-type": "application/json" });
        return res.end(JSON.stringify({ error: "not ready" }));
      }
      const businessId = "business-" + payload.organization.id;
      const userId = "team-" + payload.role + "-" + payload.user.id;
      teamProvisioned.push({ payload, businessId, userId, localRole });
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organization.id,
        hubUserId: payload.user.id,
        businessId,
        userId,
        localRole,
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
      const businessId = "business-" + payload.organizationId;
      teamDeprovisioned.push({ payload, businessId });
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        deprovisioned: true,
        organizationId: payload.organizationId,
        hubUserId: payload.user.id,
        businessId,
        userId: "removed-" + payload.user.id,
        alreadyAbsent: false,
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

  await new Promise(resolve => marketingServer.listen(0, "127.0.0.1", resolve));
  const marketingAddress = marketingServer.address();
  const marketingOrigin = `http://127.0.0.1:${marketingAddress.port}`;
  t.after(() => new Promise(resolve => marketingServer.close(resolve)));

  const dir = await mkdtemp(join(tmpdir(), "v79-marketing-tenant-contract-"));
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
      MARKETING_INTERNAL_URL: marketingOrigin,
      MARKETING_PUBLIC_URL: "https://marketing.v79sl.com",
      V79_HUB_ADMIN_PASSWORD: "owner-password-123456789",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_PLATFORM_SHARED_SECRET: platformSecret,
      V79_MARKETING_LAUNCH_SECRET: launchSecret,
      FFPRO_INTERNAL_URL: dead,
      TIQUET_INTERNAL_URL: dead,
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
      body: JSON.stringify({ organizationName: name, email, appIds: ["app-marketing"], expiresInHours: 24 }),
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
      body: JSON.stringify({ email, role, appIds: ["app-marketing"], expiresInHours: 24 }),
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

  const a = await onboard("Marketing A", "a@example.test", "marketing-a-password-123");
  const b = await onboard("Marketing B", "b@example.test", "marketing-b-password-123");
  assert.notEqual(a.organization.id, b.organization.id);

  assert.equal((await request("/api/apps/marketing/launch", { headers: { Cookie: a.cookie } })).status, 409);
  assert.equal((await request(
    `/api/admin/onboarding/organizations/${a.organization.id}/apps/marketing/provision`,
    { method: "POST", headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" }, body: "{}" },
  )).status, 403);

  for (const customer of [a, b]) {
    const response = await request(
      `/api/admin/onboarding/organizations/${customer.organization.id}/apps/marketing/provision`,
      { method: "POST", headers: operatorHeaders, body: "{}" },
    );
    assert.equal(response.status, 200, await response.clone().text());
    const body = await response.json();
    assert.equal(body.mapping.status, "active");
    assert.equal(body.mapping.externalTenantId, `business-${customer.organization.id}`);
    assert.equal(body.mapping.externalOwnerId, `user-${customer.organization.id}`);
    assert.equal(body.businessId, `business-${customer.organization.id}`);
    assert.equal(body.userId, `user-${customer.organization.id}`);
  }

  assert.equal(provisioned.size, 2);
  assert.notEqual(provisioned.get(a.organization.id).user.id, provisioned.get(b.organization.id).user.id);

  async function launchAndConsume(cookie, expectedOrganizationId, expectedEmail, expectedRole = "owner") {
    const launch = await request("/api/apps/marketing/launch", { headers: { Cookie: cookie } });
    assert.equal(launch.status, 302, await launch.clone().text());
    const location = new URL(launch.headers.get("location"));
    assert.equal(location.origin, "https://marketing.v79sl.com");
    const ticket = location.searchParams.get("ticket");
    assert.ok(ticket);

    const payload = JSON.stringify({ product: "marketing", ticket });
    const timestamp = String(Date.now());
    const headers = {
      "content-type": "application/json",
      "x-v79-service-id": "v79-marketing",
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
    assert.equal(result.entitlement.product, "marketing");
    assert.equal(result.entitlement.access, expectedRole === "owner" ? "owner" : "team");
    assert.equal((await request("/api/platform/session/consume", { method: "POST", headers, body: payload })).status, 401);
    return result;
  }

  const sessionA = await launchAndConsume(a.cookie, a.organization.id, a.email);
  const sessionB = await launchAndConsume(b.cookie, b.organization.id, b.email);
  assert.notEqual(sessionA.user.id, sessionB.user.id);

  const expectedLocalRoles = {
    manager: "MARKETING_MANAGER",
    staff: "MARKETING_STAFF",
    viewer: "MARKETING_VIEWER",
  };
  const membersByRole = {};
  for (const role of ["manager", "staff", "viewer"]) {
    const email = role + ".marketing@example.test";
    const member = await addTeamMember(a, email, role, role + "-marketing-password-12345");
    membersByRole[role] = member;
    assert.equal(member.body.user.workspaceOwner, false);
    assert.equal(member.body.user.platformOperator, false);
    assert.equal(member.body.teamOnboarding.managedProductAccess.marketing, "role_mapped");

    const appsResponse = await request("/api/ecosystem/apps", { headers: { Cookie: member.cookie } });
    assert.equal(appsResponse.status, 200);
    const apps = await appsResponse.json();
    const marketingApp = apps.find(app => app.id === "app-marketing");
    assert.equal(marketingApp.launchReady, true);
    assert.equal(marketingApp.ssoSupported, true);

    const identity = await launchAndConsume(member.cookie, a.organization.id, email, role);
    assert.equal(identity.entitlement.access, "team");
    const provisionCall = teamProvisioned.at(-1);
    assert.equal(provisionCall.payload.organization.id, a.organization.id);
    assert.equal(provisionCall.payload.role, role);
    assert.equal(provisionCall.localRole, expectedLocalRoles[role]);
    assert.equal(provisionCall.businessId, "business-" + a.organization.id);
    assert.equal((await request("/api/apps/ffpro/launch", { headers: { Cookie: member.cookie } })).status, 403);
    assert.equal((await request("/api/admin/platform/overview", { headers: { Cookie: member.cookie } })).status, 403);
  }
  assert.equal(teamProvisioned.length, 3);

  const manager = membersByRole.manager;
  const managerProvision = teamProvisioned.find(entry => entry.payload.user.email === manager.email);
  const managerRoleUpdate = await request(`/api/users/${manager.body.user.id}`, {
    method: "PUT",
    headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ role: "viewer" }),
  });
  assert.equal(managerRoleUpdate.status, 200, await managerRoleUpdate.clone().text());
  const managerDeprovision = teamDeprovisioned.at(-1);
  assert.equal(managerDeprovision.payload.organizationId, a.organization.id);
  assert.equal(managerDeprovision.payload.user.id, managerProvision.payload.user.id);
  assert.equal(managerDeprovision.businessId, "business-" + a.organization.id);

  const managerRelogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: manager.email,
      password: "manager-marketing-password-12345",
      organizationId: a.organization.id,
    }),
  });
  assert.equal(managerRelogin.status, 200, await managerRelogin.clone().text());
  const managerViewerCookie = managerRelogin.headers.get("set-cookie").split(";")[0];
  assert.equal((await managerRelogin.clone().json()).user.role, "viewer");
  await launchAndConsume(managerViewerCookie, a.organization.id, manager.email, "viewer");
  const managerReprovision = teamProvisioned.at(-1);
  assert.equal(managerReprovision.payload.role, "viewer");
  assert.equal(managerReprovision.localRole, "MARKETING_VIEWER");

  const staff = membersByRole.staff;
  const staffProvision = teamProvisioned.find(entry => entry.payload.user.email === staff.email);
  const removeStaffMarketing = await request(`/api/users/${staff.body.user.id}`, {
    method: "PUT",
    headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ appIds: [] }),
  });
  assert.equal(removeStaffMarketing.status, 200, await removeStaffMarketing.clone().text());
  const staffDeprovision = teamDeprovisioned.at(-1);
  assert.equal(staffDeprovision.payload.organizationId, a.organization.id);
  assert.equal(staffDeprovision.payload.user.id, staffProvision.payload.user.id);
  assert.equal((await request("/api/apps/marketing/launch", { headers: { Cookie: staff.cookie } })).status, 401);

  const viewer = membersByRole.viewer;
  const viewerProvision = teamProvisioned.find(entry => entry.payload.user.email === viewer.email);
  const deleteViewer = await request(`/api/users/${viewer.body.user.id}`, {
    method: "DELETE",
    headers: { Cookie: a.cookie, Origin: origin, "content-type": "application/json" },
  });
  assert.equal(deleteViewer.status, 200, await deleteViewer.clone().text());
  const viewerDeprovision = teamDeprovisioned.at(-1);
  assert.equal(viewerDeprovision.payload.organizationId, a.organization.id);
  assert.equal(viewerDeprovision.payload.user.id, viewerProvision.payload.user.id);
  assert.equal((await request("/api/apps/marketing/launch", { headers: { Cookie: viewer.cookie } })).status, 401);
  assert.equal(teamDeprovisioned.length, 3);

  const dashA = await (await request("/api/dashboard/summary", { headers: { Cookie: a.cookie } })).json();
  const dashB = await (await request("/api/dashboard/summary", { headers: { Cookie: b.cookie } })).json();
  assert.equal(dashA.apps.marketing.status, "ok");
  assert.equal(dashB.apps.marketing.status, "ok");
  assert.equal(dashA.apps.marketing.metrics.organizationMarker, a.organization.id);
  assert.equal(dashB.apps.marketing.metrics.organizationMarker, b.organization.id);
  assert.notEqual(dashA.apps.marketing.metrics.organizationMarker, dashB.apps.marketing.metrics.organizationMarker);
});
