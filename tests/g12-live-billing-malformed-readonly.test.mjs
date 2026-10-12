import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
const script=fs.readFileSync(new URL("../scripts/g12-explain-live-billing-malformed-readonly.sh",import.meta.url),"utf8");
test("synthetic live billing type-check script is valid and read only",()=>{
  const r=spawnSync("bash",["-n"],{input:script,encoding:"utf8"});
  assert.equal(r.status,0,r.stderr);
  assert.match(script,/af7db645565e7737f052493bd4ca9fa6ae2da089/);
  assert.match(script,/strictCandidateRejectsMalformedValues:true/);
  assert.match(script,/const result = platformOwnerBillingAllowed\(args\)/);
  assert.match(script,/releaseApproved:false/);
  assert.match(script,/docker exec -i v79-hub node --input-type=module -/);
  assert.doesNotMatch(script,/\bdocker (?:cp|run|stop|restart|kill|rm|build|compose up|compose down)\b/);
  assert.doesNotMatch(script,/\b(?:writeFile|chmod|chown|rm -rf|psql|pg_dump|curl|wget)\b/);
});
