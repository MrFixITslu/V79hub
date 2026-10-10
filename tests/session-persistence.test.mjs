import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

async function freeOrigin() {
  const server = createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return `http://127.0.0.1:${port}`;
}

async function startHub(origin, dir) {
  const secret = "session-persistence-test-secret-123456789";
  const child = spawn(process.execPath, ["--import", "tsx", "server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      DATA_DIR: dir,
      PORT: new URL(origin).port,
      APP_URL: origin,
      V79_HUB_ADMIN_PASSWORD: "restart-safe-owner-password-123",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_PLATFORM_SHARED_SECRET: secret,
      V79_FFPRO_LAUNCH_SECRET: secret,
      V79_TIQUET_LAUNCH_SECRET: secret,
      V79_MARKETING_LAUNCH_SECRET: secret,
      POS_BASE_URL: "http://127.0.0.1:9",
      ACADEMY_INTERNAL_URL: "http://127.0.0.1:9",
      TIQUET_INTERNAL_URL: "http://127.0.0.1:9",
      FFPRO_INTERNAL_URL: "http://127.0.0.1:9",
      MARKETING_INTERNAL_URL: "http://127.0.0.1:9",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let logs = "";
  child.stdout.on("data", chunk => logs += chunk);
  child.stderr.on("data", chunk => logs += chunk);

  for (let i = 0; i < 150; i++) {
    try {
      if ((await fetch(origin + "/api/health")).ok) return { child, logs: () => logs };
    } catch {}
    if (child.exitCode !== null) break;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error(logs || "Hub did not start");
}

async function stopHub(child) {
  if (child.exitCode !== null) return;
  const exited = new Promise(resolve => child.once("exit", resolve));
  child.kill();
  await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 1500))]);
}

test("Hub session survives restart without persisting the raw cookie token", { timeout: 30000 }, async t => {
  const dir = await mkdtemp(join(tmpdir(), "v79-session-persistence-"));
  await writeFile(join(dir, "v79_store.json"), JSON.stringify({
    users: [],
    inventory: [],
    settings: { companyName: "Restart Test", taxRate: 0 },
  }));

  const origin = await freeOrigin();
  let running = await startHub(origin, dir);
  t.after(async () => {
    await stopHub(running.child);
    await rm(dir, { recursive: true, force: true });
  });

  const login = await fetch(origin + "/api/auth/login", {
    method: "POST",
    redirect: "manual",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "restart-safe-owner-password-123" }),
  });
  assert.equal(login.status, 200, running.logs());
  const cookie = (login.headers.get("set-cookie") || "").split(";")[0];
  assert.match(cookie, /^v79_hub_session=v79_tok_[a-f0-9]{48}$/);

  const beforeRestart = await fetch(origin + "/api/auth/me", { headers: { Cookie: cookie } });
  assert.equal(beforeRestart.status, 200);

  const sessionStore = JSON.parse(await readFile(join(dir, "hub-sessions.json"), "utf8"));
  assert.equal(sessionStore.version, 1);
  assert.equal(sessionStore.sessions.length, 1);
  assert.match(sessionStore.sessions[0].tokenHash, /^[a-f0-9]{64}$/);
  assert.doesNotMatch(JSON.stringify(sessionStore), /v79_tok_/);

  await stopHub(running.child);
  running = await startHub(origin, dir);

  const afterRestart = await fetch(origin + "/api/auth/me", { headers: { Cookie: cookie } });
  assert.equal(afterRestart.status, 200, running.logs());
  const identity = await afterRestart.json();
  assert.equal(identity.user.email, "vision79slu@gmail.com");

  const logout = await fetch(origin + "/api/auth/logout", {
    method: "POST",
    headers: { Cookie: cookie, Origin: origin },
  });
  assert.equal(logout.status, 200);

  const revoked = await fetch(origin + "/api/auth/me", { headers: { Cookie: cookie } });
  assert.equal(revoked.status, 401);
  const afterLogoutStore = JSON.parse(await readFile(join(dir, "hub-sessions.json"), "utf8"));
  assert.equal(afterLogoutStore.sessions.length, 0);
});