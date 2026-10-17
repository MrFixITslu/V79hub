import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { caribbeanSlot, createWorkforceBriefings } from '../server/workforce-briefings.mjs';

const report = () => ({ mode: 'read-only', state: 'ceo-review-only', executionEnabled: false, ownerApprovalGranted: false,
  source: { collectedAt: '2026-10-16T12:00:00.000Z', coverage: 'available' },
  ceoReview: { priority: 'routine' }, cooReport: { findings: [], unavailableSources: [] } });
const at = () => new Date('2026-10-16T12:00:00.000Z');
test('Saint Lucia slots do not shift during North American daylight saving', () => {
  assert.equal(caribbeanSlot(at()).slot, '2026-10-16:8');
  assert.equal(caribbeanSlot(new Date('2026-01-16T23:00:00Z')).slot, '2026-01-16:19');
});
test('private briefing store, deduplication, and owner gate', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'v79-workforce-'));
  try {
    let calls = 0;
    const w = createWorkforceBriefings({file:path.join(dir,'reports.json'), enabled:()=>true, ownerReady:()=>true, now:at,
      collect:async()=>{calls++;return report()}});
    assert.equal((await w.run('startup')).state,'available');
    assert.equal((await w.run('startup')).state,'already_complete');
    assert.equal(calls,1);
    assert.equal((await fs.stat(path.join(dir,'reports.json'))).mode & 0o077,0);
    assert.equal((await w.status()).reports.length,1);
    const blocked = createWorkforceBriefings({file:path.join(dir,'never.json'), enabled:()=>true, ownerReady:()=>false, now:at,
      collect:async()=>{throw Error('must not call')}});
    assert.equal((await blocked.run('startup')).state,'disabled_or_busy');
  } finally { await fs.rm(dir,{recursive:true,force:true}); }
});
test('injection, stale data, and agent action claims fail closed', async () => {
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'v79-workforce-'));
  try {
    const w=createWorkforceBriefings({file:path.join(dir,'r.json'),enabled:()=>true,ownerReady:()=>true,now:at,
      collect:async()=>({...report(), executionEnabled:true})});
    assert.equal((await w.run('startup')).state,'failed');
    assert.equal((await w.status()).status,'stale_or_unavailable');
    assert.equal((await w.status()).reports.length,0);
  } finally { await fs.rm(dir,{recursive:true,force:true}); }
});
test('saved history rejects corrupt, future, duplicate and contradictory records', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'v79-history-'));
  const file = path.join(dir, 'r.json');
  try {
    const w = createWorkforceBriefings({file, enabled:()=>true, ownerReady:()=>true, now:at, collect:async()=>report()});
    await w.run('startup');
    const valid = JSON.parse(await fs.readFile(file, 'utf8'));
    for (const mutate of [
      x => { x.entries[0].ranAt = '2027-01-01T00:00:00Z'; },
      x => { x.entries[0].report.findings = [{ id: 'injection' }]; },
      x => { x.entries.push(x.entries[0]); },
      x => { x.entries[0].state = 'incomplete'; },
    ]) {
      const corrupted = structuredClone(valid); mutate(corrupted);
      await fs.writeFile(file, JSON.stringify(corrupted), {mode:0o600});
      const status = await w.status();
      assert.equal(status.status, 'unavailable');
      assert.deepEqual(status.reports, []);
    }
    await fs.writeFile(file, JSON.stringify(valid));
    assert.equal((await w.status()).status, 'report_available');
  } finally { await fs.rm(dir, {recursive:true,force:true}); }
});
test('untrusted extra fields and reported timestamps never leave saved history', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'v79-fields-'));
  const file = path.join(dir, 'r.json');
  try {
    const raw = report();
    raw.cooReport.findings = [{id:'fault',system:'hub',severity:'watch',metric:'faults',value:1,reportedAt:{secret:'INJECTED'}}];
    raw.cooReport.unavailableSources = [{system:'<script>INJECTED</script>'}];
    const w = createWorkforceBriefings({file, enabled:()=>true, ownerReady:()=>true, now:at, collect:async()=>raw});
    assert.equal((await w.run('startup')).state, 'incomplete');
    const saved = JSON.parse(await fs.readFile(file, 'utf8'));
    saved.entries[0].secret = 'INJECTED';
    saved.entries[0].report.secret = 'INJECTED';
    await fs.writeFile(file, JSON.stringify(saved));
    const status = await w.status();
    assert.equal(status.status, 'incomplete');
    assert.equal(JSON.stringify(status).includes('INJECTED'), false);
    assert.equal(status.reports[0].report.findings[0].reportedAt, raw.source.collectedAt);
  } finally { await fs.rm(dir, {recursive:true,force:true}); }
});
test('missing source coverage and oversized evidence cannot produce a healthy briefing', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'v79-coverage-'));
  try {
    for (const [index, mutate] of [
      r => { delete r.cooReport.unavailableSources; },
      r => { r.cooReport.findings = Array(11).fill({id:'fault',system:'hub',severity:'watch',metric:'faults',value:1}); },
      r => { r.cooReport.unavailableSources = Array(13).fill({system:'hub'}); },
      r => { r.source.collectedAt = '2026-10-16T11:00:00Z'; },
    ].entries()) {
      const raw = report(); mutate(raw);
      const w = createWorkforceBriefings({file:path.join(dir,`${index}.json`),enabled:()=>true,ownerReady:()=>true,now:at,
        collect:async()=>raw,onError:()=>{throw Error('logger unavailable')}});
      assert.equal((await w.run('startup')).state, 'failed');
      assert.deepEqual((await w.status()).reports, []);
    }
  } finally { await fs.rm(dir,{recursive:true,force:true}); }
});
test('owner readiness revocation prevents both collection and report disclosure', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'v79-revoke-'));
  try {
    let ready = true, calls = 0;
    const w = createWorkforceBriefings({file:path.join(dir,'r.json'), enabled:()=>true,ownerReady:()=>ready,now:at,
      collect:async()=>{calls++;return report()}});
    assert.equal((await w.run('startup')).state,'available');
    ready = false;
    assert.deepEqual((await w.status()).reports,[]);
    assert.equal((await w.run()).state,'disabled_or_busy');
    assert.equal(calls,1);
  } finally { await fs.rm(dir,{recursive:true,force:true}); }
});
test('restart preserves scheduled deduplication and expired reports remain visibly stale', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'v79-restart-'));
  try {
    let clock = at(), calls = 0;
    const options = {file:path.join(dir,'r.json'),enabled:()=>true,ownerReady:()=>true,now:()=>clock,
      collect:async()=>{calls++;return report()}};
    assert.equal((await createWorkforceBriefings(options).run()).state,'available');
    const restarted = createWorkforceBriefings(options);
    assert.equal((await restarted.run()).state,'already_complete');
    assert.equal(calls,1);
    clock = new Date('2026-10-18T12:00:00Z');
    assert.equal((await restarted.status()).status,'stale_or_unavailable');
    assert.equal((await restarted.status()).reports.length,1);
  } finally { await fs.rm(dir,{recursive:true,force:true}); }
});
