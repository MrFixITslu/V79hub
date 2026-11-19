import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const refs=JSON.parse(readFileSync('staging/acceptance-revisions.json','utf8'));
const workflow=readFileSync(refs.runtime_workflow,'utf8');
test('all eight application revisions are independently pinned',()=>{
  assert.deepEqual(Object.keys(refs.applications).sort(),['academy','ffpro','hub','marketing','pos','sentinel','tiquet','website']);
  for(const app of Object.values(refs.applications))assert.match(app.main_sha,/^[0-9a-f]{40}$/);
});
test('all five runtime image source refs match the acceptance manifest',()=>{
  for(const app of refs.runtime_scope){
    const revision=refs.applications[app];
    assert.ok(workflow.includes('service: '+app+'\n            repo: '+revision.repository+'\n            sha: '+revision.main_sha),app);
  }
  assert.match(workflow,/matrix\.service == 'hub' && github\.event\.pull_request\.head\.sha \|\| matrix\.sha/);
});
test('untested real runtime coverage and recovery are not promoted to pass',()=>{
  assert.deepEqual(refs.remaining_runtime_acceptance.sort(),['academy','sentinel','website']);
  assert.equal(refs.deployment_authorized,false);
  assert.equal(refs.recovery,'UNKNOWN');
  assert.match(workflow,/contents: read/);
  assert.doesNotMatch(workflow,/docker push|^\s*environment:\s*production|DEPLOY_SSH_KEY/m);
});
