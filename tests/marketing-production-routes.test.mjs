import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import { marketingProductionRouter,marketingWorkerAuthorization } from '../server/marketing-production-routes.mjs';

test('production bridge binds real founder context and fresh MFA; never forwards caller identity',async()=>{
  const app=express();app.use(express.json());let calls=0,forwarded;
  app.use((req,_res,next)=>{req.user={mfaVerifiedAt:req.get('fresh')==='yes'?10000:0};next();});
  app.use('/production',marketingProductionRouter({now:()=>10000,enabled:()=>true,sameOrigin:req=>req.get('origin')==='https://hub.test',
    ownerContext:req=>req.get('owner')==='yes'?{organizationId:'real-owner-org',userId:'real-owner-user'}:null,
    forward:async body=>{calls++;forwarded=body;return {status:200,body:{ok:true}};}}));
  const server=app.listen(0,'127.0.0.1');await new Promise(r=>server.on('listening',r));
  const url='http://127.0.0.1:'+server.address().port+'/production';
  const call=(body,extra={})=>fetch(url,{method:'POST',headers:{'content-type':'application/json','origin':'https://hub.test',...extra},body:JSON.stringify(body)});
  try{
    assert.equal((await call({action:'list'})).status,403);
    assert.equal((await call({action:'queue'},{owner:'yes',origin:'https://attacker.test'})).status,403);
    assert.equal((await call({action:'list',organizationId:'other'},{owner:'yes'})).status,400);
    assert.equal((await call({action:'publish-anything'},{owner:'yes'})).status,400);
    assert.equal(calls,0);
    assert.equal((await call({action:'decision',digest:'exact'},{owner:'yes',fresh:'yes'})).status,200);
    assert.equal(forwarded.organizationId,'real-owner-org');assert.equal(forwarded.actorHubUserId,'real-owner-user');assert.equal(forwarded.mfaVerifiedAt,10000);
    assert.equal((await call({action:'approve_batch',batchDigest:'b'.repeat(64)},{owner:'yes',fresh:'yes'})).status,200);
    assert.equal(forwarded.request.action,'approve_batch');
  }finally{await new Promise(r=>server.close(r));}
});

test('background authorization checks exact current founder without caching an old permit',async()=>{
  let permitted=true;const app=express();app.use(express.json());
  app.post('/worker',marketingWorkerAuthorization({enabled:()=>true,verifySignature:req=>req.get('signature')==='valid',
    allowed:body=>permitted&&body.organizationId==='owner-org'&&body.actorHubUserId==='scoped-owner'}));
  const server=app.listen(0,'127.0.0.1');await new Promise(r=>server.on('listening',r));const url='http://127.0.0.1:'+server.address().port+'/worker';
  const call=(body,headers={})=>fetch(url,{method:'POST',headers:{'content-type':'application/json','x-v79-service-id':'v79-marketing',signature:'valid',...headers},body:JSON.stringify(body)});
  try{
    assert.equal((await call({organizationId:'owner-org',actorHubUserId:'scoped-owner'},{cookie:'not-allowed'})).status,401);
    assert.equal((await call({organizationId:'owner-org',actorHubUserId:'scoped-owner'},{signature:'invalid'})).status,401);
    assert.equal((await (await call({organizationId:'other-org',actorHubUserId:'scoped-owner'})).json()).allowed,false);
    assert.equal((await (await call({organizationId:'owner-org',actorHubUserId:'scoped-owner'})).json()).allowed,true);
    permitted=false;assert.equal((await (await call({organizationId:'owner-org',actorHubUserId:'scoped-owner'})).json()).allowed,false);
  }finally{await new Promise(r=>server.close(r));}
});

test('expired MFA and disabled feature cannot forward mutations',async()=>{
  let calls=0;const app=express();app.use(express.json());
  app.use((req,_res,next)=>{req.user={mfaVerifiedAt:1};next();});
  app.use('/expired',marketingProductionRouter({now:()=>400000,enabled:()=>true,sameOrigin:()=>true,ownerContext:()=>({userId:'owner',organizationId:'org'}),forward:async()=>{calls++;}}));
  app.use('/disabled',marketingProductionRouter({enabled:()=>false,sameOrigin:()=>true,ownerContext:()=>({userId:'owner',organizationId:'org'}),forward:async()=>{calls++;}}));
  const server=app.listen(0,'127.0.0.1');await new Promise(r=>server.on('listening',r));const base='http://127.0.0.1:'+server.address().port;
  try{for(const [route,status] of [['expired',403],['disabled',503]])assert.equal((await fetch(base+'/'+route,{method:'POST',headers:{'content-type':'application/json'},body:'{"action":"configure"}'})).status,status);assert.equal(calls,0);}
  finally{await new Promise(r=>server.close(r));}
});
