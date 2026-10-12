import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";

const script = fs.readFileSync(
  new URL("../scripts/g12-live-preserved-module-parity.sh", import.meta.url), "utf8"
);
test("read-only runtime fingerprint command is syntactically valid", () => {
  const result = spawnSync("bash", ["-n"], {input: script, encoding:"utf8"});
  assert.equal(result.status,0,result.stderr);
});
test("exact fixed module allowlist, no token or application data contents printed", () => {
  for (const file of [
    "server/platform-owner-billing.mjs",
    "server/sentinel-service-entitlement.mjs",
    "server/sentinel-service-grants.mjs",
    "server/sentinel-grant-operator.mjs",
  ]) assert.ok(script.includes(file));
  for (const hash of [
    "b679af6330d0b75033283ee36bcdcae2648217a5",
    "6454da6d6216af26c5f844772d665a2ca0bd24ac",
    "5ddfe367cdc6383a5af75358df92601b8e688fe3",
  ]) assert.ok(script.includes(hash));
  assert.match(script,/readFileSync\('\/app\/\' \+ file\)/);
  assert.match(script,/candidateReleaseApproved: false/);
  assert.match(script,/noProductionWrites: true/);
  assert.doesNotMatch(script,/\bdocker (?:cp|restart|rm|build|run|compose up|compose down)\b/);
  assert.doesNotMatch(script,/\b(?:rm -rf|chmod|chown|sudo|writeFileSync|process\.env\[[^\]]+\]\s*=)\b/);
});
