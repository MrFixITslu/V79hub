#!/usr/bin/env bash
set -euo pipefail

# Acer read-only check. Only fixed runtime code paths and Boolean feature flags
# are examined; no file contents, secrets, credentials, or tenant data are printed.
# This is NOT a release approval, nor a replacement for independent review.
test "${HOSTNAME:-}" != "v79sl" || { echo "STOP: run this Acer-side, not on the server"; exit 2; }
command -v ssh >/dev/null
printf '%s\n' '=== V79 LIVE MODULE PARITY / READ ONLY ==='
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
  firelion@v79sl 'timeout 30s docker exec -i v79-hub node --input-type=module -' <<'JS'
import fs from 'node:fs';
import crypto from 'node:crypto';

const files = Object.freeze({
  'server/platform-owner-billing.mjs': null,
  'server/sentinel-service-entitlement.mjs': 'b679af6330d0b75033283ee36bcdcae2648217a5',
  'server/sentinel-service-grants.mjs': '6454da6d6216af26c5f844772d665a2ca0bd24ac',
  'server/sentinel-grant-operator.mjs': '5ddfe367cdc6383a5af75358df92601b8e688fe3',
});
const flags = [
  'V79_SENTINEL_HUB_SERVICE_ENABLED',
  'V79_SENTINEL_GRANT_ADMIN_ENABLED',
  'V79_SENTINEL_OWNER_MAPPING_ATTESTED',
];
const output = {
  scope: 'V79 LIVE MODULE PARITY / READ ONLY',
  noProductionWrites: true,
  candidateReleaseApproved: false,
  runtimeFiles: {},
  featureFlags: {},
};
for (const [file, expected] of Object.entries(files)) {
  try {
    const bytes = fs.readFileSync('/app/' + file);
    const hash = crypto.createHash('sha1')
      .update(Buffer.from('blob ' + bytes.length + '\0'))
      .update(bytes).digest('hex');
    output.runtimeFiles[file] = {
      state: 'present',
      gitBlobSha1: hash,
      referenceMatches: expected === null ? 'NO_PUBLISHED_REFERENCE' :
        hash === expected ? 'MATCH' : 'DIFFERENT',
      reviewedReference: expected,
    };
  } catch (error) {
    output.runtimeFiles[file] = { state: 'missing_or_unreadable', referenceMatches: 'UNVERIFIED' };
  }
}
for (const flag of flags) output.featureFlags[flag] = process.env[flag] === '1' ? 'ENABLED' : 'NOT_ENABLED';
console.log(JSON.stringify(output, null, 2));
JS
printf '%s\n' '=== READ ONLY CHECK COMPLETE ==='
