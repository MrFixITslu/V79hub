import {Router} from 'express';
import {createHash,randomUUID} from 'node:crypto';
import {priceSelection,pricingCatalog} from '../shared/pricing-catalog.mjs';
const digest=quote=>createHash('sha256').update(JSON.stringify(quote)).digest('hex');
const safeRequest=r=>({id:r.id,status:r.status,quote:r.quote,createdAt:r.createdAt,updatedAt:r.updatedAt,reviewNote:r.reviewNote||null});
const reply=(status,body)=>({status,body});
export function pricingRequestRouter({readStore,ledger,sameOrigin,context,isOperator=false,now=()=>new Date().toISOString()}){
 const router=Router();
 router.use((req,res,next)=>{res.setHeader('Cache-Control','no-store');const c=context(req);if(!c?.organizationId||!c?.userId)return res.status(403).json({error:'Authenticated billing workspace required.'});req.pricingContext=c;next()});
 if(!isOperator){
  router.get('/catalog',(_req,res)=>res.json(pricingCatalog()));
  router.post('/quote',(req,res)=>{
   if(!sameOrigin(req))return res.status(403).json({error:'Same-origin request required.'});
   try{const quote=priceSelection(req.body);return res.json({quote,digest:digest(quote)})}catch(e){return res.status(409).json({error:e.message})}
  });
 }
 router.get('/requests',async(req,res)=>{
  try{
   const state=await ledger.read(),store=readStore(),scope=req.pricingContext;
   const requests=state.requests.filter(r=>isOperator||r.organizationId===scope.organizationId).slice(-100).reverse().map(r=>({...safeRequest(r),...(isOperator?{organizationId:r.organizationId,organization:store.organizations.find(o=>o.id===r.organizationId)?.name||'Workspace'}:{})}));
   return res.json({requests,automaticActivation:false});
  }catch{return res.status(503).json({error:'Saved pricing requests unavailable. Do not resubmit until status is checked.'})}
 });
 if(!isOperator)router.post('/requests',async(req,res)=>{
  if(!sameOrigin(req))return res.status(403).json({error:'Same-origin request required.'});
  try{
   const b=req.body,c=req.pricingContext;
   if(!b||typeof b!=='object'||Array.isArray(b)||Object.keys(b).sort().join('|')!=='digest|idempotencyKey|selection'||typeof b.idempotencyKey!=='string'||!/^pricing-[a-f0-9-]{36}$/.test(b.idempotencyKey)||typeof b.digest!=='string')return res.status(400).json({error:'Exact reviewed pricing selection required.'});
   const quote=priceSelection(b.selection),hash=digest(quote);
   if(hash!==b.digest)return res.status(409).json({error:'The price changed. Review the selection again.'});
   const result=await ledger.transact(state=>{
    const organization=readStore().organizations.find(o=>o.id===c.organizationId);
    if(!organization||organization.status!=='active'||c.internalOwner)return reply(403,{error:'Customer billing workspace required.'});
    const prior=state.requests.find(r=>r.organizationId===c.organizationId&&r.idempotencyKey===b.idempotencyKey);
    if(prior)return prior.digest===hash?reply(200,{request:safeRequest(prior),replayed:true,accessChanged:false}):reply(409,{error:'This request key already belongs to different details.'});
    if(state.requests.some(r=>r.organizationId===c.organizationId&&r.status==='pending'))return reply(409,{error:'A plan request is already awaiting review. Check your saved requests before submitting another.'});
    if(state.requests.length>=5000||state.requests.filter(r=>r.organizationId===c.organizationId).length>=100)return reply(409,{error:'Contact V79 Digital to review existing pricing requests.'});
    const time=now(),request={id:randomUUID(),organizationId:c.organizationId,actorUserId:c.userId,idempotencyKey:b.idempotencyKey,digest:hash,quote,status:'pending',createdAt:time,updatedAt:time};
    state.requests.push(request);state.events.push({id:randomUUID(),type:'pricing_requested',requestId:request.id,organizationId:c.organizationId,actorUserId:c.userId,digest:hash,createdAt:time});
    return reply(201,{request:safeRequest(request),accessChanged:false,charged:false});
   });return res.status(result.status).json(result.body);
  }catch(e){if(e?.message?.startsWith('Choose a valid')||e?.message?.startsWith('Pricing changed'))return res.status(409).json({error:e.message});return res.status(503).json({error:'Request outcome needs checking. Refresh saved requests before retrying.'})}
 });
 if(isOperator)router.post('/requests/:id/review',async(req,res)=>{
  if(!sameOrigin(req))return res.status(403).json({error:'Same-origin request required.'});
  try{
   const b=req.body;if(!b||Object.keys(b).sort().join('|')!=='decision|expectedUpdatedAt|note'||!['reviewed','declined'].includes(b.decision)||typeof b.note!=='string'||b.note.trim().length<5||b.note.length>500)return res.status(400).json({error:'An exact review decision and note are required.'});
   const result=await ledger.transact(state=>{
    const r=state.requests.find(x=>x.id===req.params.id);
    if(!r)return reply(404,{error:'Request not found.'});
    if(r.status!=='pending'||r.updatedAt!==b.expectedUpdatedAt)return reply(409,{error:'Request changed. Refresh before reviewing.'});
    r.status=b.decision;r.reviewNote=b.note.trim();r.updatedAt=now();r.reviewedBy=req.pricingContext.userId;
    state.events.push({id:randomUUID(),type:'pricing_'+b.decision,requestId:r.id,organizationId:r.organizationId,actorUserId:req.pricingContext.userId,createdAt:r.updatedAt});
    return reply(200,{request:safeRequest(r),accessChanged:false,charged:false});
   });return res.status(result.status).json(result.body);
  }catch{return res.status(503).json({error:'Review outcome needs checking. Refresh before retrying.'})}
 });return router;
}
