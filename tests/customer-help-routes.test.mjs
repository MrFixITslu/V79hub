import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import {customerHelpRouter} from '../server/customer-help-routes.mjs';
import {createHelpService} from '../server/customer-help.mjs';

test('authenticated customer help over HTTP: identity, origin, schema, privacy and isolated rate budgets',async t=>{
 let now=100;const app=express();app.use(express.json());
 app.use('/api/help',customerHelpRouter({clock:()=>now,maxPerMinute:2,service:createHelpService({env:{}}),
  context:req=>req.get('x-test-user')?{userId:req.get('x-test-user'),organizationId:req.get('x-test-org')||'one'}:null,
  sameOrigin:req=>req.get('origin')==='https://hub.synthetic.test'}));
 const server=app.listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));
 t.after(()=>new Promise(r=>{server.closeAllConnections();server.close(r);}));
 const base='http://127.0.0.1:'+server.address().port+'/api/help';
 const call=(path='',body,headers={})=>fetch(base+path,{method:body?'POST':'GET',headers:{'x-test-user':'viewer','content-type':'application/json',origin:'https://hub.synthetic.test',...headers},...(body?{body:JSON.stringify(body)}:{})});
 assert.equal((await call('/catalog',null,{'x-test-user':''})).status,401);
 const catalog=await call('/catalog');assert.equal(catalog.status,200);assert.equal(catalog.headers.get('cache-control'),'no-store');
 assert.equal((await catalog.json()).articles.length,49);
 assert.equal((await call('/articles/manual-1-6')).status,404);
 assert.equal((await call('/articles/manual-3-6')).status,200);
 assert.equal((await call('/unknown')).status,404);
 assert.equal((await call('/chat',{message:'POS refund'},{origin:'https://evil.test'})).status,403);
 assert.equal((await call('/chat',{message:'POS refund',organizationId:'owner'})).status,400);
 assert.equal((await call('/chat',{message:'a'.repeat(13000)})).status,413);
 const a=await call('/chat',{message:'POS refund'});assert.equal(a.status,200);const first=await a.json();assert.equal(first.articles[0].section,'3.6');
 assert.equal((await call('/chat',{message:'POS stock'})).status,200);
 const limit=await call('/chat',{message:'POS register'});assert.equal(limit.status,429);assert.ok(Number(limit.headers.get('retry-after'))>0);
 const other=await call('/chat',{message:'POS refund'},{'x-test-org':'two'});assert.equal(other.status,200);assert.deepEqual(await other.json(),first);
 assert.equal((await call('/chat',{message:'POS refund'},{'x-test-user':'other-viewer'})).status,200);
 now+=61000;assert.equal((await call('/chat',{message:'POS refund'})).status,200);
});
test('parallel asks by the same customer cannot consume simultaneous inference slots',async t=>{
 let release;let count=0;const app=express();app.use(express.json());
 app.use('/help',customerHelpRouter({context:()=>({userId:'one',organizationId:'org'}),sameOrigin:()=>true,
  service:{answer:async()=>{count++;await new Promise(r=>release=r);return {answer:'test'};}}}));
 const server=app.listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));
 t.after(()=>new Promise(r=>{server.closeAllConnections();server.close(r);}));
 const call=()=>fetch('http://127.0.0.1:'+server.address().port+'/help/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message:'POS refund'})});
 const pending=call();while(!release)await new Promise(r=>setTimeout(r,5));
 assert.equal((await call()).status,429);assert.equal(count,1);release();assert.equal((await pending).status,200);
});
