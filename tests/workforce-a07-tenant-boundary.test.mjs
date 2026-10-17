/**
 * A07: synthetic HTTP authorization and tenant isolation against the REAL G2
 * route/store implementation. Loopback ephemeral test server, temp ledger,
 * synthetic tokens, no production app endpoints or persistent data.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createServer } from 'node:http';
import { createWorkActionStore } from '../server/workforce-action-store.mjs';
import { workforceActionRouters } from '../server/workforce-action-routes.mjs';

test('A07 owner MFA, tenant fence, separate worker token and rejected task path', async t => {
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'v79-a07-boundary-'));
  const ledger=createWorkActionStore({file:path.join(directory,'ledger.json'),
    secret:'SYNTHETIC-ONLY-A07-OWNER-AUDIT-KEY-20261017'});
  const NOW=Date.parse('2026-10-17T04:30:00Z');
  const TOKEN='SYNTHETIC-A07-TASK-WORKER-TOKEN-20261017';
  let enabled=true,ready=true;
  const app=express();
  app.use(express.json());
  // Test-only identity injection. Live server must use its actual session,
  // founder allowlist, recent MFA, origin checks and authenticated HMAC ledger.
  app.use((req,_res,next)=>{
    req.user={mfaVerifiedAt:req.get('x-test-stale-mfa') ? NOW-300001 : NOW};
    next();
  });
  const routes=workforceActionRouters({
    ledger,enabled:()=>enabled,ownerReady:()=>ready,workerToken:()=>TOKEN,
    ownerOrganizationId:()=> 'org-alpha',
    ownerContext:req=>{
      const claimed=req.get('x-test-role');
      if(!['alpha','beta'].includes(claimed)) return null;
      return {organizationId:claimed==='alpha'?'org-alpha':'org-beta',
        userId:'synthetic-founder-'+claimed};
    },
    sameOrigin:req=>req.get('origin')==='https://hub.synthetic.test',
    now:()=>NOW,
  });
  app.use('/owner',routes.owner);
  app.use('/worker',routes.worker);
  const server=createServer(app);
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(async()=>{
    await new Promise(resolve=>server.close(resolve));
    await ledger.close();
    await fs.rm(directory,{recursive:true,force:true});
  });
  const base='http://127.0.0.1:'+server.address().port;
  const owner=role=>({origin:'https://hub.synthetic.test','x-test-role':role});
  const worker={'x-v79-workforce-token':TOKEN};
  async function call(route,body,headers={}){
    const res=await fetch(base+route,{
      method:body===undefined?'GET':'POST',
      headers:{'content-type':'application/json',...headers},
      ...(body===undefined?{}:{body:JSON.stringify(body)}),
    });
    let data;try{data=await res.json()}catch{data={}}
    return {status:res.status,data};
  }
  const input=(summary,key)=>({
    operation:'create_work_item',system:'hub',summary,
    payload:{detail:'Synthetic internal contract check only. No external tasks.'},
    idempotencyKey:key,
  });

  // An unauthenticated/cross-origin/stale-MFA client cannot propose or read.
  assert.equal((await call('/owner')).status,403);
  assert.equal((await call('/owner',input('Synthetic alpha task','a07-alpha-key-20261017'))).status,403);
  assert.equal((await call('/owner',input('Synthetic alpha task','a07-alpha-key-20261017'),
    {...owner('alpha'),origin:'https://evil.synthetic.test'})).status,403);
  assert.equal((await call('/owner',input('Synthetic alpha task','a07-alpha-key-20261017'),
    {...owner('alpha'),'x-test-stale-mfa':'1'})).status,403);

  const proposed=await call('/owner',input('Synthetic alpha task','a07-alpha-key-20261017'),owner('alpha'));
  assert.equal(proposed.status,201);
  const job=proposed.data.job;
  assert.equal(job.status,'pending');
  const decision={decision:'approve',expectedRevision:job.revision,digest:job.digest};

  // An authenticated member of another synthetic org sees no alpha rows.
  const betaView=await call('/owner',undefined,owner('beta'));
  assert.equal(betaView.status,200);
  assert.equal(betaView.data.jobs.length,0);
  assert.equal(betaView.data.tasks.length,0);
  assert.equal((await call('/owner/'+job.id+'/decision',decision,owner('beta'))).status,409);
  assert.equal((await call('/owner/'+job.id+'/cancel',{expectedRevision:job.revision},owner('beta'))).status,409);
  assert.equal((await call('/owner/'+job.id+'/execute',{expectedRevision:job.revision},owner('beta'))).status,409);

  // Browser credentials, agent token and requests bearing Origin/Cookie must
  // never be accepted as the separate private task worker credential.
  assert.equal((await call('/worker/execute-work-item',{},{})).status,403);
  assert.equal((await call('/worker/execute-work-item',{},{
    'x-v79-agent-token':TOKEN})).status,403);
  assert.equal((await call('/worker/execute-work-item',{},{
    ...worker,origin:'https://hub.synthetic.test'})).status,403);
  assert.equal((await call('/worker/execute-work-item',{},{
    ...worker,cookie:'synthetic-session=present'})).status,403);
  assert.equal((await call('/worker/execute-work-item',{force:true},worker)).status,400);
  assert.deepEqual((await call('/worker/execute-work-item',{},worker)).data,{job:null});

  // Rejected alpha job cannot be stolen by the worker or executed via owner.
  const rejected=await call('/owner/'+job.id+'/decision',{
    decision:'reject',expectedRevision:job.revision,digest:job.digest,
  },owner('alpha'));
  assert.equal(rejected.status,200);
  assert.equal(rejected.data.job.status,'rejected');
  assert.equal((await call('/owner/'+job.id+'/execute',{
    expectedRevision:rejected.data.job.revision,
  },owner('alpha'))).status,409);
  assert.deepEqual((await call('/worker/execute-work-item',{},worker)).data,{job:null});
  let state=await ledger.read();
  assert.equal(state.tasks.length,0);
  assert.deepEqual(state.events.filter(e=>e.jobId===job.id).map(e=>e.type),
    ['proposed','rejected']);

  // A separate approved synthetic job is executed once, then worker is idle.
  const readyJob=(await call('/owner',input(
    'Synthetic alpha approved item','a07-approved-key-20261017'),owner('alpha'))).data.job;
  const approved=await call('/owner/'+readyJob.id+'/decision',{
    decision:'approve',expectedRevision:readyJob.revision,digest:readyJob.digest,
  },owner('alpha'));
  assert.equal(approved.status,200);
  // OwnerReady is a hard worker fence, independent from queue status.
  ready=false;
  assert.equal((await call('/worker/execute-work-item',{},worker)).status,503);
  ready=true;
  const executed=await call('/worker/execute-work-item',{},worker);
  assert.equal(executed.status,200);
  assert.equal(executed.data.job.status,'succeeded');
  assert.equal((await call('/worker/execute-work-item',{},worker)).data.job,null);
  state=await ledger.read();
  assert.equal(state.tasks.length,1);
  assert.equal(state.tasks[0].jobId,readyJob.id);
  assert.equal(state.tasks[0].organizationId,'org-alpha');
  assert.equal(state.tasks[0].id,executed.data.job.result.taskId);
  assert.deepEqual(state.events.filter(e=>e.jobId===readyJob.id).map(e=>e.type),
    ['proposed','approved','work_item_created']);
  assert.equal(state.events.find(e=>e.jobId===readyJob.id&&e.type==='work_item_created').actor,'coo-worker');
  assert.equal((await call('/owner',undefined,owner('beta'))).data.tasks.length,0);
  assert.equal((await call('/owner',undefined,owner('alpha'))).data.tasks.length,1);

  // Global disable stops dispatch even with a valid trusted worker token.
  enabled=false;
  assert.equal((await call('/worker/execute-work-item',{},worker)).status,503);
});
