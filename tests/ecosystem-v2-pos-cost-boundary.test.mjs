import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { createEcosystemEventInbox } from "../server/ecosystem-v2-event-ingress.mjs";

const server=readFileSync(new URL("../server.ts",import.meta.url),"utf8");
const posRoute=server.slice(
  server.indexOf('app.get("/api/ecosystem/v2/job-cost-evidence/:jobId"'),
  server.indexOf('app.use("/api", requireAuth);'));
test("job-cost endpoint requires Hub membership, both app entitlements and signed job proof",()=>{
 for(const text of [
  'requireAuth',
  'V79_ECOSYSTEM_V2_POS_COST_READ_ENABLED',
  'activeMembership(store,ctx.userId,ctx.organizationId)',
  '["owner","admin"].includes(membership.role)',
  'appId==="app-pos"',
  'appId==="app-tiquet"',
  'hasTiquetJob(org,jobId)',
  'V79_POS_PLATFORM_SHARED_SECRET',
  'signPlatformRequest({method:"GET"',
  'redirect:"error"',
  'AbortSignal.timeout(5000)',
  'verifiedPosJobAssociation:false',
  'confirmedMargin:null',
  'paymentSettlementVerified:false',
 ])assert.ok(posRoute.includes(text),"Missing risk control: "+text);
 assert.doesNotMatch(posRoute,/INSERT INTO payments|UPDATE jobs|INSERT INTO inventory/);
});

test("signed job proof is scoped to exact event type and organisation",async()=>{
 const org="org_v79_customer_A",id=randomUUID();
 const statements=[];
 const pool={async query(sql,args=[]){
   if(sql.includes("CREATE TABLE"))return {rowCount:0,rows:[]};
   statements.push({sql,args});
   return {rowCount:args[0]===org && args[1]===id?1:0,rows:[]};
 }};
 const inbox=createEcosystemEventInbox(pool);
 assert.equal(await inbox.hasTiquetJob(org,id),true);
 assert.equal(await inbox.hasTiquetJob("org_v79_customer_B",id),false);
 assert.match(statements[0].sql,/organization_id=\$1 AND source='tiquet'/);
 assert.match(statements[0].sql,/event_type='job.created' AND subject_id=\$2/);
 await assert.rejects(inbox.hasTiquetJob(org,"TIQUET-001"));
});
