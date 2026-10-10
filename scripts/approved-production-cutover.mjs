#!/usr/bin/env node
// V79-01 one-time production cutover. FAIL CLOSED; exact owner-approved baseline.
// This is deliberately separate from staging-only rehearsal scripts.
import { Pool } from "pg";
import { prepareApprovedLegacyCutover } from "../server/legacy-cutover.mjs";

const flags=process.argv.slice(2);
const apply=flags.includes("--apply");
const dryRun=flags.includes("--dry-run");
const yes=process.env.V79_PRODUCTION_CUTOVER_APPROVED==="OWNER_APPROVED_V79_01_2026_10_08";
if(apply===dryRun || flags.some(x=>!["--apply","--dry-run"].includes(x))) {
  console.error("Exactly one of --dry-run or --apply is required.");
  process.exit(2);
}
if(process.env.NODE_ENV!=="production" ||
  process.env.V79_HUB_STORE_BACKEND!=="postgres" ||
  process.env.GITHUB_ACTIONS==="true" ||
  process.env.V79_EPHEMERAL_CI==="1" ||
  (apply&&!yes)){
  console.error("Production cutover guard failed; no writes attempted.");
  process.exit(2);
}
const raw=process.env.DATABASE_URL||"";
let uri;
try { uri=new URL(raw); } catch {uri=null;}
if(!uri || !["postgresql:","postgres:"].includes(uri.protocol) ||
  uri.hostname!=="v79-hub-postgres" ||
  uri.pathname!=="/v79hub" ||
  !(!uri.port||uri.port==="5432") ||
  uri.username!=="v79hub" ||
  !process.env.V79_HUB_ADMIN_EMAIL) {
  console.error("Database/owner identity guard failed; no writes attempted.");
  process.exit(2);
}
const pool=new Pool({connectionString:raw,max:1,connectionTimeoutMillis:4500});
let client;
try {
  client=await pool.connect();
  await client.query(apply?"BEGIN":"BEGIN READ ONLY");
  await client.query("SET LOCAL statement_timeout = '8s'");
  await client.query("SET LOCAL lock_timeout = '4s'");
  const db=await client.query("SELECT current_database() AS db, pg_is_in_recovery() AS replica, inet_server_addr() AS addr");
  if(db.rowCount!==1 || db.rows[0].db!=="v79hub" ||
    db.rows[0].replica!==false || db.rows[0].addr===null) {
    throw Error("Production database connection does not match release contract.");
  }
  const state=await client.query(
    "SELECT revision, state FROM v79_hub_state WHERE store_key='main' FOR UPDATE");
  if(state.rowCount!==1 || !(Number(state.rows[0].revision)>0)) {
    throw Error("Unexpected Hub store state.");
  }
  const before=state.rows[0].state;
  const users=Array.isArray(before.users)?before.users:[];
  const ownerEmail=String(process.env.V79_HUB_ADMIN_EMAIL).trim().toLowerCase();
  if(ownerEmail!=="vision79slu@gmail.com") throw Error("Owner identity differs from approved founder.");
  const matchingUsers=users.filter(u=>String(u.email||"").toLowerCase()===ownerEmail);
  if(matchingUsers.length!==1)throw Error("Verified founder account count is not one.");
  const memberships=Array.isArray(before.memberships)?before.memberships:[];
  const founderMemberships=memberships.filter(m=>m.userId===matchingUsers[0].id &&
    m.role==="owner"&&m.status==="active");
  if(founderMemberships.length!==1)throw Error("Founder must have exactly one active owner membership.");
  const ownerOrgId=founderMemberships[0].organizationId;
  const customers=(before.organizations||[]).filter(o=>o.id!==ownerOrgId);
  if(customers.length!==1)throw Error("Expected exactly one existing customer organisation.");
  const activationAt=new Date().toISOString();
  const plan=prepareApprovedLegacyCutover(before,{
    ownerOrganizationId:ownerOrgId,
    verifiedOwnerUserId:matchingUsers[0].id,
    customerOrganizationId:customers[0].id,
    activationAt,
  });
  if(apply && !plan.alreadyApplied){
    const next=await client.query(
      "UPDATE v79_hub_state SET state=$1::jsonb, revision=revision+1, updated_at=NOW() WHERE store_key='main' AND revision=$2 RETURNING revision",
      [JSON.stringify(plan.planned),state.rows[0].revision]);
    if(next.rowCount!==1 || Number(next.rows[0].revision)!==Number(state.rows[0].revision)+1){
      throw Error("Optimistic revision update failed.");
    }
  }
  if(apply){
    await client.query("COMMIT");
  }else{
    await client.query("ROLLBACK");
  }
  console.log(JSON.stringify({
    mode:apply?"PRODUCTION_CUTOVER_APPLY":"PRODUCTION_CUTOVER_DRY_RUN",
    updated:apply&&!plan.alreadyApplied,
    alreadyApplied:plan.alreadyApplied,
    customerOrganizations:customers.length,
    customerAppEntitlements:plan.summary.retainedEntitlements,
    approvedOn:plan.summary.approvedOn,
    trialStartsAt:plan.summary.trialStart,
    trialEndsAt:plan.summary.trialEnd,
    ownerOrganizationProtected:true,
    releaseGate:"V79-01",
  }));
}catch(e){
  if(client)await client.query("ROLLBACK").catch(()=>{});
  console.error("V79-01 CUTOVER REFUSED:",e?.message||"Unknown safety failure");
  process.exitCode=1;
}finally{
  if(client)client.release();
  await pool.end();
}
