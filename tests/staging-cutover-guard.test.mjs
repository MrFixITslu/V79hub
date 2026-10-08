import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

test("a staging cutover cannot run without the deliberate staging safety flag", () => {
  const env = { ...process.env };
  delete env.V79_STAGING_MIGRATION;
  delete env.PGHOST;
  delete env.PGDATABASE;
  const result = spawnSync(process.execPath, [
    "scripts/rehearse-approved-cutover.mjs", "--apply-staging"
  ], { env, encoding: "utf8", timeout: 4000 });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /STAGING SAFETY GUARD: refused/);
});

test("a staging cutover refuses database names other than the exact disposable staging name", () => {
  const result = spawnSync(process.execPath, [
    "scripts/rehearse-approved-cutover.mjs", "--apply-staging"
  ], {
    env: {
      ...process.env,
      V79_STAGING_MIGRATION: "I_UNDERSTAND_STAGING_ONLY",
      PGHOST: "/home/firelion/v79-staging-v79-01-20261008/pgsocket",
      PGDATABASE: "v79hub"
    },
    encoding: "utf8", timeout: 4000
  });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /STAGING SAFETY GUARD: refused/);
});
