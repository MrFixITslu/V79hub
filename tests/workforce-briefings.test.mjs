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
