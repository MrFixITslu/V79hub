import test from 'node:test';
import assert from 'node:assert/strict';
import { createOwnerBriefingReader } from '../server/workforce-briefing-route.mjs';
function response() {
  return {code:200,headers:{},setHeader(k,v){this.headers[k]=v},status(n){this.code=n;return this},json(x){this.body=x;return this}};
}
test('anonymous and non-MFA users cannot read reports, even when disabled', async () => {
  let reads=0;
  const reader=createOwnerBriefingReader({ownerMfaContext:()=>null,enabled:()=>false,readStatus:async()=>{reads++}});
  const res=response(); await reader({method:'GET'},res);
  assert.equal(res.code,403);assert.equal(reads,0);assert.equal(res.headers['Cache-Control'],'no-store');
});
test('disabled access and mutation methods never invoke the report reader', async () => {
  for(const [enabled,method,expected] of [[false,'GET',503],[true,'POST',405],[true,'DELETE',405]]) {
    const reader=createOwnerBriefingReader({ownerMfaContext:()=>({owner:true}),enabled:()=>enabled,readStatus:()=>{throw Error('must not read')}});
    const res=response();await reader({method},res);assert.equal(res.code,expected);
  }
});
test('owner reads preserve truthful unavailable and stale states', async () => {
  for(const state of ['unavailable','stale_or_unavailable','incomplete','report_available']) {
    const status={mode:'read-only',status:state,reports:[]};
    const reader=createOwnerBriefingReader({ownerMfaContext:()=>({owner:true}),enabled:()=>true,readStatus:async()=>status});
    const res=response();await reader({method:'GET'},res);
    assert.equal(res.code,200);assert.deepEqual(res.body,status);
  }
});
test('invalid contracts and private errors produce generic unavailable responses', async () => {
  for(const readStatus of [async()=>{throw Error('PRIVATE SECRET')},async()=>({mode:'execute',status:'report_available',reports:[]}),async()=>null]) {
    const reader=createOwnerBriefingReader({ownerMfaContext:()=>({owner:true}),enabled:()=>true,readStatus});
    const res=response();await reader({method:'GET'},res);
    assert.equal(res.code,503);assert.equal(JSON.stringify(res.body).includes('PRIVATE'),false);
  }
});
