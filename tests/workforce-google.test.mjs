import test from 'node:test';
import assert from 'node:assert/strict';
import { googleWorkforceClient, GOOGLE_OWNER, validateGooglePayload, GoogleWorkforceError } from '../server/workforce-google.mjs';
import { initialWorkState, proposeWork, decideWork, workDigest, validateWorkRequest } from '../server/workforce-actions.mjs';
import { runGoogleWorkOnce } from '../server/workforce-google-worker.mjs';
const at = Date.parse('2026-10-19T21:00:00.000Z');
const appointment = {summary:'Client planning session',start:'2026-10-20T14:00:00.000Z',end:'2026-10-20T15:00:00.000Z',attendees:[]};
const draft = {threadId:'thread1',messageId:'message1',to:'client@example.com',subject:'Re: Meeting',body:'Thank you. I will review your request.'};
function job(operation='create_email_draft',payload=draft) {
  return {id:'job-1',organizationId:'owner-org',operation,system:operation==='create_email_draft'?'gmail':'calendar',summary:'Owner reviewed Google action',idempotencyKey:'google-synthetic-key-1234',payload:structuredClone(payload)};
}
function fake(responses) {
  const calls=[];
  const client=googleWorkforceClient({getAccessToken:async()=> 'synthetic-token',fetchImpl:async(url,opts)=>{
    calls.push({url,opts}); const r=responses.shift();
    if (r instanceof Error) throw r;
    assert.ok(r,`Unexpected call: ${url}`);
    return new Response(r.status===204?null:JSON.stringify(r.body??r),{status:r.status??200});
  }});
  return {client,calls};
}
const profile={emailAddress:GOOGLE_OWNER}, calendar={id:GOOGLE_OWNER};
const metadata={threadId:'thread1',payload:{headers:[{name:'Message-ID',value:'<original@example.com>'}]}};
const availability={calendars:{[GOOGLE_OWNER]:{busy:[]}}};
const event={id:'event1',etag:'"old"',organizer:{email:GOOGLE_OWNER}};
test('inbox metadata uses bounded fixed endpoints and returns no raw message payload',async()=>{
  const f=fake([profile,{messages:[{id:'message1'}]}, {threadId:'thread1',payload:{headers:[{name:'Subject',value:'Client request'},{name:'From',value:'client@example.com'}]}}]);
  const result=await f.client.listEmails();
  assert.deepEqual(result.messages,[{id:'message1',threadId:'thread1',subject:'Client request',from:'client@example.com'}]);
  assert.equal(f.calls.length,3);assert.ok(f.calls[2].url.includes('format=metadata'));
});
test('oversized provider response is rejected before JSON parsing',async()=>{
  const client=googleWorkforceClient({getAccessToken:async()=>'synthetic',fetchImpl:async()=>new Response('{}',{headers:{'content-length':'99999999'}})});
  await assert.rejects(client.status(),e=>e.code==='GOOGLE_RESPONSE_TOO_LARGE');
});
test('Google requests reject header injection, URL traversal, foreign systems and impossible dates',()=>{
  for(const p of [{...draft,to:'x@example.com\r\nBcc: x@example.com'}, {...draft,subject:'Hi\r\nBcc: x'}, {...draft,threadId:'../send'}, {...draft,body:'x\u0000'}]) assert.throws(()=>validateGooglePayload('create_email_draft','gmail',p));
  for(const p of [{...appointment,start:'2026-02-30T14:00:00.000Z'}, {...appointment,end:appointment.start}, {...appointment,attendees:['x@example.com','X@example.com']}, {...appointment,calendarId:'family'}]) assert.throws(()=>validateGooglePayload('create_calendar_event','calendar',p));
  assert.throws(()=>validateGooglePayload('send_email','gmail',draft));
  assert.throws(()=>validateWorkRequest({...job(),operation:'deploy_release',payload:{commitSha:'a'.repeat(40),manifestSha256:'b'.repeat(64)}}));
});
test('approval digest binds recipient, body, attendees and time, independent of object key order',()=>{
  const a=job(); delete a.id; delete a.organizationId;
  assert.equal(workDigest(a),workDigest({...a,payload:Object.fromEntries(Object.entries(a.payload).reverse())}));
  for(const payload of [{...draft,to:'other@example.com'},{...draft,body:'Changed reply'}]) assert.notEqual(workDigest(a),workDigest({...a,payload}));
  const b=job('create_calendar_event',appointment); delete b.id; delete b.organizationId;
  assert.notEqual(workDigest(b),workDigest({...b,payload:{...appointment,attendees:['other@example.com']}}));
});
test('reply creates one UTF8 MIME draft, pins thread and exposes no sending capability',async()=>{
  const {client,calls}=fake([profile,metadata,{id:'draft1'}]);
  const receipt=await client.execute(job()); assert.deepEqual(receipt,{providerId:'draft1',effect:'draft-created',sent:false});
  assert.equal(client.send,undefined); assert.equal(calls.length,3);
  assert.ok(calls.every(c=>!c.url.includes('/send')));
  const body=JSON.parse(calls[2].opts.body);
  assert.equal(body.message.threadId,'thread1');
  const raw=Buffer.from(body.message.raw,'base64url').toString();
  assert.match(raw,/In-Reply-To: <original@example.com>/); assert.match(raw,/Content-Transfer-Encoding: base64/);
  assert.equal(calls[2].opts.redirect,'error');
});
test('account mismatch and changed email thread stop before draft creation',async()=>{
  for(const responses of [[{emailAddress:'other@example.com'}],[profile,{...metadata,threadId:'other'}],[profile,{...metadata,payload:{headers:[{name:'Message-ID',value:'<bad>\r\nBcc:x'}]}}]]) {
    const {client,calls}=fake(responses); await assert.rejects(client.execute(job()));
    assert.ok(calls.every(c=>c.opts.method==='GET'));
  }
});
test('calendar creation checks availability and uses deterministic ID and Saint Lucia time',async()=>{
  const {client,calls}=fake([calendar,availability,{id:'event1',etag:'"new"'}]);
  await client.execute(job('create_calendar_event',appointment));
  const payload=JSON.parse(calls.at(-1).opts.body);
  assert.match(payload.id,/^v79[a-f0-9]{64}$/); assert.equal(payload.start.timeZone,'America/St_Lucia');
  assert.ok(calls.every(c=>!c.url.includes('family')));
});
test('busy and unavailable calendars stop creation',async()=>{
  for(const busy of [{calendars:{}},{calendars:{[GOOGLE_OWNER]:{errors:[{reason:'internalError'}],busy:[]}}},{calendars:{[GOOGLE_OWNER]:{busy:[{start:appointment.start,end:appointment.end}]}}}]) {
    const {client,calls}=fake([calendar,busy]); await assert.rejects(client.execute(job('create_calendar_event',appointment)));
    assert.equal(calls.length,2);
  }
});
test('calendar edits and cancellation require same etag and owner-organized single event',async()=>{
  const payload={...appointment,eventId:'event1',etag:'"old"'};
  const {client,calls}=fake([calendar,event,availability,{items:[event]},{id:'event1',etag:'"new"'}]);
  await client.execute(job('update_calendar_event',payload));
  assert.equal(calls.at(-1).opts.method,'PATCH'); assert.equal(calls.at(-1).opts.headers['If-Match'],'"old"');
  for(const changed of [{...event,etag:'"changed"'},{...event,recurringEventId:'series1'},{...event,organizer:{email:'client@example.com'}}]) {
    const f=fake([calendar,changed]); await assert.rejects(f.client.execute(job('delete_calendar_event',{eventId:'event1',etag:'"old"'}))); assert.equal(f.calls.length,2);
  }
  const f=fake([calendar,event,{status:204}]); await f.client.execute(job('delete_calendar_event',{eventId:'event1',etag:'"old"'}));
  assert.equal(f.calls.at(-1).opts.method,'DELETE');
});
test('calendar edit rejects another overlap and incomplete event listings',async()=>{
  for(const result of [{items:[event,{id:'another'}]},{items:[event],nextPageToken:'more'},{items:null}]) {
    const f=fake([calendar,event,availability,result]);
    await assert.rejects(f.client.execute(job('update_calendar_event',{...appointment,eventId:'event1',etag:'"old"'})));
    assert.equal(f.calls.length,4);
  }
});
test('Google authorization, rate limit, changed version and uncertain writes have bounded errors',async()=>{
  for(const [status,code] of [[401,'GOOGLE_AUTH_REQUIRED'],[429,'GOOGLE_RATE_LIMITED'],[412,'GOOGLE_EVENT_CHANGED']]) {
    const f=fake([{status,body:{error:'sensitive data'}}]);
    await assert.rejects(f.client.execute(job()),e=>e.code===code && !e.message.includes('sensitive'));
  }
  const f=fake([profile,metadata,new Error('secret-token')]);
  await assert.rejects(f.client.execute(job()),e=>e.uncertain && !e.message.includes('secret-token'));
});
function fixture({approved=true}={}) {
  const state=initialWorkState(); const scope={organizationId:'owner-org',actor:'owner-user',now:at};
  const request=job(); delete request.id; delete request.organizationId;
  const queued=proposeWork(state,request,scope);
  if(approved) decideWork(state,queued.id,'approve',{...scope,expectedRevision:queued.revision,digest:queued.digest});
  const receipts=[]; let effects=0;
  const options={ledger:{read:async()=>structuredClone(state),transact:async fn=>structuredClone(await fn(state))},
    client:{execute:async()=>{effects++;return {providerId:'draft1',sent:false};}},enabled:()=>true,ownerOrganizationId:'owner-org',storeReceipt:async r=>receipts.push(r),now:()=>at};
  return {state,queued,receipts,options,effects:()=>effects};
}
test('durable worker never runs unapproved, rejected, expired, paused or foreign jobs',async()=>{
  for(const mutate of [f=>{f.queued.status='pending'},f=>{f.queued.status='rejected'},f=>{f.queued.approval.expiresAt=new Date(at-1).toISOString()},f=>{f.state.paused=true},f=>{f.options.ownerOrganizationId='foreign'}]) {
    const f=fixture(); mutate(f); assert.equal((await runGoogleWorkOnce(f.options)).status,'idle'); assert.equal(f.effects(),0);
  }
});
test('durable worker executes exactly once and stores provider receipt before final status',async()=>{
  const f=fixture(); assert.equal((await runGoogleWorkOnce(f.options)).status,'succeeded');
  assert.equal((await runGoogleWorkOnce(f.options)).status,'idle'); assert.equal(f.effects(),1); assert.equal(f.receipts.length,1);
  assert.equal(f.receipts[0].providerReceipt.providerId,'draft1'); assert.equal(f.queued.status,'succeeded');
});
test('timeout and receipt storage failure latch execution instead of retrying',async()=>{
  const f=fixture(); let effects=0;
  f.options.client.execute=async()=>{effects++;throw new GoogleWorkforceError('GOOGLE_OUTCOME_UNKNOWN',true)};
  assert.equal((await runGoogleWorkOnce(f.options)).status,'uncertain');
  await runGoogleWorkOnce(f.options); assert.equal(effects,1);
  const g=fixture(); g.options.storeReceipt=async()=>{throw new Error('disk unavailable')};
  await assert.rejects(runGoogleWorkOnce(g.options)); assert.equal(g.queued.status,'running');
  await runGoogleWorkOnce(g.options); assert.equal(g.effects(),1);
});
test('disabled worker does not touch ledger or Google',async()=>{
  const f=fixture(); f.options.enabled=()=>false;
  assert.equal((await runGoogleWorkOnce(f.options)).status,'disabled'); assert.equal(f.effects(),0);
});

