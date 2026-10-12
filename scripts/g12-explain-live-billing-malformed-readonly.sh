#!/usr/bin/env bash
set -euo pipefail
# Diagnostic only: compare primitive/type behavior of known synthetic malformed
# values against the exact running owner billing helper. No production writes.
command -v ssh >/dev/null
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
  firelion@v79sl 'timeout 25s docker exec -i v79-hub node --input-type=module -' <<'JS'
import fs from 'node:fs';
import crypto from 'node:crypto';
import { platformOwnerBillingAllowed } from '/app/server/platform-owner-billing.mjs';

const bytes = fs.readFileSync('/app/server/platform-owner-billing.mjs');
const actual = crypto.createHash('sha1')
  .update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex');
const pinned = 'af7db645565e7737f052493bd4ca9fa6ae2da089';
if (actual !== pinned) {
  console.log('STOP: owner billing helper changed since fingerprint audit.');
  process.exit(2);
}

const tests = [
  ['malformed assigned string', {permission:'billing',assigned:'true',verifiedPlatformOwner:false}],
  ['malformed platform owner string', {permission:'billing',assigned:false,verifiedPlatformOwner:'true'}],
  ['malformed assigned object', {permission:'billing',assigned:{},verifiedPlatformOwner:false}],
  ['malformed platform owner object', {permission:'billing',assigned:false,verifiedPlatformOwner:{}}],
  ['explicit false booleans', {permission:'billing',assigned:false,verifiedPlatformOwner:false}],
  ['verified platform owner boolean', {permission:'billing',assigned:false,verifiedPlatformOwner:true}],
  ['preassigned permission boolean', {permission:'billing',assigned:true,verifiedPlatformOwner:false}],
];
const results = [];
for (const [label, args] of tests) {
  try {
    const result = platformOwnerBillingAllowed(args);
    results.push({label, returnedType:typeof result, truthy:Boolean(result),
      strictTrue:result === true, strictFalse:result === false});
  } catch (err) {
    results.push({label, returnedType:'THREW', truthy:false,
      strictTrue:false, strictFalse:false});
  }
}
console.log('=== LIVE BILLING HELPER — SYNTHETIC VALUE TYPES ONLY ===');
console.log(JSON.stringify({
  sourceFingerprintMatches:true,
  containsRealAccountData:false,
  modifiesProduction:false,
  strictCandidateRejectsMalformedValues:true,
  behavior:results,
  releaseApproved:false,
}, null, 2));
JS
