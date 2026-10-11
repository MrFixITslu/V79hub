import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, readdirSync, statSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, join } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
function snapshot(directory) {
  const result = {};
  function walk(relative='') {
    for (const name of readdirSync(join(directory,relative)).sort()) {
      const path = relative ? relative+'/'+name : name;
      const stat = statSync(join(directory,path),{bigint:true});
      result[path] = {mode:stat.mode.toString(),mtime:stat.mtimeNs.toString(),
        sha256:stat.isFile() ? createHash('sha256').update(readFileSync(join(directory,path))).digest('hex') : null};
      if (stat.isDirectory()) walk(path);
    }
  }
  walk();return result;
}
test('release HOLD preserves active/historical env, source, persistent state and backups without rsync', () => {
  const directory = mkdtempSync(join(tmpdir(),'v79-protected-files-'));
  try {
    for (const path of ['.env','.env.previous','server.ts','data/store.json','backups/prior.dump','.git/HEAD','.incoming.review/server.ts']) {
      mkdirSync(dirname(join(directory,path)),{recursive:true});
      writeFileSync(join(directory,path),'synthetic protected fixture: '+path+'\n',{mode:0o600});
    }
    const before = snapshot(directory);
    for (const file of ['scripts/deploy-server.sh','scripts/deploy-ecosystem-release.sh']) {
      const result = spawnSync('bash',[join(root,file),'a'.repeat(40)],{cwd:directory,encoding:'utf8',timeout:5000});
      assert.equal(result.status,78,result.stderr);
      assert.match(result.stderr,/BLOCKED: release HOLD/);
      assert.deepEqual(snapshot(directory),before,'Protected source/config/state/backup fixture changed');
    }
  } finally { rmSync(directory,{recursive:true,force:true}); }
});
