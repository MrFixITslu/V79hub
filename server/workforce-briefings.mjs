import fs from 'node:fs/promises';
import path from 'node:path';

const ZONE = 'America/St_Lucia';
const HOURS = Object.freeze([8, 19]);
const MAX_AGE_MS = 36 * 60 * 60 * 1000;
const MAX_HISTORY = 20;

export function caribbeanSlot(now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(now).map(p => [p.type, p.value]));
  const hour = Number(parts.hour), minute = Number(parts.minute);
  const day = `${parts.year}-${parts.month}-${parts.day}`;
  return { day, hour, minute, slot: HOURS.includes(hour) && minute < 5 ? `${day}:${hour}` : null };
}

function safeReport(raw, collectedAt) {
  if (!raw || raw.mode !== 'read-only' || raw.state !== 'ceo-review-only' ||
      raw.executionEnabled !== false || raw.ownerApprovalGranted !== false ||
      !raw.cooReport || !Array.isArray(raw.cooReport.findings) || !raw.source) {
    throw Error('Executive evidence contract unavailable');
  }
  const timestamp = raw.source.collectedAt;
  const age = typeof timestamp === 'string' ? collectedAt - Date.parse(timestamp) : NaN;
  if (!Number.isFinite(age) || age < -120000 || age > 900000) {
    throw Error('Executive evidence outside freshness window');
  }
  const findings = raw.cooReport.findings.slice(0, 10).map(f => {
    if (!f || typeof f.id !== 'string' || !/^[a-z0-9:_-]{1,100}$/i.test(f.id) ||
        !['attention', 'watch', 'information'].includes(f.severity) ||
        !/^[a-z0-9_-]{2,32}$/i.test(f.system) ||
        typeof f.value !== 'number' || !Number.isFinite(f.value) ||
        typeof f.metric !== 'string' || !/^[a-zA-Z0-9_]{1,90}$/.test(f.metric)) {
      throw Error('Unexpected executive evidence field');
    }
    return { id: f.id, system: f.system, severity: f.severity,
      metric: f.metric, value: f.value, reportedAt: f.reportedAt };
  });
  const missing = Array.isArray(raw.cooReport.unavailableSources) ?
    raw.cooReport.unavailableSources.slice(0, 12).map(item => String(item?.system || 'unknown').slice(0, 30)) : [];
  return { collectedAt: timestamp, coverage: raw.source.coverage === 'available' && !missing.length ? 'available' : 'incomplete',
    priority: ['attention', 'watch', 'routine'].includes(raw.ceoReview?.priority) ? raw.ceoReview.priority : 'unknown',
    findings, missingSources: missing };
}

export function createWorkforceBriefings({ file, enabled, ownerReady, collect, now = () => new Date(),
  onError = () => {}, intervalMs = 60_000 }) {
  if (typeof file !== 'string' || !path.isAbsolute(file) ||
      typeof enabled !== 'function' || typeof ownerReady !== 'function' ||
      typeof collect !== 'function') throw Error('Invalid private briefing configuration');
  let busy = false, lastErrorAt = null, timer = null;
  const empty = () => ({ schema: 1, entries: [] });
  async function load() {
    try {
      const stat = await fs.lstat(file);
      if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o077) !== 0 || stat.size > 100_000) {
        throw Error('Unsafe briefing data file');
      }
      const obj = JSON.parse(await fs.readFile(file, 'utf8'));
      if (obj?.schema !== 1 || !Array.isArray(obj.entries) || obj.entries.length > MAX_HISTORY) {
        throw Error('Briefing data validation failed');
      }
      return obj;
    } catch (e) {
      if (e?.code === 'ENOENT') return empty();
      throw e;
    }
  }
  async function persist(next) {
    const dir = path.dirname(file);
    await fs.mkdir(dir, { recursive: true, mode: 0o700 });
    const stat = await fs.lstat(dir);
    if (!stat.isDirectory() || stat.isSymbolicLink() || (stat.mode & 0o077) !== 0) throw Error('Unsafe briefing directory');
    const temp = `${file}.tmp-${process.pid}`;
    try {
      await fs.writeFile(temp, JSON.stringify(next), { flag: 'wx', mode: 0o600 });
      await fs.rename(temp, file);
    } finally { await fs.unlink(temp).catch(() => {}); }
  }
  async function run(kind = 'scheduled') {
    if (busy || !enabled() || !ownerReady()) return { state: 'disabled_or_busy' };
    const at = now(), local = caribbeanSlot(at);
    const slot = kind === 'startup' ? `${local.day}:startup` : local.slot;
    if (!slot) return { state: 'not_due' };
    busy = true;
    try {
      const existing = await load();
      if (existing.entries.some(e => e.slot === slot)) return { state: 'already_complete' };
      const raw = await collect();
      const report = safeReport(raw, at.getTime());
      const entry = { slot, ranAt: at.toISOString(), state: report.coverage === 'available' ? 'available' : 'incomplete', report };
      const entries = [...existing.entries, entry].slice(-MAX_HISTORY);
      await persist({ schema: 1, entries });
      lastErrorAt = null;
      return { state: entry.state };
    } catch {
      lastErrorAt = at.toISOString();
      onError('WORKFORCE_BRIEFING_COLLECTION_FAILED');
      return { state: 'failed' };
    } finally { busy = false; }
  }
  async function status() {
    if (!enabled()) return { mode: 'read-only', enabled: false, status: 'disabled', reports: [] };
    try {
      const loaded = await load(), nowMs = now().getTime(), last = loaded.entries.at(-1);
      const healthy = last && nowMs - Date.parse(last.ranAt) < MAX_AGE_MS && !lastErrorAt;
      return { mode: 'read-only', enabled: true,
        status: healthy ? (last.state === 'available' ? 'report_available' : 'incomplete') : 'stale_or_unavailable',
        timezone: ZONE, slots: ['08:00', '19:00'],
        reports: loaded.entries.slice(-12).reverse(), lastFailureAt: lastErrorAt };
    } catch { return { mode: 'read-only', enabled: true, status: 'unavailable', reports: [] }; }
  }
  function start() {
    if (timer) return;
    void run('startup');
    timer = setInterval(() => { void run('scheduled'); }, intervalMs);
    timer.unref?.();
  }
  function stop() { if (timer) clearInterval(timer); timer = null; }
  return { run, status, start, stop };
}
