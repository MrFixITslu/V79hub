import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

async function freeOrigin() {
  const server = createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return `http://127.0.0.1:${port}`;
}

test("platform operator invite-only onboarding is single-use and workspace isolated", { timeout: 40000 }, async t => {
  const dir = await mkdtemp(join(tmpdir(), "v79-invite-onboarding-"));
  const origin = await freeOrigin();
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
      if ((await request("/api/health")).ok) { ready = true; break; }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.equal(ready, true, logs || "Hub test server did not become ready.");

  assert.equal((await request("/api/auth/register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  })).status, 403);
  assert.equal((await request("/api/admin/onboarding/invitations")).status, 401);

  const operatorLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "owner-password-123456789" }),
  });
  assert.equal(operatorLogin.status, 200, logs);
  const operatorCookie = operatorLogin.headers.get("set-cookie").split(";")[0];
  const operatorHeaders = { Cookie: operatorCookie, Origin: origin, "content-type": "application/json" };
  const inviteHeaders = (token, requestOrigin = origin) => ({
    Origin: requestOrigin,
    "content-type": "application/json",
    "x-v79-invite-token": token,
  });
  const tokenFromUrl = (url) => new URLSearchParams(new URL(url).hash.replace(/^#/, "")).get("invite");

  const createInvite = async (body) => request("/api/admin/onboarding/invitations", {
    method: "POST",
    headers: operatorHeaders,
    body: JSON.stringify(body),
  });

  assert.equal((await createInvite({
    organizationName: "Bad Apps Ltd",
    email: "bad@example.test",
    appIds: ["app-lasertag"],
  })).status, 400);

  const firstInviteResponse = await createInvite({
    organizationName: "Island Tech Ltd",
    email: "owner@example.test",
    appIds: ["app-tiquet", "app-academy"],
    expiresInHours: 24,
  });
  assert.equal(firstInviteResponse.status, 201);
  const firstInvite = await firstInviteResponse.json();
  const firstInviteUrl = new URL(firstInvite.inviteUrl);
  const firstToken = tokenFromUrl(firstInvite.inviteUrl);
  assert.ok(firstToken);
  assert.equal(firstInviteUrl.search, "");
  assert.match(firstInviteUrl.hash, /^#invite=[A-Za-z0-9_%+-]+$/);
  assert.equal(firstInvite.invitation.organizationName, "Island Tech Ltd");
  assert.equal("tokenHash" in firstInvite.invitation, false);

  const diskAfterCreate = await readFile(join(dir, "v79_store.json"), "utf8");
  assert.equal(diskAfterCreate.includes(firstToken), false);
  const createdStore = JSON.parse(diskAfterCreate);
  assert.match(createdStore.ownerInvitations[0].tokenHash, /^[a-f0-9]{64}$/);
  assert.equal(createdStore.ownerInvitations[0].status, "pending");

  assert.equal((await createInvite({
    organizationName: "Island Tech Ltd",
    email: "owner@example.test",
    appIds: [],
  })).status, 409);

  const metadata = await request("/api/onboarding/invitation", { headers: { "x-v79-invite-token": firstToken } });
  assert.equal(metadata.status, 200);
  const invitationDetails = await metadata.json();
  assert.equal(invitationDetails.organizationName, "Island Tech Ltd");
  assert.notEqual(invitationDetails.email, "owner@example.test");

  assert.equal((await request("/api/onboarding/invitation/accept", {
    method: "POST",
    headers: inviteHeaders(firstToken, "https://evil.example"),
    body: JSON.stringify({ fullName: "Island Owner", password: "customer-password-12345" }),
  })).status, 403);

  const accepted = await request("/api/onboarding/invitation/accept", {
    method: "POST",
    headers: inviteHeaders(firstToken),
    body: JSON.stringify({ fullName: "Island Owner", password: "customer-password-12345" }),
  });
  assert.equal(accepted.status, 201, await accepted.clone().text());
  const acceptedBody = await accepted.json();
  const firstOrgId = acceptedBody.organization.id;
  const customerCookie = accepted.headers.get("set-cookie").split(";")[0];
  assert.equal(acceptedBody.user.username, "owner@example.test");
  assert.equal(acceptedBody.user.role, "admin");
  assert.equal(acceptedBody.user.platformOperator, false);
  assert.deepEqual(acceptedBody.onboarding.productSetupPending, ["app-tiquet"]);

  const storeAfterAccept = JSON.parse(await readFile(join(dir, "v79_store.json"), "utf8"));
  assert.equal(storeAfterAccept.organizations.some(org => org.id === firstOrgId && org.name === "Island Tech Ltd"), true);
  const trialPlan = storeAfterAccept.organizationPlans.find(plan => plan.organizationId === firstOrgId);
  assert.equal(trialPlan.status, "trial");
  assert.equal(trialPlan.accessPolicyType, "trial");
  assert.equal(Date.parse(trialPlan.trialEndsAt) - Date.parse(trialPlan.trialStartedAt), 14 * 86400000);
  assert.equal(storeAfterAccept.memberships.some(member => member.organizationId === firstOrgId && member.role === "owner"), true);
  assert.deepEqual(
    storeAfterAccept.appEntitlements.filter(row => row.organizationId === firstOrgId).map(row => row.appId).sort(),
    ["app-academy", "app-tiquet"]
  );
  assert.deepEqual(
    storeAfterAccept.appTenantMappings.filter(row => row.organizationId === firstOrgId).map(row => [row.appId, row.status]),
    [["app-tiquet", "pending"]]
  );
  assert.equal(storeAfterAccept.auditEvents.some(event => event.type === "owner_invitation_accepted" && event.organizationId === firstOrgId), true);

  assert.equal((await request("/api/onboarding/invitation/accept", {
    method: "POST",
    headers: inviteHeaders(firstToken),
    body: JSON.stringify({ fullName: "Island Owner", password: "customer-password-12345" }),
  })).status, 410);

  const customerUsers = await request("/api/users", { headers: { Cookie: customerCookie } });
  assert.equal(customerUsers.status, 200);
  const customerUserList = await customerUsers.json();
  assert.equal(customerUserList.length, 1);
  assert.equal(customerUserList[0].username, "owner@example.test");
  assert.equal((await request("/api/admin/onboarding/invitations", { headers: { Cookie: customerCookie } })).status, 403);
  for (const product of ["lasertag", "website", "games"]) {
    assert.equal(
      (await request(`/api/admin/platform/${product}/overview`, { headers: { Cookie: customerCookie } })).status,
      403,
      `customer workspace must not access ${product} platform administration`,
    );
  }

  const customerApps = await (await request("/api/ecosystem/apps", { headers: { Cookie: customerCookie } })).json();
  const tiquet = customerApps.find(app => app.id === "app-tiquet");
  const academy = customerApps.find(app => app.id === "app-academy");
  assert.equal(tiquet.launchReady, false);
  assert.equal(tiquet.status, "syncing");
  assert.equal(academy.launchReady, true);
  assert.equal((await request("/api/apps/tiquet/launch", { headers: { Cookie: customerCookie } })).status, 409);

  const secondInviteResponse = await createInvite({
    organizationName: "Second Business Inc",
    email: "owner@example.test",
    appIds: ["app-ffpro"],
  });
  assert.equal(secondInviteResponse.status, 201);
  const secondInvite = await secondInviteResponse.json();
  const secondToken = tokenFromUrl(secondInvite.inviteUrl);
  assert.ok(secondToken);

  assert.equal((await request("/api/onboarding/invitation/accept", {
    method: "POST",
    headers: inviteHeaders(secondToken),
    body: JSON.stringify({ fullName: "Island Owner", password: "wrong-existing-password" }),
  })).status, 401);

  const secondAccepted = await request("/api/onboarding/invitation/accept", {
    method: "POST",
    headers: inviteHeaders(secondToken),
    body: JSON.stringify({ fullName: "Island Owner", password: "customer-password-12345" }),
  });
  assert.equal(secondAccepted.status, 201);
  const secondAcceptedBody = await secondAccepted.json();
  const secondOrgId = secondAcceptedBody.organization.id;

  const storeAfterSecond = JSON.parse(await readFile(join(dir, "v79_store.json"), "utf8"));
  const customerUsersOnDisk = storeAfterSecond.users.filter(user => user.username === "owner@example.test");
  assert.equal(customerUsersOnDisk.length, 1);
  const customerUserId = customerUsersOnDisk[0].id;
  assert.equal(storeAfterSecond.memberships.filter(member => member.userId === customerUserId && member.role === "owner").length, 2);

  const ambiguousLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "owner@example.test", password: "customer-password-12345" }),
  });
  assert.equal(ambiguousLogin.status, 409);
  const workspaceChoice = await ambiguousLogin.json();
  assert.equal(workspaceChoice.organizations.length, 2);
  assert.deepEqual(new Set(workspaceChoice.organizations.map(org => org.id)), new Set([firstOrgId, secondOrgId]));

  const selectedLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "owner@example.test",
      password: "customer-password-12345",
      organizationId: firstOrgId,
    }),
  });
  assert.equal(selectedLogin.status, 200);
  assert.equal((await selectedLogin.json()).organization.id, firstOrgId);

  const revokedInviteResponse = await createInvite({
    organizationName: "Revoked Business",
    email: "revoked@example.test",
    appIds: [],
  });
  assert.equal(revokedInviteResponse.status, 201);
  const revokedInvite = await revokedInviteResponse.json();
  const revokedToken = tokenFromUrl(revokedInvite.inviteUrl);
  assert.ok(revokedToken);

  const revokeResponse = await request(
    `/api/admin/onboarding/invitations/${revokedInvite.invitation.id}/revoke`,
    { method: "POST", headers: operatorHeaders, body: "{}" },
  );
  assert.equal(revokeResponse.status, 200);
  assert.equal((await request("/api/onboarding/invitation", { headers: { "x-v79-invite-token": revokedToken } })).status, 410);
  assert.equal((await request("/api/onboarding/invitation/accept", {
    method: "POST",
    headers: inviteHeaders(revokedToken),
    body: JSON.stringify({ fullName: "Revoked Owner", password: "revoked-password-12345" }),
  })).status, 410);

  const finalAdminList = await request("/api/admin/onboarding/invitations", { headers: { Cookie: operatorCookie } });
  assert.equal(finalAdminList.status, 200);
  const finalAdminBody = await finalAdminList.json();
  assert.equal(finalAdminBody.invitations.some(invite => invite.status === "accepted"), true);
  assert.equal(finalAdminBody.invitations.some(invite => invite.status === "revoked"), true);
});
