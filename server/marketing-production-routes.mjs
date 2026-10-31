import express from 'express';
import { randomUUID } from 'node:crypto';
// Browser never supplies tenant identity, MFA attestation, service URLs or keys.
export function marketingProductionRouter({ownerContext,sameOrigin,enabled,forward,now=Date.now}) {
  const router=express.Router();
  router.post('/',async(req,res)=>{
    res.setHeader('Cache-Control','no-store');
    const context=ownerContext(req);
    if(!context)return res.status(403).json({error:'MFA-verified founder required'});
    if(!enabled())return res.status(503).json({error:'Marketing production is not enabled'});
    if(!sameOrigin(req))return res.status(403).json({error:'Same-origin request required'});
    const action=req.body?.action;
    if(!['list','asset','configure','queue','regenerate','decision','approve_batch','pause','cancel'].includes(action))return res.status(400).json({error:'Unknown production action'});
    const at=req.user?.mfaVerifiedAt;
    if(!['list','asset'].includes(action)&&(!Number.isFinite(at)||now()-at<0||now()-at>300000))
      return res.status(403).json({error:'Sign in with MFA again before approving marketing changes'});
    // Reject caller attempts to replace the trusted identity boundary.
    if(['organizationId','actorHubUserId','mfaVerifiedAt','requestNonce','token','secret','url'].some(k=>Object.hasOwn(req.body,k)))
      return res.status(400).json({error:'Caller-supplied identity or credentials forbidden'});
    try{
      const result=await forward({organizationId:context.organizationId,actorHubUserId:context.userId,
        mfaVerifiedAt:Number.isFinite(at)?at:null,requestNonce:randomUUID(),request:req.body});
      return res.status(result.status).json(result.body);
    }catch{return res.status(503).json({error:'Marketing production unavailable. Refresh current state before retrying a mutation.'});}
  });
  return router;
}

export function marketingWorkerAuthorization({enabled,verifySignature,allowed}) {
  return (req,res)=>{
    res.setHeader('Cache-Control','no-store');
    if(!enabled())return res.status(503).json({allowed:false});
    if(req.get('origin')||req.get('cookie')||req.get('x-v79-service-id')!=='v79-marketing'||!verifySignature(req))
      return res.status(401).json({allowed:false});
    if(!req.body||Object.keys(req.body).sort().join(',')!=='actorHubUserId,organizationId'||
       typeof req.body.organizationId!=='string'||typeof req.body.actorHubUserId!=='string')
      return res.status(400).json({allowed:false});
    return res.json({allowed:allowed(req.body)===true,cacheSeconds:0});
  };
}
