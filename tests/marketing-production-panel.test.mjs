import test from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'tsx/esm/api';
import { Window } from 'happy-dom';
import React, { act } from 'react';
register();

const window = new Window({url:'https://hub.test', settings:{disableCSSFileLoading:true,disableJavaScriptFileLoading:true}});
for (const key of ['window','document','HTMLElement','HTMLInputElement','Event','MouseEvent','DOMException']) globalThis[key]=key==='window'?window:window[key];
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const {createRoot}=await import('react-dom/client');
const {MarketingProductionPanel}=await import('../src/components/MarketingProductionPanel.tsx');
const png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=';
const brand={name:'V79 Digital',tagline:'From Idea to Advantage.',audience:'Caribbean businesses',tone:'Practical',website:'https://v79sl.com',cta:'Visit our website',primaryColor:'#081827',accentColor:'#00D5C9',logoPng:null,mailingAddress:null,facts:[{id:'ict-support',service:'ICT support',statement:'V79 Digital provides ICT support.'}]};
const plan={automaticDrafts:false,cadenceDays:7,channels:['youtube'],publishDelayHours:24,newsletterSegmentId:null,newsletterFrom:null,newsletterConsentConfirmed:false,youtubePrivacy:'private'};

async function harness(t){
  let state={mode:'owner-approved-marketing-production',paused:false,configRevision:1,brand:structuredClone(brand),plan:structuredClone(plan),publishEnabled:false,jobs:[]};
  const calls=[],timers=new Map(),reads=[];let nextTimer=0,failure=false,visibility='visible',slowList=null,cancelFailure=null;
  Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>visibility});
  window.setTimeout=(fn,ms)=>{timers.set(++nextTimer,{fn,ms});return nextTimer;};window.clearTimeout=id=>timers.delete(id);
  window.confirm=()=>true;
  globalThis.FileReader=class{readAsDataURL(file){this.file=file;reads.push(this);}};
  globalThis.Image=class{naturalWidth=100;naturalHeight=100;set src(v){queueMicrotask(()=>v===png?this.onload():this.onerror());}};
  globalThis.fetch=async(_url,options)=>{
    const body=JSON.parse(options.body);calls.push(body);
    if(body.action==='list'){
      if(slowList){const wait=slowList;slowList=null;await wait;}
      if(failure)throw Error('offline');
      return {ok:true,json:async()=>structuredClone(state)};
    }
    if(body.action==='configure'){if(body.config.expectedRevision!==state.configRevision)return {ok:false,json:async()=>({error:'Configuration revision changed'})};state={...state,brand:body.config.brand,plan:body.config.plan,configRevision:state.configRevision+1};return {ok:true,json:async()=>({ok:true})};}
    if(body.action==='queue'){state.jobs=[{id:'campaign',status:'queued',factId:body.request.factId,angle:body.request.angle,deliveries:[]}];return {ok:true,json:async()=>({ok:true})};}
    if(body.action==='approve_batch'){
      if(!state.publishEnabled||!state.approvalBatch||body.batchDigest!==state.approvalBatch.batchDigest)
        return {ok:false,json:async()=>({error:'Exact batch changed'})};
      const approved=state.approvalBatch.deliveries.length;
      state.approvalBatch={batchDigest:null,deliveries:[]};
      return {ok:true,json:async()=>({approved})};
    }
    if(body.action==='cancel'){
      if(body.jobId===cancelFailure)return {ok:false,json:async()=>({error:'Fresh founder MFA required'})};
      const job=state.jobs.find(j=>j.id===body.jobId);
      if(!job||job.status==='generating'||job.deliveries.some(d=>['running','succeeded','uncertain'].includes(d.status)))return {ok:false,json:async()=>({error:'Started effects require operator reconciliation'})};
      job.status='cancelled';for(const d of job.deliveries)if(['awaiting_owner','approved','blocked'].includes(d.status))d.status='cancelled';
      return {ok:true,json:async()=>({cancelled:true})};
    }
    throw Error('Unexpected UI mutation: '+body.action);
  };
  const container=document.createElement('div');document.body.append(container);const root=createRoot(container);
  await act(async()=>root.render(React.createElement(MarketingProductionPanel)));
  t.after(async()=>{await act(async()=>root.unmount());container.remove();});
  const button=label=>[...container.querySelectorAll('button')].find(b=>b.textContent===label);
  const click=async label=>{assert.ok(button(label),label);await act(async()=>button(label).click());};
  const input=label=>[...container.querySelectorAll('label')].find(l=>l.textContent.trim().startsWith(label))?.querySelector('input');
  const change=async(label,value)=>{const el=input(label);assert.ok(el,label);await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new window.Event('input',{bubbles:true}));});};
  const upload=async file=>{const el=container.querySelector('input[type=file]');Object.defineProperty(el,'files',{configurable:true,value:[file]});await act(async()=>el.dispatchEvent(new window.Event('change',{bubbles:true})));};
  const finishLogo=async(index=reads.length-1,value=png)=>{await act(async()=>{reads[index].result=value;reads[index].onload();});};
  const poll=async()=>{const entry=[...timers].find(([,v])=>v.ms===10000);assert.ok(entry,'an automatic update is scheduled');timers.delete(entry[0]);await act(async()=>entry[1].fn());};
  await click('V79 marketing · Production and approvals');
  return {container,button,click,input,change,upload,finishLogo,reads,calls,timers,poll,get state(){return state;},set state(v){state=v;},set failure(v){failure=v;},set slowList(v){slowList=v;},set cancelFailure(v){cancelFailure=v;},async visible(v){visibility=v;await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));}};
}

test('one approval presents all exact accounts, captions and Saint Lucia schedules and rejects stale action',async t=>{
  const h=await harness(t);
  h.state.publishEnabled=true;
  h.state.approvalBatch={batchDigest:'b'.repeat(64),deliveries:[
    {jobId:'job-1',deliveryId:'delivery-1',digest:'1'.repeat(64),channel:'linkedin',
      providerAccountId:'v79-business',accountId:'a-1',scheduledAt:'2026-11-05T14:00:00Z',
      payload:{caption:'Exact LinkedIn copy'},assets:[{name:'image.png',sha256:'f'.repeat(64),mime:'image/png'}],
      material:{title:'Business efficiency',caption:'Approved LinkedIn caption',altText:'ICT service image',videoScript:'Approved script'}},
    {jobId:'job-1',deliveryId:'delivery-2',digest:'2'.repeat(64),channel:'youtube',
      providerAccountId:'v79-channel',accountId:'a-2',scheduledAt:'2026-11-06T18:00:00Z',
      payload:{caption:'Exact YouTube copy'},assets:[],
      material:{title:'Short video',caption:'Approved YouTube caption',altText:'Video cover',videoScript:'Approved script'}},
  ]};
  await h.poll();
  assert.match(h.container.textContent,/Approved LinkedIn caption/);
  assert.match(h.container.textContent,/Approved YouTube caption/);
  assert.match(h.container.textContent,/v79-business/);
  assert.match(h.container.textContent,/v79-channel/);
  assert.match(h.container.textContent,/AST/);
  window.confirm=()=>false;
  await h.click('Approve all 2 scheduled posts');
  assert.equal(h.calls.filter(v=>v.action==='approve_batch').length,0);
  window.confirm=()=>true;
  await h.click('Approve all 2 scheduled posts');
  assert.deepEqual(h.calls.filter(v=>v.action==='approve_batch'),[{action:'approve_batch',batchDigest:'b'.repeat(64)}]);
  assert.match(h.container.textContent,/2 exact publication\(s\) approved/);
});
test('worker readiness appears automatically, reads alone never approve or publish, closed and hidden panels stop polling',async t=>{
  const h=await harness(t);await h.click('Produce a campaign package');
  assert.match(h.container.textContent,/updates automatically when the materials are ready/);
  h.state.jobs[0].status='awaiting_owner';h.state.jobs[0].bundle={source:'brand-template',brand,materials:[],assets:[],review:{warnings:['Text wordmark used; original brand logo has not been supplied'],blockers:[]}};
  await h.poll();assert.match(h.container.textContent,/Awaiting your review/);assert.match(h.container.textContent,/This package was created without a saved logo/);
  assert.deepEqual(h.calls.map(c=>c.action),['list','queue','list','list']);
  await h.visible('hidden');assert.equal(h.timers.size,0);
  const count=h.calls.length;await h.visible('visible');assert.equal(h.calls.length,count+1);
  await h.click('V79 marketing · Production and approvals');assert.equal(h.timers.size,0);
});

test('polling and a delayed file read preserve edited facts and logo; queue requires saving the new brand',async t=>{
  const h=await harness(t);await h.click('Review brand and draft plan');
  await h.upload({type:'image/png',size:100});assert.match(h.container.textContent,/Reading and checking your logo/);
  await h.change('Business name','V79 revised');await h.poll();assert.equal(h.input('Business name').value,'V79 revised');
  await h.finishLogo();assert.equal(h.input('Business name').value,'V79 revised');assert.equal(h.container.querySelector('img').getAttribute('src'),png);
  await h.poll();assert.equal(h.container.querySelector('img').getAttribute('src'),png);assert.equal(h.button('Produce a campaign package').disabled,true);
  await act(async()=>h.input('I verified these facts').click());await h.click('Approve brand and draft plan');
  const saved=h.calls.find(c=>c.action==='configure').config;assert.equal(saved.brand.logoPng,png);assert.equal(saved.brand.name,'V79 revised');assert.equal(saved.expectedRevision,1);
  assert.match(h.container.textContent,/Approved brand includes your uploaded logo/);assert.equal(h.button('Produce a campaign package').disabled,false);
  await h.click('Review brand and draft plan');assert.match(h.container.textContent,/Logo saved in your approved brand/);
});

test('newer file selection wins; invalid logos block saving and surface a specific error',async t=>{
  const h=await harness(t);await h.click('Review brand and draft plan');
  await h.upload({type:'image/png',size:100});await h.upload({type:'image/png',size:100});
  await h.finishLogo(1);await h.finishLogo(0,'invalid-old-file');assert.equal(h.container.querySelector('img').getAttribute('src'),png);
  await h.upload({type:'image/png',size:1048577});assert.match(h.container.textContent,/no larger than 1 MB/);
  await act(async()=>h.input('I verified these facts').click());assert.equal(h.button('Approve brand and draft plan').disabled,true);assert.equal(h.container.querySelector('img').getAttribute('src'),png);
  await h.upload({type:'image/jpeg',size:100});assert.match(h.container.textContent,/Choose a PNG logo/);
  await h.upload({type:'image/png',size:100});await h.finishLogo(h.reads.length-1,'not-a-valid-image');assert.match(h.container.textContent,/not a readable PNG/);
  await h.upload({type:'image/png',size:100});await h.finishLogo();assert.equal(h.container.querySelectorAll('[role=alert]').length,0);
});

test('a failed status request recovers automatically without erasing form edits or replaying a mutation',async t=>{
  const h=await harness(t);await h.click('Review brand and draft plan');await h.change('Business name','Unsaved name');
  h.failure=true;await h.poll();assert.match(h.container.textContent,/Retrying automatically/);assert.equal(h.input('Business name').value,'Unsaved name');
  h.failure=false;await h.poll();assert.doesNotMatch(h.container.textContent,/Retrying automatically/);assert.equal(h.input('Business name').value,'Unsaved name');
  assert.ok(h.calls.every(c=>c.action==='list'));
});


test('a background revision change cannot silently approve edits based on an older brand',async t=>{
  const h=await harness(t);await h.click('Review brand and draft plan');await h.change('Business name','My edited brand');
  h.state.configRevision=2;await h.poll();await act(async()=>h.input('I verified these facts').click());await h.click('Approve brand and draft plan');
  assert.equal(h.calls.find(c=>c.action==='configure').config.expectedRevision,1);assert.match(h.container.textContent,/Configuration revision changed/);
  assert.equal(h.input('Business name').value,'My edited brand');
});

test('an oversized image is rejected before approval',async t=>{
  const h=await harness(t);await h.click('Review brand and draft plan');
  globalThis.Image=class{naturalWidth=2049;naturalHeight=100;set src(_v){queueMicrotask(()=>this.onload());}};
  await h.upload({type:'image/png',size:100});await h.finishLogo();assert.match(h.container.textContent,/at most 2048 × 2048/);
  await act(async()=>h.input('I verified these facts').click());assert.equal(h.button('Approve brand and draft plan').disabled,true);
});


test('clear failed attempts cancels only failed unstarted packages and keeps recoverable history',async t=>{
  const h=await harness(t);
  h.state.jobs=[{id:'failed',status:'blocked',failure:'Generation failed',angle:'Failed local render',deliveries:[]},
    {id:'pending',status:'awaiting_owner',angle:'Current campaign',deliveries:[]},
    ...['approved','running','succeeded','uncertain'].map(status=>({id:status,status:'blocked',failure:'A failure',angle:'Protected '+status,deliveries:[{id:status,status,channel:'youtube'}]})),
    {id:'receipt',status:'blocked',failure:'A failure',angle:'Has provider receipt',deliveries:[{status:'blocked',channel:'youtube',result:{providerPostId:'receipt'}}]},
    {id:'prior-approval',status:'blocked',failure:'A failure',angle:'Has prior approval',deliveries:[{status:'blocked',channel:'youtube',approval:{digest:'prior'}}]},
    {id:'channel-blocked',status:'awaiting_owner',angle:'Disconnected channel',deliveries:[{status:'blocked',channel:'youtube'}]}];
  await h.poll();await h.click('Clear failed attempts (1)');
  assert.deepEqual(h.calls.filter(c=>c.action==='cancel'),[{action:'cancel',jobId:'failed'}]);
  assert.doesNotMatch(h.container.textContent,/Failed local render/);assert.match(h.container.textContent,/Current campaign/);
  for(const text of ['Protected approved','Protected running','Protected succeeded','Protected uncertain','Has provider receipt','Has prior approval','Disconnected channel'])assert.match(h.container.textContent,new RegExp(text));
  await h.click('Show canceled history (1)');assert.match(h.container.textContent,/Failed local render/);
  await h.click('Hide canceled history');assert.doesNotMatch(h.container.textContent,/Failed local render/);
  const mutations=h.calls.filter(c=>c.action!=='list');assert.deepEqual(mutations,[{action:'cancel',jobId:'failed'}]);
});

test('declining cleanup changes nothing; an MFA failure is shown without retrying the mutation',async t=>{
  const h=await harness(t);h.state.jobs=[{id:'failed',status:'blocked',failure:'Generation failed',angle:'Failed render',deliveries:[]}];
  await h.poll();window.confirm=()=>false;await h.click('Clear failed attempts (1)');assert.equal(h.calls.filter(c=>c.action==='cancel').length,0);
  window.confirm=()=>true;h.cancelFailure='failed';await h.click('Clear failed attempts (1)');assert.match(h.container.textContent,/Fresh founder MFA required/);
  await h.poll();assert.equal(h.calls.filter(c=>c.action==='cancel').length,1);assert.match(h.container.textContent,/Failed render/);
});

test('bulk cleanup stops at the first failure and polling reflects partial progress without replay',async t=>{
  const h=await harness(t);h.state.jobs=['one','two','three'].map(id=>({id,status:'blocked',failure:'Generation failed',angle:'Failed '+id,deliveries:[]}));
  await h.poll();h.cancelFailure='two';await h.click('Clear failed attempts (3)');
  assert.deepEqual(h.calls.filter(c=>c.action==='cancel').map(c=>c.jobId),['one','two']);
  await h.poll();assert.doesNotMatch(h.container.textContent,/Failed one/);assert.match(h.container.textContent,/Failed two/);assert.match(h.container.textContent,/Failed three/);
  assert.equal(h.calls.filter(c=>c.action==='cancel').length,2);assert.ok(h.button('Show canceled history (1)'));
});

test('approved deliveries show scheduled approval instead of awaiting owner; successful uploads show a full safe YouTube link and tracking receipt',async t=>{
  const h=await harness(t);h.state.jobs=[{id:'campaign',status:'awaiting_owner',angle:'Current campaign',bundle:{source:'ollama',brand,assets:[],materials:[],review:{warnings:[],blockers:[]}},deliveries:[{id:'youtube',channel:'youtube',status:'approved',providerAccountId:'channel-id',scheduledAt:'2026-10-16T03:08:52Z',payload:{youtube:{privacyStatus:'private'}}}]}];
  await h.poll();assert.match(h.container.textContent,/Approved · scheduled/);assert.doesNotMatch(h.container.textContent,/awaiting_owner|Awaiting your approval/);assert.match(h.container.textContent,/YouTube visibility: private/);assert.equal(h.container.querySelectorAll('a').length,0);
  h.state.jobs[0].deliveries[0].status='running';await h.poll();assert.match(h.container.textContent,/Uploading/);assert.doesNotMatch(h.container.textContent,/Approved · scheduled/);
  Object.assign(h.state.jobs[0].deliveries[0],{status:'succeeded',result:{providerPostId:'dQw4w9WgXcQ',at:'2026-10-16T03:09:01Z',marketingPostId:'production-youtube'}});
  await h.poll();assert.match(h.container.textContent,/Publication complete/);assert.match(h.container.textContent,/Upload confirmed/);assert.match(h.container.textContent,/Recorded in V79 Marketing/);
  const link=h.container.querySelector('a');assert.equal(link.textContent,'https://www.youtube.com/watch?v=dQw4w9WgXcQ');assert.equal(link.getAttribute('href'),link.textContent);assert.equal(link.getAttribute('rel'),'noopener noreferrer');
  assert.ok(h.calls.every(c=>c.action==='list'));
});

test('partial campaign approvals remain explicit, and uncertain or forged receipts never become uploaded links',async t=>{
  const h=await harness(t);h.state.jobs=[{id:'campaign',status:'awaiting_owner',angle:'Partial campaign',bundle:{source:'ollama',brand,assets:[],materials:[],review:{warnings:[],blockers:[]}},deliveries:[{id:'youtube',channel:'youtube',status:'approved',providerAccountId:'channel-id',scheduledAt:'2026-10-16T03:08:52Z'},{id:'facebook',channel:'facebook',status:'awaiting_owner',providerAccountId:'page-id',scheduledAt:'2026-10-16T03:08:52Z'}]}];
  await h.poll();assert.match(h.container.textContent,/Partly approved · approval required/);
  const d=h.state.jobs[0].deliveries[0];Object.assign(d,{status:'uncertain',result:{providerPostId:'dQw4w9WgXcQ',at:'2026-10-16T03:09:01Z'}});
  await h.poll();assert.match(h.container.textContent,/Outcome uncertain · verify provider/);assert.equal(h.container.querySelectorAll('a').length,0);
  Object.assign(d,{status:'succeeded',result:{providerPostId:'https://evil.test',providerUrl:'javascript:alert(1)',at:'2026-10-16T03:09:01Z'}});
  await h.poll();assert.equal(h.container.querySelectorAll('a').length,0);assert.match(h.container.textContent,/Partly published · approval required/);assert.match(h.container.textContent,/Marketing record sync pending/);
});
