import test from 'node:test';
import assert from 'node:assert/strict';
import {register} from 'tsx/esm/api';
import {Window} from 'happy-dom';
import React,{act} from 'react';
register();
const browser=new Window({url:'https://hub.synthetic.test'});
for(const key of ['document','HTMLElement','Event','MouseEvent','DOMException'])globalThis[key]=browser[key];
globalThis.window=browser;globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const {createRoot}=await import('react-dom/client');
const {WorkforceDeliveryPanel}=await import('../src/components/WorkforceDeliveryPanel.tsx');
const data={mode:'owner-approved-actions',delivery:{mode:'read-only',state:'verified_queue_projection',independentDeliveryVerification:'not_configured',window:'latest-200-work-items',totals:{awaiting:0,created:1,blocked:0,delivered:0},rows:[{jobId:'job-1',taskId:'task-1',system:'hub',state:'work_item_created',created:true,delivered:false}]}};
test('delivery panel GET-only, clears data after access failure, never treats creation as completion',async()=>{
 const box=document.createElement('div');document.body.append(box);const root=createRoot(box);const calls=[];
 globalThis.fetch=async(url,opts)=>{calls.push({url,opts});return calls.length===1?{ok:true,json:async()=>structuredClone(data)}:{ok:false,status:403}};
 try{
  await act(async()=>root.render(React.createElement(WorkforceDeliveryPanel,{active:false})));
  assert.equal(calls.length,0);
  await act(async()=>root.render(React.createElement(WorkforceDeliveryPanel,{active:true})));
  assert.equal(calls[0].opts.method,'GET');assert.equal(calls[0].url,'/api/agent/work-actions');
  assert.match(box.textContent,/task-1/);assert.match(box.textContent,/delivery unverified/);
  await act(async()=>box.querySelector('button').click());
  assert.doesNotMatch(box.textContent,/task-1/);assert.match(box.textContent,/MFA-verified/);
 }finally{await act(async()=>root.unmount());box.remove();delete globalThis.fetch;}
});
test('forged verified-delivery response fails closed in the UI',async()=>{
 const box=document.createElement('div'),root=createRoot(box);
 const forged=structuredClone(data);forged.delivery.totals.delivered=1;forged.delivery.rows[0].delivered=true;
 globalThis.fetch=async()=>({ok:true,json:async()=>forged});
 try{await act(async()=>root.render(React.createElement(WorkforceDeliveryPanel)));assert.match(box.textContent,/unavailable on this release/);assert.doesNotMatch(box.textContent,/task-1/);}
 finally{await act(async()=>root.unmount());delete globalThis.fetch;}
});
