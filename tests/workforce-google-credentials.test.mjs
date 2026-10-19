import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { GOOGLE_SCOPES, googleCredentialBroker } from '../server/workforce-google-credentials.mjs';
const fakeCredentials = {schema:1,owner:'vision79slu@gmail.com',client_id:'synthetic-client',client_secret:'synthetic-client-secret',refresh_token:'synthetic-refresh',scopes:GOOGLE_SCOPES};
async function fixture(t) {
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'v79-oauth-test-'));
  const file=path.join(directory,'credentials.json');
  await fs.writeFile(file,JSON.stringify(fakeCredentials),{mode:0o600});
  t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  let calls=0, active=true;
  const requests=[];
  const broker=googleCredentialBroker({file,enabled:()=>active,fetchImpl:async(url,options)=>{
    calls++;requests.push({url,options});
    return new Response(JSON.stringify({access_token:'synthetic-access',token_type:'Bearer',expires_in:3600}));
  }});
  return {file,directory,broker,requests,calls:()=>calls,disable:()=>{active=false}};
}
test('credential broker refreshes only fixed Google token endpoint and caches in memory',async t=>{
  const f=await fixture(t);
  const tokens=await Promise.all([f.broker.getAccessToken('gmail'),f.broker.getAccessToken('calendar')]);
  assert.deepEqual(tokens,['synthetic-access','synthetic-access']);assert.equal(f.calls(),1);
  await f.broker.getAccessToken('gmail');assert.equal(f.calls(),1);
  assert.equal(f.requests[0].url,'https://oauth2.googleapis.com/token');assert.equal(f.requests[0].options.redirect,'error');
  assert.equal(new URLSearchParams(f.requests[0].options.body).get('grant_type'),'refresh_token');
  const disk=JSON.parse(await fs.readFile(f.file,'utf8'));assert.equal(disk.access_token,undefined);
});
test('disabled broker and arbitrary service cannot obtain credentials',async t=>{
  const f=await fixture(t);await assert.rejects(f.broker.getAccessToken('arbitrary'));
  f.disable();await assert.rejects(f.broker.getAccessToken('gmail'));assert.equal(f.calls(),0);
});
test('missing, exposed, symlinked, wrong-account or wrong-scope credentials fail closed',async t=>{
  const f=await fixture(t);
  for(const change of [async()=>fs.chmod(f.file,0o644),async()=>fs.writeFile(f.file,JSON.stringify({...fakeCredentials,owner:'other@example.com'}),{mode:0o600}),async()=>fs.writeFile(f.file,JSON.stringify({...fakeCredentials,scopes:[...GOOGLE_SCOPES,'https://mail.google.com/']}),{mode:0o600})]) {
    await fs.chmod(f.file,0o600);await change();await assert.rejects(f.broker.getAccessToken('gmail'),e=>e.code==='GOOGLE_CREDENTIALS_UNAVAILABLE');
  }
  await fs.unlink(f.file);await fs.symlink('/does/not/exist',f.file);
  await assert.rejects(f.broker.getAccessToken('gmail'));assert.equal(f.calls(),0);
});
test('removing credentials invalidates use of a cached access token',async t=>{
  const f=await fixture(t);await f.broker.getAccessToken('gmail');await fs.unlink(f.file);
  await assert.rejects(f.broker.getAccessToken('gmail'));assert.equal(f.calls(),1);
});
test('refresh failures never expose token response or raw errors',async t=>{
  const f=await fixture(t);
  for(const fetchImpl of [async()=>new Response('sensitive-refresh',{status:400}),async()=>{throw new Error('sensitive-refresh')},async()=>new Response(JSON.stringify({access_token:'sensitive-refresh',token_type:'Bearer',expires_in:3600,scope:'unexpected'}))]) {
    const broker=googleCredentialBroker({file:f.file,enabled:()=>true,fetchImpl});
    await assert.rejects(broker.getAccessToken('gmail'),e=>!e.message.includes('sensitive-refresh'));
  }
});
