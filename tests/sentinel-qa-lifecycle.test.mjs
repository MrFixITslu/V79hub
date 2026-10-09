import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import {stageSentinelQaCreation} from "../server/sentinel-qa-create.mjs";
import {previewSentinelCleanup,removeSentinelCleanup,SentinelCleanupError} from "../server/sentinel-qa-cleanup.mjs";
const OPERATOR="original-platform-owner-id";
const TEST_ORG="256e40fb-1c92-4cea-b959-d1c4e55e08d0";
const MEMBER_IDS=[
 "b6aaf4bd-d1db-497b-ab3f-92d74d10f36d",
 "b431eb6f-397b-4e91-94d1-6b57b5f46798",
 "1288e7a4-a702-42bd-a93a-2e46146dfbf4",
];
function blank(){
 return {
  users:[{id:OPERATOR,username:"production-owner",password:"prod-secret"},
    {id:"real-customer",username:"real-user",password:"existing-secret"}],
  workspace:{companyName:"V79 Digital"},ecosystemApps:[{id:"app1",name:"Existing V79 App"}],
  organizations:[{id:"existing-org",name:"Existing Customer",slug:"existing-customer"}],
  memberships:[{organizationId:"existing-org",userId:"real-customer",role:"owner"}],
  appEntitlements:[], organizationPlans:[],trialReminderEvents:[],
  billingOrders:[],billingPaymentEvents:[], ownerInvitations:[],teamInvitations:[],
  appTenantMappings:[],passwordResetRequests:[],
  auditEvents:[{id:"existing-audit",organizationId:"existing-org",actorUserId:"real-customer",
    type:"existing_event",details:{}}]
 };
}
const accounts=()=>["owner","staff","viewer"].map((role,i)=>({
  id:MEMBER_IDS[i],role,passwordHash:"scrypt:"+"a".repeat(32)+":"+"b".repeat(128),
}));
const opts=()=>({operatorUserId:OPERATOR, organizationId:TEST_ORG,
  markerId:"87bd1562-248d-4a25-94df-a6450166d7da",
  createdAt:"2026-10-09T20:00:00Z",syntheticAccounts:accounts()});
test("create then preview then delete entirely in memory: original V79 customers intact", () => {
 const before=blank(),saved=structuredClone(before);
 const created=stageSentinelQaCreation(before,opts());
 assert.deepEqual(before,saved,"Cannot mutate production fixture");
 assert.equal(created.syntheticUsers.length,3);
 assert.equal(created.nextStore.organizations.length,2);
 assert.equal(created.nextStore.memberships.length,4);
 assert.equal(created.nextStore.auditEvents.length,2);
 assert.equal(created.nextStore.appEntitlements.length,0);
 assert.equal(created.nextStore.appTenantMappings.length,0);
 const p=previewSentinelCleanup(created.nextStore,{organizationId:TEST_ORG,operatorUserId:OPERATOR});
 assert.equal(p.memberCount,3);
 assert.equal(p.previewHash,created.cleanupPreviewHash);
 const deleted=removeSentinelCleanup(created.nextStore,{
  organizationId:TEST_ORG,operatorUserId:OPERATOR,
  confirmName:"DELETE Sentinel-QA-"+TEST_ORG,
  previewHash:p.previewHash,deletedAt:"2026-10-09T21:00:00Z",
  auditId:"5d75e87e-8fa8-4ab6-8b69-dfa9b7e2534c"
 });
 assert.deepEqual(deleted.nextStore.organizations,before.organizations);
 assert.deepEqual(deleted.nextStore.users,before.users);
 assert.deepEqual(deleted.nextStore.memberships,before.memberships);
 assert.deepEqual(deleted.nextStore.workspace,before.workspace);
 assert.deepEqual(deleted.nextStore.ecosystemApps,before.ecosystemApps);
 assert.equal(deleted.nextStore.auditEvents.length,2);
 assert.deepEqual(deleted.nextStore.auditEvents[0],before.auditEvents[0]);
 assert.equal(deleted.nextStore.auditEvents[1].type,"sentinel_qa_tenant_deleted");
 assert.equal(deleted.removed.memberCount,3);
});
test("creation rejects duplicate synthetic users or mismatched roles",()=>{
 const bad=opts();
 bad.syntheticAccounts[1].id=bad.syntheticAccounts[0].id;
 assert.throws(()=>stageSentinelQaCreation(blank(),bad),SentinelCleanupError);
 const wrong=opts();
 wrong.syntheticAccounts[2].role="admin";
 assert.throws(()=>stageSentinelQaCreation(blank(),wrong),SentinelCleanupError);
});
test("creation does not send email or create app entitlements",()=>{
 const s=blank();
 const result=stageSentinelQaCreation(s,opts());
 assert.equal(result.nextStore.ownerInvitations.length,0);
 assert.equal(result.nextStore.teamInvitations.length,0);
 assert.equal(result.nextStore.appTenantMappings.length,0);
 assert.equal(result.nextStore.billingOrders.length,0);
 assert(result.syntheticUsers.every(u=>u.username.endsWith("@sentinel-qa.invalid")));
 assert(result.syntheticUsers.some(u=>u.role==="staff"));
 assert(result.syntheticUsers.some(u=>u.role==="viewer"));
});
test("adding an external mapping after creation blocks deletion, with no partial cleanup",()=>{
 const c=stageSentinelQaCreation(blank(),opts());
 const s=c.nextStore;
 s.appTenantMappings.push({organizationId:TEST_ORG,appId:"app-pos",status:"active"});
 const frozen=structuredClone(s);
 assert.throws(()=>removeSentinelCleanup(s,{
  organizationId:TEST_ORG,operatorUserId:OPERATOR,
  confirmName:"DELETE Sentinel-QA-"+TEST_ORG,
  previewHash:c.cleanupPreviewHash,deletedAt:"2026-10-09T21:00:00Z",
  auditId:"5d75e87e-8fa8-4ab6-8b69-dfa9b7e2534c"
 }),SentinelCleanupError);
 assert.deepEqual(s,frozen);
});
test("all creation identities must be unique and all generated only once",()=>{
 const s=blank();const c=stageSentinelQaCreation(s,opts());
 assert.throws(()=>stageSentinelQaCreation(c.nextStore,opts()),SentinelCleanupError);
});
