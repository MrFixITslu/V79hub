import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';

const MAX_AGE = 36 * 3600_000;
const enumValue = (value, allowed) => typeof value === 'string' && allowed.includes(value.toLowerCase()) ? value.toLowerCase() : null;
const timestamp = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value) ? Date.parse(value) : NaN;
const label = value => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,90}$/.test(value);

export function validatePythonBriefing(raw, nowMs = Date.now()) {
  const checked = timestamp(raw?.checkedAt), evidence = timestamp(raw?.report?.evidenceCollectedAt);
  const r = raw?.report;
  const priority = enumValue(r?.priority, ['attention','watch','routine']);
  const coverage = enumValue(r?.coverage, ['available','incomplete']);
  const storedState = enumValue(raw?.state, ['recorded','available','incomplete']);
  // Python persistence state is separate from evidence coverage.
  const state = storedState === 'recorded' ? coverage : storedState;
  if (raw?.schema !== 1 || !/^\d{4}-\d{2}-\d{2}-(?:morning|evening|manual-\d{6})$/.test(raw?.slot || '') ||
      !Number.isFinite(checked) || !Number.isFinite(evidence) || checked > nowMs + 120000 ||
      checked - evidence < -120000 || checked - evidence > 900000 ||
      !priority || !coverage || !state || r.noActionsExecuted !== true ||
      !Array.isArray(r.verifiedFindings) || r.verifiedFindings.length > 50 ||
      !Array.isArray(r.missingSources) || r.missingSources.length > 20) throw Error('Invalid Python briefing');
  const findings = r.verifiedFindings.map((f, index) => {
    const severity = enumValue(f?.severity, ['attention','watch','information']);
    if (!label(f?.system) || !label(f?.metric) || !severity || typeof f.value !== 'number' || !Number.isFinite(f.value)) throw Error('Invalid finding');
    return {id:`finding-${index}`,system:f.system,metric:f.metric,value:f.value,severity,reportedAt:r.evidenceCollectedAt};
  });
  const missingSources = r.missingSources.map(system => {
    if (!label(system)) throw Error('Invalid missing source');
    return system;
  });
  if (state !== coverage || (coverage === 'available' && missingSources.length)) throw Error('Contradictory coverage');
  return {slot:raw.slot,ranAt:raw.checkedAt,state,report:{collectedAt:r.evidenceCollectedAt,priority,coverage,findings,missingSources}};
}

export function createPythonBriefingStatus({ directory, now = () => new Date() }) {
  if (!path.isAbsolute(directory || '')) throw Error('Absolute report directory required');
  return async function readStatus() {
    const unavailable = {mode:'read-only',enabled:true,status:'unavailable',reports:[]};
    try {
      const dir = await fs.lstat(directory);
      if (!dir.isDirectory() || dir.isSymbolicLink() || (dir.mode & 0o077)) return unavailable;
      const files = (await fs.readdir(directory)).filter(name => /^\d{4}-\d{2}-\d{2}-(?:morning|evening|manual-\d{6})\.json$/.test(name));
      if (files.length > 500) return unavailable;
      const entries = [];
      for (const name of files) {
        const handle = await fs.open(path.join(directory,name), constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
        try {
          const stat = await handle.stat();
          if (!stat.isFile() || (stat.mode & 0o077) || stat.size > 100000) throw Error('Unsafe report');
          const buffer = Buffer.alloc(100001);
          const {bytesRead} = await handle.read(buffer,0,buffer.length,0);
          if (bytesRead > 100000) throw Error('Oversized report');
          const entry = validatePythonBriefing(JSON.parse(buffer.subarray(0,bytesRead).toString('utf8')), now().getTime());
          if (`${entry.slot}.json` !== name) throw Error('Slot mismatch');
          entries.push(entry);
        } finally { await handle.close(); }
      }
      entries.sort((a,b) => Date.parse(b.ranAt)-Date.parse(a.ranAt));
      const latest = entries[0];
      const stale = !latest || now().getTime()-Date.parse(latest.ranAt) >= MAX_AGE;
      return {mode:'read-only',enabled:true,status:stale?'stale_or_unavailable':latest.state==='available'?'report_available':'incomplete',
        timezone:'America/St_Lucia',slots:['08:00','19:00'],reports:entries.slice(0,12)};
    } catch { return unavailable; }
  };
}
