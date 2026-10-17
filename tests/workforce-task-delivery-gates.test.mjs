import test from 'node:test';
import assert from 'node:assert/strict';
import {projectWorkItem,summarizeDeliveryBoard} from '../workforce/quality/task-delivery-gates.mjs';

const NOW=Date.parse('2026-10-16T23:55:00Z');
const AT='2026-10-16T23:01:00.000Z';
const DIGEST='a'.repeat(64);
const COMMIT='c'.repeat(40);
// Exact installed G2 createApprovedWorkItem public data shape:
// job.result={taskId,at}, plus independently authenticated state.tasks[].
const queue=({status='succeeded',...changes}={})=>({
 id:'job-001',operation:'create_work_item',organizationId:'org-v79',system:'hub',
 revision:5,digest:DIGEST,status,result:{taskId:'task-001',at:AT},...changes,
});
const task=(changes={})=>({
 id:'task-001',jobId:'job-001',organizationId:'org-v79',system:'hub',
 title:'Test approved task',detail:'No operation carried out',status:'open',
 assignedTo:'coo',createdAt:AT,...changes,
});
const delivery=(changes={})=>({
 jobId:'job-001',taskId:'task-001',actionDigest:DIGEST,
 organizationId:'org-v79',system:'hub',scope:'v79-owned',
 state:'owner_accepted',commitSha:COMMIT,
 independentTestRef:'ci:validated-012',acceptanceRef:'owner:accept-001',
 acceptedAt:'2026-10-16T23:00:00Z',...changes,
});
const defaults=(changes={})=>({
 job:queue(),taskRecord:task(),organizationId:'org-v79',nowMs:NOW,
 verifyQueueRecord:()=>true,verifyTaskRecord:()=>true,
 verifyDeliveryEvidence:()=>true,...changes,
});

test('missing authenticated owner queue or cross-org scope fails closed',()=>{
 assert.equal(projectWorkItem({job:queue(),organizationId:'org-v79'}).state,'unknown');
 assert.equal(projectWorkItem(defaults({organizationId:'other-org'})).state,'unknown');
 assert.equal(projectWorkItem(defaults({verifyQueueRecord:()=>false})).state,'unknown');
 assert.equal(projectWorkItem(defaults({verifyQueueRecord:()=>{throw Error('offline')}})).state,'unknown');
});
test('actual G2 create_work_item result without receipt SHA proves task creation only with trusted tasks[] row',()=>{
 const p=projectWorkItem(defaults());
 assert.equal(p.state,'work_item_created');
 assert.equal(p.created,true);
 assert.equal(p.delivered,false);
 assert.equal(p.taskId,'task-001');
 assert.equal(p.evidenceRef,null);
 assert.equal(JSON.stringify(p).includes('Test approved task'),false);
 assert.equal(Object.isFrozen(p),true);
});
test('approval and running states never assert task creation',()=>{
 const states={pending:'awaiting_approval',approved:'awaiting_execution',running:'execution_unconfirmed'};
 for(const [status,expected] of Object.entries(states)){
   const p=projectWorkItem(defaults({job:queue({status})}));
   assert.equal(p.state,expected);
   assert.equal(p.created,false);
 }
});
test('denied, failed, cancelled and uncertain never become delivered even with fake acceptance',()=>{
 const states={rejected:'rejected',failed:'failed',cancelled:'cancelled',uncertain:'blocked_uncertain'};
 for(const [status,expected] of Object.entries(states)){
   const p=projectWorkItem(defaults({job:queue({status}),deliveryEvidence:delivery()}));
   assert.equal(p.state,expected);
   assert.equal(p.delivered,false);
 }
});
test('G2 result must have its authentic task ID and created timestamp',()=>{
 for(const result of [undefined,null,{taskId:'task-001'},{taskId:'task-001',at:'invalid'},
 {taskId:'task-002',at:AT},{taskId:'task-001',at:'2026-10-16T23:01:01.000Z'}]){
  const p=projectWorkItem(defaults({job:queue({result})}));
  assert.equal(p.state,'blocked_uncertain');
  assert.equal(p.delivered,false);
 }
});
test('G2 task row must match exact task, job, tenant, app, COO, open state and timestamp',()=>{
 for(const changes of [
   {id:'task-002'},{jobId:'job-002'},{organizationId:'other-org'},
   {system:'tiquet'},{assignedTo:'agent'},{status:'completed'},
   {createdAt:'2026-10-16T23:01:01.000Z'},
   {createdAt:'2026-11-16T23:01:00.000Z'},
 ]){
  const p=projectWorkItem(defaults({taskRecord:task(changes)}));
  assert.equal(p.state,'blocked_uncertain',JSON.stringify(changes));
 }
});
test('missing, false or throwing trusted task-row verifier refuses creation',()=>{
 for(const verifyTaskRecord of [undefined,()=>false,()=>{throw Error('untrusted')}]) {
  const p=projectWorkItem(defaults({verifyTaskRecord}));
  assert.equal(p.state,'blocked_uncertain');
 }
 assert.equal(projectWorkItem(defaults({taskRecord:null})).state,'blocked_uncertain');
});
test('independent founder-accepted delivery matches G2 row and digest',()=>{
 const p=projectWorkItem(defaults({deliveryEvidence:delivery()}));
 assert.equal(p.created,true);
 assert.equal(p.delivered,true);
 assert.equal(p.state,'delivery_verified');
 assert.equal(p.evidenceRef,'owner:accept-001');
});
test('self asserted, forged or verifier-throwing delivery never passes',()=>{
 for(const verifyDeliveryEvidence of [undefined,()=>false,()=>{throw Error('bad signature')}]) {
  const p=projectWorkItem(defaults({deliveryEvidence:delivery(),verifyDeliveryEvidence}));
  assert.equal(p.state,'delivery_unverified');
  assert.equal(p.delivered,false);
 }
});
test('bad scope, digest, task, CI, timing and owner identity block delivery',()=>{
 for(const change of [
  {jobId:'job-002'},{taskId:'task-002'},{actionDigest:'d'.repeat(64)},
  {organizationId:'org-other'},{system:'tiquet'},{scope:'customer'},
  {state:'developer_complete'},{commitSha:'not-a-commit'},
  {independentTestRef:'bad ref'},{acceptanceRef:''},
  {acceptedAt:'2026-11-20T23:00:00Z'},
 ]){
  const p=projectWorkItem(defaults({deliveryEvidence:delivery(change)}));
  assert.equal(p.delivered,false,JSON.stringify(change));
  assert.equal(p.state,'delivery_unverified',JSON.stringify(change));
 }
});
test('unrecognized operations, bad digest and cross-org jobs cannot enter G2 board',()=>{
 for(const changes of [
  {operation:'deploy_release'},{system:'arbitrary'},{digest:'bad'},
  {status:'agent_claimed_succeeded'},{revision:-1},{organizationId:'org-other'},
 ]){
  assert.equal(projectWorkItem(defaults({job:queue(changes)})).state,'unknown',JSON.stringify(changes));
 }
});
test('board projects authentic real G2 jobs and linked task rows without leaking task text',()=>{
 const jobs=[
   queue({id:'job-001'}),
   queue({id:'job-002',status:'approved',result:null}),
   queue({id:'job-003',result:{taskId:'task-003',at:AT}}),
 ];
 const tasks=[task(),task({id:'task-003',jobId:'job-003'})];
 const board=summarizeDeliveryBoard({
  jobs,tasks,organizationId:'org-v79',nowMs:NOW,
  verifyQueueRecord:()=>true,verifyTaskRecord:()=>true,verifyDeliveryEvidence:()=>true,
  deliveryEvidenceByJobId:{'job-001':delivery()},
 });
 assert.equal(board.state,'verified_queue_projection');
 assert.deepEqual(board.totals,{awaiting:1,created:1,delivered:1,blocked:0});
 assert.equal(JSON.stringify(board).includes('Test approved task'),false);
 assert.equal(JSON.stringify(board).includes('receiptSha256'),false);
});
test('board refuses duplicate jobs or task row identity collisions',()=>{
 for(const bad of [
  {jobs:[queue(),queue()],tasks:[task()]},
  {jobs:[queue()],tasks:[task(),task()]},
 ]){
  const out=summarizeDeliveryBoard({...bad,organizationId:'org-v79',
    verifyQueueRecord:()=>true,verifyTaskRecord:()=>true});
  assert.equal(out.state,'unavailable');
 }
});
test('unverifiable queue invalidates entire board instead of publishing guessed counts',()=>{
 const out=summarizeDeliveryBoard({
   jobs:[queue()],tasks:[task()],organizationId:'org-v79',verifyQueueRecord:()=>false,
 });
 assert.equal(out.state,'unavailable');
 assert.equal(out.rows.length,0);
});
test('missing authenticated task row produces blocked status rather than phantom creation',()=>{
 const out=summarizeDeliveryBoard({
   jobs:[queue()],tasks:[],organizationId:'org-v79',
   verifyQueueRecord:()=>true,verifyTaskRecord:()=>true,
 });
 assert.deepEqual(out.totals,{awaiting:0,created:0,delivered:0,blocked:1});
 assert.equal(out.rows[0].state,'blocked_uncertain');
});
