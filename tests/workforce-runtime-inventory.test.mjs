import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
test("G2 inventory compiles, refuses off-server execution and contains only read-only Docker inspection", () => {
  const source = readFileSync(new URL("../scripts/workforce-runtime-inventory.py", import.meta.url), "utf8");
  const syntax = spawnSync("python3", ["-c", "import sys; compile(sys.stdin.read(), '<inventory>', 'exec')"], { input: source });
  assert.equal(syntax.status, 0);
  const run = spawnSync("python3", ["scripts/workforce-runtime-inventory.py"], { encoding: "utf8" });
  assert.equal(run.status, 1); assert.match(run.stderr, /only for v79sl/);
  assert.doesNotMatch(source, /private.key|read_text\(|\.env|write_bytes|write_text|shell=True/);
  assert.deepEqual([...source.matchAll(/subprocess\.run\(\["docker", "([^"]+)"/g)].map(m => m[1]), ["inspect"]);
  assert.match(source, /\["docker", "inspect", name\]/);
});
