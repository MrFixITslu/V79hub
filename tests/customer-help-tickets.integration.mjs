// Explicit isolated cross-repository integration: actual Hub + Tiquet route + PG17.
// V79_TEST_POSTGRES_BIN and V79_HELP_TIQUET_TEST_SOURCE are required, absolute paths.
import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs/promises';
import {execFile,spawn,fork} from 'node:child_process';
import {promisify} from 'node:util';
import {createServer} from 'node:http';
import pg from 'pg';
import {helpFixture} from './customer-help-fixture.mjs';
import {HELP_SUPPORT_PATH} from '../server/customer-help-tickets.mjs';
import {signPlatformRequest} from '../server/platform-contract.mjs';
const exec=promisify(execFile),uuid=()=>crypto.randomUUID();
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function terminate(proc){if(!proc||proc.exitCode!==null||proc.signalCode!==null)return;const ended=new Promise(r=>proc.once('exit',r));proc.kill('SIGTERM');await ended;}
async function freePort(){const s=createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p;}
test('real Hub customer → signed Tiquet service → atomic high-priority owner ticket, retry and boundaries',{timeout:90000},async t=>{
 const bin=process.env.V79_TEST_POSTGRES_BIN,source=process.env.V79_HELP_TIQUET_TEST_SOURCE;
 assert(bin&&path.isAbsolute(bin));assert(source&&path.isAbsolute(source));
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'v79-help-ticket-pg-'));await fs.chmod(root,0o700);
 const socket=path.join(root,'socket');await fs.mkdir(socket,{mode:0o700});const data=path.join(root,'data'),port=await freePort(),user=os.userInfo().username;
 let postgres,pool,tiquet,hub;const fixture=helpFixture();
 t.after(async()=>{await terminate(hub);await terminate(tiquet);if(pool)await pool.end();await terminate(postgres);fixture.cleanup();await fs.rm(root,{recursive:true,force:true});});
 await exec(path.join(bin,'initdb'),['-D',data,'-A','trust','--no-locale','-U',user],{timeout:20000});
 postgres=spawn(path.join(bin,'postgres'),['-D',data,'-k','','-h','127.0.0.1','-p',String(port),'-c','unix_socket_permissions=0700'],{stdio:['ignore','pipe','pipe']});
 let pgLogs='';postgres.stderr.on('data',b=>pgLogs=(pgLogs+b).slice(-3000));
 const dbEnv={PGHOST:'127.0.0.1',PGPORT:String(port),PGUSER:user};
 pool=new pg.Pool({host:'127.0.0.1',port,user,database:'postgres',max:4,connectionTimeoutMillis:1000});
 let ready=false;for(let n=0;n<100;n++){try{await pool.query('SELECT 1');ready=true;break;}catch{await sleep(50);}}assert(ready,'PG ready: '+pgLogs);
 await pool.query(await fs.readFile(path.join(source,'server/schema.sql'),'utf8'));
 const now=new Date().toISOString();
 await pool.query('INSERT INTO accounts (id,name,createdAt,status,hub_organization_id) VALUES ($1,$2,$3,$4,$5)',['v79-support','Synthetic V79',now,'active','v79-owner-org']);
 await pool.query('INSERT INTO users (id,name,email,role,account_id,hub_user_id) VALUES ($1,$2,$3,$4,$5,$6)',['v79-owner','Synthetic Neil','owner@example.invalid','Admin','v79-support','v79-hub-owner']);
 const config={enabled:true,secret:'isolated-support-secret-'.repeat(4),accountId:'v79-support',organizationId:'v79-owner-org',ownerUserId:'v79-owner',ownerHubUserId:'v79-hub-owner'};
 async function receiver(){
  const proc=fork(new URL('./fixtures/help-tiquet-receiver.mjs',import.meta.url),[],{execArgv:[],env:{PATH:process.env.PATH,...dbEnv,V79_HELP_TIQUET_TEST_SOURCE:source,V79_HELP_TEST_CONFIG:JSON.stringify(config)},stdio:['ignore','pipe','pipe','ipc']});
  let logs='';proc.stderr.on('data',b=>logs+=b);const p=await new Promise((resolve,reject)=>{proc.once('message',m=>resolve(m.port));proc.once('exit',()=>reject(Error(logs)));});return {proc,url:'http://127.0.0.1:'+p};
 }
 let receiverState=await receiver();tiquet=receiverState.proc;
 // A loopback test-only proxy can drop a committed response or redirect. No live hosts.
 let drop=false,redirect=false;
 const proxy=createServer(async(req,res)=>{
  if(redirect){res.writeHead(307,{location:receiverState.url+HELP_SUPPORT_PATH});res.end();return;}
  const chunks=[];for await(const chunk of req)chunks.push(chunk);
  try{const response=await fetch(receiverState.url+HELP_SUPPORT_PATH,{method:'POST',headers:req.headers,body:Buffer.concat(chunks)});const body=await response.text();if(drop){drop=false;req.socket.destroy();return;}res.writeHead(response.status,{'content-type':'application/json'});res.end(body);}catch{res.writeHead(503).end();}
 });await new Promise(r=>proxy.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>{proxy.closeAllConnections();proxy.close(r);}));
 const tiquetUrl='http://127.0.0.1:'+proxy.address().port;
 const hubPort=await freePort(),hubUrl='http://127.0.0.1:'+hubPort;
 let hubLogs='';
 async function startHub(){
  hub=spawn(process.execPath,['--import','tsx','server.ts'],{cwd:process.cwd(),env:{...process.env,...fixture.env,PORT:String(hubPort),APP_URL:hubUrl,V79_HUB_BIND_HOST:'127.0.0.1',V79_HELP_SUPPORT_ENABLED:'1',V79_HELP_SUPPORT_SHARED_SECRET:config.secret,V79_HELP_SUPPORT_TIQUET_URL:tiquetUrl},stdio:['ignore','pipe','pipe']});
  hub.stdout.on('data',b=>hubLogs=(hubLogs+b).slice(-4000));hub.stderr.on('data',b=>hubLogs=(hubLogs+b).slice(-4000));
  let ok=false;for(let n=0;n<150;n++){try{if((await fetch(hubUrl+'/api/health',{signal:AbortSignal.timeout(300)})).ok){ok=true;break;}}catch{}if(hub.exitCode!==null)break;await sleep(50);}assert(ok,hubLogs);
 }
 await startHub();
 const request=()=>({idempotencyKey:uuid(),app:'marketing',kind:'error',summary:'Synthetic reviewed error: save failed. Conversation not included.'});
 const call=(body,who='viewer-a',headers={})=>fetch(hubUrl+'/api/help/support/tickets',{method:'POST',headers:{origin:hubUrl,'content-type':'application/json',...(who?{cookie:'v79_hub_session='+fixture.tokens[who]}:{}),...headers},body:JSON.stringify(body)});
 const counts=async()=>{const out={};for(const table of ['jobs','hub_help_support_receipts','notifications','activity_logs','job_tags','clients'])out[table]=Number((await pool.query(`SELECT COUNT(*) AS n FROM ${table}`)).rows[0].n);return out;};
 for(const who of [null,'revoked','suspended'])assert.equal((await call(request(),who)).status,401);
 assert.equal((await call(request(),'viewer-a',{origin:'https://evil.test'})).status,403);
 assert.equal((await call({...request(),accountId:'foreign',priority:'low'})).status,400);
 assert.equal((await counts()).jobs,0);
 const body=request();drop=true;assert.equal((await call(body)).status,503);assert.equal((await counts()).jobs,1,'committed response was deliberately lost');
 const retry=await call(body);assert.equal(retry.status,200);const ack=await retry.json();assert.equal(ack.submitted,true);assert.equal(ack.priority,'high');
 assert.deepEqual(await counts(),{jobs:1,hub_help_support_receipts:1,notifications:1,activity_logs:1,job_tags:1,clients:0});
 const job=(await pool.query('SELECT * FROM jobs')).rows[0];assert.equal(job.account_id,'v79-support');assert.equal(job.priority,'high');assert.equal(job.status,'request');assert.equal(job.assignedto,'Synthetic Neil');assert.equal(job.clientemail,'viewer-a@example.invalid');assert.equal(job.securetoken,null);assert.match(job.description,/Synthetic reviewed error/);assert.match(job.description,/customer-a/);
 const note=(await pool.query('SELECT * FROM notifications')).rows[0];assert.equal(note.user_id,'v79-owner');assert.equal(note.account_id,'v79-support');assert.equal(note.isread,0);
 const concurrent=await Promise.all(Array.from({length:4},()=>call(body)));assert(concurrent.every(r=>r.status===200));for(const r of concurrent)assert.equal((await r.json()).reference,ack.reference);
 assert.equal((await call({...body,summary:body.summary+' changed'})).status,409);assert.equal((await counts()).jobs,1);
 // A different workspace/user gets a different request, never another customer's receipt.
 const other=await call(body,'viewer-b');assert.equal(other.status,200);assert.notEqual((await other.json()).reference,ack.reference);assert.equal((await counts()).jobs,2);
 await terminate(tiquet);receiverState=await receiver();tiquet=receiverState.proc;
 await terminate(hub);await startHub();
 const afterRestart=await call(body);assert.equal(afterRestart.status,200);assert.equal((await afterRestart.json()).reference,ack.reference);assert.equal((await counts()).jobs,2);
 // Redirect must not follow with machine credentials or create a job.
 redirect=true;assert.equal((await call(request())).status,503);redirect=false;assert.equal((await counts()).jobs,2);
 // Direct receiver: signature/body tampering, wrong service, stale timestamp, browser credentials and explicit destination/priority overrides.
 const event={schemaVersion:1,requestId:crypto.randomBytes(32).toString('hex'),requester:{organizationId:'direct-org',userId:'direct-user',name:'Synthetic Customer',email:'direct@example.invalid',workspace:'Synthetic direct workspace'},app:'hub',kind:'unresolved',summary:'Synthetic request for an isolated integration check.'};
 async function direct(e=event,overrides={},ts=String(Date.now())){const raw=JSON.stringify(e);return fetch(receiverState.url+HELP_SUPPORT_PATH,{method:'POST',headers:{'content-type':'application/json','x-v79-service-id':'v79-hub-help','x-v79-timestamp':ts,'x-v79-signature':signPlatformRequest({method:'POST',pathname:HELP_SUPPORT_PATH,timestamp:ts,body:raw,secret:config.secret}),...overrides},body:raw});}
 assert.equal((await direct(event,{'x-v79-signature':'0'.repeat(64)})).status,401);assert.equal((await direct(event,{},String(Date.now()-3600000))).status,401);assert.equal((await direct(event,{origin:'https://hub.test'})).status,403);assert.equal((await direct(event,{cookie:'session=fake'})).status,403);assert.equal((await direct(event,{'x-v79-service-id':'v79-sentinel'})).status,401);assert.equal((await direct({...event,priority:'low'})).status,400);assert.equal((await direct({...event,requester:{...event.requester,accountId:'foreign'}})).status,400);
 // Destination and owner are verified on each call, even existing receipts.
 await pool.query("UPDATE accounts SET status='suspended' WHERE id='v79-support'");assert.equal((await call(request())).status,503);await pool.query("UPDATE accounts SET status='active' WHERE id='v79-support'");
 await pool.query("UPDATE users SET role='Member' WHERE id='v79-owner'");assert.equal((await direct()).status,503);await pool.query("UPDATE users SET role='Admin' WHERE id='v79-owner'");
 await pool.query("UPDATE accounts SET hub_organization_id='wrong' WHERE id='v79-support'");assert.equal((await direct()).status,503);await pool.query("UPDATE accounts SET hub_organization_id='v79-owner-org' WHERE id='v79-support'");
 await pool.query("UPDATE users SET hub_user_id='wrong' WHERE id='v79-owner'");assert.equal((await direct()).status,503);await pool.query("UPDATE users SET hub_user_id='v79-hub-owner' WHERE id='v79-owner'");
 // Failure after inserting job must roll back all records.
 await pool.query("ALTER TABLE notifications ADD CONSTRAINT synthetic_notification_failure CHECK (title <> 'High-priority App Help ticket') NOT VALID");
 const before=await counts();assert.equal((await direct()).status,503);assert.deepEqual(await counts(),before);await pool.query('ALTER TABLE notifications DROP CONSTRAINT synthetic_notification_failure');
 const created=await direct();assert.equal(created.status,201);const directAck=await created.json();
 // Deleted job leaves a receipt/tombstone, and is never recreated by replay.
 await pool.query('DELETE FROM jobs WHERE id=$1',[directAck.reference.slice(5)]);const afterDelete=await counts();assert.equal((await direct()).status,410);assert.deepEqual(await counts(),afterDelete);
 // Durable per-requester creation cap, independent of new keys or process restart.
 for(let i=0;i<4;i++)assert.equal((await direct({...event,requestId:crypto.randomBytes(32).toString('hex')})).status,201);
 assert.equal((await direct({...event,requestId:crypto.randomBytes(32).toString('hex')})).status,429);
 console.log('ISOLATED_HELP_SUPPORT_PASS: real Hub, Tiquet child process and PG; lost acknowledgement, concurrent retry, restarts, identity, fixed priority/owner, atomic rollback and durable quota. No production records.');
});
