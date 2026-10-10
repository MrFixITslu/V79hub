import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {retainSentinelAuditMarkers} from "../server/sentinel-audit-retention.mjs";

const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(dir,"..");
const marker=(id)=>({id,type:"sentinel_qa_tenant_created",organizationId:id});
const ordinary=(id)=>({id,type:"ordinary_hub_audit"});

test("ordinary Hub audit retention is unchanged without Sentinel marker",()=>{
 const original=Array.from({length:5008},(_,i)=>ordinary("e"+i));
 const actual=retainSentinelAuditMarkers(original);
 assert.equal(actual.length,5000);
 assert.deepEqual(actual,original.slice(-5000));
 assert.equal(original.length,5008);
});
test("creation marker survives 5200 subsequent ordinary events without mutation",()=>{
 const original=[marker("sentinel-id"),
  ...Array.from({length:5200},(_,i)=>ordinary("e"+i))];
 const actual=retainSentinelAuditMarkers(original);
 assert.equal(actual.length,5000);
 assert.equal(actual[0].type,"sentinel_qa_tenant_created");
 assert.equal(actual[0].organizationId,"sentinel-id");
 assert.equal(actual.at(-1).id,"e5199");
 assert.equal(original.length,5201);
});
test("multiple creation markers retained regardless of age",()=>{
 const original=[
  marker("sentinel-a"),...Array.from({length:5030},(_,i)=>ordinary("e"+i)),
  marker("sentinel-b")
 ];
 const actual=retainSentinelAuditMarkers(original);
 assert.equal(actual.length,5000);
 assert.deepEqual(actual.filter(r=>r.type==="sentinel_qa_tenant_created").map(r=>r.organizationId),
  ["sentinel-a","sentinel-b"]);
});
test("bounds and malformed data fail closed",()=>{
 assert.throws(()=>retainSentinelAuditMarkers(null));
 assert.throws(()=>retainSentinelAuditMarkers([],0));
 assert.throws(()=>retainSentinelAuditMarkers(Array.from({length:5001},(_,i)=>marker("id"+i))));
});
test("all Hub audit pruning paths use marker preserving helper",()=>{
 const names=[
  "server.ts","server/onboarding-store.mjs","server/team-invitation-store.mjs",
  "server/pos-provisioning.mjs","server/marketing-provisioning.mjs",
  "server/ffpro-provisioning.mjs","server/tiquet-provisioning.mjs",
  "server/sentinel-qa-cleanup.mjs"
 ];
 for(const name of names){
  const text=fs.readFileSync(path.join(root,name),"utf8");
  assert.match(text,/retainSentinelAuditMarkers\(/,name+" missing marker-retention helper");
  assert.doesNotMatch(text,/auditEvents\s*=\s*[^;]+\.slice\(-5000\)/,name+" vulnerable audit truncation");
 }
});
