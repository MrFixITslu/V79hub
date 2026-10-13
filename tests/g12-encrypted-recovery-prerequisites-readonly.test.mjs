import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";

const name = new URL("../scripts/g12-encrypted-recovery-prerequisites-readonly.py", import.meta.url);
const script = fs.readFileSync(name, "utf8");

test("consolidated recovery prerequisite probe has valid Python syntax", () => {
  const p = spawnSync("python3", ["-B", "-c",
    "import ast,sys; ast.parse(sys.stdin.read(),filename='readonly-recovery')"], {
    input: script, encoding: "utf8", timeout: 3000,
  });
  assert.equal(p.status, 0, p.stderr);
});

test("live recovery check is read-only, pins exact four images and owner Compose", () => {
  for (const needle of [
    "releaseApproved\": False",
    "backupWritten\": False",
    "restoreVerified\": False",
    "modifiesState\": False",
        "v79-hub-postgres",
    "v79-tiquet-manager",
    "wipay-return-585f701.pinned.yml",
    "8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74",
    "imageMatchesPinnedBaseline",
    "pg_isready -q",
    "pg_dump",
    "pg_restore",
    "volumeName",
    "tiquetPostgresCandidates",
  ]) {
    const expected = needle.replaceAll("\\", "");
    assert.ok(script.includes(expected), "Missing safety check: " + needle);
  }
  assert.match(script, /socket\.gethostname\(\)\.split\("\."\)\[0\] != "v79sl"/);
  assert.match(script, /sys\.exit\(3\)/);
  assert.doesNotMatch(script, /\["docker", "(?:run|cp|stop|restart|rm|compose|exec\s+pg_dump)"\]/);
  assert.doesNotMatch(script, /(?:subprocess|os)\.(?:system|Popen)\(/);
  assert.doesNotMatch(script, /(?:write_text|write_bytes|unlink|rmtree|mkdir|makedirs|remove|rename|chmod)\(/);
  assert.doesNotMatch(script, /\bPOSTGRES_PASSWORD\s*=/);
  assert.doesNotMatch(script, /\bm\.get\("Source"\)/);
});

test("running off the v79sl host refuses safely without reading Docker state", () => {
  if (process.env.HOSTNAME === "v79sl") return;
  const r = spawnSync("python3", ["-B",name.pathname], {
    encoding:"utf8",timeout: 4000,
  });
  assert.equal(r.status, 2);
  const parsed = JSON.parse(r.stdout);
  assert.equal(parsed.noWrites, true);
  assert.equal(parsed.releaseApproved, false);
});
