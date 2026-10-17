#!/usr/bin/env bash
set -euo pipefail
# Acer-only, no-write synthetic behavior check against deployed owner billing helper.
# Prints no source, credentials, user IDs, records, or environment variables.
command -v ssh >/dev/null
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
  firelion@v79sl 'timeout 25s docker exec -i v79-hub node --input-type=module -' <<'JS'
import fs from 'node:fs';
import crypto from 'node:crypto';
import { platformOwnerBillingAllowed } from '/app/server/platform-owner-billing.mjs';

const src = fs.readFileSync('/app/server/platform-owner-billing.mjs');
const blob = crypto.createHash('sha1')
  .update(Buffer.from('blob ' + src.length + '\0'))
  .update(src).digest('hex');
const reference = 'af7db645565e7737f052493bd4ca9fa6ae2da089';
if (blob !== reference) {
  console.log('STOP: live billing helper changed since recorded fingerprint');
  process.exitCode = 2;
} else {
  const cases = [
    ['owner billing fallback', {permission:'billing',assigned:false,verifiedPlatformOwner:true}, true],
    ['nonowner billing denied', {permission:'billing',assigned:false,verifiedPlatformOwner:false}, false],
    ['unverified platform owner denied', {permission:'billing',assigned:false}, false],
    ['owner team permission denied', {permission:'team',assigned:false,verifiedPlatformOwner:true}, false],
    ['owner security permission denied', {permission:'security',assigned:false,verifiedPlatformOwner:true}, false],
    ['owner admin permission denied', {permission:'admin',assigned:false,verifiedPlatformOwner:true}, false],
    ['preassigned team access preserved', {permission:'team',assigned:true,verifiedPlatformOwner:false}, true],
    ['malformed assigned value denied', {permission:'billing',assigned:'true',verifiedPlatformOwner:false}, false],
    ['malformed owner value denied', {permission:'billing',assigned:false,verifiedPlatformOwner:'true'}, false],
  ];
  let errors = 0;
  for (const [label, args, expected] of cases) {
    try {
      const result = platformOwnerBillingAllowed(args);
      const pass = result === expected;
      console.log((pass?'PASS':'FAIL') + ': ' + label);
      if (!pass) errors++;
    } catch {
      console.log('FAIL: ' + label + ' (helper rejected synthetic input)');
      errors++;
    }
  }
  console.log('Synthetic live billing contract:', errors === 0 ? 'PASS' : 'MISMATCH');
  if (errors !== 0) process.exitCode = 2;
}
JS
