import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {managedSkillGuidance,verifyManagedSkills} from "../src/managed-skills.js";

const workers=["ceo","coo","finance","strategy","marketing","customer-service","technical-security","sales"];
const text="# Content\nUse verified evidence, not fabricated claims.";
const base=()=>Object.fromEntries(workers.map(id=>[id,[]])) as Record<string,any[]>;
const entry=()=>({id:"skill-1122334455667788",name:"Test",version:1,
  sha256:createHash("sha256").update(text).digest("hex"),content:text});

test("valid skill is attached only to chosen worker and pinned to digest",()=>{
 const payload=base();payload.marketing=[entry()];
 const result=verifyManagedSkills(payload);
 assert.equal(managedSkillGuidance(result,"marketing").versions[0],"skill-1122334455667788@v1");
 assert.match(managedSkillGuidance(result,"marketing").instructions,/LOWER TRUST/);
 assert.deepEqual(managedSkillGuidance(result,"coo").versions,[]);
});
test("reject tampered or malformed skill source instead of silently using it",()=>{
 for(const bad of [
  (m:Record<string,any[]>)=>{m.marketing=[{...entry(),content:"modified"}];},
  (m:Record<string,any[]>)=>{m.sales=[{...entry(),unknown:"field"}];},
  (m:Record<string,any[]>)=>{m.sales=[{...entry(),version:"1"}];},
  (m:Record<string,any[]>)=>{m.marketing=[entry(),entry(),entry()];},
  (m:Record<string,any[]>)=>{m.fake=[];},
 ]) {
  const payload=base();bad(payload);
  assert.throws(()=>verifyManagedSkills(payload));
 }
});
test("no duplicate skill under the same worker and no 6kB overflow",()=>{
 const payload=base();payload.marketing=[entry(),entry()];
 assert.throws(()=>verifyManagedSkills(payload));
 const oversized=base();oversized.marketing=[{...entry(),content:"z".repeat(6001)}];
 assert.throws(()=>verifyManagedSkills(oversized));
});
