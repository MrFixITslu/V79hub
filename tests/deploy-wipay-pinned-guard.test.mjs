import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const script = fs.readFileSync(path.join(root, "scripts/deploy-server.sh"), "utf8");

test("generic production deployment fails closed for pinned WiPay overlays", () => {
  const inspectAt = script.indexOf("running_hub_compose_files=");
  const guardAt = script.indexOf('if [[ "$running_hub_compose_files" == *".pinned.yml"* ]]');
  const stopAt = script.indexOf("STOP: live Hub is using a pinned Compose override");
  const stagesAt = script.indexOf("stage=$(mktemp");
  const syncAt = script.indexOf("rsync -a --delete");
  const upAt = script.indexOf("docker compose --project-name v79-hub up");

  for (const n of [inspectAt, guardAt, stopAt, stagesAt, syncAt, upAt]) {
    assert.ok(n >= 0, "Expected production release protection missing");
  }
  assert.ok(inspectAt < guardAt && guardAt < stopAt);
  assert.ok(stopAt < stagesAt && stagesAt < syncAt && syncAt < upAt,
    "Pinned-overlay denial must precede any staging/sync/recreation");
  assert.match(script, /docker inspect --format/);
  assert.match(script, /exit 1[\s\S]*?stage=\$\(mktemp/);
});
