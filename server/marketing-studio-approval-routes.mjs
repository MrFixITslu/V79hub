import express from 'express';
import {randomUUID} from 'node:crypto';
const digest=/^[a-f0-9]{64}$/;
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;

export function validStudioApprovalBody(body){
  if(!body||typeof body!=='object'||Array.isArray(body)||
     Object.keys(body).sort().join(',')!=='campaignId,confirmExactPublication,creatorUserId,exactDigest,packageId')
    return false;
  return typeof body.creatorUserId==='string'&&body.creatorUserId.length>0&&body.creatorUserId.length<=180&&
    typeof body.campaignId==='string'&&body.campaignId.length>0&&body.campaignId.length<=180&&
    typeof body.packageId==='string'&&uuid.test(body.packageId)&&
    typeof body.exactDigest==='string'&&digest.test(body.exactDigest)&&
    body.confirmExactPublication===true;
}
export function marketingStudioApprovalRouter({approverContext,sameOrigin,enabled,forward,now=Date.now}){
  const router=express.Router();
  router.post('/approve',async(req,res)=>{
    res.setHeader('Cache-Control','no-store');
    // Fail closed until both Hub and Marketing enable the paired gated release.
    if(!enabled())return res.status(503).json({error:'Studio publication approval is not enabled'});
    if(!sameOrigin(req))return res.status(403).json({error:'Same-origin approval required'});
    const context=approverContext(req);
    if(!context||!context.organizationId||!context.actorHubUserId||
       !Number.isFinite(context.mfaVerifiedAt)||now()-context.mfaVerifiedAt<0||
       now()-context.mfaVerifiedAt>300000)
      return res.status(403).json({error:'Fresh Hub MFA and current owner/manager membership required'});
    if(!validStudioApprovalBody(req.body))
      return res.status(400).json({error:'Exact reviewed assets, account and schedule must be confirmed'});
    try{
      const envelope={organizationId:context.organizationId,actorHubUserId:context.actorHubUserId,
        mfaVerifiedAt:context.mfaVerifiedAt,requestNonce:randomUUID(),request:req.body};
      const result=await forward(envelope);
      return res.status(result.status).json(result.body);
    }catch{return res.status(503).json({
      error:'Exact approval status is uncertain. Review Marketing history before attempting again.'});}
  });
  return router;
}
