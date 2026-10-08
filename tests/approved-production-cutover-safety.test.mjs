import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
const script = "scripts/approved-production-cutover.mjs";
function run(args=[],extraEnv={}){
 return spawnSync(process.execPath,[script,...args],{
  encoding:"utf8",timeout:5000,
  env:{...process.env,
   NODE_ENV:"test",
   V79_PRODUCTION_CUTOVER_APPROVED:"",
   DATABASE_URL:"",
   ...extraEnv}
 });
}
test("production writer rejects ambiguous invocation and missing owner approval",()=>{
 for(const args of [[],["--apply","--dry-run"],["--apply","--unsafe"]]){
  const result=run(args);
  assert.equal(result.status,2);
 }
 assert.equal(run(["--apply"]).status,2);
 assert.equal(run(["--dry-run"]).status,2);
});
test("production writer refuses GHA synthetic integration even if release flag appears",()=>{
 const r=run(["--apply"],{NODE_ENV:"production",GITHUB_ACTIONS:"true",
 V79_PRODUCTION_CUTOVER_APPROVED:"OWNER_APPROVED_V79_01_2026_10_08"});
 assert.equal(r.status,2);
});
test("production writer pins the exact live database and uses an atomic revision check",()=>{
 const source=readFileSync(script,"utf8");
 assert.match(source,/v79-hub-postgres/);
 assert.match(source,/\/v79hub/);
 assert.match(source,/pg_is_in_recovery/);
 assert.match(source,/SELECT revision, state FROM v79_hub_state/);
 assert.match(source,/WHERE store_key='main' AND revision=\$2 RETURNING revision/);
 assert.match(source,/await client.query\("COMMIT"\)/);
 assert.match(source,/await client.query\("ROLLBACK"\)/);
 assert.match(source,/prepareApprovedLegacyCutover/);
 assert.doesNotMatch(source,/\bDROP TABLE\b|\bTRUNCATE\b|\bDELETE FROM\b/i);
});
