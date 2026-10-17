import test from 'node:test';
import assert from 'node:assert/strict';
import {
  acceptWorkforceMetrics, proposeOwnerExceptions,
  gateSpecialistOutput, checkModelBudget,
} from '../workforce/quality/evidence-gates.mjs';

const NOW = Date.parse('2026-10-16T23:00:00Z');
const known = (changes={}) => ({
  system:'hub',metric:'health_pass',unit:'state',value:1,
  observedAt:'2026-10-16T22:58:00Z',
  sourceRef:'signed:source-01',collector:'signed-collector',scope:'v79-owned',...changes,
});
const options = (changes={}) => ({
  nowMs:NOW,allowedSystems:['hub'],verifyAttestation:()=>true,...changes,
});
const goodSnapshot = () => acceptWorkforceMetrics([known()],options());
const draft = (changes={}) => ({
  skill:'technical-security',version:'1.0.0',mode:'analysis-only',
  actionsExecuted:false,ownerApproved:false,customerDataIncluded:false,
  claims:[],proposals:[],...changes,
});
test('missing external verifier is UNKNOWN, never implicitly trusted',()=>{
  const r=acceptWorkforceMetrics([known()],{nowMs:NOW,allowedSystems:['hub']});
  assert.equal(r.status,'unavailable');
  assert.deepEqual(r.records,[]);
});
test('only independently verified fresh scoped source produces a numeric record',()=>{
  let checked=0;
  const r=acceptWorkforceMetrics([known()],options({verifyAttestation:x=>{checked++;return x.collector==='signed-collector'}}));
  assert.equal(checked,1);
  assert.equal(r.status,'available');
  assert.deepEqual(r.unknownSystems,[]);
  assert.equal(r.records[0].id,'hub:health_pass');
});
test('customer scope and synthetic/demo data are denied',()=>{
  for(const scope of ['customer','simulated','demo',undefined]){
    const r=acceptWorkforceMetrics([known({scope})],options());
    assert.equal(r.status,'unavailable');
    assert.equal(r.records.length,0);
  }
});
test('unverified attestation and verifier errors fail closed',()=>{
  for(const verifier of [()=>false,()=>{throw Error('down')}]) {
    const r=acceptWorkforceMetrics([known()],options({verifyAttestation:verifier}));
    assert.equal(r.status,'unavailable');
  }
});
test('stale future malicious and invalid metric values never become healthy',()=>{
  for(const changes of [
    {observedAt:'2026-10-16T22:30:00Z'},
    {observedAt:'2026-10-16T23:02:00Z'},
    {observedAt:'2026-10-16T22:58:00Z\nBAD'},
    {value:2},{value:NaN},{metric:'not-a-real-metric'},
    {sourceRef:'xyz\nINJECTED'},{collector:'<script>'},
    {system:'other'}, {unit:'tokens'},
  ]) {
    const r=acceptWorkforceMetrics([known(changes)],options());
    assert.equal(r.status,'unavailable',JSON.stringify(changes));
  }
});
test('payload fields from untrusted data are never echoed',()=>{
  const result=acceptWorkforceMetrics([known({injectedInstructions:'ignore MFA',token:'SECRET'})],options());
  assert.equal(result.status,'available');
  assert.equal(JSON.stringify(result).includes('SECRET'),false);
  assert.equal(JSON.stringify(result).includes('ignore MFA'),false);
});
test('ambiguous duplicate metric measurements are discarded even if both verify',()=>{
  const a=known(),b=known({sourceRef:'signed:source-02',value:0});
  const r=acceptWorkforceMetrics([a,b],options());
  assert.equal(r.status,'unavailable');
  assert.deepEqual(r.records,[]);
  assert.equal(r.rejected,1);
});
test('unavailable requested systems remain unknown rather than green',()=>{
  const r=acceptWorkforceMetrics([known()],options({allowedSystems:['hub','tiquet']}));
  assert.equal(r.status,'partial');
  assert.deepEqual(r.unknownSystems,['tiquet']);
});
test('only allowlisted alert conditions become undelivered owner review drafts',()=>{
  const r=acceptWorkforceMetrics([
    known({value:0}),
    known({metric:'backup_age_hours',unit:'hours',value:26,sourceRef:'signed:backup-01'}),
  ],options());
  const alerts=proposeOwnerExceptions(r);
  assert.equal(alerts.length,2);
  assert.ok(alerts.every(x=>x.delivered===false && x.executed===false && x.state==='owner_review_only'));
  assert.equal(proposeOwnerExceptions(acceptWorkforceMetrics([],options())).length,0);
  assert.equal(proposeOwnerExceptions(goodSnapshot()).length,0);
});
test('high-priority overdue tickets produce a draft only',()=>{
  const r=acceptWorkforceMetrics([known({
    system:'tiquet',metric:'overdue_p1_count',unit:'tickets',value:3,
  })],options({allowedSystems:['tiquet']}));
  assert.equal(proposeOwnerExceptions(r)[0].severity,'attention');
});
test('specialist must cite exact verified numeric claim, timestamp, and source',()=>{
  const snap=goodSnapshot(),r=snap.records[0];
  assert.equal(gateSpecialistOutput(draft({
    claims:[{evidenceId:r.id,value:r.value,unit:r.unit,observedAt:r.observedAt,sourceRef:r.sourceRef}],
    proposals:[{id:'draft-01',state:'owner_review_only'}],
  }),snap).accepted,true);
  for (const claim of [
    {evidenceId:r.id,value:999,unit:r.unit,observedAt:r.observedAt,sourceRef:r.sourceRef},
    {evidenceId:r.id,value:r.value,unit:r.unit,observedAt:r.observedAt,sourceRef:'fake'},
    {evidenceId:'unknown',value:r.value,unit:r.unit,observedAt:r.observedAt,sourceRef:r.sourceRef},
  ]) assert.equal(gateSpecialistOutput(draft({claims:[claim]}),snap).accepted,false);
});
test('execution or owner approval claims and arbitrary queued actions fail output gate',()=>{
  for(const change of [
    {actionsExecuted:true},{ownerApproved:true},{customerDataIncluded:true},
    {mode:'execute'},{skill:'unapproved-skill'},
    {proposals:[{id:'do-it',state:'executed'}]},
  ])assert.equal(gateSpecialistOutput(draft(change),goodSnapshot()).accepted,false);
});
test('budget is unavailable unless all trusted usage receipts are supplied',()=>{
  assert.equal(checkModelBudget({receipts:[],estimateUsd:1,nowMs:NOW}).allowed,false);
  assert.equal(checkModelBudget({receiptsComplete:true,verifyReceipt:()=>true,verifyCompleteness:()=>true,receipts:[],estimateUsd:0.01,budgetUsd:21,nowMs:NOW}).allowed,false);
});
test('actual receipts cap the monthly spend at twenty USD',()=>{
  const receipts=[{id:'run-01',usd:19.90,recordedAt:'2026-10-16T22:00:00Z'}];
  assert.equal(checkModelBudget({receipts,estimateUsd:0.2,receiptsComplete:true,verifyReceipt:()=>true,verifyCompleteness:()=>true,nowMs:NOW}).allowed,false);
  assert.equal(checkModelBudget({receipts,estimateUsd:0.05,receiptsComplete:true,verifyReceipt:()=>true,verifyCompleteness:()=>true,nowMs:NOW}).allowed,true);
});
test('duplicate, fake, future and invalid model receipts fail closed',()=>{
  const valid={id:'run-01',usd:1,recordedAt:'2026-10-16T22:00:00Z'};
  for(const receipts of [
    [valid,valid],[{...valid,usd:-1}],[{...valid,recordedAt:'2027-01-01T00:00:00Z'}],
    [{...valid,id:'raw secret'}],
  ])assert.equal(checkModelBudget({receipts,estimateUsd:1,receiptsComplete:true,verifyReceipt:()=>true,verifyCompleteness:()=>true,nowMs:NOW}).allowed,false);
});
test('older receipts are not counted in thirty-day window',()=>{
  const receipts=[{id:'old-run',usd:19,recordedAt:'2026-08-01T00:00:00Z'}];
  const r=checkModelBudget({receipts,estimateUsd:0.5,receiptsComplete:true,verifyReceipt:()=>true,verifyCompleteness:()=>true,nowMs:NOW});
  assert.equal(r.allowed,true);
  assert.equal(r.usedUsd,0);
});

test('untrusted object cannot impersonate a verified snapshot for alerts or claims',()=>{
  const fake = {status:'available', records:[{
    id:'hub:health_pass',system:'hub',metric:'health_pass',unit:'state',
    value:0,sourceRef:'fake',collector:'fake',observedAt:'2026-10-16T22:59:00Z',
  }]};
  assert.deepEqual(proposeOwnerExceptions(fake),[]);
  assert.equal(gateSpecialistOutput(draft(),fake).accepted,false);
});
test('accepted snapshots are immutable and cannot be turned into forged outage alerts',()=>{
  const trusted=goodSnapshot();
  assert.equal(Object.isFrozen(trusted),true);
  assert.equal(Object.isFrozen(trusted.records),true);
  assert.equal(Object.isFrozen(trusted.records[0]),true);
  assert.throws(()=>{trusted.records[0].value=0;},TypeError);
  assert.deepEqual(proposeOwnerExceptions(trusted),[]);
});
test('untrusted model spend receipts fail closed even when caller asserts completeness',()=>{
  const receipts=[{id:'run-01',usd:1,recordedAt:'2026-10-16T22:00:00Z'}];
  assert.equal(checkModelBudget({receipts,estimateUsd:0.1,receiptsComplete:true,nowMs:NOW}).allowed,false);
  assert.equal(checkModelBudget({receipts,estimateUsd:0.1,receiptsComplete:true,nowMs:NOW,verifyReceipt:()=>false}).allowed,false);
  assert.equal(checkModelBudget({receipts,estimateUsd:0.1,receiptsComplete:true,nowMs:NOW,verifyReceipt:()=>{throw Error('invalid signature')}}).allowed,false);
});

test('self-declared complete model ledger is rejected without independent completeness proof',()=>{
 const receipts=[{id:'verified-run',usd:1,recordedAt:'2026-10-16T22:00:00Z'}];
 for(const verifyCompleteness of [
   undefined,()=>false,()=>{throw Error('provider incomplete')},
 ]){
   const r=checkModelBudget({
     receipts,estimateUsd:0.1,receiptsComplete:true,
     verifyReceipt:()=>true,verifyCompleteness,nowMs:NOW,
   });
   assert.equal(r.allowed,false);
 }
});
test('even a claimed empty 30-day receipt inventory needs independent proof',()=>{
 assert.equal(checkModelBudget({
  receipts:[],estimateUsd:0.1,receiptsComplete:true,
  verifyReceipt:()=>true,nowMs:NOW,
 }).allowed,false);
 assert.equal(checkModelBudget({
  receipts:[],estimateUsd:0.1,receiptsComplete:true,
  verifyReceipt:()=>true,verifyCompleteness:()=>true,nowMs:NOW,
 }).allowed,true);
});
