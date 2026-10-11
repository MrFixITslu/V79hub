import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
const root = new URL('../', import.meta.url).pathname;
for (const file of ['scripts/deploy-server.sh', 'scripts/deploy-ecosystem-release.sh']) {
  test(file + ' refuses valid and attempted bypass arguments before external commands', () => {
    const dir = mkdtempSync(join(tmpdir(),'v79-hold-'));
    const log = join(dir,'mutation-attempt');
    try {
      for (const name of ['docker','rsync','tar','ssh','scp','curl','wget','head','install']) {
        writeFileSync(join(dir,name),'#!/usr/bin/env bash\nprintf attempted >> "$V79_HOLD_TEST_LOG"\nexit 99\n',{mode:0o755});
      }
      for (const args of [[], ['a'.repeat(40)], ['a'.repeat(40),'--apply','--force']]) {
        const result = spawnSync('bash',[join(root,file),...args],{cwd:dir,encoding:'utf8',
          env:{...process.env,PATH:dir+':'+process.env.PATH,V79_HOLD_TEST_LOG:log,V79_RELEASE_APPROVED:'1'},timeout:5000});
        assert.equal(result.status,78,result.stderr);
        assert.match(result.stderr,/BLOCKED: release HOLD/);
        assert.equal(existsSync(log),false,'An external mutation command was attempted');
      }
    } finally { rmSync(dir,{recursive:true,force:true}); }
  });
}
test('workflow HOLD occurs before production access', () => {
  const workflow = readFileSync(join(root,'.github/workflows/v79-ci-cd.yml'),'utf8');
  const deploy = workflow.slice(workflow.indexOf('\n  deploy:'));
  assert.ok(deploy.indexOf('run: bash scripts/deploy-server.sh') >= 0);
  assert.ok(deploy.indexOf('run: bash scripts/deploy-server.sh') < deploy.indexOf('actions/download-artifact@v4'));
  assert.doesNotMatch(deploy.slice(0,deploy.indexOf('run: bash scripts/deploy-server.sh')),/continue-on-error/);
});
test('approval HOLD blocks image publishing before the exact-SHA check', () => {
  const workflow = readFileSync(join(root,'.github/workflows/v79-ci-cd.yml'),'utf8');
  const approval = workflow.slice(workflow.indexOf('\n  release-approval:'),workflow.indexOf('\n  deliver-container:'));
  const first = approval.match(/        run: \|\n((?:          .*\n)+)/);
  assert.ok(first,'Missing first release HOLD step');
  const script = first[1].replace(/^          /gm,'');
  const result = spawnSync('bash',['-s'],{input:script,encoding:'utf8',timeout:5000});
  assert.equal(result.status,78,result.stderr);
  assert.match(result.stderr,/BLOCKED: release HOLD/);
  assert.ok(approval.indexOf('exit 78') < approval.indexOf('REQUESTED_SHA:'));
  assert.doesNotMatch(approval.slice(0,approval.indexOf('exit 78')),/continue-on-error/);
});
