import test from 'node:test';
import assert from 'node:assert/strict';
import {projectWorkItem,summarizeDeliveryBoard} from '../workforce/quality/task-delivery-gates.mjs';

const NOW=Date.parse('2026-10-16T23:55:00Z');
const DIGEST='a'.repeat(64);
const RECEIPT='b'.repeat(64);
const COMMIT='c'.repeat(40);
const queue=({status='succeeded',...changes}={})=>({
 id:'job-001',operation:'create_work_item',organizationId:'org-v79',system:'hub',
 revision:5,digest:DIGEST,status,
 result:{taskId:'task-001',receiptSha256:RECEIPT},...changes,
});
const delivery=(changes={})=>({
 jobId:'job-001',taskId:'task-001',actionDigest:DIGEST,
 organizationId:'org-v79',system:'hub',scope:'v79-owned',
 state:'owner_accepted',commitSha:COMMIT,
 independentTestRef:'ci:validated-012',acceptanceRef:'owner:accept-001',
 acceptedAt:'2026-10-16T23:00:00Z',...changes,
});
const defaults=(changes={})=>({
 job:queue(),organizationId:'org-v79',nowMs:NOW,
 verifyQueueRecord:()=>true,verifyDeliveryEvidence:()=>true,...changes,
});
test('missing authenticated source verifier or scope fails closed',()=>{
 assert.equal(projectWorkItem({job:queue(),organizationId:'org-v79'}).state,'unknown');
 assert.equal(projectWorkItem(defaults({organizationId:'other-org'})).state,'unknown');
 assert.equal(projectWorkItem(defaults({verifyQueueRecord:()=>false})).state,'unknown');
 assert.equal(projectWorkItem(defaults({verifyQueueRecord:()=>{throw Error('offline')}})).state,'unknown');
});
test('G2 queue success means only work item created; not engineering delivery',()=>{
 const p=projectWorkItem(defaults());
 assert.equal(p.state,'work_item_created');
 assert.equal(p.created,true);
 assert.equal(p.delivered,false);
 assert.equal(p.taskId,'task-001');
 assert.equal(JSON.stringify(p).includes('customer'),false);
 assert.equal(Object.isFrozen(p),true);
});
test('pending, approved and running do not assert creation',()=>{
 const mapping={pending:'awaiting_approval',approved:'awaiting_execution',running:'execution_unconfirmed'};
 for(const [status,expected] of Object.entries(mapping)){
   const p=projectWorkItem(defaults({job:queue({status})}));
   assert.equal(p.state,expected);
   assert.equal(p.created,false);
 }
});
test('denied, failed, cancelled and uncertain never become delivered',()=>{
 const mapping={rejected:'rejected',failed:'failed',cancelled:'cancelled',uncertain:'blocked_uncertain'};
 for(const [status,expected] of Object.entries(mapping)){
   const p=projectWorkItem(defaults({job:queue({status}),deliveryEvidence:delivery()}));
   assert.equal(p.state,expected);
   assert.equal(p.delivered,false);
 }
});
test('missing task creation receipt requires reconciliation',()=>{
 for(const result of [undefined,null,{taskId:'task-001'}, {taskId:'task-001',receiptSha256:'invalid'}]){
  const p=projectWorkItem(defaults({job:queue({result})}));
  assert.equal(p.state,'blocked_uncertain');
  assert.equal(p.delivered,false);
 }
});
test('an independent matching founder-accepted delivery can be projected only after G2 receipt',()=>{
 const p=projectWorkItem(defaults({deliveryEvidence:delivery()}));
 assert.equal(p.created,true);
 assert.equal(p.delivered,true);
 assert.equal(p.state,'delivery_verified');
 assert.equal(p.evidenceRef,'owner:accept-001');
});
test('self asserted, forged and verifier-throwing delivery never passes',()=>{
 for(const verifyDeliveryEvidence of [undefined,()=>false,()=>{throw Error('bad signature')}]) {
  const p=projectWorkItem(defaults({deliveryEvidence:delivery(),verifyDeliveryEvidence}));
  assert.equal(p.state,'delivery_unverified');
  assert.equal(p.delivered,false);
 }
});
test('scope mismatch, digest mismatch, task mismatch, missing tests and future owner acceptance deny delivery',()=>{
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
test('unrecognized operations, bad digest and synthetic other-org queue do not enter board',()=>{
 for(const change of [
  {operation:'deploy_release'},{system:'arbitrary'},{digest:'bad'},
  {status:'agent_claimed_succeeded'},{revision:-1},{organizationId:'org-other'},
 ]){
  const p=projectWorkItem(defaults({job:queue(change)}));
  assert.equal(p.state,'unknown',JSON.stringify(change));
 }
});
test('board counts created vs delivered vs awaiting, without task text or duplicate job IDs',()=>{
 const records=[
   queue({id:'job-001'}),
   queue({id:'job-002',status:'approved',result:null}),
   queue({id:'job-003',result:{taskId:'task-003',receiptSha256:RECEIPT}}),
 ];
 const snapshot=summarizeDeliveryBoard({
  jobs:records,organizationId:'org-v79',nowMs:NOW,
  verifyQueueRecord:()=>true,verifyDeliveryEvidence:()=>true,
  deliveryEvidenceByJobId:{'job-001':delivery()},
 });
 assert.equal(snapshot.state,'verified_queue_projection');
 assert.deepEqual(snapshot.totals,{awaiting:1,created:1,delivered:1,blocked:0});
 assert.equal(JSON.stringify(snapshot).includes('summary'),false);
 assert.equal(summarizeDeliveryBoard({
   jobs:[records[0],records[0]],organizationId:'org-v79',
   verifyQueueRecord:()=>true
 }).state,'unavailable');
});
test('failed queue verification fails the whole board rather than returning partial false counts',()=>{
 const snapshot=summarizeDeliveryBoard({
  jobs:[queue()],organizationId:'org-v79',verifyQueueRecord:()=>false,
 });
 assert.equal(snapshot.state,'unavailable');
 assert.equal(snapshot.rows.length,0);
});
