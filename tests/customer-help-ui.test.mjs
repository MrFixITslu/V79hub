import test from 'node:test';
import assert from 'node:assert/strict';
import {register} from 'tsx/esm/api';
import {readFileSync} from 'node:fs';
import {Window} from 'happy-dom';
import React,{act} from 'react';
import {helpCatalog,createHelpService} from '../server/customer-help.mjs';
register();
// tsx cannot import CSS in Node; bundle just this component through the existing
// esbuild test toolchain and an empty CSS loader, without changing product code.
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'v79-help-ui-'));
const output=join(temp,'component.mjs');
await build({entryPoints:['src/components/CustomerAppHelp.tsx'],bundle:true,format:'esm',platform:'node',jsx:'automatic',packages:'external',loader:{'.css':'empty'},outfile:output});
// External React resolves relative to this repository through a local temporary
// entry, avoiding a second React copy or dependence on a global module path.
const bundled=readFileSync(output,'utf8').replaceAll('from "react"',`from ${JSON.stringify(pathToFileURL(join(process.cwd(),'node_modules/react/index.js')).href)}`).replaceAll('from "react/jsx-runtime"',`from ${JSON.stringify(pathToFileURL(join(process.cwd(),'node_modules/react/jsx-runtime.js')).href)}`).replaceAll('from "lucide-react"',`from ${JSON.stringify(pathToFileURL(join(process.cwd(),'node_modules/lucide-react/dist/cjs/lucide-react.js')).href)}`);
const {writeFile}=await import('node:fs/promises');await writeFile(output,bundled);
const browser=new Window({url:'https://hub.synthetic.test'});
for(const key of ['document','HTMLElement','Event','MouseEvent','DOMException'])globalThis[key]=browser[key];
globalThis.window=browser;globalThis.IS_REACT_ACT_ENVIRONMENT=true;
Object.defineProperty(globalThis,'navigator',{configurable:true,value:browser.navigator});
const {createRoot}=await import('react-dom/client');
const {CustomerAppHelp}=await import(pathToFileURL(output).href);
test.after(async()=>{await rm(temp,{recursive:true,force:true});await browser.happyDOM.abort();});
async function mount(t,handler){
 const box=document.createElement('div');document.body.append(box);const root=createRoot(box),calls=[];
 globalThis.fetch=async(url,opts={})=>{
  calls.push({url,opts});
  const result=handler?await handler(url,opts):url.endsWith('/catalog')?helpCatalog():await createHelpService({env:{}}).answer(JSON.parse(opts.body));
  return result instanceof Response?result:new Response(JSON.stringify(result),{headers:{'content-type':'application/json'}});
 };
 await act(async()=>root.render(React.createElement(CustomerAppHelp)));
 t.after(async()=>{await act(async()=>root.unmount());box.remove();delete globalThis.fetch;});
 const click=async label=>{
  const button=[...box.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith(label)||b.getAttribute('aria-label')===label);
  assert.ok(button,label);await act(async()=>button.click());
 };
 return {box,calls,click};
}
test('customer UI browses real topics, answers with source steps and resets without persistence',async t=>{
 const h=await mount(t);
 assert.equal(h.calls[0].url,'/api/help/catalog');assert.equal(h.box.querySelectorAll('.help-topics li').length,49);
 await h.click('How do I create a Tiquet service request?');
 assert.match(h.box.querySelector('.help-answer').textContent,/Submit Request/);
 assert.equal(h.box.querySelectorAll('.help-answer ol li').length,4);
 assert.match(h.box.querySelector('.help-source').textContent,/§2\.3/);
 assert.equal(h.box.querySelector('select').value,'tiquet');
 const post=JSON.parse(h.calls[1].opts.body);assert.equal(post.message,'How do I create a Tiquet service request?');assert.deepEqual(post.history,[]);
 assert.equal(h.calls.some(c=>c.url.startsWith('/api/agent')),false);
 await h.click('New conversation');assert.equal(h.box.querySelectorAll('.help-turn').length,0);
 assert.equal(browser.localStorage.length,0);assert.equal(browser.sessionStorage.length,0);
});
test('untrusted response content is rendered as text, never HTML',async t=>{
 const h=await mount(t,async(url,opts)=>{
  if(url.endsWith('/catalog'))return helpCatalog();
  const response=await createHelpService({env:{}}).answer(JSON.parse(opts.body));
  response.answer='<img src=x onerror=alert(1)>';
  response.articles[0].steps[0]='<script>alert(1)</script>';
  return response;
 });
 await h.click('Review sales and process an authorised return');
 assert.equal(h.box.querySelectorAll('.help-answer img,.help-answer script').length,0);
 assert.match(h.box.querySelector('.help-answer').textContent,/<img src=x/);
 assert.match(h.box.querySelector('.help-answer').textContent,/Complete return/);
});
test('request failures keep a retry action; expiry requires sign-in',async t=>{
 let fail=true;
 const h=await mount(t,async(url,opts)=>url.endsWith('/catalog')?helpCatalog():fail?new Response(JSON.stringify({error:'Synthetic failure'}),{status:503}):await createHelpService({env:{}}).answer(JSON.parse(opts.body)));
 await h.click('How do I open the POS register?');assert.match(h.box.querySelector('[role=alert]').textContent,/Synthetic failure/);
 fail=false;await h.click('Try again');assert.match(h.box.querySelector('.help-answer').textContent,/Opening cash float/);
 globalThis.fetch=async()=>new Response('{}',{status:401});
 await h.click('Set a replenishment policy');assert.match(h.box.querySelector('[role=alert]').textContent,/session has expired/);
 assert.equal(h.box.querySelector('textarea').disabled,true);assert.equal(h.box.querySelector('a[href="/"]').textContent,'Sign in to Hub');
});
test('a session that expired before Help opened gives a sign-in action and accurate recovery text',async t=>{
 const h=await mount(t,()=>new Response('{}',{status:401}));
 assert.match(h.box.querySelector('[role=alert]').textContent,/session has expired/);
 assert.equal(h.box.querySelector('textarea').disabled,true);
 assert.equal(h.box.querySelector('a[href="/"]').textContent,'Sign in to Hub');
 assert.doesNotMatch(h.box.textContent,/You can still try asking/);
});
test('changing apps aborts a pending question and discards its late answer',async t=>{
 let release;
 const h=await mount(t,(url)=>url.endsWith('/catalog')?helpCatalog():new Promise(r=>release=r));
 const button=[...h.box.querySelectorAll('button')].find(b=>b.textContent.includes('How do I open the POS register?'));
 await act(async()=>button.click());assert.ok(release);
 const select=h.box.querySelector('select');
 await act(async()=>{select.value='academy';select.dispatchEvent(new browser.Event('change',{bubbles:true}));});
 assert.equal(h.calls[1].opts.signal.aborted,true);
 await act(async()=>release(await createHelpService({env:{}}).answer({message:'POS refund'})));
 assert.equal(h.box.querySelectorAll('.help-turn').length,0);assert.equal(h.box.querySelector('select').value,'academy');
});

test('walkthrough UI moves through prerequisites, exact steps, blocking, review and customer-confirmed resolution',async t=>{
 const h=await mount(t);
 await h.click('How do I open the POS register?');await h.click('Walk me through this');
 assert.match(h.box.querySelector('.help-turn:last-child .help-walkthrough').textContent,/Before you start/);
 assert.equal(h.box.querySelector('.help-turn:last-child .help-app-link').getAttribute('href'),'/?view=connections');
 await h.click('Start steps');
 assert.match(h.box.querySelector('.help-turn:last-child .help-step-instruction').textContent,/confirm the intended register/);
 await h.click('Done, next step');await h.click('I am stuck');
 assert.match(h.box.querySelector('.help-turn:last-child .help-step-heading').textContent,/Stuck at step 2/);
 await h.click('Review this step');assert.match(h.box.querySelector('.help-turn:last-child .help-step-heading').textContent,/Step 2 of 4/);
 await h.click('Done, next step');await h.click('Done, next step');await h.click('Check my result');
 assert.match(h.box.querySelector('.help-turn:last-child .help-step-heading').textContent,/Check the result/);
 await h.click('Yes, resolved');assert.match(h.box.querySelector('.help-turn:last-child .help-step-instruction').textContent,/You marked.*not checked/);
 assert.equal(h.box.querySelectorAll('.help-turn:not(:last-child) .help-step-actions').length,0);
 const requests=h.calls.filter(c=>c.url.endsWith('/chat')).map(c=>JSON.parse(c.opts.body));
 assert.equal(requests[1].guide.action,'start');assert.equal(requests.at(-1).guide.action,'solved');
});

test('support draft is reviewed locally, excludes transcript by default, masks obvious secrets and clears on reset',async t=>{
 const copied=[];Object.defineProperty(browser.navigator,'clipboard',{configurable:true,value:{writeText:async text=>copied.push(text)}});
 const h=await mount(t);await h.click('How do I open the POS register?');await h.click('Walk me through this');await h.click('Start steps');await h.click('I am stuck');
 await h.click('Prepare support summary');
 const preview=()=>h.box.querySelector('#help-support-preview').value;
 assert.match(preview(),/Customer reported: blocked at step 1/);assert.match(preview(),/Displayed does not mean completed/);
 assert.match(preview(),/Conversation: not included/);assert.doesNotMatch(preview(),/Customer:|Help:/);
 const requestCount=h.calls.length;
 // Exercise React's controlled inputs using its native value setter.
 const input=h.box.querySelector('#help-support-actual');
 await act(async()=>{
  Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype,'value').set.call(input,'Failed; password=example-secret token: example-token 4111 1111 1111 1111');
  input.dispatchEvent(new browser.Event('input',{bubbles:true}));
  input.dispatchEvent(new browser.Event('change',{bubbles:true}));
 });
 await act(async()=>h.box.querySelector('.help-transcript input').click());
 assert.match(preview(),/customer chose to include/);
 assert.match(preview(),/Failed; password: \[removed\]/);
 assert.doesNotMatch(preview(),/example-secret|example-token|4111/);
 await h.click('Copy reviewed summary');assert.equal(copied.length,1);assert.equal(copied[0],preview());assert.equal(h.calls.length,requestCount);
 assert.match(h.box.textContent,/Summary copied/);
 await h.click('New conversation');assert.equal(h.box.querySelector('#help-support-preview'),null);
 await h.click('Prepare support summary');assert.doesNotMatch(preview(),/blocked at step|register/);assert.equal(h.box.querySelector('.help-transcript input').checked,false);
 assert.equal(browser.localStorage.length,0);assert.equal(browser.sessionStorage.length,0);
});

test('customer-selected screen context sends only a reviewed ID and produces a focused guide choice',async t=>{
 const h=await mount(t);const select=h.box.querySelector('#help-screen');
 await act(async()=>{select.value='manual-2-5';select.dispatchEvent(new browser.Event('change',{bubbles:true}));});
 // A guide topic still uses the ordinary article selection, with minimal context.
 await h.click('Update job details and internal notes');
 assert.deepEqual(JSON.parse(h.calls.at(-1).opts.body).context,{articleId:'manual-2-5'});
 assert.equal(h.box.querySelector('#help-screen').value,'manual-2-5');
 await h.click('Walk me through this');assert.equal(JSON.parse(h.calls.at(-1).opts.body).guide.articleId,'manual-2-5');
});

test('failed guide requests retry the same action, and expired sessions disable guide and sharing controls',async t=>{
 let fail=false;
 const h=await mount(t,async(url,opts)=>url.endsWith('/catalog')?helpCatalog():fail?new Response(JSON.stringify({error:'Guide temporarily unavailable'}),{status:503}):await createHelpService({env:{}}).answer(JSON.parse(opts.body)));
 await h.click('How do I open the POS register?');await h.click('Walk me through this');
 fail=true;await h.click('Start steps');const original=JSON.parse(h.calls.at(-1).opts.body).guide;
 fail=false;await h.click('Try again');assert.deepEqual(JSON.parse(h.calls.at(-1).opts.body).guide,original);
 globalThis.fetch=async()=>new Response('{}',{status:401});await h.click('I am stuck');
 assert.equal(h.box.querySelector('.help-turn:last-child .help-step-actions button').disabled,true);
 assert.equal([...h.box.querySelectorAll('button')].find(b=>b.textContent==='Prepare support summary').disabled,true);
 assert.ok(h.box.querySelector('a[href="/"]'));
});
