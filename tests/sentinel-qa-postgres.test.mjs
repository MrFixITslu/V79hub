import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import os from "node:os";
import fs from "node:fs";
import path from "node:path";
import {newDb} from "pg-mem";
import {PostgresStoreRepository,migrateJsonState,StoreRevisionConflictError} from "../server/postgres-store.mjs";
import {createHubStorePersistence} from "../server/runtime-store.mjs";
import {stageSentinelQaCreation} from "../server/sentinel-qa-create.mjs";
import {previewSentinelCleanup,removeSentinelCleanup,SentinelCleanupError} from "../server/sentinel-qa-cleanup.mjs";

const OPERATOR="operator-existing";
const OTHER="customer-existing";
const ORGANIZATION="cd051c59-518c-4290-9875-7d786fa5bc5a";
const OWNER="04209a40-72e4-49e2-9554-2a746eac6885";
const STAFF="1b2b5d07-7d62-45be-95ec-a830e4a9fb36";
const VIEWER="ff7c9ee6-7290-44c9-954b-e7b92debc471";
const time="2026-10-09T18:50:00Z";
function defaultStore(){
 return {
  workspace:{companyName:"Existing V79"},
  users:[{id:OPERATOR,username:"platform-owner@v79sl.com",password:"existing"},
         {id:OTHER,username:"real-user@example.com",password:"existing"}],
  organizations:[{id:"real-org",name:"Real Customer",slug:"real-customer"}],
  memberships:[{organizationId:"real-org",userId:OTHER,role:"owner"}],
  ecosystemApps:[],appEntitlements:[],organizationPlans:[],trialReminderEvents:[],
  billingOrders:[],billingPaymentEvents:[],ownerInvitations:[],teamInvitations:[],
  appTenantMappings:[],passwordResetRequests:[],
  auditEvents:[{id:"existing-audit",organizationId:"real-org",actorUserId:OTHER,
                type:"existing_customer_event",details:{}}],
 };
}
function accounts() {
 return ["owner","staff","viewer"].map((role,i)=>({
  role,id:[OWNER,STAFF,VIEWER][i],
  passwordHash:"scrypt:"+crypto.randomBytes(16).toString("hex")+":"+
     crypto.randomBytes(64).toString("hex"),
 }));
}
test("Sentinel creation/teardown persists safely with Hub PostgreSQL repository",async t=>{
 const memory=newDb({autoCreateForeignKeyIndices:true,noAstCoverageCheck:true});
 const adapter=memory.adapters.createPg();
 const pool=new adapter.Pool();
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),"sentinel-qa-pg-"));
 t.after(async()=>{await pool.end();fs.rmSync(temp,{recursive:true,force:true});});
 const repository=new PostgresStoreRepository(pool);
 const initial=defaultStore();
 const legacySetting={legacyAccountDomain:"existing-private-state"};
 const initialized=await migrateJsonState(repository,{...initial,legacySetting});
 const storeFile=path.join(temp,"no-prod-json.json");
 const persistence=createHubStorePersistence({backend:"postgres",storeFile,pool});
 let stored=await persistence.load(x=>x,()=>{throw Error("No seeded store");});
 assert.deepEqual(stored.organizations,initial.organizations);
 assert.equal(persistence.revision(),1);
 // Test isolated creator on the same deserialized JSON shape Hub uses.
 const c=stageSentinelQaCreation(stored,{
  operatorUserId:OPERATOR,organizationId:ORGANIZATION,createdAt:time,
  markerId:"900e2f1e-a32e-4422-9364-e73944ca5f45",syntheticAccounts:accounts()
 });
 await persistence.save(c.nextStore);
 assert.equal(persistence.revision(),2);
 const loaded=await repository.load();
 assert.equal(loaded.revision,2);
 assert.equal(loaded.state.organizations.length,2);
 assert.deepEqual(loaded.state.legacySetting,legacySetting);
 const preview=previewSentinelCleanup(loaded.state,{organizationId:ORGANIZATION,operatorUserId:OPERATOR});
 assert.equal(preview.memberCount,3);
 const deleted=removeSentinelCleanup(loaded.state,{
  organizationId:ORGANIZATION,operatorUserId:OPERATOR,
  confirmName:"DELETE Sentinel-QA-"+ORGANIZATION,previewHash:preview.previewHash,
  auditId:"ac8a9a07-f178-4359-9b2e-109c42ee3d80",deletedAt:"2026-10-09T18:55:00Z"
 });
 await persistence.save(deleted.nextStore);
 const persisted=await repository.load();
 assert.equal(persisted.revision,3);
 assert.deepEqual(persisted.state.organizations,initial.organizations);
 assert.deepEqual(persisted.state.users,initial.users);
 assert.deepEqual(persisted.state.memberships,initial.memberships);
 assert.deepEqual(persisted.state.workspace,initial.workspace);
 assert.deepEqual(persisted.state.legacySetting,legacySetting);
 assert.deepEqual(persisted.state.auditEvents[0],initial.auditEvents[0]);
 assert.equal(persisted.state.auditEvents.at(-1).type,"sentinel_qa_tenant_deleted");
 assert.equal(fs.existsSync(storeFile),false,"PostgreSQL backend must not overwrite a JSON file");
 await persistence.close();
});
test("stale PostgreSQL revision refuses Sentinel cleanup and preserves newer state",async t=>{
 const memory=newDb({autoCreateForeignKeyIndices:true,noAstCoverageCheck:true});
 const adapter=memory.adapters.createPg();
 const pool=new adapter.Pool();
 t.after(()=>pool.end());
 const repository=new PostgresStoreRepository(pool);
 await migrateJsonState(repository,defaultStore());
 const first=await repository.load();
 const second=await repository.load();
 await repository.replace(first.revision,{...first.state,unrelatedMarker:"newer-unrelated-write"});
 await assert.rejects(repository.replace(second.revision,second.state),StoreRevisionConflictError);
 const final=await repository.load();
 assert.equal(final.revision,2);
 assert.equal(final.state.unrelatedMarker,"newer-unrelated-write");
 assert.deepEqual(final.state.organizations,defaultStore().organizations);
});
