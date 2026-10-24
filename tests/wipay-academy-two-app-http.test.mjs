// Two real, disposable application HTTP servers; all identities, card
// transactions and keys are synthetic. No requests go to a payment provider.
// Requires ACADEMY_TEST_ROOT pointing at a built/pinned Academy checkout.
import test from "node:test";
import assert from "node:assert/strict";
import { createHmac, createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";

const academyRoot = process.env.ACADEMY_TEST_ROOT;
if (!academyRoot) {
  test("cross-repo Academy HTTP test runs only with explicit pinned source fixture", { skip: true }, () => {});
} else {
  const hubRoot = process.cwd();
  const hubSecret = "SYNTHETIC_HUB_ACADEMY_SHARED_BILLING_SECRET_2026_ONLY";
  const fakeMerchantKey = "SYNTHETIC_PAYMENT_HASH_KEY_NOT_WIPAY";
  const stateSecret = "SYNTHETIC_HUB_BILLING_STATE_SIGNING_SECRET_2026";
  const amount = 249;
  async function port() {
    const server = createServer();
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    const chosen = server.address().port;
    await new Promise(resolve => server.close(resolve));
    return chosen;
  }
  function serviceSignature(route, body) {
    const stamp = String(Date.now());
    const canonical = ["POST", route, stamp, createHash("sha256").update(body).digest("hex")].join("\n");
    const signature = createHmac("sha256", hubSecret).update(canonical).digest("hex");
    return { "content-type": "application/json", "x-v79-service-id": "v79-academy-billing",
      "x-v79-timestamp": stamp, "x-v79-signature": signature };
  }
  async function signedStatus(hub, orderId) {
    const pathname = "/api/billing/internal/status";
    const body = JSON.stringify({ orderId });
    const response = await fetch(hub + pathname, { method: "POST", headers: serviceSignature(pathname, body), body });
    return { status: response.status, data: await response.json() };
  }
  function payerHash(transactionId, originalAmount) {
    return createHash("md5").update(transactionId + originalAmount.toFixed(2) + fakeMerchantKey).digest("hex");
  }
  async function checkReady(base, pathname, child, label, getLogs) {
    for (let attempt = 0; attempt < 170; attempt++) {
      if (child.exitCode !== null) throw Error(label + " exited: " + getLogs().slice(-1000));
      try {
        const response = await fetch(base + pathname, { signal: AbortSignal.timeout(500) });
        if (response.ok) return;
      } catch {}
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    throw Error(label + " did not start: " + getLogs().slice(-1500));
  }
  async function json(base, pathname, { method = "GET", cookie, body, status = 200 } = {}) {
    const response = await fetch(base + pathname, {
      method, redirect: "manual", signal: AbortSignal.timeout(8000),
      headers: { ...(cookie ? { cookie } : {}), ...(body !== undefined ? { "content-type": "application/json" } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); } catch { data = { raw: raw.slice(0, 300) }; }
    assert.equal(response.status, status, method + " " + pathname + ": " + JSON.stringify(data));
    return { data, cookie: response.headers.get("set-cookie")?.split(";")[0], response };
  }

  test("real Academy↔Hub synthetic signed checkout: pending, invalid return, sandbox paid, replay and learner isolation",
    { timeout: 90000 }, async t => {
      const academyFile = resolve(academyRoot, "dist/server.cjs");
      const directory = await mkdtemp(join(tmpdir(), "vision79-cross-app-synthetic-"));
      t.after(() => rm(directory, { recursive: true, force: true }));
      await mkdir(join(directory, "academy"), { recursive: true });
      const hubPort = await port(), academyPort = await port();
      const hub = "http://127.0.0.1:" + hubPort, academy = "http://127.0.0.1:" + academyPort;
      const programs = [];
      function start(label, command, args, cwd, env) {
        const p = spawn(command, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
        let logs = "";
        for (const stream of [p.stdout, p.stderr]) stream.on("data", bytes => {
          logs = (logs + bytes.toString()).slice(-6000);
        });
        programs.push({ process: p, label });
        return { process: p, logs: () => logs };
      }
      t.after(async () => {
        for (const entry of programs.reverse()) {
          const p = entry.process;
          if (p.exitCode === null) {
            const exit = new Promise(resolve => p.once("exit", resolve));
            p.kill("SIGTERM");
            await Promise.race([exit, new Promise(resolve => setTimeout(resolve, 1500))]);
            if (p.exitCode === null) p.kill("SIGKILL");
          }
        }
      });

      const hubProgram = start("Hub", process.execPath, ["--import", "tsx", "server.ts"], hubRoot, {
        ...process.env, NODE_ENV: "production", PORT: String(hubPort),
        DATA_DIR: join(directory, "hub"), APP_URL: hub, V79_HUB_STORE_BACKEND: "json",
        V79_HUB_ADMIN_PASSWORD: "synthetic-only-owner-password-123456",
        V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
        V79_HUB_SECURITY_KEY: "synthetic-hub-security-unique-32-char-2026",
        V79_PLATFORM_SHARED_SECRET: "synthetic-platform-shared-secret-unique-2026",
        V79_BILLING_STATE_SECRET: stateSecret,
        V79_ACADEMY_BILLING_SECRET: hubSecret,
        WIPAY_ENABLED: "1", WIPAY_ENV: "sandbox",
        WIPAY_SANDBOX_DOC_DEFAULTS: "0",
        WIPAY_ACCOUNT_NUMBER: "SYNTHETIC-ACCOUNT-DO-NOT-USE",
        WIPAY_API_KEY: fakeMerchantKey,
        WIPAY_PAYMENT_URL: "https://sandbox.example.invalid/hosted-checkout-not-real",
        WIPAY_COUNTRY_CODE: "LC", WIPAY_CURRENCY: "XCD",
        WIPAY_RESPONSE_URL: "https://hub.example.invalid/api/billing/wipay/return",
        V79_TRIAL_REMINDERS_ENABLED: "0",
      });
      await checkReady(hub, "/api/health", hubProgram.process, "Hub", hubProgram.logs);
      const academyProgram = start("Academy", process.execPath, [academyFile], join(directory, "academy"), {
        ...process.env, NODE_ENV: "production", PORT: String(academyPort),
        ACADEMY_STANDALONE_ADMIN_ENABLED: "1",
        ADMIN_PASSWORD: "synthetic-academy-admin-password-123456",
        V79_PLATFORM_SHARED_SECRET: "synthetic-academy-admin-shared-secret-2026",
        V79_HUB_BILLING_URL: hub, V79_ACADEMY_BILLING_SECRET: hubSecret,
        V79_ACADEMY_BILLING_CURRENCY: "XCD",
      });
      await checkReady(academy, "/healthz", academyProgram.process, "Academy", academyProgram.logs);

      // Anonymous Hub order creation must be rejected before touching the ledger.
      assert.equal((await json(hub, "/api/billing/internal/order", {
        method: "POST", body: { kind: "course", amount }, status: 401,
      })).response.status, 401);

      const adminLogin = await json(academy, "/api/admin/login", {
        method: "POST", body: { password: "synthetic-academy-admin-password-123456" },
      });
      const changed = await json(academy, "/api/admin/change-password", {
        method: "POST", cookie: adminLogin.cookie,
        body: { currentPassword: "synthetic-academy-admin-password-123456",
          newPassword: "synthetic-academy-admin-new-password-123456" },
      });
      const adminCookie = changed.cookie || (await json(academy, "/api/admin/login", {
        method: "POST", body: { password: "synthetic-academy-admin-new-password-123456" },
      })).cookie;
      const course = (await json(academy, "/api/courses", {
        method: "POST", cookie: adminCookie, status: 201,
        body: { title: "From Idea to Advantage — SYNTHETIC", pricingType: "premium",
          price: amount, category: "Synthetic CI Only", status: "Published" },
      })).data;
      const module = (await json(academy, "/api/courses/" + course.id + "/modules", {
        method: "POST", cookie: adminCookie, status: 201,
        body: { title: "Synthetic premium lesson module" },
      })).data;
      await json(academy, "/api/modules/" + module.id + "/lessons", {
        method: "POST", cookie: adminCookie, status: 201,
        body: { title: "Protected synthetic content", lessonContent: "PRIVATE_SYNTHETIC_ACCESS_ONLY" },
      });
      const alpha = await json(academy, "/api/learner/register", { method: "POST",
        body: { email: "alpha@example.test", name: "Synthetic Alpha",
          password: "synthetic-alpha-password-123456" } });
      const beta = await json(academy, "/api/learner/register", { method: "POST",
        body: { email: "beta@example.test", name: "Synthetic Beta",
          password: "synthetic-beta-password-123456" } });
      const contentPath = "/api/public/modules/" + module.id + "/lessons";
      let content = (await json(academy, contentPath, { cookie: alpha.cookie })).data;
      assert.equal(content[0].lessonContent, undefined);

      const checkout = (await json(academy, "/api/learner/checkout", {
        method: "POST", cookie: alpha.cookie, status: 201,
        body: { courseId: course.id },
      })).data;
      const orderId = checkout.order.id;
      assert.match(orderId, /^v79_/);
      assert.equal(checkout.order.amount, 249);
      assert.equal(checkout.order.sourceApp, "academy");
      assert.equal(checkout.checkout.fields.email, "alpha@example.test");
      assert.equal(checkout.checkout.fields.method, "credit_card_co");
      assert.equal(checkout.checkout.fields.currency, "XCD");
      assert.equal(checkout.checkout.environment, "sandbox");
      assert.equal(new URL(checkout.checkout.action).hostname, "sandbox.example.invalid");
      assert.equal((await signedStatus(hub, orderId)).data.order.status, "pending");

      const confirmPath = "/api/learner/checkout/confirm";
      let confirm = (await json(academy, confirmPath, {
        method: "POST", cookie: alpha.cookie, status: 409, body: { orderId },
      })).data;
      assert.equal(confirm.code, "PAYMENT_NOT_VERIFIED");
      assert.equal((await json(academy, confirmPath, {
        method: "POST", cookie: beta.cookie, status: 403, body: { orderId },
      })).response.status, 403);

      const transactionId = "SYNTHETIC-NO-REAL-PROVIDER-TX";
      const query = new URLSearchParams({
        order_id: orderId, status: "success", transaction_id: transactionId,
        currency: "XCD", total: "249.00",
        hash: payerHash(transactionId, amount),
        data: checkout.checkout.fields.data,
      });
      const callback = "/api/billing/wipay/return?";
      const wrong = new URLSearchParams(query);
      wrong.set("total", "250.00");
      const rejected = await fetch(hub + callback + wrong, { redirect: "manual" });
      assert.equal(rejected.status, 302, "tampered query must redirect, not settle");
      assert.equal((await signedStatus(hub, orderId)).data.order.status, "pending");
      const fakeFailure = new URLSearchParams(query);
      fakeFailure.set("status", "failed");
      assert.equal((await fetch(hub + callback + fakeFailure, { redirect: "manual" })).status, 302);
      assert.equal((await signedStatus(hub, orderId)).data.order.status, "pending");

      const accepted = await fetch(hub + callback + query, { redirect: "manual" });
      assert.equal(accepted.status, 302);
      assert.match(accepted.headers.get("location") || "", /payment=success/);
      let status = (await signedStatus(hub, orderId)).data.order;
      assert.equal(status.status, "paid");
      assert.equal(status.providerEnvironment, "sandbox");
      assert.equal(status.providerTransactionId, transactionId);

      // Sandbox may verify the synthetic provider HMAC, but it cannot confer ownership.
      confirm = (await json(academy, confirmPath, {
        method: "POST", cookie: alpha.cookie, status: 409, body: { orderId },
      })).data;
      assert.equal(confirm.code, "SANDBOX_PAYMENT_VERIFIED");
      assert.equal((await json(academy, confirmPath, {
        method: "POST", cookie: beta.cookie, status: 403, body: { orderId },
      })).response.status, 403);
      content = (await json(academy, contentPath, { cookie: alpha.cookie })).data;
      assert.equal(content[0].lessonContent, undefined);

      const replay = await fetch(hub + callback + query, { redirect: "manual" });
      assert.equal(replay.status, 302);
      assert.match(replay.headers.get("location") || "", /already_processed/);
      assert.equal((await signedStatus(hub, orderId)).data.order.status, "paid");
      console.log("CROSS_APP_SYNTHETIC_HTTP=PASS: signed payer email, no provider request, pending/failed/tamper, sandbox no entitlement, foreign learner, replay");
    });
}
