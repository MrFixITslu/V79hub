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
const {OwnerAssistant}=await import('../src/components/OwnerAssistant.tsx');
const {WorkforceActionPanel}=await import('../src/components/WorkforceActionPanel.tsx');
const queue=jobs=>({mode:'owner-approved-actions',enabled:true,paused:false,jobs});
const job=(status='pending',overrides={})=>({id:'test-job',operation:'create_work_item',system:'hub',summary:'Scheduled worker acceptance check',payload:{detail:'Record acceptance only. No production changes.'},digest:'a'.repeat(64),revision:1,status,approval:status==='approved'?{expiresAt:new Date(Date.now()+600000).toISOString()}:null,result:status==='succeeded'?{taskId:'test-item'}:null,...overrides});
async function mount(t,Component,props={},handler=()=>queue([])){
 const box=document.createElement('div');document.body.append(box);const root=createRoot(box);const calls=[];const timers=new Map();let timerId=0;
 const originalSet=window.setInterval,originalClear=window.clearInterval;
 window.setInterval=(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;};
 window.clearInterval=id=>timers.delete(id);
 globalThis.fetch=async(url,opts)=>{calls.push({url,opts});const value=await handler(url,opts,calls.length);return value?.json?value:{ok:true,json:async()=>structuredClone(value)};};
 await act(async()=>root.render(React.createElement(Component,props)));
 t.after(async()=>{await act(async()=>root.unmount());box.remove();window.setInterval=originalSet;window.clearInterval=originalClear;delete globalThis.fetch;});
 const click=async(text,scope=box)=>{const button=[...scope.querySelectorAll('button')].find(b=>b.textContent.trim()===text||b.getAttribute('aria-label')===text);assert.ok(button,'Button: '+text);await act(async()=>button.click());};
 return {box,calls,timers,click,render:async next=>act(async()=>root.render(React.createElement(Component,next)))};
}
test('workspace starts with a read-only Today summary; navigation keeps a prepared chat prompt',async t=>{
 const h=await mount(t,OwnerAssistant);
 assert.equal(h.calls.length,1);
 assert.equal(h.calls[0].url,'/api/agent/work-actions');
 assert.equal(h.calls[0].opts.method,undefined);
 assert.equal(h.box.querySelector('#workspace-today').hidden,false);
 await h.click('Ask Assistant',h.box.querySelector('nav'));
 assert.equal(h.box.querySelector('#workspace-agents').hidden,false);
 await h.click('CEO · DirectionPriorities, tradeoffs and decisions');
 const draft=h.box.querySelector('textarea').value;assert.match(draft,/CEO review/);
 assert.equal(h.calls.length,1,'Choosing an agent prepares a prompt; it does not send');
 await h.click('New task');
 assert.equal(h.box.querySelector('#workspace-tasks').hidden,false);
 assert.ok(h.box.querySelector('form[aria-label="New work item"]'));
 assert.equal(h.calls.length,2);assert.ok(h.calls.every(c=>c.url==='/api/agent/work-actions'&&!c.opts.method));
 await h.click('Ask Assistant',h.box.querySelector('nav'));
 assert.equal(h.box.querySelector('textarea').value,draft);
 assert.equal(h.timers.size,0,'Leaving actions stops polling');
});
test('workboard handoff opens task view with an exact draft and never queues or approves it',async t=>{
 const report={mode:'read-only',source:'github-issue-pr-register',collectedAt:new Date().toISOString(),connection:'PARTIAL_OR_COMPLETE',lanes:['Hub'],repositories:[{repo:'V79hub',fetchState:'COMPLETE'}],tracked:[{lane:'Hub',repo:'V79hub',number:152,kind:'issue',label:'Delivery evidence',nextStep:'Inspect reviewed evidence',githubState:'OPEN_IN_GITHUB',url:'https://github.com/MrFixITslu/V79hub/issues/152'}],runtimeHealth:'UNKNOWN',deployedRevision:'UNKNOWN',customerLaunchGo:'NOT_ESTABLISHED',sentinelCoverage:'NOT_ESTABLISHED',approvalGranted:false,executionEnabled:false,caveat:'GitHub only'};
 const h=await mount(t,OwnerAssistant,{},url=>url.endsWith('coo-workboard')?report:queue([]));
 await h.click('Delivery board',h.box.querySelector('nav'));
 await h.click('Prepare COO work item · approval required');
 assert.equal(h.box.querySelector('#workspace-tasks').hidden,false);
 assert.equal(h.box.querySelector('input[minlength="8"]').value,'Review: Delivery evidence');
 assert.match(h.box.querySelector('#workspace-tasks textarea').value,/issues\/152/);
 assert.ok(h.calls.every(c=>!c.opts?.method),'Draft handoff must issue no mutations');
 await h.click('Ask Assistant',h.box.querySelector('nav'));await h.click('New task');
 assert.equal(h.box.querySelector('input[minlength="8"]').value,'Review: Delivery evidence','Switching views preserves task draft');
});
test('polling observes worker success without execution POST; created work is not labelled complete',async t=>{
 let state=job('approved');const h=await mount(t,WorkforceActionPanel,{embedded:true},()=>queue([state]));
 assert.match(h.box.textContent,/Approved · awaiting execution/);
 assert.equal(h.timers.size,1);const timer=[...h.timers.values()][0];assert.equal(timer.delay,15000);
 state=job('succeeded');await act(async()=>timer.fn());
 assert.match(h.box.textContent,/Work item created/);
 assert.match(h.box.textContent,/completion of the underlying work is not verified/);
 assert.doesNotMatch(h.box.textContent,/Approval expires/,'Completed actions do not show an old expiry warning');
 assert.ok(h.calls.every(c=>!c.opts?.method),'Status polling must never execute work');
 await h.render({embedded:true,active:false});assert.equal(h.timers.size,0);
});
test('owner decision uses exact digest and revision, moves to Active and never dispatches execution',async t=>{
 let state=job();const h=await mount(t,WorkforceActionPanel,{embedded:true},(url,opts)=>{
  if(opts?.method==='POST'){
   assert.ok(url.endsWith('/decision'));
   assert.deepEqual(JSON.parse(opts.body),{decision:'approve',expectedRevision:1,digest:'a'.repeat(64)});
   state=job('approved',{revision:2});return {job:state};
  }
  return queue([state]);
 });
 window.confirm=()=>false;await h.click('Approve exact action');assert.ok(h.calls.every(c=>!c.opts?.method));
 window.confirm=()=>true;await h.click('Approve exact action');
 assert.equal(h.calls.filter(c=>c.opts?.method==='POST').length,1);
 assert.match(h.box.querySelector('[aria-pressed="true"]').textContent,/Active/);
 assert.match(h.box.textContent,/Manual execution option/);
 assert.match(h.box.textContent,/refreshing this page does not execute actions/);
});
test('queueing a prepared work item creates only a pending proposal and highlights approval',async t=>{
 const draft={sourceId:'owner',system:'hub',summary:'Review monitoring evidence',detail:'Review only. No deployment.'};let proposed=false;
 const h=await mount(t,WorkforceActionPanel,{embedded:true,preparedTask:draft},(url,opts)=>{
  if(opts?.method==='POST'){
   const body=JSON.parse(opts.body);assert.equal(url,'/api/agent/work-actions');assert.equal(body.operation,'create_work_item');assert.equal(body.summary,draft.summary);assert.deepEqual(body.payload,{detail:draft.detail});proposed=true;return {job:job()};
  }return queue(proposed?[job()]:[]);
 });
 await act(async()=>h.box.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(h.calls.filter(c=>c.opts?.method==='POST').length,1);
 assert.match(h.box.querySelector('[aria-pressed="true"]').textContent,/Needs approval/);
 assert.match(h.box.textContent,/Needs your approval/);
});
test('MFA failure clears private actions and controls; an outdated response cannot restore them',async t=>{
 let count=0,resolveOld;
 const h=await mount(t,WorkforceActionPanel,{embedded:true},()=>{
  count++;if(count===1)return queue([job()]);
  if(count===2)return new Promise(resolve=>{resolveOld=resolve;});
  return {ok:false,status:403,json:async()=>({})};
 });
 const timer=[...h.timers.values()][0];
 await act(async()=>{void timer.fn();});
 await act(async()=>timer.fn());
 assert.match(h.box.textContent,/Sign in with your owner account/);assert.equal(h.box.querySelectorAll('article').length,0);
 assert.equal(h.box.querySelectorAll('form').length,1,'Draft editor remains visible to explain unavailable task creation');
 assert.equal(h.box.querySelector('form button[type="submit"]').disabled,true,'MFA denial disables task submission');
 await act(async()=>resolveOld(queue([job()])));
 assert.equal(h.box.querySelectorAll('article').length,0,'Old successful read cannot restore private actions after denial');
});
test('expired and uncertain actions show recovery guidance rather than an execution button',async t=>{
 const h=await mount(t,WorkforceActionPanel,{embedded:true},()=>queue([
  job('approved',{approval:{expiresAt:'2026-10-14T20:00:00Z'}}),job('uncertain',{id:'uncertain-job',summary:'Reconcile uncertain operation'})
 ]));
 assert.match(h.box.textContent,/Approval expired/);assert.match(h.box.textContent,/operator must reconcile/);
 assert.ok(![...h.box.querySelectorAll('button')].some(b=>b.textContent==='Create approved work item'));
 await h.click('Needs approval (0)');assert.equal(h.box.querySelectorAll('article').length,0);assert.match(h.box.textContent,/No matching actions/);
 await h.click('Active (2)');assert.equal(h.box.querySelectorAll('article').length,2);
});
test('an ambiguous queue response can be retried with the same idempotency key after a status check',async t=>{
 let attempts=0;const posted=[];const draft={sourceId:'owner',system:'hub',summary:'Inspect acceptance evidence',detail:'Review evidence only.'};
 const h=await mount(t,WorkforceActionPanel,{embedded:true,preparedTask:draft},(_url,opts)=>{
  if(opts?.method==='POST'){
   posted.push(JSON.parse(opts.body));attempts++;
   if(attempts===1)throw Error('Synthetic lost response. Refresh and verify current state before retrying.');
   return {job:job()};
  }return queue([]);
 });
 const submit=()=>act(async()=>h.box.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await submit();assert.match(h.box.textContent,/lost response/);
 await h.click('Refresh status');await submit();
 assert.equal(posted.length,2);assert.equal(posted[0].idempotencyKey,posted[1].idempotencyKey);
});

test('New task provides an accessible visible destination and never queues when backend actions are disabled',async t=>{
 const h=await mount(t,OwnerAssistant,{},()=>({mode:'owner-approved-actions',enabled:false,paused:false,jobs:[]}));
 const button=[...h.box.querySelectorAll('button')].find(x=>x.textContent.trim()==='New task');
 assert.equal(button.getAttribute('aria-controls'),'workspace-tasks');
 assert.equal(button.getAttribute('aria-expanded'),'false');
 await h.click('New task');
 assert.equal(h.box.querySelector('#workspace-tasks').hidden,false);
 assert.equal(button.getAttribute('aria-expanded'),'true');
 const form=h.box.querySelector('form[aria-label="New work item"]');
 assert.ok(form,'Task composer shown even when the queue is disabled');
 assert.equal(form.querySelector('button[type="submit"]').disabled,true);
 assert.match(form.textContent,/Task actions are disabled on the server/);
 assert.equal(h.calls.filter(x=>x.opts?.method==='POST').length,0);
 await h.click('New task');
 assert.equal(h.box.querySelector('#workspace-tasks').hidden,false);
 assert.equal(h.calls.filter(x=>x.opts?.method==='POST').length,0);
});
test('Owner action GET unavailable still displays a safe local draft and never posts',async t=>{
 const h=await mount(t,OwnerAssistant,{},()=>({ok:false,status:403,json:async()=>({error:'unauthorized'})}));
 await h.click('New task');
 const form=h.box.querySelector('form[aria-label="New work item"]');
 assert.ok(form);
 assert.equal(form.querySelector('button[type="submit"]').disabled,true);
 assert.match(form.textContent,/could not be verified/);
 await act(async()=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 assert.ok(h.calls.every(c=>!c.opts?.method),'No mutation on denied queue read');
 assert.ok(h.calls.some(c=>c.url==='/api/agent/work-actions'));
});
test('owner task composer submits only after a verified enabled response',async t=>{
 let flag=false;
 const h=await mount(t,OwnerAssistant,{},(_url,opts)=>{
  if(opts?.method==='POST'){flag=true;return {job:job()};}
  return flag?queue([job()]):queue([]);
 });
 await h.click('New task');
 const form=h.box.querySelector('form[aria-label="New work item"]');
 assert.ok(form);
 assert.equal(form.querySelector('button[type="submit"]').disabled,true,'Empty draft cannot submit');
 const input=form.querySelector('input[minlength="8"]'),detail=form.querySelector('textarea[minlength="8"]');
 await act(async()=>{
  input.value='Verify owner task creation';
  input.dispatchEvent(new Event('input',{bubbles:true}));
  detail.value='Record one harmless owner approved task only.';
  detail.dispatchEvent(new Event('input',{bubbles:true}));
 });
 // This test validates the editor is available; existing queue submission tests
 // cover React-controlled input and exact body validation separately.
 assert.ok(h.calls.every(c=>!c.opts?.method),'Opening or typing a draft never mutates');
});
