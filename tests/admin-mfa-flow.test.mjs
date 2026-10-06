import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { totpCode } from "../server/security-contract.mjs";

async function listen(server) {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

test("production platform admin enrolls mandatory MFA before a session is issued", { timeout: 20000 }, async t => {
  const dir = await mkdtemp(join(tmpdir(), "v79-admin-mfa-"));
  const probe = createServer();
  const origin = await listen(probe);
  await new Promise(resolve => probe.close(resolve));

  const child = spawn(process.execPath, ["--import", "tsx", "server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      DATA_DIR: dir,
      PORT: new URL(origin).port,
      APP_URL: origin,
      V79_HUB_ADMIN_PASSWORD: "a-unique-admin-password-1234",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_REQUIRE_ADMIN_MFA: "1",
      V79_PLATFORM_SHARED_SECRET: "platform-test-secret-12345678901234567890",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let output = "";
  child.stdout.on("data", chunk => output += chunk);
  child.stderr.on("data", chunk => output += chunk);
  t.after(async () => {
    if (child.exitCode === null) {
      const exited = new Promise(resolve => child.once("exit", resolve));
      child.kill();
      await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 1200))]);
    }
    await rm(dir, { recursive: true, force: true });
  });

  const request = (path, options = {}) => fetch(origin + path, { redirect: "manual", ...options });
  for (let i = 0; i < 100; i++) {
    try { if ((await request("/api/health")).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 80));
  }

  const login = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "a-unique-admin-password-1234" }),
  });
  assert.equal(login.status, 202, output);
  assert.equal(login.headers.get("set-cookie"), null);
  const challenge = await login.json();
  assert.equal(challenge.mfaRequired, true);
  assert.equal(challenge.setupRequired, true);
  assert.match(challenge.secret, /^[A-Z2-7]+$/);

  const retryLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "a-unique-admin-password-1234" }),
  });
  assert.equal(retryLogin.status, 202, output);
  const retryChallenge = await retryLogin.json();
  assert.equal(retryChallenge.setupRequired, true);
  assert.equal(retryChallenge.secret, challenge.secret, "pending MFA enrollment must reuse the same setup secret");

  const complete = await request("/api/auth/mfa/complete-login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ challengeId: challenge.challengeId, code: totpCode(challenge.secret) }),
  });
  assert.equal(complete.status, 200, output);
  assert.match(complete.headers.get("set-cookie") || "", /v79_hub_session=/);
  const identity = await complete.json();
  assert.equal(identity.user.platformOperator, true);
  assert.equal(identity.user.mfaEnabled, true);

  const secondLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "vision79slu@gmail.com", password: "a-unique-admin-password-1234" }),
  });
  assert.equal(secondLogin.status, 202, output);
  const verifyChallenge = await secondLogin.json();
  assert.equal(verifyChallenge.setupRequired, false);
  assert.equal("secret" in verifyChallenge, false);
});
