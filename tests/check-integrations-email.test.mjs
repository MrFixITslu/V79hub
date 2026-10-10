import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

test('integration checker accepts the configured V79 owner email', () => {
  const dataDir = mkdtempSync(path.join(tmpdir(), 'v79-check-integrations-'));
  const result = spawnSync(process.execPath, ['scripts/check-integrations.mjs', '--only', 'pos'], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      DATA_DIR: dataDir,
      V79_HUB_ADMIN_EMAIL: 'vision79slu@gmail.com',
      V79_PLATFORM_SHARED_SECRET: 'x'.repeat(32),
    },
    encoding: 'utf8',
  });

  assert.equal(result.status, 1);
  assert.match(result.stderr, /Hub workspace identity is missing/);
  assert.doesNotMatch(result.stderr, /V79_HUB_ADMIN_EMAIL is not configured/);
});
