import test from 'node:test';
import assert from 'node:assert/strict';
import {register} from 'tsx/esm/api';
import {Window} from 'happy-dom';
import React,{act} from 'react';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
register();
const browser=new Window({url:'https://hub.synthetic.test'});
for(const key of ['document','HTMLElement','Event','MouseEvent','DOMException'])globalThis[key]=browser[key];
globalThis.window=browser;globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const {createRoot}=await import('react-dom/client');
const {PlatformAdminOverview,countMetric}=await import('../src/components/PlatformAdminOverview.tsx');
const {OwnerToday}=await import('../src/components/OwnerToday.tsx');
const base='7bd2e8234dc4bb4ee36af4d83f9e292d6c5ffb31';
const protectedPaths=['server.ts','src/components/WorkforceActionPanel.tsx','src/components/AgentApprovalInbox.tsx','src/components/GoogleWorkforcePanel.tsx','src/components/MarketingProductionPanel.tsx','src/components/OwnerCooWorkboardPanel.tsx','src/components/WorkforceBriefingHistory.tsx','src/components/ExecutiveReviewPanel.tsx','src/components/PlatformCustomersAdmin.tsx','src/components/PlatformPlansAdmin.tsx','src/components/PlatformAuditAdmin.tsx','src/lib/hubNavigation.ts','src/lib/appLaunch.ts'];
test('authorization, execution, subscription and confirmation implementations remain unchanged',()=>{
 for(const path of protectedPaths)assert.equal(readFileSync(path,'utf8'),execFileSync('git',['show',`${base}:${path}`],{encoding:'utf8'}),path);
});
async function mount(t,Component,props,handler){
 const box=document.createElement('div');document.body.append(box);const root=createRoot(box),calls=[];
 const originalSet=window.setInterval,originalClear=window.clearInterval;
 window.setInterval=()=>1;window.clearInterval=()=>{};
 globalThis.fetch=async(url,opts={})=>{calls.push({url,opts});const value=await handler(url,opts);return value?.json?value:{ok:true,status:200,json:async()=>structuredClone(value)};};
 await act(async()=>root.render(React.createElement(Component,props)));
 t.after(async()=>{await act(async()=>root.unmount());box.remove();window.setInterval=originalSet;window.clearInterval=originalClear;delete globalThis.fetch;});
 return {box,calls,click:async label=>{const b=[...box.querySelectorAll('button')].find(b=>b.textContent.trim()===label);assert.ok(b,label);await act(async()=>b.click());},render:async props=>act(async()=>root.render(React.createElement(Component,props)))};
}
const snapshot=()=>({generatedAt:new Date().toISOString(),hub:{customers:7,activeCustomers:6,provisioningCustomers:2,pendingInvitations:1},apps:{pos:{status:'ok',metrics:{totalTenants:0,activeTenants:3,completedSales:19,openPurchaseOrders:2}},tiquet:{status:'ok',metrics:{}},ffpro:{status:'error',metrics:{totalAccounts:999}}}});
const props={onOpen:()=>{},onCustomers:()=>{}};
test('missing, invalid and unavailable metrics never become zero',async t=>{
 for(const value of [undefined,null,'',false,'7',NaN,Infinity,-1,{},[]])assert.equal(countMetric(value),'—');
 assert.equal(countMetric(0),0);assert.equal(countMetric(12),12);
 const h=await mount(t,PlatformAdminOverview,props,snapshot);
 assert.equal(h.box.querySelector('[data-product=pos] dd').textContent,'0');
 for(const product of ['tiquet','ffpro'])assert.ok([...h.box.querySelectorAll(`[data-product=${product}] dd`)].every(e=>e.textContent==='—'));
 assert.match(h.box.textContent,/Partial statistics/);assert.doesNotMatch(h.box.textContent,/Healthy|Core services healthy|999/);
});
test('initial failure shows unknown customer counts',async t=>{
 const h=await mount(t,PlatformAdminOverview,props,()=>({ok:false,status:503,json:async()=>({error:'Synthetic unavailable'})}));
 assert.ok([...h.box.querySelectorAll('.v79-admin-metric strong')].every(e=>e.textContent==='—'));assert.match(h.box.textContent,/Synthetic unavailable/);
});
test('malformed statistics do not replace a verified snapshot',async t=>{
 let data=snapshot();const h=await mount(t,PlatformAdminOverview,props,()=>data);data={hub:[],apps:{},generatedAt:'invalid'};await h.click('Refresh');
 assert.match(h.box.textContent,/could not be verified/);assert.match(h.box.textContent,/Stale snapshot/);
});
test('refresh failure marks retained data stale; access denial clears it',async t=>{
 let mode=200;const h=await mount(t,PlatformAdminOverview,props,()=>mode===200?snapshot():{ok:false,status:mode,json:async()=>({error:'Synthetic failure'})});
 mode=503;await h.click('Refresh');assert.match(h.box.textContent,/Stale snapshot/);assert.equal(h.box.querySelector('.v79-admin-metric strong').textContent,'7');
 assert.ok([...h.box.querySelectorAll('.v79-data-status')].every(e=>e.textContent==='Stale snapshot'));
 mode=403;await h.click('Refresh');assert.ok([...h.box.querySelectorAll('.v79-admin-metric strong')].every(e=>e.textContent==='—'));assert.match(h.box.textContent,/authorized platform administrator/);
});
test('old and future-dated snapshots are marked stale',async t=>{
 const data=snapshot();data.generatedAt=new Date(Date.now()-3600000).toISOString();const h=await mount(t,PlatformAdminOverview,props,()=>data);assert.match(h.box.textContent,/Stale snapshot/);
 data.generatedAt=new Date(Date.now()+3600000).toISOString();await h.click('Refresh');assert.match(h.box.textContent,/Stale snapshot/);
});
test('provisioning opens customers, while application cards retain product destinations',async t=>{
 let customers=0,product=null;const h=await mount(t,PlatformAdminOverview,{onCustomers:()=>customers++,onOpen:p=>product=p},snapshot);
 await act(async()=>[...h.box.querySelectorAll('button')].find(b=>b.textContent.includes('Customers awaiting provisioning')).click());assert.equal(customers,1);assert.equal(product,null);
 await act(async()=>h.box.querySelector('[data-product=academy]').click());assert.equal(product,'academy');assert.ok(h.calls.every(c=>!c.opts.method));
});
const todayProps={active:true,onTasks:()=>{},onAsk:()=>{},onDelivery:()=>{}};
const queue=()=>({mode:'owner-approved-actions',enabled:true,paused:false,jobs:[
 {id:'pending',summary:'Review pilot invitation',system:'hub',status:'pending'},
 {id:'uncertain',summary:'Reconcile prior operation',system:'hub',status:'uncertain'},
 {id:'expired',summary:'Expired authorization',system:'hub',status:'approved',approval:{expiresAt:'2020-01-01'}},
 {id:'running',summary:'Active operation',system:'hub',status:'running'},
 {id:'created',summary:'Created work item',system:'hub',status:'succeeded'},
]});
test('Today separates pending, executing and follow-up without claiming work complete',async t=>{
 const h=await mount(t,OwnerToday,todayProps,queue);assert.deepEqual([...h.box.querySelectorAll('.v79-owner-metric strong')].map(e=>e.textContent),['1','1','2']);
 assert.match(h.box.textContent,/Approval expired/);assert.match(h.box.textContent,/Needs reconciliation/);assert.ok(h.calls.every(c=>!c.opts.method));assert.equal(h.calls.length,1);
});
test('Today clears private summaries on denial and does not present unknown as zero',async t=>{
 let denied=false;const h=await mount(t,OwnerToday,todayProps,()=>denied?{ok:false,status:403,json:async()=>({})}:queue());denied=true;await h.click('Refresh summary');
 assert.ok([...h.box.querySelectorAll('.v79-owner-metric strong')].every(e=>e.textContent==='—'));assert.doesNotMatch(h.box.textContent,/Review pilot invitation/);assert.match(h.box.textContent,/MFA-verified owner/);
});
test('Today ignores a late response after leaving the view',async t=>{
 let resolve;const h=await mount(t,OwnerToday,todayProps,()=>new Promise(r=>resolve=r));await h.render({...todayProps,active:false});assert.equal(h.calls[0].opts.signal.aborted,true);
 await act(async()=>resolve(queue()));assert.doesNotMatch(h.box.textContent,/Review pilot invitation/);
});
