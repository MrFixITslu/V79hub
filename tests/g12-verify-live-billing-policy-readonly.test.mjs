import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
const src = fs.readFileSync(new URL("../scripts/g12-verify-live-billing-policy-readonly.sh", import.meta.url), "utf8");

test("live billing semantic audit is valid and cannot modify application state",()=>{
  const r=spawnSync("bash",["-n"],{input:src,encoding:"utf8"});
  assert.equal(r.status,0,r.stderr);
  assert.match(src,/af7db645565e7737f052493bd4ca9fa6ae2da089/);
  assert.match(src,/docker exec -i v79-hub node --input-type=module -/);
  assert.match(src,/Synthetic live billing contract/);
  assert.doesNotMatch(src,/\bdocker (?:cp|run|stop|restart|kill|rm|build|compose up|compose down)\b/);
  assert.doesNotMatch(src,/\b(?:writeFile|chmod|chown|rm -rf|psql|pg_dump|curl|wget)\b/);
});
