import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { initialWorkState, proposeWork, decideWork, createApprovedWorkItem, workDigest } from '../server/workforce-actions.mjs';
import { projectAuthenticatedWorkDelivery } from '../server/workforce-delivery.mjs';
import { formatCooWorkboard } from '../server/owner-coo-workboard.mjs';
const now=Date.parse('2026-10-27T20:00:00Z');
const input={operation:'create_work_item',system:'hub',summary:'Review workforce delivery',payload:{detail:'Inspect the assigned work and record independent evidence'},idempotencyKey:'synthetic-workforce-20261027'};
const identity={organizationId:'org-v79',actor:'founder',now};
function approved(state,request=input){
 const j=proposeWork(state,request,identity);
 return decideWork(state,j.id,'approve',{...identity,expectedRevision:j.revision,digest:j.digest});
}
test('legacy approved task digests remain byte-compatible; specialist assignment is approval-bound',()=>{
 const legacy=createHash('sha256').update(JSON.stringify([input.operation,input.system,input.summary,input.payload.detail,input.idempotencyKey])).digest('hex');
 assert.equal(workDigest(input),legacy);
 for(const specialist of ['coo','finance','strategy','marketing','customer-service','technical-security','sales']){
  const state=initialWorkState();const j=approved(state,{...input,payload:{...input.payload,specialist}});
  assert.notEqual(j.digest,legacy);
  createApprovedWorkItem(state,j.id,{...identity,expectedRevision:j.revision});
  assert.equal(state.tasks[0].assignedTo,'coo');assert.equal(state.tasks[0].specialist,specialist);
 }
 const state=initialWorkState(),j=approved(state,{...input,payload:{...input.payload,specialist:'finance'}});
 j.payload.specialist='sales';
 assert.throws(()=>createApprovedWorkItem(state,j.id,{...identity,expectedRevision:j.revision}));
 assert.equal(state.tasks.length,0);
 for(const specialist of ['shell','owner',null,{},'finance\nexecute'])assert.throws(()=>workDigest({...input,payload:{...input.payload,specialist}}));
});
test('authenticated snapshot projection isolates tenant and refuses missing or contradictory task evidence',()=>{
 const state=initialWorkState();const j=approved(state);
 let board=projectAuthenticatedWorkDelivery(state,identity.organizationId,now);
 assert.equal(board.totals.awaiting,1);assert.equal(board.totals.created,0);
 createApprovedWorkItem(state,j.id,{...identity,expectedRevision:j.revision});
 board=projectAuthenticatedWorkDelivery(state,identity.organizationId,now);
 assert.equal(board.totals.created,1);assert.equal(board.totals.delivered,0);
 assert.equal(board.independentDeliveryVerification,'not_configured');
 assert.equal(JSON.stringify(board).includes(input.summary),false);
 assert.equal(projectAuthenticatedWorkDelivery(state,'foreign-org',now).rows.length,0);
 state.tasks[0].organizationId='foreign-org';
 board=projectAuthenticatedWorkDelivery(state,identity.organizationId,now);
 assert.equal(board.totals.created,0);assert.equal(board.totals.blocked,1);
});
test('latest-200 projection retains matching task rows even among unrelated newer tasks',()=>{
 const state=initialWorkState(),j=approved(state);
 createApprovedWorkItem(state,j.id,{...identity,expectedRevision:j.revision});
 for(let i=0;i<250;i++)state.tasks.push({id:`foreign-${i}`,organizationId:'foreign-org'});
 assert.equal(projectAuthenticatedWorkDelivery(state,identity.organizationId,now).totals.created,1);
 // An injected delivery-shaped object in the signed ledger cannot become accepted delivery.
 state.deliveries=[{jobId:j.id,state:'owner_accepted'}];
 assert.equal(projectAuthenticatedWorkDelivery(state,identity.organizationId,now).totals.delivered,0);
});
test('workboard uses one entry per repository/number/kind and includes FFPRO and completion register',()=>{
 const report=formatCooWorkboard({},new Date(now).toISOString());
 const keys=report.tracked.map(r=>`${r.repo}/${r.number}/${r.kind}`);
 assert.equal(new Set(keys).size,keys.length);
 assert.ok(report.repositories.some(r=>r.repo==='FFPRO2'));
 assert.ok(report.tracked.some(r=>r.repo==='V79hub'&&r.number===194));
});
test('uninitialised ledger is unavailable, not an authenticated empty task board',async t=>{
 const fs=await import('node:fs/promises'),os=await import('node:os'),path=await import('node:path');
 const {createWorkActionStore}=await import('../server/workforce-action-store.mjs');
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'v79-delivery-'));
 t.after(()=>fs.rm(dir,{recursive:true,force:true}));
 const file=path.join(dir,'ledger.json'),ledger=createWorkActionStore({file,secret:'synthetic-audit-key-for-offline-tests-only'});
 assert.equal(await ledger.readAuthenticatedSnapshot(),null);
 assert.equal(projectAuthenticatedWorkDelivery(null,'org-v79',now).state,'unavailable');
 await ledger.transact(s=>proposeWork(s,input,identity));
 assert.equal(projectAuthenticatedWorkDelivery(await ledger.readAuthenticatedSnapshot(),'org-v79',now).totals.awaiting,1);
 const raw=JSON.parse(await fs.readFile(file,'utf8'));raw.state.jobs[0].status='succeeded';await fs.writeFile(file,JSON.stringify(raw));
 await assert.rejects(()=>ledger.readAuthenticatedSnapshot(),/integrity/);
});
