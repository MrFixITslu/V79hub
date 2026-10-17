import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const root = new URL('../workforce/skills/', import.meta.url);
const load = async name => readFile(new URL(name,root),'utf8');
const catalog = JSON.parse(await load('catalog.json'));
const evals = JSON.parse(await load('adversarial-evals.json'));

test('specialist and CEO/COO skills are versioned, distinct and draft-only', async()=>{
  assert.equal(catalog.schema,1);
  assert.equal(catalog.version,'1.0.0');
  assert.equal(catalog.specialists.length,6);
  assert.equal(catalog.orchestrators.length,2);
  assert.equal(new Set(catalog.allSkills).size,8);
  assert.deepEqual(catalog.allowedEffects,[]);
  assert.deepEqual(catalog.commercialScope,['hub','tiquet']);
  assert.equal(catalog.ownerFinalAuthority,true);
  for(const id of catalog.allSkills){
    const text=await load(id+'/SKILL.md');
    assert.ok(text.includes('**Skill ID:** '+id),id);
    assert.ok(text.includes('**Version:** 1.0.0'),id);
    assert.match(text,/(unknown|unavailable|stale)/i,id);
    assert.match(text,/(owner approval|founder approve|owner controls|owner-approved|founder retains|owner final)/i,id);
    assert.match(text,/(never|no auto-|no privileged|non-negotiable)/i,id);
    assert.match(text,/(acceptance|evaluation)/i,id);
  }
});
test('model adversarial suite covers all roles and risky execution/PII/source spoofing cases',()=>{
  assert.equal(evals.schema,1);
  assert.equal(evals.version,catalog.version);
  assert.equal(new Set(evals.cases.map(c=>c.id)).size,evals.cases.length);
  assert.ok(evals.cases.length >= 10);
  for(const id of catalog.allSkills)assert.ok(evals.cases.some(c=>c.skill===id),id);
  for(const e of evals.cases){
    assert.ok(catalog.allSkills.includes(e.skill));
    assert.match(e.id,/^[a-z0-9-]{4,32}$/);
    assert.ok(e.input.length>=20);
    assert.ok(e.expected.length>=2);
    assert.ok(e.forbidden.length>=1);
    assert.ok(e.expected.every(s=>typeof s==='string'&&s.length>=10));
  }
  const suite=evals.cases.map(c=>c.input).join(' ');
  for(const x of ['tenant','Sandbox','TikTok','secret scan','credential','spend receipts']) assert.ok(suite.toLowerCase().includes(x.toLowerCase()),x);
});
test('catalog does not introduce external side-effect permissions',()=>{
  assert.equal(catalog.mode,'analysis-and-draft');
  assert.equal(catalog.requiresIndependentRuntimeAcceptance,true);
  assert.ok(catalog.modelBudgetUsd30d<=20);
  assert.equal(JSON.stringify(catalog).includes('password'),false);
});
