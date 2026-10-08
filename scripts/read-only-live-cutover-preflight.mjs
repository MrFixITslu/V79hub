#!/usr/bin/env node
// V79-01 owner-authorised, strictly READ-ONLY production preflight.
// No identifiers, email addresses, passwords, connection strings or secrets
// are ever printed or written to disk.
import { spawnSync } from "node:child_process";

const inspect=String.raw`
import { Client } from "pg";
const connectionString=process.env.DATABASE_URL;
if (!connectionString) throw Error("PRODUCTION_DATABASE_URL_MISSING");
const client=new Client({connectionString,connectionTimeoutMillis:4000});
await client.connect();
try {
  await client.query("BEGIN READ ONLY");
  await client.query("SET LOCAL statement_timeout = 4000");
  const result=await client.query(
    "SELECT state,revision FROM v79_hub_state WHERE store_key='main'");
  if(result.rowCount!==1)throw Error("UNEXPECTED_STORE_ROW_COUNT");
  const store=result.rows[0].state;
  // POS_* external IDs are app-scoped: never equate them to Hub org IDs.
  const ownerEmail=String(process.env.V79_HUB_ADMIN_EMAIL||"").toLowerCase();
  const organizations=Array.isArray(store.organizations)?store.organizations:[];
  const active=organizations.filter(o=>o.status==="active");
  const membership=Array.isArray(store.memberships)?store.memberships:[];
  const entitlements=Array.isArray(store.appEntitlements)?store.appEntitlements:[];
  const plans=Array.isArray(store.organizationPlans)?store.organizationPlans:[];
  const matchingOwners=Array.isArray(store.users)?store.users.filter(u=>
    String(u.email||u.username||"").toLowerCase()===ownerEmail):[];
  const verifiedOwner=matchingOwners.length===1;
  const ownerUserId=verifiedOwner?matchingOwners[0].id:null;
  const founderMemberships=membership.filter(m=>
    m.userId===ownerUserId && m.role==="owner" && m.status==="active");
  const ownerOrgId=founderMemberships.length===1?founderMemberships[0].organizationId:null;
  const owner=active.find(o=>o.id===ownerOrgId);
  const customers=organizations.filter(o=>o.id!==ownerOrgId);
  const customer=customers[0];
  const hasOwnerMembership=membership.some(m=>
    m.userId===ownerUserId&&m.organizationId===ownerOrgId&&
    m.role==="owner"&&m.status==="active");
  const customerOwners=membership.filter(m=>m.organizationId===customer?.id&&
    m.role==="owner"&&m.status==="active");
  const customerEntitlements=entitlements.filter(e=>
    e.organizationId===customer?.id &&e.enabled);
  const out={
    storeRowCount:result.rowCount,
    revisionIsPositive:Number(result.rows[0].revision)>0,
    organizationCount:organizations.length,
    activeOrganizationCount:active.length,
    ownerOrganizationActive:!!owner,
    ownerUserVerified:verifiedOwner,
    founderActiveOwnerMembershipCount:founderMemberships.length,
    ownerMembershipActive:hasOwnerMembership,
    customerOrganizationCount:customers.length,
    customerActive:customer?.status==="active",
    customerActiveOwners:customerOwners.length,
    customerEnabledEntitlements:customerEntitlements.length,
    customerDistinctEnabledApps:new Set(customerEntitlements.map(e=>e.appId)).size,
    planCount:plans.length,
    trialReminderEvents:Array.isArray(store.trialReminderEvents)?store.trialReminderEvents.length:0,
    emailKeyConfigured:!!process.env.RESEND_API_KEY,
    reminderWorkerEnabled:process.env.V79_TRIAL_REMINDERS_ENABLED==="1",
    productionReadOnly:true,
  };
  out.cutoverBaselineReady=
    out.revisionIsPositive&&out.organizationCount===2&&
    out.activeOrganizationCount===2&&out.ownerOrganizationActive&&
    out.ownerUserVerified&&out.ownerMembershipActive&&
    out.customerOrganizationCount===1&&out.customerActive&&
    out.customerActiveOwners===1&&
    out.customerEnabledEntitlements===5&&out.customerDistinctEnabledApps===5&&
    out.planCount===0;
  console.log(JSON.stringify(out));
  await client.query("ROLLBACK");
} finally {await client.end();}
`;
const p=spawnSync("docker",["exec","-i","v79-hub","node","--input-type=module","-"],{
  encoding:"utf8",input:inspect,timeout:18000,maxBuffer:512*1024,
});
if(p.status!==0){
  console.error("V79_PRODUCTION_PREFLIGHT_READ_FAILED");
  process.exit(1);
}
let result;
try{result=JSON.parse(p.stdout.trim());}
catch{console.error("V79_PRODUCTION_PREFLIGHT_BAD_RESULT");process.exit(1);}
console.log(JSON.stringify(result,null,2));
if(!result.cutoverBaselineReady)process.exitCode=2;
