import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const scriptPath = path.resolve(here, "../scripts/g12-live-wipay-recovery-inventory.py");
const source = fs.readFileSync(scriptPath, "utf8");

test("read-only recovery inventory is valid Python and has a hard host guard", () => {
  const result = spawnSync("python3", ["-c",
    "import ast,sys; ast.parse(sys.stdin.read()); print('PARSE_PASS')"], {
    input: source, encoding: "utf8"
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(source, /socket\.gethostname\(\)/);
  assert.match(source, /only run on the v79sl server/);
  assert.match(source, /"release_ready": False/);
  assert.match(source, /"restore_tested": False/);
});

test("inventory excludes secrets, accounts and destructive operations", () => {
  assert.ok(source.includes("wipay-return-585f701.pinned.yml"));
  assert.ok(source.includes("running_hub_code_blobs"));
  assert.ok(source.includes("running_business_agent_code_blobs"));
  assert.ok(source.includes("pilot_business_agent_code_blobs"));
  assert.ok(source.includes("matches_preflight"));
  assert.ok(source.includes('GITHUB_REFERENCE_SHA = "7f84d276a90b8d426c0a2fe33ca652321aee8d88"'));
  assert.ok(source.includes("MATCH_REFERENCE"));
  assert.ok(source.includes("DIFFERENT_FROM_REFERENCE"));
  assert.ok(source.includes("focused-launch-checkpoint-20261010"));
  assert.ok(source.includes("no_resources_modified"));
  assert.doesNotMatch(source, /subprocess\.run\([^\n]*(?:\b(?:rm|restart|stop|kill|up|down|chmod|chown|pg_dump|psql)\b)/);
  assert.doesNotMatch(source, /\b(?:unlink|rmtree|write_text|write_bytes|chmod|chown|makedirs|mkdir)\s*\(/);
  assert.doesNotMatch(source, /"docker",\s*"(?:run|rm|restart|stop|kill|cp|build)"/);
  assert.doesNotMatch(source, /\b(?:password|api_key|token_value)\s*=\s*os\.environ/);
});

test("refuses run on non-server CI host without Docker contact or side effects", () => {
  const result = spawnSync("python3", [scriptPath], {
    encoding: "utf8", timeout: 4000
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /only run on the v79sl server/);
});
