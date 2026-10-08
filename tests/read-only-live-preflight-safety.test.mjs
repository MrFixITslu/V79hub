import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("live cutover preflight contains only READ ONLY transaction SQL",()=>{
  const source=readFileSync("scripts/read-only-live-cutover-preflight.mjs","utf8");
  assert.match(source,/BEGIN READ ONLY/);
  assert.match(source,/SELECT state,revision FROM v79_hub_state/);
  assert.match(source,/await client.query\("ROLLBACK"\)/);
  assert.doesNotMatch(source,/client\.query\(["'`]\s*(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP)\b/i);
  assert.match(source,/productionReadOnly:true/);
});
test("live cutover preflight derives Hub owner from account membership rather than POS-scoped ID",()=>{
  const source=readFileSync("scripts/read-only-live-cutover-preflight.mjs","utf8");
  assert.match(source,/founderMemberships/);
  assert.doesNotMatch(source,/const ownerOrgId=process\.env\.V79_POS_ORG_ID/);
});
