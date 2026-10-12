import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const file = path.join(root, "scripts/g12-live-server-delta-metadata.py");
const source = fs.readFileSync(file, "utf8");

test("source delta script compiles and synthetic self-test passes offline", () => {
  const syntax = spawnSync("python3", ["-c", "import ast,sys;ast.parse(sys.stdin.read())"], {
    input: source, encoding: "utf8", timeout: 5000
  });
  assert.equal(syntax.status, 0, syntax.stderr);
  const trial = spawnSync("python3", ["-B", file, "--self-test"], {
    encoding: "utf8", timeout: 5000
  });
  assert.equal(trial.status, 0, trial.stderr);
  assert.equal(trial.stdout.trim(), "READ_ONLY_DELTA_SELF_TEST_PASS");
});

test("read-only delta script prints only bounded metadata and cannot modify production", () => {
  assert.match(source, /EXPECTED_PREVIOUS_LIVE_BLOB = "349c54621b8bb4d3abe54bf50ffade9db768f4e9"/);
  assert.match(source, /SOURCE_COMMIT = "7bbea7b597910e52d27d8fece6b9089a01fcec86"/);
  assert.match(source, /"source_code_printed": False/);
  assert.match(source, /"release_authorized": False/);
  assert.match(source, /"production_modified": False/);
  assert.match(source, /"docker", "exec", "v79-hub", "cat", "\/app\/server\.ts"/);
  assert.doesNotMatch(source, /"docker", "(?:stop|restart|kill|rm|run|cp|build)"/);
  assert.doesNotMatch(source, /(?:\bunlink|\brmtree|\bwrite_text|\bwrite_bytes|\bchmod|\bchown)\s*\(/);
  assert.doesNotMatch(source, /\b(?:print|json\.dumps)\([^\n]*\blive\b/);
});
