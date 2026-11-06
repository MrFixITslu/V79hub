import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {helpFixture} from './customer-help-fixture.mjs';

test('full Hub: customer/viewer help works without owner or app permissions; sessions and owner boundaries remain enforced',{timeout:30000},async t=>{
 const fixture=helpFixture();
 const reserve=createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));const port=reserve.address().port;await new Promise(r=>reserve.close(r));
 const url='http://127.0.0.1:'+port;
 const child=spawn(process.execPath,['--import','tsx','server.ts'],{cwd:process.cwd(),env:{...process.env,...fixture.env,PORT:String(port),APP_URL:url,V79_HUB_BIND_HOST:'127.0.0.1'},stdio:['ignore','pipe','pipe']});
 let logs='';child.stdout.on('data',b=>logs=(logs+b).slice(-4000));child.stderr.on('data',b=>logs=(logs+b).slice(-4000));
 t.after(async()=>{if(child.exitCode===null){const exit=new Promise(r=>child.once('exit',r));child.kill();await exit;}fixture.cleanup();});
 let ready=false;
 for(let n=0;n<150;n++){try{if((await fetch(url+'/api/health',{signal:AbortSignal.timeout(500)})).ok){ready=true;break;}}catch{}if(child.exitCode!==null)break;await new Promise(r=>setTimeout(r,50));}
 assert.equal(ready,true,logs);
 const call=(path,body,who='viewer-a',headers={})=>fetch(url+path,{method:body?'POST':'GET',headers:{origin:url,'content-type':'application/json',...(who?{cookie:'v79_hub_session='+fixture.tokens[who]}:{}),...headers},...(body?{body:JSON.stringify(body)}:{})});
 assert.equal((await call('/api/help/catalog',null,null)).status,401);
 assert.equal((await call('/api/help/catalog',null,'revoked')).status,401);
 assert.equal((await call('/api/help/catalog',null,'suspended')).status,401);
 const me=await (await call('/api/auth/me')).json();assert.equal(me.user.ownerAgent,false);assert.equal(me.user.platformOperator,false);assert.equal(me.user.role,'viewer');
 const a=await call('/api/help/chat',{message:'How do I create a Tiquet service request?'});assert.equal(a.status,200);const answer=await a.json();assert.equal(answer.articles[0].section,'2.3');
 const b=await call('/api/help/chat',{message:'How do I create a Tiquet service request?'},'viewer-b');assert.equal(b.status,200);const second=await b.json();assert.notEqual(second.feedback.ticket,answer.feedback.ticket);const {feedback:_feedbackA,...firstGuide}=answer,{feedback:_feedbackB,...secondGuide}=second;assert.deepEqual(secondGuide,firstGuide);
 const guideBody={message:'Walk me through this',guide:{articleId:'manual-2-3',version:answer.version,action:'start'}};
 const guide=await call('/api/help/chat',guideBody);assert.equal(guide.status,200);assert.equal((await guide.json()).guide.stage,'before');
 assert.equal((await call('/api/help/chat',guideBody,'revoked')).status,401);
 assert.equal((await call('/api/help/chat',guideBody,'suspended')).status,401);
 const screenHelp=await call('/api/help/chat',{message:"It won't save",context:{articleId:'manual-2-5'}});assert.equal(screenHelp.status,200);assert.equal((await screenHelp.json()).suggestions[0].articleId,'manual-2-5');
 assert.equal((await call('/api/help/chat',{message:'POS refund'},'viewer-a',{origin:'https://evil.test'})).status,403);
 assert.equal((await call('/api/help/chat',{message:'POS refund',userId:'admin'})).status,400);
 assert.equal((await call('/api/help/articles/manual-1-6')).status,404);
 for(const path of ['/api/agent/chat','/api/agent/work-actions']) assert.equal((await call(path,path.endsWith('/chat')?{message:'Help'}:null)).status,403,path);
 assert.equal((await call('/api/admin/customers')).status,403);
 // The existing sign-in and logout paths still issue/revoke a real Hub session.
 const login=await call('/api/auth/login',{username:'viewer-a',password:fixture.password},null);
 assert.equal(login.status,200);const cookie=login.headers.get('set-cookie').split(';')[0];
 assert.equal((await call('/api/help/catalog',null,null,{cookie})).status,200);
 assert.equal((await call('/api/auth/logout',{},null,{cookie})).status,200);
 assert.equal((await call('/api/help/catalog',null,null,{cookie})).status,401);
});
