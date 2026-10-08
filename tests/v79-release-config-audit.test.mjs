import test from "node:test";
import assert from "node:assert/strict";
import { validateV79ReleaseConfig } from "../scripts/release-config-audit.mjs";

function fixture() {
  const same="test-matching-pos-service-secret-1234567890";
  const base="test-platform-shared-secret-1234567890";
  const launch="another-test-launch-secret-1234567890";
  const env={
    "v79-hub":{
      V79_POS_PLATFORM_SHARED_SECRET:same,
      V79_PLATFORM_SHARED_SECRET:base,
      V79_FFPRO_LAUNCH_SECRET:launch,
      V79_TIQUET_LAUNCH_SECRET:launch,
      V79_MARKETING_LAUNCH_SECRET:launch,
      RESEND_API_KEY:"test-mail-api-key",
      V79_HUB_EMAIL_FROM:"test@example.test",
    },
    "v79-pos":{V79_PLATFORM_SHARED_SECRET:same,HUB_INTERNAL_URL:"http://v79-hub:3040"},
    "fire-finance-app":{V79_FFPRO_LAUNCH_SECRET:launch,V79_HUB_INTERNAL_URL:"http://v79-hub:3040"},
    "v79-tiquet-manager":{V79_TIQUET_LAUNCH_SECRET:launch,V79_HUB_INTERNAL_URL:"http://v79-hub:3040"},
    "v79marketing-app":{V79_MARKETING_LAUNCH_SECRET:launch,V79_HUB_INTERNAL_URL:"http://v79-hub:3040"},
  };
  const networks=Object.fromEntries(Object.keys(env).map(n=>[n,["proxy_network"]]));
  return {env,networks};
}
test("POS dedicated Hub secret takes precedence over general platform secret",()=>{
  const {env,networks}=fixture();
  assert.equal(validateV79ReleaseConfig(env,networks).ready,true);
});
test("mismatched dedicated POS identity blocks release without exposing secret values",()=>{
  const {env,networks}=fixture();
  env["v79-pos"].V79_PLATFORM_SHARED_SECRET="wrong-local-key-with-length-over-32-chars";
  const result=validateV79ReleaseConfig(env,networks);
  assert.equal(result.ready,false);
  assert.ok(result.issues.includes("v79-pos:signature_secret_mismatch"));
  assert.doesNotMatch(JSON.stringify(result),/wrong-local-key/);
});
test("missing mail delivery configuration fails only mail configuration gate",()=>{
  const {env,networks}=fixture();
  delete env["v79-hub"].RESEND_API_KEY;
  delete env["v79-hub"].V79_HUB_EMAIL_FROM;
  const result=validateV79ReleaseConfig(env,networks);
  assert.deepEqual(result.issues,["v79-hub:trial_email_provider_unconfigured"]);
});
test("network and invalid Hub hostname fail with scoped issue codes",()=>{
  const {env,networks}=fixture();
  networks["v79marketing-app"]=[];
  env["v79-tiquet-manager"].V79_HUB_INTERNAL_URL="https://example.invalid";
  const result=validateV79ReleaseConfig(env,networks);
  assert.ok(result.issues.includes("v79marketing-app:proxy_network_missing"));
  assert.ok(result.issues.includes("v79-tiquet-manager:hub_route_incorrect"));
});
