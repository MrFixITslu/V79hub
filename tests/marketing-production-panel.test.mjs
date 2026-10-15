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
  const calls=[],timers=new Map(),reads=[];let nextTimer=0,failure=false,visibility='visible',slowList=null;
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
  return {container,button,click,input,change,upload,finishLogo,reads,calls,timers,poll,get state(){return state;},set state(v){state=v;},set failure(v){failure=v;},set slowList(v){slowList=v;},async visible(v){visibility=v;await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));}};
}

test('worker readiness appears automatically, reads alone never approve or publish, closed and hidden panels stop polling',async t=>{
  const h=await harness(t);await h.click('Produce a campaign package');
  assert.match(h.container.textContent,/updates automatically when the materials are ready/);
  h.state.jobs[0].status='awaiting_owner';h.state.jobs[0].bundle={source:'brand-template',brand,materials:[],assets:[],review:{warnings:['Text wordmark used; original brand logo has not been supplied'],blockers:[]}};
  await h.poll();assert.match(h.container.textContent,/awaiting_owner/);assert.match(h.container.textContent,/This package was created without a saved logo/);
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
