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
const {GoogleWorkforcePanel}=await import('../src/components/GoogleWorkforcePanel.tsx');
const id='11111111-1111-4111-8111-111111111111';
const job=(status='pending')=>({id,operation:'create_email_draft',system:'gmail',summary:'Acceptance draft',payload:{to:'vision79slu@gmail.com',subject:'Re: test',body:'Exact reviewed reply'},digest:'a'.repeat(64),revision:1,status,approval:{expiresAt:new Date(Date.now()+600000).toISOString()}});
async function mount(t,handler){
 const box=document.createElement('div');document.body.append(box);const root=createRoot(box),calls=[];
 const prior=window.setInterval,clear=window.clearInterval;window.setInterval=()=>1;window.clearInterval=()=>{};
 globalThis.fetch=async(url,opts={})=>{calls.push({url,opts});const result=await handler(url,opts);return result?.json?result:{ok:true,json:async()=>structuredClone(result)}};
 await act(async()=>root.render(React.createElement(GoogleWorkforcePanel)));
 t.after(async()=>{await act(async()=>root.unmount());box.remove();window.setInterval=prior;window.clearInterval=clear;delete globalThis.fetch});
 const click=async text=>{const b=[...box.querySelectorAll('button')].find(x=>x.textContent===text);assert.ok(b,text);assert.equal(b.disabled,false,text+' enabled');await act(async()=>b.click())};
 const type=async(label,value)=>{const input=[...box.querySelectorAll('label')].find(x=>x.textContent.startsWith(label)).querySelector('input,textarea');await act(async()=>{const setter=Object.getOwnPropertyDescriptor(input.tagName==='TEXTAREA'?browser.HTMLTextAreaElement.prototype:browser.HTMLInputElement.prototype,'value').set;setter.call(input,value);input.dispatchEvent(new browser.Event('input',{bubbles:true}));input.dispatchEvent(new browser.Event('change',{bubbles:true}))})};
 return {box,calls,click,type};
}
const queue=(jobs,extra={})=>({mode:'owner-approved-actions',enabled:true,paused:false,jobs,...extra});
test('one inline approval saves only its reviewed draft and displays completion without navigation',async t=>{
 let saved=job();const h=await mount(t,async(url,opts)=>{
  if(url.endsWith('/status'))return {enabled:true,connected:true};
  if(url==='/api/agent/work-actions')return queue([saved]);
  if(url.endsWith('/decision')){const p=JSON.parse(opts.body);assert.equal(p.digest,saved.digest);assert.equal(p.expectedRevision,saved.revision);saved={...saved,status:'approved',revision:2};return {job:saved}}
  if(url.endsWith('/run-once')){assert.deepEqual(JSON.parse(opts.body),{jobId:id});saved={...saved,status:'succeeded',revision:3};return {jobId:id,status:'succeeded'}}
  throw Error('Unexpected request');
 });
 await h.click('Check Google connection');assert.match(h.box.textContent,/Exact reviewed reply/);
 assert.equal(h.calls.filter(c=>c.opts.method==='POST').length,0);
 await h.click('Approve & save draft');assert.match(h.box.textContent,/Draft saved — email not sent/);
 assert.deepEqual(h.calls.filter(c=>c.opts.method==='POST').map(c=>c.url),['/api/agent/work-actions/'+id+'/decision','/api/agent/google/run-once']);
 assert.equal([...h.box.querySelectorAll('button')].some(b=>b.textContent==='Execute next approved Google action'),false);
});
test('already approved draft finishes in the same panel without approving again',async t=>{
 let saved=job('approved');const h=await mount(t,async(url,opts)=>{
  if(url.endsWith('/status'))return {connected:true,enabled:true};
  if(url==='/api/agent/work-actions')return queue([saved]);
  if(url.endsWith('/run-once')){saved={...saved,status:'succeeded'};return {jobId:id,status:'succeeded'}}
  throw Error('Unexpected approval');
 });await h.click('Check Google connection');await h.click('save draft');assert.equal(h.calls.some(c=>c.url.endsWith('/decision')),false);
});
test('changed digest refreshes review and blocks approval and execution',async t=>{
 let reads=0;const h=await mount(t,async url=>url.endsWith('/status')?{connected:true,enabled:true}:queue([{...job(),...(++reads>1?{digest:'b'.repeat(64)}:{})}]));
 await h.click('Check Google connection');await h.click('Approve & save draft');assert.match(h.box.textContent,/This action changed/);assert.equal(h.calls.some(c=>c.opts.method==='POST'),false);
});
test('paused queue and uncertain results never expose an executable action',async t=>{
 const h=await mount(t,async url=>url.endsWith('/status')?{connected:true,enabled:true}:queue([job(),{...job('uncertain'),id:'uncertain-job'}],{paused:true}));
 await h.click('Check Google connection');assert.match(h.box.textContent,/queue is paused/);assert.match(h.box.textContent,/do not retry/);
 const button=[...h.box.querySelectorAll('button')].find(b=>b.textContent==='Approve & save draft');assert.equal(button.disabled,true);assert.equal(h.calls.some(c=>c.opts.method==='POST'),false);
});
test('fresh queue disablement blocks execution despite a previously enabled review',async t=>{
 let reads=0;const h=await mount(t,async url=>url.endsWith('/status')?{connected:true,enabled:true}:queue([job()],{enabled:++reads===1}));
 await h.click('Check Google connection');await h.click('Approve & save draft');assert.match(h.box.textContent,/queue is unavailable or paused/);assert.equal(h.calls.some(c=>c.opts.method==='POST'),false);
});
test('incomplete thread explains disabled Review draft instead of silently blocking the owner',async t=>{
 const h=await mount(t,async url=>url.endsWith('/status')?{connected:true,enabled:true}:url==='/api/agent/work-actions'?queue([]):url.includes('/inbox?')?{messages:[{id:'message1',threadId:'thread1',subject:'HTML message',from:'client@example.invalid'}]}:{id:'thread1',partial:true,messages:[{id:'message1',subject:'HTML message',text:''}]});
 await h.click('Check Google connection');await h.click('Review inbox');await h.click('HTML messageclient@example.invalid');assert.match(h.box.textContent,/This thread is incomplete/);assert.equal([...h.box.querySelectorAll('button')].find(b=>b.textContent==='Review draft').disabled,true);assert.equal(h.calls.some(c=>c.opts.method==='POST'),false);
});
test('expired approval offers no execution button',async t=>{
 const h=await mount(t,async url=>url.endsWith('/status')?{connected:true,enabled:true}:queue([{...job('approved'),approval:{expiresAt:new Date(Date.now()-1).toISOString()}}]));await h.click('Check Google connection');assert.match(h.box.textContent,/Approval expired/);assert.equal([...h.box.querySelectorAll('button')].some(b=>b.textContent==='save draft'),false);
});
test('preparing a reply queues only a proposal and opens its inline review without approving',async t=>{
 let saved=null;const h=await mount(t,async(url,opts)=>{
  if(url.endsWith('/status'))return {enabled:true,connected:true};
  if(url==='/api/agent/work-actions'){
   if(opts.method==='POST'){const p=JSON.parse(opts.body);saved={...job(),summary:p.summary,payload:p.payload};return {job:saved}}
   return queue(saved?[saved]:[]);
  }
  if(url.includes('/inbox?'))return {messages:[{id:'message1',threadId:'thread1',subject:'Test',from:'client@example.invalid'}]};
  if(url.includes('/threads/'))return {id:'thread1',partial:false,messages:[{id:'message1',subject:'Test',text:'Readable synthetic message'}]};
  throw Error('Unexpected request');
 });
 await h.click('Check Google connection');await h.click('Review inbox');await h.click('Testclient@example.invalid');
 await h.type('Verified recipient email','vision79slu@gmail.com');await h.type('Reply for your review','Exact reviewed reply');
 await h.click('Review draft');assert.match(h.box.textContent,/Review the saved details/);
 assert.deepEqual(h.calls.filter(c=>c.opts.method==='POST').map(c=>c.url),['/api/agent/work-actions']);
 assert.ok([...h.box.querySelectorAll('button')].find(b=>b.textContent==='Approve & save draft'));
 await h.click('Review draft');assert.equal(h.calls.filter(c=>c.opts.method==='POST').length,1,'repeated review reuses the same proposal');
});
test('calendar creation is reviewed and completed inline with exact dates and selected ID',async t=>{
 let saved={...job(),operation:'create_calendar_event',system:'calendar',summary:'Planning appointment',payload:{summary:'Planning appointment',start:'2026-10-22T14:00:00.000Z',end:'2026-10-22T14:30:00.000Z',attendees:[]}};
 const h=await mount(t,async(url,opts)=>{
  if(url.endsWith('/status'))return {connected:true,enabled:true};
  if(url==='/api/agent/work-actions')return queue([saved]);
  if(url.endsWith('/decision')){saved={...saved,status:'approved'};return {job:saved}}
  if(url.endsWith('/run-once')){assert.deepEqual(JSON.parse(opts.body),{jobId:id});saved={...saved,status:'succeeded'};return {status:'succeeded',jobId:id}}
  throw Error('Unexpected request');
 });await h.click('Check Google connection');assert.match(h.box.textContent,/Starts:/);assert.match(h.box.textContent,/Attendees: None/);await h.click('Approve & create appointment');assert.match(h.box.textContent,/Appointment action completed/);
});
test('invalid owner session clears private review and exposes no execution control',async t=>{
 let reads=0;const h=await mount(t,async url=>{
  if(url.endsWith('/status'))return {connected:true,enabled:true};
  if(++reads===1)return queue([job()]);
  return {ok:false,status:403,json:async()=>({error:'Fresh MFA required'})};
 });await h.click('Check Google connection');await h.click('Approve & save draft');assert.match(h.box.textContent,/owner session is unavailable/);assert.doesNotMatch(h.box.textContent,/Exact reviewed reply/);assert.equal(h.calls.some(c=>c.opts.method==='POST'),false);
});
test('uncertain execution response is reconciled with GET and never automatically posted again',async t=>{
 let saved=job('approved');const h=await mount(t,async(url,opts)=>{
  if(url.endsWith('/status'))return {connected:true,enabled:true};
  if(url==='/api/agent/work-actions')return queue([saved]);
  if(url.endsWith('/run-once')){saved={...saved,status:'uncertain'};throw Error('Network interrupted. Refresh status before retrying.')}
  throw Error('Unexpected request');
 });await h.click('Check Google connection');await h.click('save draft');assert.match(h.box.textContent,/Outcome needs checking — do not retry/);assert.equal(h.calls.filter(c=>c.url.endsWith('/run-once')).length,1);assert.equal([...h.box.querySelectorAll('button')].some(b=>b.textContent==='save draft'),false);
});

const appointment=(etag='"v1"')=>({id:'event-test-123',etag,summary:'V79 acceptance test',start:{dateTime:'2026-10-23T14:00:00Z'},end:{dateTime:'2026-10-23T14:10:00Z'},attendees:[],organizer:'vision79slu@gmail.com',recurring:false});
async function calendarHarness(t,operation,{refreshFailure=false,outcome='succeeded'}={}){
 let saved={...job('approved'),operation,system:'calendar',summary:'Calendar action',payload:{eventId:'event-test-123',etag:'"v1"'}};
 let agendaReads=0,executed=false,proposal;
 const h=await mount(t,async(url,opts)=>{
  if(url.endsWith('/status'))return {connected:true,enabled:true};
  if(url==='/api/agent/work-actions'){
   if(opts.method==='POST'){proposal=JSON.parse(opts.body);saved={...job(),...proposal,revision:1};return {job:saved}}
   return queue([saved]);
  }
  if(url.includes('/appointments?')){
   agendaReads++;
   if(executed&&refreshFailure)throw Error('Offline agenda');
   return {items:executed&&operation==='delete_calendar_event'?[]:[appointment(executed?'"v2"':'"v1"')]};
  }
  if(url.endsWith('/run-once')){executed=true;saved={...saved,status:outcome};return {jobId:id,status:outcome}}
  throw Error('Unexpected request');
 });
 await h.click('Check Google connection');await h.type('Agenda from','2026-10-23T00:00');await h.type('Agenda until','2026-10-24T00:00');await h.click('Review appointments');
 const select=async()=>{const b=[...h.box.querySelectorAll('button')].find(b=>b.textContent.startsWith('V79 acceptance test'));assert.ok(b);await act(async()=>b.click())};
 await select();
 return {...h,select,reads:()=>agendaReads,proposal:()=>proposal};
}
for(const [operation,label] of [['create_calendar_event','create appointment'],['update_calendar_event','update appointment'],['delete_calendar_event','cancel appointment']]){
 test(operation+' reloads agenda and clears stale selection after success',async t=>{
  const h=await calendarHarness(t,operation);await h.click(label);assert.equal(h.reads(),2);
  assert.equal([...h.box.querySelectorAll('button')].some(b=>b.textContent==='Cancel appointment'),false);
  assert.equal(h.box.querySelectorAll('input')[3].value,'','selected title cleared');
  if(operation==='delete_calendar_event')assert.equal([...h.box.querySelectorAll('button')].some(b=>b.textContent.startsWith('V79 acceptance test')),false);
  else {await h.select();await h.click('Review change');assert.equal(h.proposal().payload.etag,'"v2"','next action uses fresh event version')}
  assert.equal(h.calls.filter(c=>c.url.endsWith('/run-once')).length,1);
 });
}
test('successful cancellation with agenda outage keeps completion and offers read-only refresh',async t=>{
 const h=await calendarHarness(t,'delete_calendar_event',{refreshFailure:true});await h.click('cancel appointment');
 assert.match(h.box.textContent,/action completed, but the agenda could not refresh/);
 assert.match(h.box.textContent,/Appointment action completed/);assert.equal(h.reads(),2);
 assert.equal([...h.box.querySelectorAll('button')].some(b=>b.textContent.startsWith('V79 acceptance test')),false);
 assert.equal(h.calls.filter(c=>c.url.endsWith('/run-once')).length,1);
});
test('uncertain calendar execution never claims success or automatically reloads or retries',async t=>{
 const h=await calendarHarness(t,'delete_calendar_event',{outcome:'uncertain'});await h.click('cancel appointment');assert.equal(h.reads(),1);
 assert.match(h.box.textContent,/Outcome needs checking/);assert.equal(h.calls.filter(c=>c.url.endsWith('/run-once')).length,1);
});
test('manual agenda refresh clears the old selected version',async t=>{
 const h=await calendarHarness(t,'update_calendar_event');await h.click('Review appointments');
 assert.equal([...h.box.querySelectorAll('button')].some(b=>b.textContent==='Cancel appointment'),false);
});
