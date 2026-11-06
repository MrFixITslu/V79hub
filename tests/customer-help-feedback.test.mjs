import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm,stat,chmod,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHelpFeedback,validateFeedback,reportFilters} from '../server/customer-help-feedback.mjs';
import {knowledge,findArticle} from '../server/customer-help.mjs';
import {spawn} from 'node:child_process';
const secret='synthetic-feedback-key-not-for-live-2026';
const a={userId:'private-user-a',organizationId:'workspace-a'},b={userId:'private-user-b',organizationId:'workspace-b'};
const answer=(id='manual-2-5',status='answered')=>({status,app:id?findArticle(id).app:'tiquet',version:knowledge.version,articles:id?[findArticle(id)]:[],answer:'private-question-and-answer-must-not-persist'});
async function fixture(t){const root=await mkdtemp(join(tmpdir(),'v79-help-feedback-'));t.after(()=>rm(root,{recursive:true,force:true}));let now=Date.parse('2026-11-06T13:00:00Z');const file=join(root,'feedback.json');const options={file,secret,clock:()=>now};return {root,file,options,store:createHelpFeedback(options),advance:n=>now+=n,setTime:n=>now=n};}
const report=(store,actor=a,extra={})=>store.report(actor,{scope:'workspace',days:30,app:'all',...extra});
const vote=(store,ticket,rating='helpful',actor=a,reason='unclear')=>store.vote({ticket,rating,...(rating==='not_helpful'?{reason}:{})},actor);

test('durable voluntary feedback stores aggregates, no questions/answers/user IDs, and scopes reports',async t=>{
 const f=await fixture(t),s=f.store;
 await vote(s,s.issue(answer(),a).ticket);
 await vote(s,s.issue(answer(),a).ticket,'not_helpful',a,'missing_steps');
 await vote(s,s.issue(answer('manual-3-3'),b).ticket,'helpful',b);
 const r=await report(s);assert.deepEqual(r.totals,{votes:2,helpful:1,notHelpful:1,helpfulnessPercent:50,undocumentedFeedback:0});
 assert.equal(r.rows[0].reasons.missing_steps,1);assert.equal((await report(s,b)).totals.votes,1);
 assert.equal((await report(s,a,{scope:'all'})).totals.votes,3);
 const disk=await readFile(f.file,'utf8');assert.doesNotMatch(disk,/private-question|private-user|"answer"|"message"|"history"|"ticket"|email|password/);
 assert.equal((await stat(f.file)).mode&0o777,0o600);
 assert.equal((await report(createHelpFeedback(f.options))).totals.votes,2);
 assert.equal(JSON.stringify(r).includes('workspace-a'),false);
});
test('signed tickets cannot be changed, stolen across users/workspaces or vote after expiry',async t=>{
 const f=await fixture(t),s=f.store,ticket=s.issue(answer(),a).ticket;
 await assert.rejects(vote(s,ticket,'helpful',b),e=>e.code==='FORBIDDEN');
 await assert.rejects(vote(s,ticket,'helpful',{...a,userId:'another-user'}),e=>e.code==='FORBIDDEN');
 const [payload,mac]=ticket.split('.'),p=JSON.parse(Buffer.from(payload,'base64url'));p.i='manual-3-3';
 await assert.rejects(vote(s,Buffer.from(JSON.stringify(p)).toString('base64url')+'.'+mac),e=>e.code==='INVALID');
 f.advance(7200001);await assert.rejects(vote(s,ticket),e=>e.code==='EXPIRED');
 assert.equal((await report(s)).totals.votes,0);
});
test('duplicate submissions are counted once, including concurrent processes and restart-style instances',async t=>{
 const f=await fixture(t),ticket=f.store.issue(answer(),a).ticket;
 const other=createHelpFeedback(f.options);
 const results=await Promise.all(Array.from({length:8},(_,i)=>vote(i%2?f.store:other,ticket)));
 assert.equal(results.filter(r=>!r.duplicate).length,1);assert.equal((await report(other)).totals.votes,1);
 assert.equal((await vote(createHelpFeedback(f.options),ticket,'not_helpful')).duplicate,true);
 assert.equal((await report(other)).totals.helpful,1);
});
test('concurrent distinct feedback has no lost counts and separates actual source topics/versions/status',async t=>{
 const f=await fixture(t),s=f.store,other=createHelpFeedback(f.options);
 const requests=Array.from({length:12},(_,i)=>({store:i%2?s:other,ticket:s.issue(answer(i%3?'manual-2-5':'manual-3-3'),a).ticket,rating:i%2?'helpful':'not_helpful'}));
 await Promise.all(requests.map(r=>vote(r.store,r.ticket,r.rating)));
 const r=await report(s);assert.equal(r.totals.votes,12);assert.equal(r.totals.helpful,6);assert.equal(r.rows.length,2);
 assert.equal((await report(s,a,{app:'pos'})).totals.votes,4);
 const undocumented=s.issue(answer(null,'not_documented'),a);await vote(s,undocumented.ticket,'not_helpful',a,'not_documented');
 assert.equal((await report(s)).totals.undocumentedFeedback,1);
 assert.equal(s.issue(answer(null,'restricted'),a),null);
});
test('calendar windows use Saint Lucia midnight, exclude old aggregates and prune on the next vote',async t=>{
 const f=await fixture(t),s=f.store;f.setTime(Date.parse('2026-11-06T03:59:00Z'));await vote(s,s.issue(answer(),a).ticket);
 f.setTime(Date.parse('2026-11-06T04:01:00Z'));await vote(s,s.issue(answer(),a).ticket);
 const disk=JSON.parse(await readFile(f.file,'utf8'));assert.deepEqual(disk.state.buckets.map(r=>r.day),['2026-11-05','2026-11-06']);
 assert.equal((await report(s)).throughDay,'2026-11-06');
 f.advance(92*86400000);assert.equal((await report(s,a,{days:90})).totals.votes,0);
 await vote(s,s.issue(answer(),a).ticket);
 const pruned=JSON.parse(await readFile(f.file,'utf8'));assert.equal(pruned.state.buckets.length,1);assert.equal(pruned.state.receipts.length,1);
});
test('strict schemas disallow free text, identity/topic spoofing and unbounded filters',()=>{
 for(const body of [null,[],{}, {ticket:'x'.repeat(80),rating:'helpful',message:'private'},{ticket:'x'.repeat(80),rating:'not_helpful',reason:'raw-private-text'},{ticket:'x'.repeat(80),rating:'helpful',reason:'unclear'},{ticket:'x'.repeat(2000),rating:'helpful'}])assert.ok(validateFeedback(body));
 for(const query of [{organizationId:'other'},{scope:'owner'},{days:'365'},{app:'admin'},{days:['7','90']}])assert.throws(()=>reportFilters(query));
 assert.deepEqual(reportFilters({}),{scope:'workspace',days:30,app:'all'});
});
test('corruption, permissive files and symlinks fail closed without silently replacing the ledger',async t=>{
 const f=await fixture(t),s=f.store;await vote(s,s.issue(answer(),a).ticket);const original=await readFile(f.file);
 const corrupt=JSON.parse(original);corrupt.state.buckets[0].helpful=999;await writeFile(f.file,JSON.stringify(corrupt));
 await assert.rejects(report(s),e=>e.code==='UNAVAILABLE');
 await assert.rejects(vote(s,s.issue(answer(),a).ticket));assert.match(await readFile(f.file,'utf8'),/999/);
 await writeFile(f.file,original);await chmod(f.file,0o644);await assert.rejects(report(s));
 await rm(f.file);const target=join(f.root,'other.json');await writeFile(target,original,{mode:0o600});await symlink(target,f.file);await assert.rejects(report(s));assert.deepEqual(await readFile(target),original);
});
test('missing configuration disables feedback and write-fence failures release locks',async t=>{
 const f=await fixture(t);const disabled=createHelpFeedback({file:f.file});assert.equal(disabled.enabled,false);assert.equal(disabled.issue(answer(),a),null);await assert.rejects(vote(disabled,'x'.repeat(80)));
 const s=createHelpFeedback({...f.options,beginWrite:()=>{throw Error('synthetic maintenance fence');}});
 await assert.rejects(vote(s,s.issue(answer(),a).ticket),/synthetic maintenance/);
 await assert.rejects(stat(f.file+'.lock'),e=>e.code==='ENOENT');
});
test('separate Node processes share the same ledger lock without lost updates',async t=>{
 const f=await fixture(t),tickets=Array.from({length:8},()=>f.store.issue(answer(),a).ticket);
 const script="import {createHelpFeedback} from './server/customer-help-feedback.mjs';let raw='';for await(const b of process.stdin)raw+=b;const p=JSON.parse(raw);const s=createHelpFeedback(p.options);for(const ticket of p.tickets)await s.vote({ticket,rating:'helpful'},p.actor);";
 const run=list=>new Promise((resolve,reject)=>{const child=spawn(process.execPath,['--input-type=module','-e',script],{cwd:process.cwd(),stdio:['pipe','ignore','pipe']});let error='';child.stderr.on('data',b=>error+=b);child.on('error',reject);child.once('exit',code=>code===0?resolve():reject(Error(error)));child.stdin.end(JSON.stringify({options:{file:f.file,secret,clock:undefined},tickets:list,actor:a}));});
 // Use current-clock tickets for the independently started processes.
 const current=createHelpFeedback({file:f.file,secret});const liveTickets=tickets.map(()=>current.issue(answer(),a).ticket);
 await Promise.all([run(liveTickets.slice(0,4)),run(liveTickets.slice(4))]);
 assert.equal((await current.report(a,{scope:'workspace',days:30,app:'all'})).totals.votes,8);
});
