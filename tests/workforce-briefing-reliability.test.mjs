import test from 'node:test';
import assert from 'node:assert/strict';
import {auditBriefingReliability} from '../workforce/quality/briefing-reliability.mjs';
const START='2026-10-13';
const NOW='2026-10-16T01:00:00Z';
const reports=()=>{
 const out=[];
 for(let d=13;d<=15;d++){
  for(const [name,time] of [['morning','12:02:00'],['evening','23:02:00']]){
   const day='2026-10-'+String(d).padStart(2,'0');
   out.push({
    slot:day+'-'+name,checkedAt:day+'T'+time+'Z',
    state:'recorded',report:{noActionsExecuted:true,coverage:'available'},
   });
  }
 }
 return out;
};
const opts=(changes={})=>({
 firstDay:START,days:3,asOfUtc:NOW,
 reports:reports(),verifyReport:()=>true,verifyInventory:()=>true,...changes,
});
test('six morning/evening observations over three days are candidate only, not launch approval',()=>{
 const r=auditBriefingReliability(opts());
 assert.equal(r.status,'candidate_for_owner_acceptance');
 assert.equal(r.summary.verified,6);
 assert.equal(r.summary.missing,0);
 assert.equal(r.slots.length,6);
 assert.equal(r.slots[0].expectedAt,'2026-10-13T12:00:00.000Z');
 assert.equal(r.slots[1].expectedAt,'2026-10-13T23:00:00.000Z');
 assert.equal(Object.isFrozen(r.slots),true);
});
test('one evening proof is not sustained operation',()=>{
 const r=auditBriefingReliability(opts({reports:reports().slice(-1)}));
 assert.equal(r.status,'not_yet_accepted');
 assert.equal(r.summary.missing,5);
 assert.equal(r.summary.verified,1);
});
test('missing report inventory verification prevents false green',()=>{
 const r=auditBriefingReliability(opts({verifyInventory:()=>false}));
 assert.equal(r.status,'not_yet_accepted');
 assert.equal(r.inventoryVerified,false);
 const nothing=auditBriefingReliability(opts({reports:[],verifyInventory:undefined}));
 assert.equal(nothing.summary.unverified,6);
 assert.equal(nothing.summary.missing,0);
});
test('report without independent signature or protected provenance remains unverified',()=>{
 for(const v of [undefined,()=>false,()=>{throw Error('untrusted')}]) {
  const r=auditBriefingReliability(opts({verifyReport:v}));
  assert.equal(r.status,'not_yet_accepted');
  assert.equal(r.summary.unverified,6);
 }
});
test('duplicate scheduled report cannot count as reliable execution',()=>{
 const r=auditBriefingReliability(opts({reports:[...reports(),reports()[0]]}));
 assert.equal(r.status,'not_yet_accepted');
 assert.equal(r.summary.unverified,1);
 assert.equal(r.summary.verified,5);
});
test('malformed, stale, premature and delayed reports do not count',()=>{
 for(const change of [
  {checkedAt:'not-a-time'},{checkedAt:'2026-10-13T11:40:00Z'},
  {checkedAt:'2026-10-13T12:40:00Z'},
  {state:'executed'},{report:{noActionsExecuted:false,coverage:'available'}},
  {report:{noActionsExecuted:true,coverage:'unknown'}},
 ]){
  const all=reports();all[0]={...all[0],...change};
  const r=auditBriefingReliability(opts({reports:all}));
  assert.equal(r.status,'not_yet_accepted',JSON.stringify(change));
  assert.equal(r.summary.unverified,1,JSON.stringify(change));
 }
});
test('partial evidence must never be conflated with complete verified coverage',()=>{
 const a=reports();a[0].report.coverage='incomplete';
 const r=auditBriefingReliability(opts({reports:a}));
 assert.equal(r.status,'not_yet_accepted');
 assert.equal(r.summary.incomplete,1);
 assert.equal(r.summary.verified,5);
});
test('future slots remain pending rather than missed',()=>{
 const r=auditBriefingReliability(opts({
  firstDay:'2026-10-16',days:2,asOfUtc:'2026-10-16T12:05:00Z',
  reports:[],verifyInventory:()=>true,
 }));
 assert.equal(r.summary.pending,4);
 assert.equal(r.summary.missing,0);
 assert.equal(r.status,'not_yet_accepted');
});
test('a due report is only missing after its bounded grace interval',()=>{
 const before=auditBriefingReliability(opts({
  firstDay:'2026-10-16',days:1,asOfUtc:'2026-10-16T12:25:00Z',
  reports:[],
 }));
 assert.equal(before.summary.pending,2);
 const after=auditBriefingReliability(opts({
  firstDay:'2026-10-16',days:1,asOfUtc:'2026-10-16T12:31:00Z',
  reports:[],
 }));
 assert.equal(after.summary.missing,1);
 assert.equal(after.summary.pending,1);
});
test('bad scope and invalid calendar dates fail closed, not crash',()=>{
 for(const arg of [
  {firstDay:'2026-99-99'},{firstDay:'2026-02-30'},
  {days:20},{days:0},{reports:'not-array'},{asOfUtc:'2026-10-16'},
 ]){
  const r=auditBriefingReliability(opts(arg));
  assert.equal(r.status,'unavailable',JSON.stringify(arg));
  assert.equal(r.slots.length,0);
 }
});
test('one missing early slot prevents acceptance even with later perfect slots',()=>{
 const all=reports().slice(1);
 const r=auditBriefingReliability(opts({reports:all}));
 assert.equal(r.status,'not_yet_accepted');
 assert.equal(r.summary.verified,5);
 assert.equal(r.summary.missing,1);
});
