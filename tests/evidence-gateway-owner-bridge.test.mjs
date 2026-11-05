import test from 'node:test';import assert from 'node:assert/strict';import express from 'express';
import {registerEvidenceGatewayBridge} from '../server/evidence-gateway-owner-bridge.mjs';
test('Gateway consent is exact, fresh-MFA, same-origin and bound to the real owner',async t=>{
 const now=Date.now(),token='SYNTHETIC-BRIDGE-TOKEN-NOT-A-PRODUCTION-CREDENTIAL';const id='a'.repeat(43),hash='b'.repeat(64);let calls=[],redirect='https://chatgpt.com/connector_platform_oauth_redirect?code=synthetic-code',active=true;
 const app=express();app.use(express.json());app.use((req,res,next)=>{req.user={mfaVerifiedAt:now-(req.get('x-stale')?360000:0)};next();});
 registerEvidenceGatewayBridge(app,{ownerMfaContext:req=>req.get('x-owner')==='yes'?{userId:'synthetic-owner'}:null,sameOrigin:req=>req.get('origin')==='https://hub.v79sl.com',readBridgeToken:()=>token,ownerActive:()=>active,ownerSubject:()=>'synthetic-owner',gatewayBaseUrl:'http://172.25.0.1:8765',now:()=>now,fetchImpl:async(url,options)=>{calls.push({url:String(url),options});return new Response(JSON.stringify(String(url).includes('/internal/request')?{requestId:id,resource:'https://evidence.v79sl.com/mcp',scope:'evidence:read',clientIdHash:hash}:String(url).includes('/consent')?{redirect}:{revoked:true}));}});
 const server=app.listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));t.after(()=>new Promise(r=>server.close(r)));const base='http://127.0.0.1:'+server.address().port;
 const request=(path,body,headers={})=>fetch(base+path,{redirect:'manual',method:body?'POST':'GET',headers:{...(body?{'content-type':'application/json'}:{}),...headers},...(body?{body:JSON.stringify(body)}:{})});const owner={'x-owner':'yes',origin:'https://hub.v79sl.com'};
 assert.equal((await request('/api/agent/evidence-gateway/authorize?request='+id)).status,403);assert.equal(calls.length,0);
 const consent=await request('/api/agent/evidence-gateway/authorize?request='+id,undefined,owner);assert.equal(consent.status,200);assert.match(await consent.text(),/Allow read-only connection/);assert.equal(consent.headers.get('x-frame-options'),'DENY');assert.equal(consent.headers.get('referrer-policy'),'same-origin');assert.match(consent.headers.get('content-security-policy'),/form-action 'self' https:\/\/chatgpt\.com;/);
 const stale=await request('/api/agent/evidence-gateway/authorize?request='+id,undefined,{...owner,'x-stale':'yes'});assert.doesNotMatch(await stale.text(),/name="approved"/);
 calls=[];const body={requestId:id,approved:'true'};
 for(const [headers,b,status] of [[{'x-owner':'yes'},body,403],[{...owner,origin:'null'},body,403],[{...owner,origin:'https://evil.invalid'},body,403],[{...owner,'x-stale':'yes'},body,403],[owner,{...body,subject:'foreign'},400],[owner,{...body,approved:true},400]])assert.equal((await request('/api/agent/evidence-gateway/authorize',b,headers)).status,status);
 assert.equal(calls.length,0);
 const accepted=await request('/api/agent/evidence-gateway/authorize',body,owner);assert.equal(accepted.status,303);assert.equal(accepted.headers.get('location'),redirect);assert.deepEqual(JSON.parse(calls[0].options.body),{requestId:id,subject:'synthetic-owner',approved:true});
 redirect='https://evil.invalid/callback?code=synthetic';assert.equal((await request('/api/agent/evidence-gateway/authorize',body,owner)).status,409);
 assert.equal((await request('/internal/evidence-gateway/owner-active')).status,403);assert.equal((await request('/internal/evidence-gateway/owner-active',undefined,{'x-v79-gateway-internal':token,origin:'https://evil.invalid'})).status,403);
 let state=await request('/internal/evidence-gateway/owner-active',undefined,{'x-v79-gateway-internal':token});assert.deepEqual(await state.json(),{active:true});active=false;state=await request('/internal/evidence-gateway/owner-active',undefined,{'x-v79-gateway-internal':token});assert.deepEqual(await state.json(),{active:false});
 assert.equal((await request('/api/agent/evidence-gateway/revoke',{confirmation:'wrong'},owner)).status,400);assert.equal((await request('/api/agent/evidence-gateway/revoke',{confirmation:'REVOKE_GATEWAY_ACCESS'},owner)).status,200);
});
test('Gateway bridge cannot target arbitrary URLs or attach credentials to them',()=>{
 for(const url of ['https://evil.invalid/','http://172.25.0.1:8765/evil','http://user:secret@172.25.0.1:8765/','http://127.0.0.1:8765/'])assert.throws(()=>registerEvidenceGatewayBridge({}, {gatewayBaseUrl:url}),/Invalid private Gateway/);
});
