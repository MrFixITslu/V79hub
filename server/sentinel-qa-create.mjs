import { randomUUID } from "node:crypto";
import { previewSentinelCleanup, SentinelCleanupError } from "./sentinel-qa-cleanup.mjs";

const deny = (message) => {throw new SentinelCleanupError("CREATE_BLOCKED",message);};
const idFormat = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
const roles = ["owner","staff","viewer"];

/**
 * Creates only Hub-local, unmapped Sentinel synthetic identities in a cloned store.
 * No external app tenant, entitlement, payment, email, or invitation can be created here.
 * Usernames use the reserved .invalid DNS TLD to avoid contacting real email users.
 */
/** @param {any} store @param {any} options */
export function stageSentinelQaCreation(store, {
  operatorUserId, organizationId=randomUUID(), createdAt=new Date().toISOString(),
  syntheticAccounts, markerId=randomUUID(),
} = {}) {
  if(!store || typeof store !== "object" ||
     !Array.isArray(store.users) || !Array.isArray(store.organizations) ||
     !Array.isArray(store.memberships) || !Array.isArray(store.auditEvents)) {
    deny("Hub store is incomplete");
  }
  if(typeof operatorUserId !== "string" || !operatorUserId ||
     !idFormat.test(organizationId) || !idFormat.test(markerId) ||
     Number.isNaN(Date.parse(createdAt)) ||
     !Array.isArray(syntheticAccounts) || syntheticAccounts.length !== 3) {
    deny("Synthetic tenant creation requires exact operator and three identities");
  }
  const ids = new Set();
  for(let i=0;i<syntheticAccounts.length;i++) {
    const account=syntheticAccounts[i];
    if(account.role!==roles[i] || !idFormat.test(account.id) ||
       typeof account.passwordHash!=="string" ||
       !account.passwordHash.startsWith("scrypt:") ||
       account.passwordHash.length < 100 ||
       account.id===operatorUserId || ids.has(account.id)) {
      deny("Invalid or reused synthetic identity");
    }
    ids.add(account.id);
  }
  if(store.organizations.some(v=>v.id===organizationId || v.name===`Sentinel-QA-${organizationId}`) ||
     store.users.some(u=>ids.has(u.id)) ||
     store.memberships.some(m=>ids.has(m.userId)) ||
     store.auditEvents.some(e=>e.id===markerId)) {
    deny("A generated synthetic identity or organization already exists");
  }
  if (store.organizations.some(v => typeof v.name === "string" && v.name.startsWith("Sentinel-QA-"))) {
    deny("A Sentinel QA organization already exists; verify cleanup before creating another");
  }
  const name = `Sentinel-QA-${organizationId}`;
  const nextStore=structuredClone(store);
  nextStore.organizations.push({id:organizationId,name,slug:name.toLowerCase(),
                                status:"active",createdAt});
  const names=[];
  for(let i=0;i<syntheticAccounts.length;i++) {
    const a=syntheticAccounts[i];
    const username=`test-${organizationId.slice(0,8)}-${roles[i]}@sentinel-qa.invalid`;
    if(nextStore.users.some(u=>u.username.toLowerCase()===username.toLowerCase())) deny("Synthetic username collision");
    const profile={id:a.id,username,password:a.passwordHash,
                   fullName:`Sentinel QA ${roles[i]}`,
                   role:i===0?"admin":a.role,
                   // No admin/billing/security capabilities are needed for synthetic login smoke tests.
                   permissions:["overview"],createdAt};
    nextStore.users.push(profile);
    nextStore.memberships.push({organizationId,userId:a.id,role:a.role,
      permissions:profile.permissions,status:"active",createdAt});
    names.push({userId:a.id,username,role:a.role});
  }
  nextStore.auditEvents.push({
    id:markerId,type:"sentinel_qa_tenant_created",actorUserId:operatorUserId,
    organizationId,createdAt,
    details:{purpose:"synthetic_qa_only",organizationId,
             syntheticUserIds:syntheticAccounts.map(a=>a.id)}
  });
  const preview=previewSentinelCleanup(nextStore,{organizationId,operatorUserId});
  return {nextStore,organization:{id:organizationId,name,slug:name.toLowerCase()},
          syntheticUsers:names,markerId,cleanupPreviewHash:preview.previewHash};
}
