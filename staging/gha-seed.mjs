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
if (!customerPassword || customerPassword.length < 24)
  throw new Error("Synthetic customer password missing.");
const hashPassword = value => {
  const salt = randomBytes(16).toString("hex");
  return "scrypt:" + salt + ":" +
    scryptSync(value, salt, 64).toString("hex");
};
const trial = beginTrial(new Date());
const appIds = ["app-v79pos","app-ffpro","app-tiquet","app-marketing","app-academy"];
const users = ["a","b"].map(k => ({
  id:"synthetic-user-"+k, username:"owner-"+k+"@example.invalid",
  email:"owner-"+k+"@example.invalid", fullName:"Synthetic Owner "+k.toUpperCase(),
  password:hashPassword(customerPassword), role:"user", permissions:[],
  createdAt:new Date().toISOString(),
}));
const orgs = ["a","b"].map(k=>({id:"synthetic-customer-"+k,status:"active",name:"Synthetic Customer "+k.toUpperCase()}));
const memberships = orgs.map((o,i)=>({organizationId:o.id,userId:users[i].id,role:"owner",status:"active"}));
const appEntitlements = orgs.flatMap(org => appIds.map(appId=>({organizationId:org.id,appId,enabled:true})));
const appTenantMappings = orgs.flatMap(org =>
  ["pos","ffpro","tiquet","marketing"].map(product=>({
    organizationId:org.id,
    appId: product==="pos"?"app-v79pos":"app-"+product,
    status:"active",
    externalTenantId:["pos","ffpro"].includes(product)?org.id:product+"-"+org.id,
    externalOwnerId:"synthetic-"+product+"-"+org.id,
  }))
);
const plans = orgs.map((org,i)=>({
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
