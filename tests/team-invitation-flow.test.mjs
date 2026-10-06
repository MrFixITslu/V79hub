import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
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

test("workspace team invitations stay owner-controlled and isolated across SMBs", { timeout: 50000 }, async t => {
  const dir = await mkdtemp(join(tmpdir(), "v79-team-invite-flow-"));
  const origin = await freeOrigin();
  const dead = "http://127.0.0.1:9";
  const platformSecret = "platform-test-secret-12345678901234567890";
  const posProvisioning = [];
  const posDeprovisioning = [];

  const posServer = createServer(async (req, res) => {
    let body = "";
    for await (const chunk of req) body += chunk;
    const pathname = new URL(req.url, "http://pos.test").pathname;
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

    const payload = body ? JSON.parse(body) : {};
    res.setHeader("content-type", "application/json");
    if (req.method === "POST" && pathname === "/api/platform/provision") {
      posProvisioning.push({ type: "owner", payload });
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organization.id,
        ownerUserId: payload.user.id,
      }));
    }
    if (req.method === "POST" && pathname === "/api/platform/members/provision") {
      const roleKey = { manager: "MANAGER", staff: "CASHIER", viewer: "AUDITOR" }[payload.role];
      if (!roleKey) {
        res.writeHead(400);
        return res.end(JSON.stringify({ error: "invalid role" }));
      }
      posProvisioning.push({ type: "team", payload, roleKey });
      return res.end(JSON.stringify({
        provisioned: true,
        organizationId: payload.organizationId,
        userId: payload.user.id,
        roleKey,
        locationIds: [`main-${payload.organizationId}`],
      }));
    }
    if (req.method === "POST" && pathname === "/api/platform/members/deprovision") {
      posDeprovisioning.push(payload);
      return res.end(JSON.stringify({
        deprovisioned: true,
        organizationId: payload.organizationId,
        userId: payload.user.id,
      }));
    }
    res.writeHead(404);
    res.end(JSON.stringify({ error: "not found" }));
  });
  await new Promise(resolve => posServer.listen(0, "127.0.0.1", resolve));
  const posOrigin = `http://127.0.0.1:${posServer.address().port}`;

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
      POS_BASE_URL: posOrigin,
      POS_PUBLIC_URL: "https://pos.v79sl.com",
      FFPRO_INTERNAL_URL: dead,
      TIQUET_INTERNAL_URL: dead,
      MARKETING_INTERNAL_URL: dead,
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
    posServer.closeAllConnections();
    await new Promise(resolve => posServer.close(resolve));
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

  const tokenFromUrl = (url, key) => new URLSearchParams(new URL(url).hash.replace(/^#/, "")).get(key);
  const inviteHeaders = (token, header) => ({
    Origin: origin,
    "content-type": "application/json",
    [header]: token,
  });

  async function createOwner(organizationName, email, password) {
    const created = await request("/api/admin/onboarding/invitations", {
      method: "POST",
      headers: operatorHeaders,
      body: JSON.stringify({ organizationName, email, appIds: ["app-v79pos", "app-tiquet", "app-marketing"], expiresInHours: 24 }),
    });
    assert.equal(created.status, 201, await created.clone().text());
    const payload = await created.json();
    const token = tokenFromUrl(payload.inviteUrl, "invite");
    assert.ok(token);
    const accepted = await request("/api/onboarding/invitation/accept", {
      method: "POST",
      headers: inviteHeaders(token, "x-v79-invite-token"),
      body: JSON.stringify({ fullName: organizationName + " Owner", password }),
    });
    assert.equal(accepted.status, 201, await accepted.clone().text());
    return {
      body: await accepted.json(),
      cookie: accepted.headers.get("set-cookie").split(";")[0],
    };
  }

  async function provisionPosForOwner(owner) {
    const response = await request(
      `/api/admin/onboarding/organizations/${owner.body.organization.id}/apps/pos/provision`,
      {
        method: "POST",
        headers: operatorHeaders,
        body: "{}",
      },
    );
    assert.equal(response.status, 200, await response.clone().text());
    const body = await response.json();
    assert.equal(body.mapping.status, "active");
    assert.equal(body.mapping.externalTenantId, owner.body.organization.id);
  }

  async function createTeamInvite(cookie, email, role, appIds = ["app-v79pos"]) {
    const response = await request("/api/team/invitations", {
      method: "POST",
      headers: { Cookie: cookie, Origin: origin, "content-type": "application/json" },
      body: JSON.stringify({ email, role, appIds, expiresInHours: 24 }),
    });
    const body = await response.clone().json().catch(() => ({}));
    return { response, body, token: body.inviteUrl ? tokenFromUrl(body.inviteUrl, "teamInvite") : null };
  }

  async function acceptTeamInvite(token, fullName, password) {
    return request("/api/team-invitation/accept", {
      method: "POST",
      headers: inviteHeaders(token, "x-v79-team-invite-token"),
      body: JSON.stringify({ fullName, password }),
    });
  }

  async function launchAndConsumePos(cookie, expectedOrganizationId) {
    const launch = await request("/api/apps/pos/launch", { headers: { Cookie: cookie } });
    assert.equal(launch.status, 302, await launch.clone().text());
    const location = new URL(launch.headers.get("location"));
    assert.equal(location.origin, "https://pos.v79sl.com");
    const ticket = new URLSearchParams(location.hash.replace(/^#/, "")).get("ticket");
    assert.ok(ticket);

    const body = JSON.stringify({ product: "pos", ticket });
    const timestamp = String(Date.now());
    const headers = {
      "content-type": "application/json",
      "x-v79-service-id": "v79-pos",
      "x-v79-timestamp": timestamp,
      "x-v79-signature": signPlatformRequest({
        method: "POST",
        pathname: "/api/platform/session/consume",
        timestamp,
        body,
        secret: platformSecret,
      }),
    };
    const consumed = await request("/api/platform/session/consume", { method: "POST", headers, body });
    assert.equal(consumed.status, 200, await consumed.clone().text());
    const identity = await consumed.json();
    assert.equal(identity.tenantId, expectedOrganizationId);
    assert.equal(typeof identity.token, "string");
    assert.equal((await request("/api/platform/session/consume", { method: "POST", headers, body })).status, 401);
    return identity;
  }

  const firstOwner = await createOwner("Alpha Services Ltd", "alpha.owner@example.test", "alpha-owner-password-12345");
  const firstOrgId = firstOwner.body.organization.id;
  assert.equal(firstOwner.body.user.workspaceOwner, true);
  assert.equal(firstOwner.body.user.platformOperator, false);
  await provisionPosForOwner(firstOwner);

  assert.equal((await request("/api/users", {
    method: "POST",
    headers: { Cookie: firstOwner.cookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ username: "bypass", password: "password-12345", role: "staff" }),
  })).status, 403, "customer members must be created through invitations");

  const badRole = await createTeamInvite(firstOwner.cookie, "bad-admin@example.test", "admin");
  assert.equal(badRole.response.status, 400, "customer owners cannot delegate admin");
  const badFinanceAccess = await createTeamInvite(firstOwner.cookie, "bad-finance@example.test", "staff", ["app-ffpro"]);
  assert.equal(badFinanceAccess.response.status, 400, "FFPRO must remain owner-only");

  const managerInvite = await createTeamInvite(firstOwner.cookie, "shared.member@example.test", "manager");
  assert.equal(managerInvite.response.status, 201);
  assert.ok(managerInvite.token);

  const diskAfterManagerInvite = await readFile(join(dir, "v79_store.json"), "utf8");
  assert.equal(diskAfterManagerInvite.includes(managerInvite.token), false, "raw team token must never be persisted");

  const metadata = await request("/api/team-invitation", {
    headers: { "x-v79-team-invite-token": managerInvite.token },
  });
  assert.equal(metadata.status, 200);
  const metadataBody = await metadata.json();
  assert.equal(metadataBody.organizationName, "Alpha Services Ltd");
  assert.notEqual(metadataBody.email, "shared.member@example.test");
  assert.equal(metadataBody.role, "manager");
  assert.deepEqual(metadataBody.appIds, ["app-v79pos"]);

  const managerAccepted = await acceptTeamInvite(
    managerInvite.token,
    "Shared Team Member",
    "shared-team-password-12345",
  );
  assert.equal(managerAccepted.status, 201, await managerAccepted.clone().text());
  const managerCookie = managerAccepted.headers.get("set-cookie").split(";")[0];
  const managerBody = await managerAccepted.json();
  assert.equal(managerBody.user.role, "manager");
  assert.equal(managerBody.user.workspaceOwner, false);
  assert.equal(managerBody.user.platformOperator, false);
  assert.deepEqual(managerBody.user.appIds, ["app-v79pos"]);
  assert.deepEqual(managerBody.teamOnboarding.appIds, ["app-v79pos"]);
  assert.deepEqual(managerBody.teamOnboarding.managedProductAccess, {
    pos: "role_mapped",
    ffpro: "owner_only",
    tiquet: "role_mapped",
    marketing: "role_mapped",
  });
  assert.deepEqual(
    new Set(managerBody.user.permissions),
    new Set(["overview", "connections", "team", "security", "billing"]),
  );

  const managerUsers = await request("/api/users", { headers: { Cookie: managerCookie } });
  assert.equal(managerUsers.status, 200, "manager can review own workspace roster");
  const managerRoster = await managerUsers.json();
  assert.equal(managerRoster.length, 2);
  assert.equal(managerRoster.some(user => user.username === "alpha.owner@example.test"), true);
  assert.equal(managerRoster.some(user => user.username === "shared.member@example.test"), true);
  const managerApps = await (await request("/api/ecosystem/apps", { headers: { Cookie: managerCookie } })).json();
  assert.deepEqual(managerApps.map(app => app.id), ["app-v79pos"]);
  const managerPosApp = managerApps.find(app => app.id === "app-v79pos");
  assert.equal(managerPosApp.launchReady, true);
  assert.equal(managerPosApp.ssoSupported, true);
  assert.equal((await request("/api/apps/tiquet/launch", { headers: { Cookie: managerCookie } })).status, 403);
  assert.equal((await request("/api/apps/marketing/launch", { headers: { Cookie: managerCookie } })).status, 403);
  const managerDashboard = await request("/api/dashboard/summary", { headers: { Cookie: managerCookie } });
  assert.equal(managerDashboard.status, 200);
  const managerDashboardBody = await managerDashboard.json();
  assert.equal(managerDashboardBody.apps.pos.status, "restricted");
  assert.equal(managerDashboardBody.apps.ffpro.status, "not_enabled");
  assert.equal(managerDashboardBody.apps.tiquet.status, "restricted");
  assert.equal(managerDashboardBody.apps.marketing.status, "restricted");
  for (const product of ["pos", "ffpro", "tiquet", "marketing"]) {
    assert.deepEqual(managerDashboardBody.apps[product].metrics, {});
  }

  assert.equal((await createTeamInvite(managerCookie, "nope@example.test", "staff")).response.status, 403);
  assert.equal((await request("/api/users/" + firstOwner.body.user.id, {
    method: "PUT",
    headers: { Cookie: managerCookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ role: "viewer" }),
  })).status, 403);
  await launchAndConsumePos(managerCookie, firstOrgId);
  const managerPosProvision = posProvisioning.at(-1);
  assert.equal(managerPosProvision.type, "team");
  assert.equal(managerPosProvision.payload.organizationId, firstOrgId);
  assert.equal(managerPosProvision.payload.role, "manager");
  assert.equal(managerPosProvision.roleKey, "MANAGER");
  assert.equal((await request("/api/apps/ffpro/launch", { headers: { Cookie: managerCookie } })).status, 403);
  assert.equal((await request("/api/admin/platform/overview", { headers: { Cookie: managerCookie } })).status, 403);

  const staffInvite = await createTeamInvite(firstOwner.cookie, "staff.member@example.test", "staff");
  assert.equal(staffInvite.response.status, 201);
  const staffAccepted = await acceptTeamInvite(staffInvite.token, "Staff Member", "staff-team-password-12345");
  assert.equal(staffAccepted.status, 201);
  const staffCookie = staffAccepted.headers.get("set-cookie").split(";")[0];
  const staffBody = await staffAccepted.json();
  assert.deepEqual(new Set(staffBody.user.permissions), new Set(["overview", "connections"]));
  assert.equal((await request("/api/users", { headers: { Cookie: staffCookie } })).status, 403);
  assert.equal((await request("/api/team/invitations", { headers: { Cookie: staffCookie } })).status, 403);
  await launchAndConsumePos(staffCookie, firstOrgId);
  const staffPosProvision = posProvisioning.at(-1);
  assert.equal(staffPosProvision.payload.role, "staff");
  assert.equal(staffPosProvision.roleKey, "CASHIER");
  const staffConnections = await request("/api/connections/status", { headers: { Cookie: staffCookie } });
  assert.equal(staffConnections.status, 200);
  assert.deepEqual(Object.keys((await staffConnections.json()).apps), ["pos"]);

  const deleteStaff = await request(`/api/users/${staffBody.user.id}`, {
    method: "DELETE",
    headers: { Cookie: firstOwner.cookie, Origin: origin, "content-type": "application/json" },
  });
  assert.equal(deleteStaff.status, 200, await deleteStaff.clone().text());
  const staffDeleteDeprovision = posDeprovisioning.at(-1);
  assert.equal(staffDeleteDeprovision.organizationId, firstOrgId);
  assert.equal(staffDeleteDeprovision.user.id, staffPosProvision.payload.user.id);
  assert.equal((await request("/api/apps/pos/launch", { headers: { Cookie: staffCookie } })).status, 401);

  const revokeInvite = await createTeamInvite(firstOwner.cookie, "revoke.me@example.test", "viewer");
  assert.equal(revokeInvite.response.status, 201);
  const revokeResponse = await request(`/api/team/invitations/${revokeInvite.body.invitation.id}/revoke`, {
    method: "POST",
    headers: { Cookie: firstOwner.cookie, Origin: origin, "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(revokeResponse.status, 200);
  assert.equal((await request("/api/team-invitation", {
    headers: { "x-v79-team-invite-token": revokeInvite.token },
  })).status, 410);
  assert.equal((await acceptTeamInvite(
    revokeInvite.token,
    "Revoked Member",
    "revoked-password-12345",
  )).status, 410);

  const secondOwner = await createOwner("Beta Retail Ltd", "beta.owner@example.test", "beta-owner-password-12345");
  const secondOrgId = secondOwner.body.organization.id;
  await provisionPosForOwner(secondOwner);
  const sharedViewerInvite = await createTeamInvite(secondOwner.cookie, "shared.member@example.test", "viewer");
  assert.equal(sharedViewerInvite.response.status, 201);

  const wrongExistingPassword = await acceptTeamInvite(
    sharedViewerInvite.token,
    "Shared Team Member",
    "wrong-existing-password",
  );
  assert.equal(wrongExistingPassword.status, 401);

  const sharedViewerAccepted = await acceptTeamInvite(
    sharedViewerInvite.token,
    "Shared Team Member",
    "shared-team-password-12345",
  );
  assert.equal(sharedViewerAccepted.status, 201, await sharedViewerAccepted.clone().text());
  const sharedViewerCookie = sharedViewerAccepted.headers.get("set-cookie").split(";")[0];
  const sharedViewerBody = await sharedViewerAccepted.json();
  assert.equal(sharedViewerBody.user.role, "viewer");
  assert.deepEqual(sharedViewerBody.user.permissions, ["overview"]);
  assert.equal((await request("/api/connections/status", { headers: { Cookie: sharedViewerCookie } })).status, 403);
  assert.equal((await request("/api/users", { headers: { Cookie: sharedViewerCookie } })).status, 403);
  await launchAndConsumePos(sharedViewerCookie, secondOrgId);
  const viewerPosProvision = posProvisioning.at(-1);
  assert.equal(viewerPosProvision.payload.organizationId, secondOrgId);
  assert.equal(viewerPosProvision.payload.role, "viewer");
  assert.equal(viewerPosProvision.roleKey, "AUDITOR");
  assert.notEqual(
    viewerPosProvision.payload.user.id,
    managerPosProvision.payload.user.id,
    "the same Hub identity in two SMBs must receive separate POS identities",
  );

  const store = JSON.parse(await readFile(join(dir, "v79_store.json"), "utf8"));
  const sharedUsers = store.users.filter(user => user.username === "shared.member@example.test");
  assert.equal(sharedUsers.length, 1, "shared identity must not be duplicated");
  const sharedUserId = sharedUsers[0].id;
  const sharedMemberships = store.memberships.filter(member => member.userId === sharedUserId);
  assert.equal(sharedMemberships.length, 2);
  assert.equal(sharedMemberships.find(member => member.organizationId === firstOrgId).role, "manager");
  assert.deepEqual(sharedMemberships.find(member => member.organizationId === firstOrgId).appIds, ["app-v79pos"]);
  assert.equal(sharedMemberships.find(member => member.organizationId === secondOrgId).role, "viewer");
  assert.deepEqual(sharedMemberships.find(member => member.organizationId === secondOrgId).appIds, ["app-v79pos"]);

  const roleOnlyUpdate = await request(`/api/users/${sharedUserId}`, {
    method: "PUT",
    headers: { Cookie: firstOwner.cookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ role: "staff" }),
  });
  assert.equal(roleOnlyUpdate.status, 200, await roleOnlyUpdate.clone().text());
  const roleChangeDeprovision = posDeprovisioning.at(-1);
  assert.equal(roleChangeDeprovision.organizationId, firstOrgId);
  assert.equal(roleChangeDeprovision.user.id, managerPosProvision.payload.user.id);
  const storeAfterRoleUpdate = JSON.parse(await readFile(join(dir, "v79_store.json"), "utf8"));
  const updatedMemberships = storeAfterRoleUpdate.memberships.filter(member => member.userId === sharedUserId);
  assert.equal(updatedMemberships.find(member => member.organizationId === firstOrgId).role, "staff");
  assert.deepEqual(updatedMemberships.find(member => member.organizationId === firstOrgId).appIds, ["app-v79pos"]);
  assert.equal(updatedMemberships.find(member => member.organizationId === secondOrgId).role, "viewer");
  assert.deepEqual(updatedMemberships.find(member => member.organizationId === secondOrgId).appIds, ["app-v79pos"]);

  const ambiguousLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "shared.member@example.test", password: "shared-team-password-12345" }),
  });
  assert.equal(ambiguousLogin.status, 409);
  const choices = await ambiguousLogin.json();
  assert.deepEqual(new Set(choices.organizations.map(org => org.id)), new Set([firstOrgId, secondOrgId]));

  const alphaLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "shared.member@example.test",
      password: "shared-team-password-12345",
      organizationId: firstOrgId,
    }),
  });
  assert.equal(alphaLogin.status, 200);
  assert.equal((await alphaLogin.clone().json()).user.role, "staff");
  const alphaCookie = alphaLogin.headers.get("set-cookie").split(";")[0];
  await launchAndConsumePos(alphaCookie, firstOrgId);
  const resyncedPosProvision = posProvisioning.at(-1);
  assert.equal(resyncedPosProvision.payload.role, "staff");
  assert.equal(resyncedPosProvision.roleKey, "CASHIER");

  const removeAlphaPos = await request(`/api/users/${sharedUserId}`, {
    method: "PUT",
    headers: { Cookie: firstOwner.cookie, Origin: origin, "content-type": "application/json" },
    body: JSON.stringify({ appIds: [] }),
  });
  assert.equal(removeAlphaPos.status, 200, await removeAlphaPos.clone().text());
  const appRemovalDeprovision = posDeprovisioning.at(-1);
  assert.equal(appRemovalDeprovision.organizationId, firstOrgId);
  assert.equal(appRemovalDeprovision.user.id, managerPosProvision.payload.user.id);
  const storeAfterAccessUpdate = JSON.parse(await readFile(join(dir, "v79_store.json"), "utf8"));
  const accessMemberships = storeAfterAccessUpdate.memberships.filter(member => member.userId === sharedUserId);
  assert.deepEqual(accessMemberships.find(member => member.organizationId === firstOrgId).appIds, []);
  assert.deepEqual(accessMemberships.find(member => member.organizationId === secondOrgId).appIds, ["app-v79pos"]);

  const alphaAfterRemoval = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "shared.member@example.test",
      password: "shared-team-password-12345",
      organizationId: firstOrgId,
    }),
  });
  assert.equal(alphaAfterRemoval.status, 200);
  const alphaAfterRemovalBody = await alphaAfterRemoval.json();
  assert.deepEqual(alphaAfterRemovalBody.user.appIds, []);
  const alphaAfterRemovalCookie = alphaAfterRemoval.headers.get("set-cookie").split(";")[0];
  assert.deepEqual(await (await request("/api/ecosystem/apps", { headers: { Cookie: alphaAfterRemovalCookie } })).json(), []);
  const alphaConnectionsAfterRemoval = await request("/api/connections/status", { headers: { Cookie: alphaAfterRemovalCookie } });
  assert.equal(alphaConnectionsAfterRemoval.status, 200);
  assert.deepEqual(Object.keys((await alphaConnectionsAfterRemoval.json()).apps), []);
  assert.equal((await request("/api/apps/pos/launch", { headers: { Cookie: alphaAfterRemovalCookie } })).status, 403);

  const betaLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "shared.member@example.test",
      password: "shared-team-password-12345",
      organizationId: secondOrgId,
    }),
  });
  assert.equal(betaLogin.status, 200);
  const betaBody = await betaLogin.json();
  assert.equal(betaBody.user.role, "viewer");
  assert.deepEqual(betaBody.user.appIds, ["app-v79pos"]);
  assert.equal(betaBody.user.platformOperator, false);
  assert.equal(betaBody.user.workspaceOwner, false);
  const betaCookie = betaLogin.headers.get("set-cookie").split(";")[0];
  await launchAndConsumePos(betaCookie, secondOrgId);
});
