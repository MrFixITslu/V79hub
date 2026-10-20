import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import { createServer } from 'node:http';
import { workforceGoogleRouter, projectGoogleThread } from '../server/workforce-google-routes.mjs';
test('email projection exposes bounded plain text and flags omitted/HTML-only content',()=>{
  const result=projectGoogleThread({id:'thread1',messages:[{id:'m1',threadId:'thread1',payload:{mimeType:'multipart/alternative',headers:[{name:'From',value:'Client\r\nInjected'}],parts:[
    {mimeType:'text/html',body:{data:Buffer.from('<script>bad()</script>').toString('base64url')}},
    {mimeType:'text/plain',body:{data:Buffer.from('Untrusted email body').toString('base64url')}}]}}]});
  assert.equal(result.messages[0].text,'Untrusted email body');assert.equal(result.partial,false);assert.equal(result.trust,'untrusted-email-content');
  assert.equal(result.messages[0].from.includes('\n'),false);
  assert.equal(projectGoogleThread({messages:[{payload:{mimeType:'text/html'}}]}).partial,true);
  const parts=Array.from({length:21},()=>({mimeType:'text/plain',body:{data:Buffer.from('Text').toString('base64url')}}));
  assert.equal(projectGoogleThread({messages:[{payload:{parts}}]}).partial,true);
});
test('Google HTTP routes enforce owner identity, default-off gate, origin and fresh MFA',async t=>{
  let enabled=false,calls=0;
  const now=Date.now();const app=express();app.use(express.json());
  app.use((req,res,next)=>{req.user={mfaVerifiedAt:req.get('x-stale')?now-300001:now};next()});
  app.use('/google',workforceGoogleRouter({enabled:()=>enabled,ownerContext:req=>req.get('x-owner')==='yes'?{userId:'owner',organizationId:'org'}:null,
    sameOrigin:req=>req.get('origin')==='https://hub.synthetic.test',now:()=>now,ledger:null,receiptDirectory:null,
    client:{status:async()=>{calls++;return {account:'vision79slu@gmail.com',sendEnabled:false}},listEmails:async()=>{calls++;return {messages:[]}}}}));
  const server=createServer(app);await new Promise(r=>server.listen(0,'127.0.0.1',r));
  t.after(()=>new Promise(r=>server.close(r)));
  const base='http://127.0.0.1:'+server.address().port+'/google';
  assert.equal((await fetch(base+'/status')).status,403);
  const headers={'x-owner':'yes'};
  assert.equal((await (await fetch(base+'/status',{headers})).json()).enabled,false);assert.equal(calls,0);
  assert.equal((await fetch(base+'/inbox',{headers})).status,503);assert.equal(calls,0);
  enabled=true;assert.equal((await fetch(base+'/status',{headers})).status,200);assert.equal(calls,1);
  assert.equal((await fetch(base+'/run-once',{method:'POST',headers:{...headers,'content-type':'application/json'},body:'{}'})).status,403);
  assert.equal((await fetch(base+'/run-once',{method:'POST',headers:{...headers,'content-type':'application/json',origin:'https://hub.synthetic.test','x-stale':'1'},body:'{}'})).status,403);
  assert.equal((await fetch(base+'/inbox?url=https://attacker.test',{headers})).status,409);
});

