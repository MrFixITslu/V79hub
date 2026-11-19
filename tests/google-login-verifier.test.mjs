import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, sign } from 'node:crypto';
import { inspectGoogleJwt } from '../server/google-login.mjs';

const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const jwk = { ...publicKey.export({format:'jwk'}), kid:'synthetic-test-key' };
const now = 1760000000000;
const clientId = 'synthetic-client';
const nonce = 'synthetic-nonce-not-for-production';
const claims = { iss:'https://accounts.google.com', aud:clientId, nonce,
  email_verified:true, exp:now/1000+300, iat:now/1000-5,
  sub:'12345678901234567890', email:'Test.User@Gmail.com' };
const enc = v=>Buffer.from(JSON.stringify(v)).toString('base64url');
function token(c={},h={}) {
  const body=enc({alg:'RS256',kid:jwk.kid,...h})+'.'+enc({...claims,...c});
  return body+'.'+sign('RSA-SHA256',Buffer.from(body),privateKey).toString('base64url');
}
const verify=(t,opts={})=>inspectGoogleJwt(t,{clientId,nonce,keys:[jwk],now,...opts});
test('synthetic signed identity is verified and normalised',()=>{
  assert.deepEqual(verify(token()),{sub:claims.sub,email:'test.user@gmail.com'});
});
for(const [name,change] of Object.entries({
  audience:{aud:'other-client'}, nonce:{nonce:'other-nonce'},
  issuer:{iss:'https://example.invalid'}, unverified:{email_verified:false},
  expires:{exp:now/1000}, future:{iat:now/1000+61},
  stale:{iat:now/1000-7201}, subject:{sub:'invalid'},
  malformedEmail:{email:'invalid'}, untrustedDomain:{email:'test@example.invalid'},
  wrongWorkspace:{email:'test@example.invalid',hd:'other.invalid'},
}))test('reject '+name,()=>assert.throws(()=>verify(token(change))));
test('accept verified matching Workspace domain',()=>{
  assert.equal(verify(token({email:'test@example.invalid',hd:'example.invalid'})).email,'test@example.invalid');
});
test('reject algorithm substitution, unknown key and corrupt signature',()=>{
  assert.throws(()=>verify(token({}, {alg:'none'})));
  assert.throws(()=>verify(token({}, {kid:'unknown'})));
  const [h,c]=token().split('.');
  assert.throws(()=>verify(h+'.'+c+'.'+Buffer.alloc(256).toString('base64url')));
});
