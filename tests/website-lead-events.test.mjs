import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {spawnSync} from 'node:child_process';
import {createWebsiteLeadEventReceiver, WEBSITE_EVENT_PATH} from '../server/website-lead-events.mjs';
import {signPlatformRequest} from '../server/platform-contract.mjs';

await test('website event boundary and durable receipt over real loopback HTTP', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'v79-event-test-'));
  const dataDir = path.join(root, 'data'); fs.mkdirSync(dataDir);
  const env = {V79_WEBSITE_EVENTS_ENABLED:'1', V79_WEBSITE_EVENT_SECRET:crypto.randomBytes(32).toString('hex'),
    V79_WEBSITE_ORGANIZATION_REF:'platform-org'};
  const options = {dataDir, env, organizationAllowed:id => id === 'platform-org'};
  let receiver = createWebsiteLeadEventReceiver(options);
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    req.rawBody = Buffer.concat(chunks);
    req.get = name => req.headers[name.toLowerCase()];
    res.status = code => {res.statusCode = code; return res;};
    res.json = data => {res.setHeader('Content-Type','application/json'); res.end(JSON.stringify(data));};
    if (req.method === 'POST' && req.url === WEBSITE_EVENT_PATH) receiver.receive(req,res);
    else {res.status(404).json({error:'not found'});}
  });
  await new Promise(r => server.listen(0,'127.0.0.1',r));
  const base = `http://127.0.0.1:${server.address().port}`;
  function event() {return {id:crypto.randomUUID(), type:'lead.created', version:1,
    occurredAt:new Date().toISOString(), organizationRef:'platform-org', subjectId:'2',
    correlationId:crypto.randomUUID(), payload:{leadId:2, interest:'Internal test', pageOrigin:'/contact'}};}
  async function send(e, overrides = {}) {
    const body = typeof e === 'string' ? e : JSON.stringify(e);
    const timestamp = overrides.timestamp || String(Date.now());
    const signature = signPlatformRequest({method:'POST',pathname:WEBSITE_EVENT_PATH,
      timestamp,body,secret:env.V79_WEBSITE_EVENT_SECRET});
    const response = await fetch(base+WEBSITE_EVENT_PATH,{method:'POST',body,
      headers:{'content-type':'application/json','x-v79-service-id':'website',
        'x-v79-timestamp':timestamp,'x-v79-signature':signature,...overrides}});
    return {status:response.status,body:await response.json()};
  }
  try {
    await t.test('disabled and incomplete configuration refuse without storing',async()=>{
      env.V79_WEBSITE_EVENTS_ENABLED='0'; assert.equal((await send(event())).status,503);
      env.V79_WEBSITE_EVENTS_ENABLED='1'; env.V79_WEBSITE_ORGANIZATION_REF='';
      assert.equal((await send(event())).status,503); env.V79_WEBSITE_ORGANIZATION_REF='platform-org';
      const saved=env.V79_WEBSITE_EVENT_SECRET; env.V79_WEBSITE_EVENT_SECRET='short';
      const r=await fetch(base+WEBSITE_EVENT_PATH,{method:'POST',body:'{}'}); assert.equal(r.status,503);
      env.V79_WEBSITE_EVENT_SECRET=saved; assert.equal(fs.existsSync(path.join(dataDir,'website-lead-events')),false);
    });
    await t.test('wrong service, signature, modified body and timestamp rejected',async()=>{
      for(const overrides of [{'x-v79-service-id':'v79-hub'},{'x-v79-signature':'0'.repeat(64)},
        {timestamp:String(Date.now()-600000)},{timestamp:String(Date.now()+600000)}])
        assert.equal((await send(event(),overrides)).status,401);
      const e=event(), body=JSON.stringify(e), timestamp=String(Date.now());
      const sig=signPlatformRequest({method:'POST',pathname:WEBSITE_EVENT_PATH,timestamp,body,secret:env.V79_WEBSITE_EVENT_SECRET});
      assert.equal((await send({...e,subjectId:'3'}, {'x-v79-timestamp':timestamp,'x-v79-signature':sig})).status,401);
    });
    await t.test('foreign tenant and unrecognised configured tenant denied',async()=>{
      assert.equal((await send({...event(),organizationRef:'customer-org'})).status,403);
      env.V79_WEBSITE_ORGANIZATION_REF='customer-org';assert.equal((await send(event())).status,503);
      env.V79_WEBSITE_ORGANIZATION_REF='platform-org';
    });
    await t.test('unsupported actions, malformed envelopes and extra PII denied',async()=>{
      const e=event();
      for(const bad of ['{', {...e,id:'../../escape'}, {...e,type:'payment.completed'},
        {...e,version:2}, {...e,subjectId:'3'}, {...e,occurredAt:'bad'},
        {...e,payload:{...e.payload,email:'private@example.test'}},
        {...e,payload:{...e.payload,interest:'x'.repeat(4001)}}, {...e,command:'run'}])
        assert.equal((await send(bad)).status,400);
    });
    const accepted=event();
    await t.test('durable receipt created with private permissions and no execution',async()=>{
      const r=await send(accepted);assert.equal(r.status,201);assert.equal(r.body.executionEnabled,false);
      const dir=path.join(dataDir,'website-lead-events'),file=path.join(dir,accepted.id+'.json');
      assert.equal(fs.statSync(dir).mode&0o777,0o700);assert.equal(fs.statSync(file).mode&0o777,0o600);
      const receipt=JSON.parse(fs.readFileSync(file));assert.equal(receipt.event.subjectId,'2');
      assert.equal(receipt.state,'received');assert.equal(fs.readdirSync(dir).length,1);
    });
    await t.test('restart and concurrent retries preserve exactly one receipt',async()=>{
      receiver=createWebsiteLeadEventReceiver(options);
      const replies=await Promise.all(Array.from({length:12},()=>send(accepted)));
      assert.ok(replies.every(r=>r.status===200&&r.body.duplicate===true));
      assert.equal(fs.readdirSync(path.join(dataDir,'website-lead-events')).length,1);
      const fresh=event(); const first=await Promise.all(Array.from({length:6},()=>send(fresh)));
      assert.equal(first.filter(r=>r.status===201).length,1);
      assert.equal(first.filter(r=>r.status===200).length,5);
    });
    await t.test('same event ID with altered contents conflicts without overwrite',async()=>{
      const file=path.join(dataDir,'website-lead-events',accepted.id+'.json');
      const before=fs.readFileSync(file,'utf8');
      assert.equal((await send({...accepted,payload:{...accepted.payload,interest:'changed'}})).status,409);
      assert.equal(fs.readFileSync(file,'utf8'),before);
    });
    await t.test('fresh process recognises the persisted event without a new receipt',()=>{
      const moduleUrl = new URL('../server/website-lead-events.mjs',import.meta.url).href;
      const raw = JSON.stringify(accepted), timestamp = String(Date.now());
      const signature = signPlatformRequest({method:'POST',pathname:WEBSITE_EVENT_PATH,
        timestamp,body:raw,secret:env.V79_WEBSITE_EVENT_SECRET});
      const code = `import {createWebsiteLeadEventReceiver} from ${JSON.stringify(moduleUrl)};
        const input=JSON.parse(process.env.EVENT_TEST_INPUT);
        const receiver=createWebsiteLeadEventReceiver({dataDir:input.dataDir,env:input.env,
          organizationAllowed:id=>id==='platform-org'});
        let status=200;
        receiver.receive({rawBody:Buffer.from(input.raw),get:k=>input.headers[k]},
          {setHeader(){},status(s){status=s;return this;},json(body){console.log(JSON.stringify({status,body}));}});`;
      const child=spawnSync(process.execPath,['--input-type=module','-e',code],{
        encoding:'utf8',env:{...process.env,EVENT_TEST_INPUT:JSON.stringify({dataDir,env,raw,
          headers:{'x-v79-service-id':'website','x-v79-timestamp':timestamp,'x-v79-signature':signature}})}});
      assert.equal(child.status,0,child.stderr);const result=JSON.parse(child.stdout);
      assert.equal(result.status,200);assert.equal(result.body.duplicate,true);
    });
    await t.test('owner receipt lookup returns bounded metadata',()=>{
      let status=200,body;
      receiver.receipt({params:{eventId:accepted.id}}, {setHeader(){},status(s){status=s;return this;},json(v){body=v;}});
      assert.equal(status,200);assert.equal(body.subjectId,'2');assert.equal(body.executionEnabled,false);
      assert.equal(body.payload,undefined);assert.equal(body.digest,undefined);
    });
    await t.test('corrupt or unavailable persistence cannot report success',async()=>{
      const e=event();fs.writeFileSync(path.join(dataDir,'website-lead-events',e.id+'.json'),'{');
      assert.equal((await send(e)).status,503);
      const blocked=path.join(root,'not-a-directory');fs.writeFileSync(blocked,'blocked');
      receiver=createWebsiteLeadEventReceiver({...options,dataDir:blocked});
      assert.equal((await send(event())).status,503);
    });
  } finally {
    await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});
  }
});
