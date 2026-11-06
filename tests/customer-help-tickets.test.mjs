import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import express from 'express';
import {createHelpTicketBridge,validateHelpTicket,HELP_SUPPORT_PATH} from '../server/customer-help-tickets.mjs';
import {verifyPlatformRequest} from '../server/platform-contract.mjs';
import {customerHelpRouter} from '../server/customer-help-routes.mjs';
const secret='s'.repeat(64),actor={userId:'customer-a',organizationId:'workspace-a'};
const request=()=>({idempotencyKey:crypto.randomUUID(),app:'hub',kind:'error',summary:'The submit button remains disabled after saving.'});
const env={V79_HELP_SUPPORT_ENABLED:'1',V79_HELP_SUPPORT_SHARED_SECRET:secret,V79_HELP_SUPPORT_TIQUET_URL:'https://tiquet.example.invalid'};
const identity=()=>({name:'Synthetic Customer',email:'customer@example.invalid',workspace:'Synthetic Workspace'});
const ack=body=>({accepted:true,requestId:JSON.parse(body).requestId,reference:'HELP-'+crypto.randomUUID(),priority:'high'});
test('signed bridge binds caller identity and retry, sends no browser credential and accepts only a matching committed receipt',async()=>{
 const seen=[];const bridge=createHelpTicketBridge({env,identity,fetcher:async(url,options)=>{seen.push({url,options});return Response.json(ack(options.body),{status:201});}});
 const body=request(),a=await bridge.submit(body,actor);assert.equal(a.submitted,true);assert.equal(a.priority,'high');
 await bridge.submit(body,actor);await bridge.submit(body,{...actor,userId:'customer-b'});await bridge.submit(body,{...actor,organizationId:'workspace-b'});
 const events=seen.map(x=>JSON.parse(x.options.body));
 assert.equal(events[0].requestId,events[1].requestId);assert.notEqual(events[0].requestId,events[2].requestId);assert.notEqual(events[0].requestId,events[3].requestId);
 assert.deepEqual(events[0].requester,{...actor,...identity()});assert.equal(events[0].summary,body.summary);
 assert.equal('priority'in events[0],false);assert.equal('accountId'in events[0],false);
 const {options,url}=seen[0];assert.equal(new URL(url).pathname,HELP_SUPPORT_PATH);assert.equal(options.redirect,'error');
 assert.equal(options.headers.cookie,undefined);assert.equal(options.headers.authorization,undefined);assert.equal(options.headers.origin,undefined);
 assert(verifyPlatformRequest({method:'POST',pathname:HELP_SUPPORT_PATH,timestamp:options.headers['x-v79-timestamp'],body:options.body,signature:options.headers['x-v79-signature'],secret}));
});
test('bridge configuration, strict schema, errors and oversized or mismatched upstream acknowledgements fail closed',async()=>{
 for(const url of ['http://evil.test','https://name:password@tiquet.test','https://tiquet.test/private','https://tiquet.test/?x=y'])assert.equal(createHelpTicketBridge({env:{...env,V79_HELP_SUPPORT_TIQUET_URL:url},identity}).enabled,false);
 assert.equal(createHelpTicketBridge({env:{},identity}).enabled,false);
 const body=request();for(const extra of ['priority','accountId','userId','email','destination'])assert.ok(validateHelpTicket({...body,[extra]:'forged'}));
 for(const patch of [{summary:'short'},{summary:'abc\u0000'.repeat(10)},{app:'owner-assistant'},{kind:'critical'},{idempotencyKey:'guess'}])assert.ok(validateHelpTicket({...body,...patch}));
 for(const fetcher of [async()=>{throw Error('private internal URL');},async()=>Response.json({accepted:true,priority:'high',requestId:'other',reference:'HELP-'+crypto.randomUUID()}),async()=>Response.json({error:'secret internal error'},{status:503}),async()=>new Response('x'.repeat(3000)),async()=>Response.json({accepted:true,requestId:'x',reference:'https://evil.test'})]){
  await assert.rejects(createHelpTicketBridge({env,identity,fetcher}).submit(body,actor),e=>e.status===503&&!e.message.includes('private internal')&&!e.message.includes('secret internal'));
 }
 let sent=false;await assert.rejects(createHelpTicketBridge({env,identity,fetcher:async()=>{sent=true;throw Error();}}).submit({...body,summary:'語'.repeat(12000)},actor),e=>e.status===400);assert.equal(sent,false);
 for(const status of [409,410,429])await assert.rejects(createHelpTicketBridge({env,identity,fetcher:async()=>Response.json({}, {status})}).submit(body,actor),e=>e.status===status);
});
test('customer support HTTP route requires active context and origin, rejects identity/priority overrides, caps delivery and reports availability',async t=>{
 const app=express();app.use(express.json());let calls=0;
 app.use('/help',customerHelpRouter({context:req=>req.get('x-user')?actor:null,sameOrigin:req=>req.get('origin')==='https://hub.test',supportTickets:{enabled:true,submit:async(body,who)=>{calls++;assert.deepEqual(who,actor);return {submitted:true,reference:'HELP-'+crypto.randomUUID(),priority:'high'};}}}));
 const server=app.listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));t.after(()=>new Promise(r=>{server.closeAllConnections();server.close(r);}));
 const call=(body=request(),headers={})=>fetch(`http://127.0.0.1:${server.address().port}/help/support/tickets`,{method:'POST',headers:{'content-type':'application/json','x-user':'viewer',origin:'https://hub.test',...headers},body:JSON.stringify(body)});
 assert.equal((await call(request(),{'x-user':''})).status,401);assert.equal((await call(request(),{origin:'https://evil.test'})).status,403);
 assert.equal((await call({...request(),priority:'low'})).status,400);assert.equal((await call({...request(),summary:'x'.repeat(33000)})).status,413);assert.equal(calls,0);
 for(let i=0;i<10;i++){const res=await call();assert.equal(res.status,200);assert.equal(res.headers.get('cache-control'),'no-store');assert.equal((await res.json()).priority,'high');}
 assert.equal((await call()).status,429);assert.equal(calls,10);
});
