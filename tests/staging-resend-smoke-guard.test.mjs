import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

const script="scripts/staging-resend-smoke.mjs";
function run(env,recipient) {
  return spawnSync(process.execPath,[script,"--to="+recipient],{
    cwd:process.cwd(),encoding:"utf8",
    env:{...process.env,NODE_ENV:"test",...env},
    timeout:5000,
  });
}
test("staging live send requires explicit one-email confirmation",()=>{
  const result=run({V79_STAGING_RESEND_SMOKE:""},"vision79slu@gmail.com");
  assert.equal(result.status,2);
  assert.match(result.stderr,/STAGING SAFETY GUARD/);
});
test("staging live send is restricted to verified test inbox",()=>{
  const result=run({V79_STAGING_RESEND_SMOKE:"I_APPROVE_ONE_TEST_EMAIL"},"customer@example.test");
  assert.equal(result.status,2);
  assert.match(result.stderr,/STAGING SAFETY GUARD/);
});
test("staging live send rejects production NODE_ENV even with confirmation",()=>{
  const result=run({V79_STAGING_RESEND_SMOKE:"I_APPROVE_ONE_TEST_EMAIL",
    NODE_ENV:"production"},"vision79slu@gmail.com");
  assert.equal(result.status,2);
  assert.match(result.stderr,/STAGING SAFETY GUARD/);
});
