import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { platformOwnerBillingAllowed } from "../server/platform-owner-billing.mjs";

test("exact platform owner may recover only legacy billing permission", () => {
  assert.equal(platformOwnerBillingAllowed({permission:"billing",assigned:false,verifiedPlatformOwner:true}), true);
  for (const permission of ["admin","security","team","users","overview","payments","entitlement"]) {
    assert.equal(platformOwnerBillingAllowed({permission,assigned:false,verifiedPlatformOwner:true}), false);
  }
  for (const owner of [false,undefined,null,"true",1]) {
    assert.equal(platformOwnerBillingAllowed({permission:"billing",assigned:false,verifiedPlatformOwner:owner}), false);
  }
  for (const assigned of [false,undefined,null,"true",1]) {
    assert.equal(platformOwnerBillingAllowed({permission:"billing",assigned,verifiedPlatformOwner:false}), false);
  }
  assert.equal(platformOwnerBillingAllowed({permission:"billing",assigned:true,verifiedPlatformOwner:false}), true);
  assert.equal(platformOwnerBillingAllowed(),false);
});

test("platform owner proof is computed only from exact user + workspace + owner membership", () => {
  const source = fs.readFileSync(new URL("../server.ts", import.meta.url), "utf8");
  const begin = source.indexOf("function isPlatformOperatorIdentity(");
  const end = source.indexOf("\nfunction requirePlatformOperator(",begin);
  assert.ok(begin > -1 && end > begin);
  const guard = source.slice(begin,end);
  assert.match(guard,/user\.id === posIdentity\.ownerUserId/);
  assert.match(guard,/organizationId === posIdentity\.organizationId/);
  assert.match(guard,/membership\?\.role === "owner"/);
  assert.match(guard,/normalizeEmail\(user\.email\) === vision79OwnerEmail/);
  assert.match(guard,/normalizeEmail\(process\.env\.V79_HUB_ADMIN_EMAIL\) === vision79OwnerEmail/);
  assert.match(source,/verifiedPlatformOwner: isPlatformOperatorIdentity\(userId, organizationId\)/);
});

test("candidate preserves Sentinel grant persistence, default-off machine routes, and G1.2 routes", () => {
  const source = fs.readFileSync(new URL("../server.ts", import.meta.url), "utf8");
  assert.match(source,/sentinelServiceGrants: validateSentinelGrantCollection\(parsed\.sentinelServiceGrants \?\? \[\]\)/);
  assert.match(source,/sentinelServiceGrants: \[\]/);
  assert.match(source,/app\.use\(SENTINEL_SERVICE_PATH, sentinelServiceRouter\(/);
  assert.match(source,/enabled: process\.env\.V79_SENTINEL_HUB_SERVICE_ENABLED === "1"/);
  assert.match(source,/V79_SENTINEL_GRANT_ADMIN_ENABLED==="1"/);
  assert.match(source,/V79_SENTINEL_OWNER_MAPPING_ATTESTED==="1"/);
  assert.match(source,/await commitStore\(next\.store\)/);
  assert.match(source,/await commitStore\(next\)/);
  assert.doesNotMatch(source,/await commitSentinelStore\(next(?:\.store)?\)/);
  for (const endpoint of [
    'app.get("/api/agent/executive-structure"',
    'app.post("/api/agent/executive-handoff"',
    'app.post("/api/agent/executive-preview"',
  ]) assert.ok(source.includes(endpoint));
});
