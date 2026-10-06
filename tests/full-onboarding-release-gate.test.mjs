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

async function startProductMock(product, platformSecret, t) {
  const provisioned = new Map();
  const server = createServer(async (req, res) => {
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
      secret: platformSecret,
    });
    if (req.headers["x-v79-service-id"] !== "v79-hub" || !valid) {
      res.writeHead(401, { "content-type": "application/json" });
      return res.end(JSON.stringify({ error: "bad signature" }));
    }

    if (req.method === "POST" && pathname === "/api/platform/provision") {
      const payload = JSON.parse(body);
      const organizationId = payload.organization.id;
      const record = { ...payload, organizationId };
      provisioned.set(organizationId, record);

      const response = product === "pos"
        ? {
            provisioned: true,
            organizationId,
            ownerUserId: payload.user.id,
          }
        : product === "ffpro"
          ? {
              provisioned: true,
              organizationId,
              ownerHubUserId: payload.user.id,
              financeUserId: `finance-${organizationId}`,
            }
          : product === "tiquet"
            ? {
                provisioned: true,
                organizationId,
                ownerHubUserId: payload.user.id,
                accountId: `account-${organizationId}`,
                userId: `tiquet-user-${organizationId}`,
              }
            : {
                provisioned: true,
                organizationId,
                ownerHubUserId: payload.user.id,
                businessId: `business-${organizationId}`,
                userId: `marketing-user-${organizationId}`,
              };

      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify(response));
    }

    if (req.method === "GET" && pathname.startsWith("/api/platform/summary/")) {
      const organizationId = decodeURIComponent(pathname.slice("/api/platform/summary/".length));
      if (!provisioned.has(organizationId)) {
        res.writeHead(404, { "content-type": "application/json" });
        return res.end(JSON.stringify({ error: "not provisioned" }));
      }
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({
        generatedAt: new Date().toISOString(),
        metrics: {
          organizationMarker: organizationId,
          productMarker: product,
          records: 1,
        },
      }));
    }

    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "not found" }));
  });

  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  t.after(() => new Promise(resolve => server.close(resolve)));
  return {
    origin: `http://127.0.0.1:${address.port}`,
    provisioned,
  };
}

test("invite-only onboarding release gate keeps two SMBs isolated across all customer products", { timeout: 70000 }, async t => {
  const platformSecret = "platform-test-secret-12345678901234567890";
  const launchSecrets = {
    ffpro: "ffpro-launch-secret-12345678901234567890",
    tiquet: "tiquet-launch-secret-12345678901234567890",
    marketing: "marketing-launch-secret-12345678901234567890",
  };

  const mocks = {};
  for (const product of ["pos", "ffpro", "tiquet", "marketing"]) {
    mocks[product] = await startProductMock(product, platformSecret, t);
  }

  const dir = await mkdtemp(join(tmpdir(), "v79-full-onboarding-gate-"));
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
    try {
      if ((await request("/api/health")).ok) break;
    } catch {}
    if (i === 299) assert.fail(logs || "Hub did not start");
    await new Promise(resolve => setTimeout(resolve, 50));
  }

  const operatorLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "owner-password-123456789" }),
  });
  assert.equal(operatorLogin.status, 200);
  const operatorCookie = operatorLogin.headers.get("set-cookie").split(";")[0];
  const operatorHeaders = {
    Cookie: operatorCookie,
    Origin: origin,
    "content-type": "application/json",
  };

  const sharedEmail = "shared-owner@example.test";
  const sharedPassword = "shared-owner-password-12345";
  const assignedAppIds = ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing", "app-academy"];

  async function onboard(name) {
    const invitationResponse = await request("/api/admin/onboarding/invitations", {
      method: "POST",
      headers: operatorHeaders,
      body: JSON.stringify({
        organizationName: name,
        email: sharedEmail,
        appIds: assignedAppIds,
        expiresInHours: 24,
      }),
    });
    assert.equal(invitationResponse.status, 201, await invitationResponse.clone().text());
    const invitation = await invitationResponse.json();
    const token = new URLSearchParams(new URL(invitation.inviteUrl).hash.slice(1)).get("invite");
    assert.ok(token);

    const accepted = await request("/api/onboarding/invitation/accept", {
      method: "POST",
      headers: {
        Origin: origin,
        "content-type": "application/json",
        "x-v79-invite-token": token,
      },
      body: JSON.stringify({ fullName: "Shared Owner", password: sharedPassword }),
    });
    assert.equal(accepted.status, 201, await accepted.clone().text());
    const acceptedBody = await accepted.clone().json();
    return {
      organization: acceptedBody.organization,
      cookie: accepted.headers.get("set-cookie").split(";")[0],
    };
  }

  const a = await onboard("Release Gate A");
  const b = await onboard("Release Gate B");
  assert.notEqual(a.organization.id, b.organization.id);

  const ambiguous = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: sharedEmail, password: sharedPassword }),
  });
  assert.equal(ambiguous.status, 409);
  const choices = await ambiguous.json();
  assert.deepEqual(
    new Set(choices.organizations.map(row => row.id)),
    new Set([a.organization.id, b.organization.id]),
  );

  for (const customer of [a, b]) {
    const users = await request("/api/users", { headers: { Cookie: customer.cookie } });
    assert.equal(users.status, 200);
    const userRows = await users.json();
    assert.equal(userRows.length, 1);
    assert.equal(userRows[0].username, sharedEmail);

    assert.equal(
      (await request("/api/admin/onboarding/invitations", { headers: { Cookie: customer.cookie } })).status,
      403,
    );
    assert.equal(
      (await request("/api/admin/customers", { headers: { Cookie: customer.cookie } })).status,
      403,
    );

    const apps = await (await request("/api/ecosystem/apps", { headers: { Cookie: customer.cookie } })).json();
    assert.deepEqual(new Set(apps.map(app => app.id)), new Set(assignedAppIds));
    for (const appId of ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"]) {
      const app = apps.find(row => row.id === appId);
      assert.equal(app.launchReady, false);
      assert.equal(app.status, "syncing");
    }
    assert.equal(apps.find(row => row.id === "app-academy").launchReady, true);

    for (const product of ["pos", "ffpro", "tiquet", "marketing"]) {
      assert.equal(
        (await request(`/api/apps/${product}/launch`, { headers: { Cookie: customer.cookie } })).status,
        409,
      );
    }
  }

  const customerControl = await request("/api/admin/customers", { headers: operatorHeaders });
  assert.equal(customerControl.status, 200);
  const customerControlBody = await customerControl.json();
  assert.deepEqual(
    new Set(customerControlBody.customers.map(row => row.id)),
    new Set([a.organization.id, b.organization.id]),
  );
  for (const customer of customerControlBody.customers) {
    assert.equal(customer.lifecycle, "provisioning");
    assert.equal(customer.owner.email, sharedEmail);
    assert.equal(customer.memberCount, 1);
    assert.equal(customer.plan.planName, "Custom");
  }

  const planUpdate = await request(`/api/admin/customers/${a.organization.id}/plan`, {
    method: "PUT",
    headers: operatorHeaders,
    body: JSON.stringify({
      planName: "Business",
      status: "active",
      billingCycle: "monthly",
      priceXcd: 199,
      renewalDate: "2027-01-15",
      appIds: assignedAppIds,
      reason: "Release gate verifies centralized Hub plan and entitlements.",
    }),
  });
  assert.equal(planUpdate.status, 200, await planUpdate.clone().text());

  const billing = await request("/api/billing/summary", { headers: { Cookie: a.cookie } });
  assert.equal(billing.status, 200);
  const billingBody = await billing.json();
  assert.equal(billingBody.planName, "Business");
  assert.equal(billingBody.pricing.monthly, 199);
  assert.equal(billingBody.renewalDate, "2027-01-15");
  assert.deepEqual(new Set(billingBody.enabledApps.map(app => app.id)), new Set(assignedAppIds));

  for (const customer of [a, b]) {
    const provisioned = await request(
      `/api/admin/customers/${customer.organization.id}/provision`,
      {
        method: "POST",
        headers: operatorHeaders,
        body: JSON.stringify({ appIds: ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"] }),
      },
    );
    assert.equal(provisioned.status, 200, await provisioned.clone().text());
    const provisionedBody = await provisioned.json();
    assert.equal(provisionedBody.success, true);
    assert.equal(provisionedBody.lifecycle, "active");
    assert.deepEqual(
      new Set(provisionedBody.results.map(result => result.appId)),
      new Set(["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"]),
    );
    assert.equal(provisionedBody.results.every(result => result.status === "active"), true);
  }

  for (const product of ["pos", "ffpro", "tiquet", "marketing"]) {
    assert.equal(mocks[product].provisioned.size, 2);
    assert.deepEqual(
      new Set(mocks[product].provisioned.keys()),
      new Set([a.organization.id, b.organization.id]),
    );
    assert.notEqual(
      mocks[product].provisioned.get(a.organization.id).user.id,
      mocks[product].provisioned.get(b.organization.id).user.id,
    );
  }

  const consumeConfig = {
    pos: { serviceId: "v79-pos", secret: platformSecret },
    ffpro: { serviceId: "v79-ffpro", secret: launchSecrets.ffpro },
    tiquet: { serviceId: "v79-tiquet", secret: launchSecrets.tiquet },
    marketing: { serviceId: "v79-marketing", secret: launchSecrets.marketing },
  };

  async function launchAndConsume(customer, product) {
    const launch = await request(`/api/apps/${product}/launch`, { headers: { Cookie: customer.cookie } });
    assert.equal(launch.status, 302, `${product}: ${await launch.clone().text()}`);
    const location = new URL(launch.headers.get("location"));
    const ticket = product === "pos"
      ? new URLSearchParams(location.hash.slice(1)).get("ticket")
      : location.searchParams.get("ticket");
    assert.ok(ticket);

    const payload = JSON.stringify({ product, ticket });
    const timestamp = String(Date.now());
    const config = consumeConfig[product];
    const headers = {
      "content-type": "application/json",
      "x-v79-service-id": config.serviceId,
      "x-v79-timestamp": timestamp,
      "x-v79-signature": signPlatformRequest({
        method: "POST",
        pathname: "/api/platform/session/consume",
        timestamp,
        body: payload,
        secret: config.secret,
      }),
    };
    const consumed = await request("/api/platform/session/consume", { method: "POST", headers, body: payload });
    assert.equal(consumed.status, 200, `${product}: ${await consumed.clone().text()}`);
    const body = await consumed.json();
    if (product === "pos") {
      assert.equal(body.tenantId, customer.organization.id);
      const claims = JSON.parse(Buffer.from(body.token.split(".")[1], "base64url").toString("utf8"));
      assert.equal(claims.tenant_id, customer.organization.id);
      return claims.sub;
    }
    assert.equal(body.organization.id, customer.organization.id);
    assert.equal(body.user.email, sharedEmail);
    assert.equal(body.entitlement.product, product);
    assert.equal(
      (await request("/api/platform/session/consume", { method: "POST", headers, body: payload })).status,
      401,
    );
    return body.user.id;
  }

  for (const product of ["pos", "ffpro", "tiquet", "marketing"]) {
    const identityA = await launchAndConsume(a, product);
    const identityB = await launchAndConsume(b, product);
    assert.notEqual(identityA, identityB, `${product} owner identity must be workspace-scoped`);
  }

  for (const customer of [a, b]) {
    const summary = await (await request("/api/dashboard/summary", {
      headers: { Cookie: customer.cookie },
    })).json();

    for (const product of ["pos", "ffpro", "tiquet", "marketing"]) {
      assert.equal(summary.apps[product].status, "ok");
      assert.equal(summary.apps[product].metrics.organizationMarker, customer.organization.id);
      assert.equal(summary.apps[product].metrics.productMarker, product);
    }
    assert.equal(summary.apps.academy.status, "not_configured");
    assert.deepEqual(summary.apps.academy.metrics, {});
    for (const product of ["lasertag", "website", "games"]) {
      assert.equal(summary.apps[product].status, "not_enabled");
      assert.deepEqual(summary.apps[product].metrics, {});
    }
  }

  const audit = await request(`/api/admin/audit?organizationId=${a.organization.id}`, { headers: operatorHeaders });
  assert.equal(audit.status, 200);
  const auditBody = await audit.json();
  assert.equal(auditBody.events.some(event => event.type === "customer_plan_updated"), true);
  assert.equal(auditBody.events.some(event => event.type === "pos_tenant_provisioned"), true);

  const suspended = await request(`/api/admin/customers/${a.organization.id}/status`, {
    method: "POST",
    headers: operatorHeaders,
    body: JSON.stringify({
      status: "suspended",
      reason: "Release gate verifies high-impact customer suspension and session revocation.",
      confirmName: a.organization.name,
    }),
  });
  assert.equal(suspended.status, 200, await suspended.clone().text());
  assert.equal((await request("/api/users", { headers: { Cookie: a.cookie } })).status, 401);

  const reactivated = await request(`/api/admin/customers/${a.organization.id}/status`, {
    method: "POST",
    headers: operatorHeaders,
    body: JSON.stringify({
      status: "active",
      reason: "Release gate restores customer after suspension verification.",
      confirmName: a.organization.name,
    }),
  });
  assert.equal(reactivated.status, 200, await reactivated.clone().text());
});
