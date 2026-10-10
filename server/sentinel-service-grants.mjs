// Isolated owner-pilot machine grant lifecycle. No API route provisions grants.
// Authorized administrator + recent MFA + exact NOC/Tiquet mapping must be
// verified by a separate future route before calling registerSentinelGrant.
import crypto from "node:crypto";

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ACTIONS=new Set(["ticket.create","ticket.add_recovery_evidence"]);
const FAIL="Invalid or unauthorized Sentinel grant";

function validGrant(g){
  return g && typeof g==="object" && !Array.isArray(g) &&
    g.serviceId==="v79-sentinel" && UUID.test(g.sentinelCustomerId||"") &&
    UUID.test(g.organizationId||"") && UUID.test(g.tiquetAccountId||"") &&
    UUID.test(g.tiquetClientId||"") &&
    Array.isArray(g.actions) && g.actions.length>0 && g.actions.length<=2 &&
    g.actions.every(a=>ACTIONS.has(a)) &&
    new Set(g.actions).size===g.actions.length;
}

export function registerSentinelGrant(store,{proposal,ownerOrganizationId,reviewer,
  verifyMapping,now=Date.now()}={}){
  if(!store || !proposal || !validGrant(proposal) ||
     proposal.organizationId!==ownerOrganizationId ||
     !reviewer || reviewer.role!=="owner" || reviewer.mfaConfirmed!==true ||
     typeof reviewer.userId!=="string" || reviewer.userId.length<3 ||
     !Number.isFinite(reviewer.mfaVerifiedAt) ||
     now-reviewer.mfaVerifiedAt<0 || now-reviewer.mfaVerifiedAt>5*60_000 ||
     typeof verifyMapping!=="function" || verifyMapping(proposal)!==true ||
     !Number.isFinite(now) || !Number.isFinite(Date.parse(proposal.expiresAt)) ||
     Date.parse(proposal.expiresAt)<=now ||
     Date.parse(proposal.expiresAt)>now+14*86400_000)
    throw Error(FAIL);
  const old=Array.isArray(store.sentinelServiceGrants)?store.sentinelServiceGrants:[];
  // Never issue a second matching or conflicting grant while one exists.
  if(old.some(g=>g.status==="active" && g.enabled===true && (
     g.sentinelCustomerId===proposal.sentinelCustomerId ||
     (g.organizationId===proposal.organizationId && g.tiquetClientId===proposal.tiquetClientId))))
    throw Error("Existing Sentinel grant must be revoked and reviewed first");
  const grant={id:crypto.randomUUID(),serviceId:"v79-sentinel",
    sentinelCustomerId:proposal.sentinelCustomerId,
    organizationId:proposal.organizationId,
    tiquetAccountId:proposal.tiquetAccountId,tiquetClientId:proposal.tiquetClientId,
    actions:[...proposal.actions],expiresAt:proposal.expiresAt,
    status:"active",enabled:true,revokedAt:null,
    createdAt:new Date(now).toISOString(),approvedBy:reviewer.userId};
  const updated=structuredClone(store);
  updated.sentinelServiceGrants=[...old,grant];
  return {store:updated,grant:structuredClone(grant)};
}

export function revokeSentinelGrant(store,{grantId,reviewer,now=Date.now()}={}){
  if(!store || !UUID.test(grantId||"") || !reviewer ||
      reviewer.role!=="owner" || reviewer.mfaConfirmed!==true ||
      !Number.isFinite(reviewer.mfaVerifiedAt) ||
      now-reviewer.mfaVerifiedAt<0 || now-reviewer.mfaVerifiedAt>5*60_000)
    throw Error(FAIL);
  const updated=structuredClone(store);
  const matches=(updated.sentinelServiceGrants||[]).filter(g=>g.id===grantId);
  if(matches.length!==1 || matches[0].status!=="active" || matches[0].enabled!==true)
    throw Error("No unique active Sentinel grant to revoke");
  matches[0].status="revoked";matches[0].enabled=false;
  matches[0].revokedAt=new Date(now).toISOString();
  matches[0].revokedBy=reviewer.userId;
  return updated;
}

// Only accept exact, explicitly valid shapes for persisted data. Anything
// suspicious makes the receiver reject grants rather than repair stale state.
export function validateSentinelGrantCollection(value){
  if(!Array.isArray(value) || value.length>20) throw Error("Unsafe persisted Sentinel grants");
  const ids=new Set(),activeCustomers=new Set();
  for(const g of value){
    if(!validGrant(g) || !UUID.test(g.id||"") ||
       !["active","revoked"].includes(g.status) || typeof g.enabled!=="boolean" ||
       (g.status==="active")!==g.enabled ||
       !Number.isFinite(Date.parse(g.expiresAt)) || ids.has(g.id) ||
       (g.status==="active" && activeCustomers.has(g.sentinelCustomerId)))
      throw Error("Unsafe persisted Sentinel grants");
    ids.add(g.id);if(g.status==="active") activeCustomers.add(g.sentinelCustomerId);
  }
  return value.map(x=>({...x,actions:[...x.actions]}));
}
