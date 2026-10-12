import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const script = readFileSync(new URL("../scripts/g12-live-release-readonly-preflight.sh", import.meta.url), "utf8");

test("production preflight is valid shell and intentionally never claims release approval", () => {
  const lint = spawnSync("bash", ["-n"], {input:script, encoding:"utf8"});
  assert.equal(lint.status, 0, lint.stderr);
  assert.match(script, /HARD STOP: metadata inspection passed/);
  assert.match(script, /exit 3/);
  assert.match(script, /NO-GO: infrastructure preflight failures observed/);
});

test("preflight preserves WiPay pin, accounts and databases", () => {
  assert.ok(script.includes("wipay-return-585f701.pinned.yml"));
  assert.ok(script.includes("v79-hub-postgres"));
  assert.ok(script.includes("v79-tiquet-manager"));
  assert.ok(script.includes("exact-ID dry-run of disposable test accounts"));
  // It can only use Docker metadata reads. No mutating Docker, DB or shell commands.
  assert.doesNotMatch(script, /\bdocker\s+(?:run|exec|build|rm|compose\s+(?:up|down|build)|system\s+prune)\b/);
  assert.doesNotMatch(script, /\b(?:rsync|sed\s+-i|truncate|psql|pg_dump|dropdb|curl|wget|chmod|chown|rm\s+-r)\b/);
});
