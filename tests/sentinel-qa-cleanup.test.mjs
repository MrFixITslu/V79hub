import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { previewSentinelCleanup, removeSentinelCleanup, SentinelCleanupError } from "../server/sentinel-qa-cleanup.mjs";

const ORG_ID = "b359dc03-bb54-47c5-864c-fc5270a67bda";
const OWNER_ID = "a8e4a0e6-0474-4bd2-8b39-99205ea2640b";
const STAFF_ID = "3bd1604d-a19b-4ed3-a8d8-2b82c6f7e58e";
const OPERATOR = "live-owner-never-remove";
const EXISTING_ORG = "production-organization-never-remove";
const MARKER = "9a4734f4-aec7-41a9-8d89-502be8bbf94f";
const TIME = "2026-10-09T17:00:00.000Z";
const DELETION_ID = "cdadca70-5d9a-481b-b876-3a8cba34108a";

function fixture() {
  return {
    users: [
      {id:OPERATOR,username:"real-platform-owner@example.com",password:"existing-secret-hash"},
      {id:"customer-1",username:"real-customer@example.com",password:"existing"},
      {id:OWNER_ID,username:"owner-1@sentinel-qa.invalid",password:"synthetic-only"},
      {id:STAFF_ID,username:"viewer-1@sentinel-qa.invalid",password:"synthetic-only"},
    ],
    workspace:{companyName:"V79 Digital"},ecosystemApps:[],
    organizations:[
      {id:EXISTING_ORG,name:"Existing Customer",slug:"existing-customer"},
      {id:ORG_ID,name:"Sentinel-QA-"+ORG_ID,slug:("sentinel-qa-"+ORG_ID),createdAt:TIME,status:"active"},
    ],
    memberships:[
      {organizationId:EXISTING_ORG,userId:"customer-1",role:"owner"},
      {organizationId:ORG_ID,userId:OWNER_ID,role:"owner"},
      {organizationId:ORG_ID,userId:STAFF_ID,role:"viewer"},
    ],
    appEntitlements:[],organizationPlans:[],trialReminderEvents:[],
    billingOrders:[],billingPaymentEvents:[],ownerInvitations:[],
    teamInvitations:[],appTenantMappings:[],passwordResetRequests:[],
    auditEvents:[
      {id:"original-audit",organizationId:EXISTING_ORG,actorUserId:"customer-1",type:"customer_plan_updated",
       createdAt:TIME,details:{}},
      {id:MARKER,organizationId:ORG_ID,actorUserId:OPERATOR,type:"sentinel_qa_tenant_created",
       createdAt:TIME,
       details:{purpose:"synthetic_qa_only",organizationId:ORG_ID,syntheticUserIds:[OWNER_ID,STAFF_ID]}}
    ]
  };
}
const target={organizationId:ORG_ID,operatorUserId:OPERATOR};
function mustBlock(change,reason) {
 const original=fixture(),data=structuredClone(original);
 change(data);
 const baseline=structuredClone(data);
 assert.throws(()=>previewSentinelCleanup(data,target),SentinelCleanupError,reason);
 assert.deepEqual(data,baseline,"Validation must never mutate store");
}
test("clean dry-run produces stable exact preview and leaves original untouched", () => {
 const before=fixture(),frozen=structuredClone(before);
 const p=previewSentinelCleanup(before,target);
 assert.equal(p.state,"eligible-hub-only");
 assert.equal(p.memberCount,2);
 assert.equal(p.markerId,MARKER);
 assert.match(p.previewHash,/^[a-f0-9]{64}$/);
 assert.equal(p.previewHash,previewSentinelCleanup(before,target).previewHash);
 assert.deepEqual(before,frozen);
});
test("reviewed delete removes only manifest-owned Hub synthetic records", () => {
 const s=fixture(),pr=previewSentinelCleanup(s,target);
 const before=structuredClone(s);
 const res=removeSentinelCleanup(s,{...target,confirmName:"DELETE Sentinel-QA-"+ORG_ID,
   previewHash:pr.previewHash, deletedAt:"2026-10-09T18:01:00Z",auditId:DELETION_ID});
 assert.deepEqual(s,before,"Pure function cannot mutate input");
 assert.equal(res.removed.memberCount,2);
 assert.deepEqual(res.nextStore.organizations,[before.organizations[0]]);
 assert.deepEqual(res.nextStore.users,before.users.slice(0,2));
 assert.deepEqual(res.nextStore.memberships,[before.memberships[0]]);
 assert.equal(res.nextStore.auditEvents.length,2);
 assert.deepEqual(res.nextStore.auditEvents[0],before.auditEvents[0]);
 assert.equal(res.nextStore.auditEvents[1].type,"sentinel_qa_tenant_deleted");
 assert.equal(res.nextStore.auditEvents[1].organizationId,undefined);
 assert.deepEqual(res.nextStore.workspace,before.workspace);
});
test("requires fresh preview hash and exact phrase", () => {
 const s=fixture(),p=previewSentinelCleanup(s,target);
 const args={...target,confirmName:"DELETE Sentinel-QA-"+ORG_ID,previewHash:p.previewHash,
             deletedAt:"2026-10-09T18:01:00Z",auditId:DELETION_ID};
 assert.throws(()=>removeSentinelCleanup(s,{...args,previewHash:"0".repeat(64)}),/Exact deletion/);
 assert.throws(()=>removeSentinelCleanup(s,{...args,confirmName:"delete Sentinel-QA-"+ORG_ID}),/Exact deletion/);
 s.memberships.push({organizationId:ORG_ID,userId:"intruder",role:"staff"});
 assert.throws(()=>removeSentinelCleanup(s,args),SentinelCleanupError);
});
test("refuses platform owner, ordinary customer, unmatched name or marker", () => {
 assert.throws(()=>previewSentinelCleanup(fixture(),{organizationId:EXISTING_ORG,operatorUserId:OPERATOR}),SentinelCleanupError);
 mustBlock(s=>{s.organizations[1].name="An Existing Company";},"name");
 mustBlock(s=>{s.organizations[1].slug="not-sentinel";},"slug");
 mustBlock(s=>{s.auditEvents.pop();},"marker missing");
 mustBlock(s=>{s.auditEvents[1].actorUserId="some-other-operator";},"creator mismatch");
 mustBlock(s=>{s.auditEvents[1].details.purpose="regular_org";},"purpose mismatch");
 mustBlock(s=>{s.auditEvents.push(structuredClone(s.auditEvents[1]));},"duplicated marker");
});
test("refuses extra or shared users and manipulated owner", () => {
 mustBlock(s=>{s.memberships.push({organizationId:ORG_ID,userId:"real-customer",role:"staff"});},"extra member");
 mustBlock(s=>{s.memberships.push({organizationId:EXISTING_ORG,userId:STAFF_ID,role:"viewer"});},"shared user");
 mustBlock(s=>{s.memberships[1].role="staff";},"missing owner");
 mustBlock(s=>{s.users[2].username="realuser@example.com";},"unexpected email");
 mustBlock(s=>{s.users=s.users.filter(u=>u.id!==STAFF_ID);},"missing synthetic user");
 mustBlock(s=>{s.auditEvents.push({id:"other-org-audit",actorUserId:STAFF_ID,organizationId:EXISTING_ORG,type:"login"});},"cross-org audit");
});
test("refuses ALL billing, app and external references", () => {
 const tables=["appTenantMappings","appEntitlements","organizationPlans","trialReminderEvents",
               "billingOrders","billingPaymentEvents","ecosystemApps"];
 for(const table of tables) {
  mustBlock(s=>s[table].push({organizationId:ORG_ID,id:"danger"}),table);
 }
 mustBlock(s=>s.billingOrders.push({id:"order-1",subjectReference:ORG_ID}),"billing subject");
 mustBlock(s=>s.billingPaymentEvents.push({ownerOrganizationId:ORG_ID}),"billing event ownership");
 mustBlock(s=>s.passwordResetRequests.push({userId:STAFF_ID,id:"reset-1"}),"password reset");
 mustBlock(s=>s.ownerInvitations.push({organizationId:ORG_ID,status:"accepted"}),"owner invitation");
 mustBlock(s=>s.teamInvitations.push({organizationId:ORG_ID,status:"revoked"}),"team invitation");
 mustBlock(s=>s.auditEvents.push({organizationId:ORG_ID,type:"customer_plan_updated",id:"unexpected"}),"unexpected audit");
});
test("refuses incomplete, malformed, inconsistent snapshot", () => {
 mustBlock(s=>delete s.users,"missing users table");
 mustBlock(s=>s.memberships.push({organizationId:ORG_ID,userId:STAFF_ID,role:"viewer"}),"duplicate user record");
 assert.throws(()=>previewSentinelCleanup({},target),SentinelCleanupError);
 assert.throws(()=>previewSentinelCleanup(fixture(),{organizationId:"not-uuid",operatorUserId:OPERATOR}),SentinelCleanupError);
});
