import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomBytes,createHash} from 'node:crypto';
import {helpFixture} from './customer-help-fixture.mjs';

test('real Hub feedback preserves tenant/owner/MFA boundaries and durable counts through restart',{timeout:30000},async t=>{
 const fixture=helpFixture({ownerMfa:true});
 const file=join(fixture.root,'v79_store.json'),state=JSON.parse(readFileSync(file,'utf8'));
 state.memberships.find(m=>m.userId==='viewer-a').role='owner';writeFileSync(file,JSON.stringify(state),{mode:0o600});
 const sessionsFile=join(fixture.root,'hub-sessions.json'),sessions=JSON.parse(readFileSync(sessionsFile,'utf8'));
 fixture.tokens['owner-no-mfa']=randomBytes(32).toString('hex');
 const ownerSession=sessions.sessions.find(s=>s.userId==='synthetic-owner');
 sessions.sessions.push({...ownerSession,tokenHash:createHash('sha256').update(fixture.tokens['owner-no-mfa']).digest('hex'),mfaVerified:false});
 writeFileSync(sessionsFile,JSON.stringify(sessions),{mode:0o600});
 const reserve=createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));const port=reserve.address().port;await new Promise(r=>reserve.close(r));
 const url='http://127.0.0.1:'+port;let child,logs='';
 async function start(){
  child=spawn(process.execPath,['--import','tsx','server.ts'],{cwd:process.cwd(),env:{...process.env,...fixture.env,PORT:String(port),APP_URL:url,V79_HUB_BIND_HOST:'127.0.0.1'},stdio:['ignore','pipe','pipe']});
  child.stdout.on('data',b=>logs=(logs+b).slice(-3000));child.stderr.on('data',b=>logs=(logs+b).slice(-3000));
  for(let n=0;n<150;n++){try{if((await fetch(url+'/api/health',{signal:AbortSignal.timeout(500)})).ok)return;}catch{}if(child.exitCode!==null)break;await new Promise(r=>setTimeout(r,50));}throw Error('Synthetic Hub failed to start: '+logs);
 }
 async function stop(){if(child?.exitCode===null){const ended=new Promise(r=>child.once('exit',r));child.kill();await ended;}}
 t.after(async()=>{await stop();fixture.cleanup();});await start();
 const call=(path,body,who='viewer-a')=>fetch(url+'/api/help'+path,{method:body?'POST':'GET',headers:{'content-type':'application/json',origin:url,...(who?{cookie:'v79_hub_session='+fixture.tokens[who]}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const caps=who=>call('/catalog',null,who).then(r=>r.json()).then(r=>r.feedback);
 assert.deepEqual([...(Object.values(await caps('viewer-a')).filter(v=>typeof v==='boolean'))],[true,true,false]);
 assert.equal((await caps('viewer-b')).workspace,false);assert.equal((await caps('synthetic-owner')).all,true);
 const answer=await (await call('/chat',{message:'How do I create a Tiquet service request?'})).json();
 const payload={ticket:answer.feedback.ticket,rating:'helpful'};
 assert.equal((await call('/feedback',payload,'viewer-b')).status,403);
 for(const who of [null,'revoked','suspended'])assert.equal((await call('/feedback',payload,who)).status,401);
 assert.equal((await call('/feedback',payload)).status,200);
 const other=await (await call('/chat',{message:'How do I open the POS register?'},'viewer-b')).json();
 assert.equal((await call('/feedback',{ticket:other.feedback.ticket,rating:'not_helpful',reason:'unclear'},'viewer-b')).status,200);
 assert.equal((await call('/feedback/report',null,'viewer-b')).status,403);
 assert.equal((await (await call('/feedback/report')).json()).totals.votes,1);
 assert.equal((await call('/feedback/report?scope=all')).status,403);
 assert.ok([401,403].includes((await call('/feedback/report?scope=all',null,'owner-no-mfa')).status));
 const global=await call('/feedback/report?scope=all',null,'synthetic-owner');assert.equal(global.status,200);assert.equal((await global.json()).totals.votes,2);
 const unspent=await (await call('/chat',{message:'How do I save notes in Tiquet?'})).json();
 await stop();await start();
 assert.equal((await (await call('/feedback/report')).json()).totals.votes,1);
 assert.equal((await call('/feedback',{ticket:unspent.feedback.ticket,rating:'helpful'})).status,200);
 assert.equal((await (await call('/feedback',payload)).json()).duplicate,true);
 assert.equal((await (await call('/feedback/report')).json()).totals.votes,2);
 const ledger=readFileSync(join(fixture.root,'help-feedback-v1.json'),'utf8');assert.doesNotMatch(ledger,/How do I|viewer-a|viewer-b|vision79slu|"history"|"message"|"answer"/);
});
