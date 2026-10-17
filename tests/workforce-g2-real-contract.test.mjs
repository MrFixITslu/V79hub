import test from 'node:test';
import assert from 'node:assert/strict';
import {
  initialWorkState, proposeWork, decideWork, createApprovedWorkItem,
  publicWorkJob,
} from '../server/workforce-actions.mjs';
import { projectWorkItem, summarizeDeliveryBoard } from '../workforce/quality/task-delivery-gates.mjs';

const OWNER_ORG='v79-synthetic-owner';
const ACTOR='v79-synthetic-mfa-owner';
const NOW=Date.parse('2026-10-17T12:00:00.000Z');
const REQUEST={
  operation:'create_work_item',system:'hub',summary:'Review isolated synthetic acceptance',
  payload:{detail:'Validate the local synthetic task lifecycle without contacting production'},
  idempotencyKey:'synthetic-contract-20261017',
};
const trust={
  organizationId:OWNER_ORG,nowMs:NOW+120_000,
  // Synthetic fixtures only. Live callers MUST attest the HMAC-authenticated G2
  // ledger and session context, not pass identity callbacks that always return true.
  verifyQueueRecord:()=>true,verifyTaskRecord:()=>true,
  verifyDeliveryEvidence:()=>false,
};
function fixture() {
  const state=initialWorkState();
  const proposed=proposeWork(state,REQUEST,{
    organizationId:OWNER_ORG,actor:ACTOR,now:NOW,
  });
  return {state,proposed};
}
test('actual G2 createApprovedWorkItem result is taskId/at, never a release receipt hash',()=>{
  const {state,proposed}=fixture();
  const approved=decideWork(state,proposed.id,'approve',{
    organizationId:OWNER_ORG,actor:ACTOR,
    expectedRevision:proposed.revision,digest:proposed.digest,now:NOW+1000,
  });
  const executed=createApprovedWorkItem(state,approved.id,{
    organizationId:OWNER_ORG,actor:'synthetic-coo-worker',
    expectedRevision:approved.revision,now:NOW+2000,
  });
  assert.deepEqual(Object.keys(executed.result).sort(),['at','taskId']);
  assert.equal(state.tasks.length,1);
  assert.equal(state.tasks[0].status,'open');
  assert.equal(state.tasks[0].assignedTo,'coo');
  assert.equal(state.tasks[0].createdAt,executed.result.at);
  const verified=projectWorkItem({
    ...trust,job:publicWorkJob(executed),taskRecord:state.tasks[0],
  });
  assert.equal(verified.state,'work_item_created');
  assert.equal(verified.created,true);
  assert.equal(verified.delivered,false);
  assert.equal(verified.taskId,executed.result.taskId);
  assert.equal(verified.evidenceRef,null);
  const board=summarizeDeliveryBoard({
    ...trust,jobs:state.jobs.map(publicWorkJob),tasks:state.tasks,
  });
  assert.deepEqual(board.totals,{awaiting:0,created:1,delivered:0,blocked:0});
  assert.equal(JSON.stringify(board).includes('synthetic-contract-20261017'),false);
});
test('actual G2 rejection cannot create a task or be called delivered',()=>{
  const {state,proposed}=fixture();
  const denied=decideWork(state,proposed.id,'reject',{
    organizationId:OWNER_ORG,actor:ACTOR,
    expectedRevision:proposed.revision,digest:proposed.digest,now:NOW+1000,
  });
  assert.equal(state.tasks.length,0);
  assert.throws(()=>createApprovedWorkItem(state,denied.id,{
    organizationId:OWNER_ORG,actor:ACTOR,expectedRevision:denied.revision,now:NOW+2000,
  }));
  const projection=projectWorkItem({...trust,job:publicWorkJob(denied)});
  assert.equal(projection.state,'rejected');
  assert.equal(projection.created,false);
  assert.equal(projection.delivered,false);
});
test('actual G2 approval alone stays awaiting execution without a task',()=>{
  const {state,proposed}=fixture();
  const approved=decideWork(state,proposed.id,'approve',{
    organizationId:OWNER_ORG,actor:ACTOR,
    expectedRevision:proposed.revision,digest:proposed.digest,now:NOW+1000,
  });
  assert.equal(state.tasks.length,0);
  const board=summarizeDeliveryBoard({...trust,
    jobs:[publicWorkJob(approved)],tasks:state.tasks,
  });
  assert.equal(board.rows[0].state,'awaiting_execution');
  assert.deepEqual(board.totals,{awaiting:1,created:0,delivered:0,blocked:0});
});
