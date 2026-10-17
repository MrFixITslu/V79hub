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
const {WorkforceBriefingHistory}=await import('../src/components/WorkforceBriefingHistory.tsx');
const history={mode:'read-only',status:'report_available',reports:[{slot:'2026-10-16-evening',ranAt:'2026-10-16T23:00:22Z',state:'available',report:{priority:'attention',coverage:'available',findings:[{id:'1',system:'hub',metric:'faults',value:5,severity:'attention'}],missingSources:[]}}]};
test('history loads only on demand using GET and clears reports after MFA failure',async()=>{
 const box=document.createElement('div');document.body.append(box);const root=createRoot(box);const calls=[];
 globalThis.fetch=async(url,opts)=>{calls.push({url,opts});return calls.length===1?{ok:true,json:async()=>structuredClone(history)}:{ok:false,status:403}};
 try {
  await act(async()=>root.render(React.createElement(WorkforceBriefingHistory)));
  assert.equal(calls.length,0);
  await act(async()=>box.querySelector('button').click());
  assert.equal(calls[0].url,'/api/agent/workforce-briefings');assert.equal(calls[0].opts.method,'GET');
  assert.match(box.textContent,/faults: 5/);
  await act(async()=>box.querySelector('button').click());
  assert.doesNotMatch(box.textContent,/faults: 5/);assert.match(box.textContent,/MFA-verified/);
 }finally{await act(async()=>root.unmount());box.remove();delete globalThis.fetch;}
});
test('invalid evidence does not display and stale history is explicitly labelled',async()=>{
 for(const status of ['invalid','stale_or_unavailable']){
  const data=structuredClone(history);data.status=status;
  const box=document.createElement('div');const root=createRoot(box);
  globalThis.fetch=async()=>({ok:true,json:async()=>data});
  try{
   await act(async()=>root.render(React.createElement(WorkforceBriefingHistory)));
   await act(async()=>box.querySelector('button').click());
   if(status==='invalid'){assert.doesNotMatch(box.textContent,/faults: 5/);assert.match(box.textContent,/could not be verified/);}
   else assert.match(box.textContent,/Historical evidence; current conditions are unverified/);
  }finally{await act(async()=>root.unmount());delete globalThis.fetch;}
 }
});
