import {test} from 'node:test';
import assert from 'node:assert/strict';
import {authorizeOrganizationRename} from '../server/organization-name.mjs';

const basic = {
  body: {organizationId:'tenant-001', businessId:'marketing-001',hubUserId:'scoped-owner-001',name:'V79 Digital'},
  organizations:[{id:'tenant-001',name:'Old Business',status:'active'}],
  memberships:[{organizationId:'tenant-001',userId:'owner-001',role:'owner',status:'active'}],
  mapping:{status:'active',externalTenantId:'marketing-001'},
  scopedHubUserId:(id,org)=>id==='owner-001'&&org==='tenant-001'?'scoped-owner-001':'untrusted',
};
const check=(options={})=>authorizeOrganizationRename({...basic,...options});
test('canonical rename authorises only exact active owner, tenant and external Marketing mapping',()=>{
  assert.equal(check().ok,true);
  assert.equal(check({body:{...basic.body,hubUserId:'forged-user-001'}}).status,403);
  assert.equal(check({body:{...basic.body,businessId:'marketing-002'}}).status,403);
  assert.equal(check({mapping:{status:'pending',externalTenantId:'marketing-001'}}).status,403);
  assert.equal(check({organizations:[{id:'tenant-001',name:'Old Business',status:'suspended'}]}).status,403);
  assert.equal(check({memberships:[{...basic.memberships[0],role:'manager'}]}).status,403);
  assert.equal(check({memberships:[{...basic.memberships[0],status:'revoked'}]}).status,403);
  assert.equal(check({memberships:[{...basic.memberships[0],organizationId:'tenant-002'}]}).status,403);
});
test('canonical rename rejects empty, control, spoofed or oversized name values',()=>{
  for(const name of ['', '  ', 'x\nInjected', 'Name\u202eMask', 'z'.repeat(181), 2, null]){
    assert.equal(check({body:{...basic.body,name}}).status,400);
  }
});
test('canonical rename normalises spaces and Unicode without rewriting tenant identities',()=>{
  const r=check({body:{...basic.body,name:'  V79 Café  '}});
  assert.equal(r.ok,true);
  assert.equal(r.name,'V79 Café');
  assert.equal(r.organizationId,'tenant-001');
  assert.equal(r.owner.userId,'owner-001');
});
