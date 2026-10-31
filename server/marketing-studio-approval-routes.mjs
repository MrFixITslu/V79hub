import express from 'express';
import {randomUUID,createHash} from 'node:crypto';
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
export function marketingStudioApprovalRouter({approverContext,sameOrigin,enabled,readEnabled=enabled,forward,forwardRead,now=Date.now}){
  const router=express.Router();
  const guardedRead=(req,res)=>{
    res.setHeader('Cache-Control','no-store');
    res.setHeader('X-Content-Type-Options','nosniff');
    res.setHeader('Cross-Origin-Resource-Policy','same-origin');
    const c=readEnabled()?approverContext(req):null;
    return c&&Number.isFinite(c.mfaVerifiedAt)&&now()-c.mfaVerifiedAt>=0&&
      now()-c.mfaVerifiedAt<=300000?c:null;
  };
  for(const action of ['list','history']){
    router.get(action==='list'?'/inbox':'/history',async(req,res)=>{
      const c=guardedRead(req,res);
      if(!c)return res.status(403).json({error:'Fresh Hub MFA and marketing membership required'});
      try{
        const result=await forwardRead({organizationId:c.organizationId,
          actorHubUserId:c.actorHubUserId,request:{action}});
        return res.status(result.status).json(result.body);
      }catch{return res.status(503).json({error:'Signed Studio read temporarily unavailable'});}
    });
  }
  router.get('/media/:packageId/:assetId',async(req,res)=>{
    const c=guardedRead(req,res);
    if(!c||!uuid.test(req.params.packageId)||!uuid.test(req.params.assetId))
      return res.status(404).end();
    try{
      const result=await forwardRead({organizationId:c.organizationId,
        actorHubUserId:c.actorHubUserId,request:{action:'asset',
          packageId:req.params.packageId,assetId:req.params.assetId}});
      const m=result.body;
      if(result.status!==200||!['image/png','image/jpeg','video/mp4'].includes(m?.mime)||
         typeof m?.sha256!=='string'||!digest.test(m.sha256)||
         typeof m?.base64!=='string'||m.base64.length>10_000_000||
         !/^[A-Za-z0-9+/]+={0,2}$/.test(m.base64))return res.status(404).end();
      const bytes=Buffer.from(m.base64,'base64');
      if(bytes.length>7*1024*1024||
         createHash('sha256').update(bytes).digest('hex')!==m.sha256)
        return res.status(404).end();
      res.setHeader('Content-Security-Policy',"default-src 'none'");
      return res.type(m.mime).send(bytes);
    }catch{return res.status(404).end();}
  });
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
