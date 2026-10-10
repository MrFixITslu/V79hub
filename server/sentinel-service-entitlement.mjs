// Dedicated V79 Sentinel service grant (machine identity, not a human session).
// This endpoint is never a substitute for an approver's separate MFA-backed proof.
import express from "express";
import { verifyPlatformRequest } from "./platform-contract.mjs";
import { organizationCanAccessApp } from "./organization-access.mjs";

export const SERVICE_PATH="/api/platform/sentinel/service/check";
export const MAX_RECHECK_SECONDS=5;
const denied=()=>({allowed:false,validForSeconds:0});
const ID=/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,179}$/;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function validateSentinelServiceEntitlement(store,{request,ownerOrganizationId,tenantReady,now=Date.now()}){
  if(!request || !store || typeof ownerOrganizationId!=="string" ||
    typeof tenantReady!=="function" || !Number.isFinite(now)) return denied();
  const {serviceId,sentinelCustomerId,organizationId,accountId,clientId,action}=request;
  if(serviceId!=="v79-sentinel" || !UUID.test(sentinelCustomerId || "") ||
    ![organizationId,accountId,clientId].every(x=>typeof x==="string" && ID.test(x)) ||
    !["ticket.create","ticket.add_recovery_evidence"].includes(action) ||
    organizationId!==ownerOrganizationId) return denied();
  const org=(store.organizations || []).find(x=>x.id===organizationId && x.status==="active");
  if(!org || !organizationCanAccessApp(store,organizationId,"app-tiquet",ownerOrganizationId,now) ||
    !tenantReady(store,organizationId,ownerOrganizationId)) return denied();
  const grants=Array.isArray(store.sentinelServiceGrants)?store.sentinelServiceGrants:[];
  // Historical revoked grants remain auditable, but only the ONE active grant
  // can authorize. Duplicate active grants fail closed.
  const matches=grants.filter(g=>g.serviceId===serviceId &&
    g.sentinelCustomerId===sentinelCustomerId && g.organizationId===organizationId &&
    g.tiquetAccountId===accountId && g.tiquetClientId===clientId &&
    g.enabled===true && g.status==="active");
  // No grant is ever synthesized from names, human memberships or subscriptions.
  if(matches.length!==1) return denied();
  const grant=matches[0];
  if(grant.enabled!==true || grant.status!=="active" ||
    !Array.isArray(grant.actions) || !grant.actions.includes(action) ||
    grant.revokedAt || typeof grant.expiresAt!=="string") return denied();
  const expires=Date.parse(grant.expiresAt);
  if(!Number.isFinite(expires) || expires<=now || expires-now<1000) return denied();
  return {allowed:true,validForSeconds:Math.min(MAX_RECHECK_SECONDS,Math.floor((expires-now)/1000))};
}

export function sentinelServiceRouter({enabled=false,secret,getStore,getOwnerOrganizationId,tenantReady,now=Date.now}){
  const router=express.Router();
  router.post("/",(req,res)=>{
    res.setHeader("Cache-Control","no-store");
    if(!enabled) return res.status(404).json({error:"Not found"});
    try{
      if(typeof secret!=="string" || secret.length<48 ||
        typeof getStore!=="function" || typeof getOwnerOrganizationId!=="function")
        return res.status(503).json({error:"Service identity not configured"});
      // A browser cookie/JWT cannot take the place of a signed service identity.
      if(req.headers.origin || req.headers.cookie || req.headers.authorization)
        return res.status(403).json(denied());
      const body=req.rawBody;
      if(!Buffer.isBuffer(body) || !body.length || body.length>4096 ||
        !req.is("application/json")) return res.status(400).json(denied());
      if(req.get("x-v79-service-id")!=="v79-tiquet" ||
        !verifyPlatformRequest({
          method:"POST",pathname:SERVICE_PATH,body:body.toString("utf8"),
          timestamp:req.get("x-v79-timestamp") || "",
          signature:req.get("x-v79-signature") || "",secret,
          maxSkewMs:120000
        }))
        return res.status(401).json(denied());
      const decision=validateSentinelServiceEntitlement(getStore(),{
        request:req.body,ownerOrganizationId:getOwnerOrganizationId(),tenantReady,now:now()
      });
      return res.status(200).json(decision);
    }catch{
      return res.status(503).json(denied());
    }
  });
  return router;
}
