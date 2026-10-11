import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const guard = new URL('../scripts/verify-sentinel-preservation.sh', import.meta.url);
const deploy = new URL('../scripts/deploy-server.sh', import.meta.url);
const modules = ['sentinel-qa-routes.mjs', 'sentinel-qa-cleanup.mjs',
  'sentinel-write-fence.mjs', 'sentinel-audit-retention.mjs'];

// The PATH shim never invokes Docker or connects to a daemon.
const fakeDocker = `#!/usr/bin/env node
const args = process.argv.slice(2);
const scenario = process.env.RELEASE_GUARD_CASE;
if (args[0] === 'container' && args[1] === 'ls') {
  if (scenario === 'inventory-error') process.exit(1);
  console.log(scenario === 'new-install' ? 'another-container' :
    scenario === 'similar-name' ? 'v79-hub-old' : 'v79-hub');
} else if (args[0] === 'inspect') {
  if (scenario === 'inspect-error' || scenario === 'disappeared') process.exit(1);
  console.log(scenario === 'stopped' ? 'exited' : 'running');
} else if (args[0] === 'exec' && args[2] === 'test') {
  if (scenario === 'directory-error') process.exit(1);
} else if (args[0] === 'exec' && args[2] === 'sh') {
  if (scenario === 'exec-error-1') process.exit(1);
  if (scenario === 'exec-error-125') process.exit(125);
  process.stdout.write(scenario === 'modules-absent' ? 'absent' :
    scenario === 'invalid-result' ? 'unexpected' : 'present');
} else {
  console.error('Unexpected fake Docker command', args);
  process.exit(99);
}
`;

for (const [scenario, expected, includeModules] of [
  ['new-install', 0, false], ['similar-name', 0, false],
  ['inventory-error', 35, true], ['inspect-error', 35, true],
  ['disappeared', 35, true], ['stopped', 33, true],
  ['directory-error', 35, true], ['exec-error-1', 35, true],
  ['exec-error-125', 35, true], ['invalid-result', 35, true],
  ['modules-absent', 0, false], ['preserved', 0, true],
  ['missing-protected-module', 34, false],
]) {
  test(`release preservation: ${scenario}`, () => {
    const dir = mkdtempSync(join(tmpdir(), 'v79-release-guard-'));
    try {
      const stage = join(dir, 'stage');
      mkdirSync(join(stage, 'server'), { recursive: true });
      writeFileSync(join(stage, 'server.ts'), '// synthetic release source\n');
      if (includeModules) for (const file of modules) {
        writeFileSync(join(stage, 'server', file), '// synthetic protected module\n');
      }
      writeFileSync(join(dir, 'docker'), fakeDocker, { mode: 0o755 });
      const result = spawnSync('bash', [guard.pathname, stage, 'v79-hub'], {
        env: { ...process.env, PATH: `${dir}:${process.env.PATH}`,
          RELEASE_GUARD_CASE: scenario }, encoding: 'utf8', timeout: 10_000,
      });
      assert.ifError(result.error);
      assert.equal(result.status, expected, result.stdout + result.stderr);
    } finally { rmSync(dir, { recursive: true, force: true }); }
  });
}

test('deployment shell and embedded Node smoke payload parse without execution', () => {
  const shell = spawnSync('bash', ['-n', deploy.pathname], { encoding: 'utf8' });
  assert.equal(shell.status, 0, shell.stderr);
  const script = readFileSync(deploy, 'utf8');
  const payloads = [...script.matchAll(/<<'NODE'\n([\s\S]*?)\nNODE(?:\n|$)/g)];
  assert.equal(payloads.length, 1, 'Expected exactly one embedded Node payload');
  for (const [, payload] of payloads) {
    const result = spawnSync(process.execPath, ['--check', '--input-type=module'], {
      input: payload, encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr);
  }
});
