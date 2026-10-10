import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("production platform administration is locked to vision79slu@gmail.com", { timeout: 15000 }, async t => {
  const dir = await mkdtemp(join(tmpdir(), "v79-admin-lock-"));
  t.after(() => rm(dir, { recursive: true, force: true }));

  const child = spawn(process.execPath, ["--import", "tsx", "server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      DATA_DIR: dir,
      PORT: "0",
      APP_URL: "https://hub.example.test",
      V79_HUB_ADMIN_PASSWORD: "a-unique-admin-password-1234",
      V79_HUB_ADMIN_EMAIL: "other-owner@example.test",
      V79_PLATFORM_SHARED_SECRET: "platform-test-secret-12345678901234567890",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let output = "";
  child.stdout.on("data", chunk => output += chunk);
  child.stderr.on("data", chunk => output += chunk);

  const exitCode = await Promise.race([
    new Promise(resolve => child.once("exit", code => resolve(code))),
    new Promise((_, reject) => setTimeout(() => reject(new Error("Hub did not fail closed for the wrong admin email")), 8000)),
  ]);

  if (child.exitCode === null) child.kill();
  assert.notEqual(exitCode, 0);
  assert.match(output, /V79_HUB_ADMIN_EMAIL must remain vision79slu@gmail\.com/);
});
