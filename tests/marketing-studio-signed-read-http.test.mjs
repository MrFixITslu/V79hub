import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import {createHash} from 'node:crypto';
import {marketingStudioApprovalRouter} from '../server/marketing-studio-approval-routes.mjs';
const media=Buffer.from('synthetic-creative-media-for-hub-hmac-boundary-test');
const digest=createHash('sha256').update(media).digest('hex');
const pkg='81ebfd64-d6cd-4df2-a198-5fc1fba42622';
const asset='46f97b4c-815a-492b-aaed-ed7335a0db73';
async function local(router,testFn){
  const app=express();app.use(express.json());app.use('/api/studio/marketing',router);
  const server=app.listen(0,'127.0.0.1');
  await new Promise(resolve=>server.once('listening',resolve));
  const url='http://127.0.0.1:'+server.address().port;
  try{await testFn(url);}
  finally{await new Promise(resolve=>server.close(resolve));}
}
test('Fresh Hub MFA can read current exact review and verified binary; no tenant or user IDs from browser',async()=>{
 const calls=[],now=Date.now();
 const router=marketingStudioApprovalRouter({
   now:()=>now,enabled:()=>false,readEnabled:()=>true,sameOrigin:()=>true,
   approverContext:()=>({organizationId:'org-from-session',actorHubUserId:'user-from-session',mfaVerifiedAt:now}),
   forward:async()=>{throw Error('No write allowed');},
   forwardRead:async x=>{
     calls.push(x);
     if(x.request.action==='asset')return {status:200,body:{mime:'image/png',sha256:digest,base64:media.toString('base64')}};
     return {status:200,body:{packages:[]}};
   }
 });
 await local(router,async base=>{
   const list=await fetch(base+'/api/studio/marketing/inbox');
   assert.equal(list.status,200);
   const binary=await fetch(base+'/api/studio/marketing/media/'+pkg+'/'+asset);
   assert.equal(binary.status,200);
   assert.deepEqual(Buffer.from(await binary.arrayBuffer()),media);
   assert.deepEqual(calls.map(x=>x.request.action),['list','asset']);
   assert.deepEqual(calls[0],{organizationId:'org-from-session',actorHubUserId:'user-from-session',request:{action:'list'}});
   const malformed=await fetch(base+'/api/studio/marketing/media/'+pkg+'/forged');
   assert.equal(malformed.status,404);assert.equal(calls.length,2);
 });
});
test('Stale MFA and modified image digest fail closed without backend requests',async()=>{
 const now=Date.now();let calls=0;
 const make=(mfaTime,corrupt)=>marketingStudioApprovalRouter({
   now:()=>now,enabled:()=>false,readEnabled:()=>true,sameOrigin:()=>true,
   approverContext:()=>({organizationId:'org',actorHubUserId:'user',mfaVerifiedAt:mfaTime}),
   forward:async()=>{throw Error('Never publish');},
   forwardRead:async()=>{
     calls++;return {status:200,body:{mime:'image/png',sha256:corrupt?'0'.repeat(64):digest,
       base64:media.toString('base64')}};
   }
 });
 await local(make(now-360000,false),async base=>{
   const r=await fetch(base+'/api/studio/marketing/inbox');assert.equal(r.status,403);
 });
 assert.equal(calls,0);
 await local(make(now,true),async base=>{
   const r=await fetch(base+'/api/studio/marketing/media/'+pkg+'/'+asset);assert.equal(r.status,404);
 });
 assert.equal(calls,1);
});
test('Approved request with lost backend response reports uncertainty, never retries',async()=>{
 let calls=0;const now=Date.now();
 const route=marketingStudioApprovalRouter({
  now:()=>now,enabled:()=>true,readEnabled:()=>false,sameOrigin:()=>true,
  approverContext:()=>({organizationId:'org',actorHubUserId:'user',mfaVerifiedAt:now}),
  forward:async()=>{calls++;throw Error('Response lost after provider may commit');}
 });
 await local(route,async base=>{
  const r=await fetch(base+'/api/studio/marketing/approve',{
    method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({creatorUserId:'synthetic',campaignId:'campaign-synthetic',packageId:pkg,
      exactDigest:'a'.repeat(64),confirmExactPublication:true})});
  assert.equal(r.status,503);
  const data=await r.json();assert.match(data.error,/uncertain/i);
  assert.equal(calls,1);
 });
});
