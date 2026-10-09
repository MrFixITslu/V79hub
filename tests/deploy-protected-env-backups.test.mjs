import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const deployment = readFileSync(resolve(root, 'scripts/deploy-server.sh'), 'utf8');
test('production source sync preserves active and historical environment files and persistent storage', () => {
  for (const exclusion of ["--exclude='/.env'", "--exclude='/.env.*'", "--exclude='/data/'", "--exclude='/backups/'", "--exclude='/.incoming.*/'"]) {
    assert.ok(deployment.includes(exclusion), `Missing protected rsync exclusion: ${exclusion}`);
  }
});
