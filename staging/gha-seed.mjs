// Synthetic-only GitHub Actions seed. Does not connect to production.
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { randomBytes, scryptSync } from "node:crypto";
import { PostgresStoreRepository } from "../server/postgres-store.mjs";
import { beginTrial } from "../server/subscription-access.mjs";
import { Pool } from "pg";

const db = new URL(process.env.DATABASE_URL || "http://invalid");
const dir = process.env.DATA_DIR;
if (process.env.V79_EPHEMERAL_CI !== "1" ||
    process.env.GITHUB_ACTIONS !== "true" ||
    db.hostname !== "hub-db" || db.pathname !== "/hub_staging" ||
    dir !== "/app/data") {
  throw new Error("Refusing to seed a non-ephemeral database.");
}
const customerPassword = process.env.STAGE_CUSTOMER_PASSWORD;
const adminPassword = process.env.STAGE_ADMIN_PASSWORD;
if (!customerPassword || customerPassword.length < 24 ||
    !adminPassword || adminPassword.length < 24)
  throw new Error("Synthetic account passwords missing.");
const hashPassword = value => {
  const salt = randomBytes(16).toString("hex");
  return "scrypt:" + salt + ":" +
    scryptSync(value, salt, 64).toString("hex");
};
const trial = beginTrial(new Date());
const appIds = ["app-v79pos","app-ffpro","app-tiquet","app-marketing","app-academy"];
const customerUsers = ["a","b"].map(k => ({
  id:"synthetic-user-"+k, username:"owner-"+k+"@example.invalid",
  email:"owner-"+k+"@example.invalid", fullName:"Synthetic Owner "+k.toUpperCase(),
  password:hashPassword(customerPassword), role:"admin", permissions:["overview","connections","team","security","billing","admin","users"],
  createdAt:new Date().toISOString(),
}));
// The Hub refuses to retrofit the internal owner into customer data.
// Create the complete synthetic founder identity before customers.
const ownerOrgId="synthetic-v79-internal";
const founderId="synthetic-founder";
const founder={
  id:founderId,username:"admin",email:"vision79slu@gmail.com",
  fullName:"Synthetic Platform Founder",role:"admin",
  permissions:["overview","connections","team","security","billing","users"],
  password:hashPassword(adminPassword),createdAt:new Date().toISOString(),
};
const users=[founder,...customerUsers];
const customerOrgs=["a","b"].map(k=>({
  id:"synthetic-customer-"+k,
  slug:"synthetic-customer-"+k,
  status:"active",
  name:"Synthetic Customer "+k.toUpperCase(),
}));
const ownerOrg={id:ownerOrgId,name:"V79 Ephemeral Internal",slug:"v79-ephemeral-internal",status:"active"};
const orgs=[ownerOrg,...customerOrgs];
const memberships=[{organizationId:ownerOrgId,userId:founderId,role:"owner",status:"active"},
  ...customerOrgs.map((o,i)=>({organizationId:o.id,userId:customerUsers[i].id,role:"owner",status:"active"}))];
const appEntitlements = customerOrgs.flatMap(org => appIds.map(appId=>({organizationId:org.id,appId,enabled:true})));
const appTenantMappings = customerOrgs.flatMap(org =>
  ["pos","ffpro","tiquet","marketing"].map(product=>({
    organizationId:org.id,
    appId: product==="pos"?"app-v79pos":"app-"+product,
    // Stage A must be provisioned through the real downstream API, not
    // silently considered ready just because the Hub has a mapping row.
    status:org.id==="synthetic-customer-a"?"pending":"active",
    // A pending mapping must not carry invented downstream IDs.
    // Its identifiers must come solely from real signed provisioning.
    ...(org.id==="synthetic-customer-a"?{}:{
      externalTenantId:["pos","ffpro"].includes(product)?org.id:product+"-"+org.id,
      externalOwnerId:"synthetic-"+product+"-"+org.id,
    }),
  }))
);
const plans = customerOrgs.map((org,i)=>({
  organizationId:org.id,planName:"Synthetic CI trial",
  ...trial,
  ...(i===1?{status:"cancelled"}:{}),
  appIds,
}));
const store = {users, workspace:{companyName:"V79 Ephemeral CI"},
  ecosystemApps:[], organizations:orgs, memberships,
  appEntitlements,appTenantMappings,organizationPlans:plans,
  trialReminderEvents:[],billingOrders:[],billingPaymentEvents:[],
  ownerInvitations:[],teamInvitations:[],passwordResetRequests:[],
  auditEvents:[],
};
mkdirSync(dir,{recursive:true,mode:0o700});
const path=dir+"/v79_store.json";
if(existsSync(path))throw Error("Refusing to overwrite staged Hub data.");
writeFileSync(path,JSON.stringify(store),{mode:0o600,flag:"wx"});
const pool=new Pool({connectionString:process.env.DATABASE_URL,max:1});
try{
  const repo=new PostgresStoreRepository(pool);
  await repo.ensureSchema();
  const result=await repo.initialize(store);
  if(!result.initialized)throw Error("Synthetic Hub database already populated.");
  console.log("SYNTHETIC_POSTGRES_SEEDED two_isolated_tenants=true");
}finally{await pool.end();}
