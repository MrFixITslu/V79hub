/**
 * Isolated V79 AI workforce evidence and cost gates, v1.
 * SOURCE-ONLY: not wired into live Hub or Sentinel. No I/O or side effects.
 * Caller must supply an independent trusted attestation verifier.
 */
export const METRICS = Object.freeze({
  hub: Object.freeze({ health_pass: ['bool', 'state'], backup_age_hours: ['range', 'hours', 0, 8760] }),
  tiquet: Object.freeze({ health_pass: ['bool', 'state'], overdue_p1_count: ['count', 'tickets', 0, 100000] }),
  marketing: Object.freeze({ failed_publications_count: ['count', 'posts', 0, 100000] }),
  ffpro: Object.freeze({ overdue_invoice_count: ['count', 'invoices', 0, 100000] }),
  academy: Object.freeze({ publish_failures_count: ['count', 'courses', 0, 100000] }),
  pos: Object.freeze({ health_pass: ['bool', 'state'] }),
  website: Object.freeze({ health_pass: ['bool', 'state'] }),
  sentinel: Object.freeze({ collector_fresh: ['bool', 'state'] }),
});
const ID = /^[a-z0-9][a-z0-9._:-]{0,95}$/i;
const OBSERVED = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const MAX_AGE_MS = 15 * 60 * 1000;
const verifiedSnapshots = new WeakSet();
const VALID_SKILLS = new Set(['finance', 'strategy', 'marketing', 'customer-service', 'technical-security', 'sales', 'ceo', 'coo']);
const owns = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const safeId = v => typeof v === 'string' && ID.test(v);
const when = v => typeof v === 'string' && OBSERVED.test(v) ? Date.parse(v) : NaN;
const isMoney = v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 10000;

function validRecord(r, nowMs, allowedSystems) {
  if (!r || typeof r !== 'object' || !owns(METRICS, r.system) ||
      !allowedSystems.includes(r.system) || !owns(METRICS[r.system], r.metric) ||
      r.scope !== 'v79-owned' || !safeId(r.sourceRef) || !safeId(r.collector) ||
      !Number.isFinite(when(r.observedAt))) return false;
  const age = nowMs - when(r.observedAt);
  if (age < -60000 || age > MAX_AGE_MS) return false;
  const [kind, unit, low, high] = METRICS[r.system][r.metric];
  if (r.unit !== unit || typeof r.value !== 'number' || !Number.isFinite(r.value)) return false;
  if (kind === 'bool') return r.value === 0 || r.value === 1;
  if (r.value < low || r.value > high) return false;
  return kind === 'count' ? Number.isSafeInteger(r.value) : true;
}

/**
 * Returns strictly projected records only; never echoes unknown source data.
 * verifyAttestation(record) must be a separately trusted verifier; neither a
 * JSON field claiming "verified" nor an AI judgment is sufficient.
 * Ambiguous duplicate system/metric readings are removed, not averaged.
 */
export function acceptWorkforceMetrics(records, { allowedSystems = ['hub', 'tiquet'], verifyAttestation, nowMs = Date.now() } = {}) {
  if (!Array.isArray(records) || records.length > 100 ||
      !Array.isArray(allowedSystems) || !allowedSystems.length ||
      allowedSystems.length > Object.keys(METRICS).length ||
      new Set(allowedSystems).size !== allowedSystems.length ||
      !allowedSystems.every(x => owns(METRICS, x)) ||
      typeof verifyAttestation !== 'function' || !Number.isFinite(nowMs)) {
    return { status: 'unavailable', records: [], unknownSystems: ['verification_unavailable'], rejected: 0 };
  }
  const keyed = new Map(), duplicates = new Set();
  let rejected = 0;
  for (const record of records) {
    if (!validRecord(record, nowMs, allowedSystems)) { rejected++; continue; }
    let approved = false;
    try { approved = verifyAttestation(record) === true; } catch { approved = false; }
    if (!approved) { rejected++; continue; }
    const key = record.system + ':' + record.metric;
    if (keyed.has(key)) { duplicates.add(key); rejected++; continue; }
    keyed.set(key, {
      id: key, system: record.system, metric: record.metric,
      value: record.value, unit: record.unit, observedAt: record.observedAt,
      sourceRef: record.sourceRef, collector: record.collector, scope: 'v79-owned',
    });
  }
  for (const key of duplicates) keyed.delete(key);
  const accepted = [...keyed.values()].sort((a,b)=>a.id.localeCompare(b.id));
  const systems = new Set(accepted.map(r=>r.system));
  const unknownSystems = allowedSystems.filter(s=>!systems.has(s));
  const snapshot = Object.freeze({
    status: accepted.length === 0 ? 'unavailable' : unknownSystems.length || rejected ? 'partial' : 'available',
    records: Object.freeze(accepted.map(r=>Object.freeze(r))),
    unknownSystems: Object.freeze(unknownSystems), rejected,
  });
  verifiedSnapshots.add(snapshot);
  return snapshot;
}

/** Draft owner alerts only: no network, delivery, ticket creation or queue mutation. */
export function proposeOwnerExceptions(snapshot) {
  if (!snapshot || !verifiedSnapshots.has(snapshot) || !['available','partial'].includes(snapshot.status) || !Array.isArray(snapshot.records)) return [];
  const alerts = [];
  for (const r of snapshot.records) {
    const isDown = r.metric === 'health_pass' && r.value === 0;
    const missingCollector = r.system === 'sentinel' && r.metric === 'collector_fresh' && r.value === 0;
    const backupRisk = r.system === 'hub' && r.metric === 'backup_age_hours' && r.value > 24;
    const highPriority = r.system === 'tiquet' && r.metric === 'overdue_p1_count' && r.value > 0;
    const failedPublication = r.system === 'marketing' && r.metric === 'failed_publications_count' && r.value > 0;
    const publishFailure = r.system === 'academy' && r.metric === 'publish_failures_count' && r.value > 0;
    if (!isDown && !missingCollector && !backupRisk && !highPriority && !failedPublication && !publishFailure) continue;
    if (!owns(METRICS, r.system) || !owns(METRICS[r.system], r.metric) ||
        !safeId(r.sourceRef) || !safeId(r.collector) || !Number.isFinite(when(r.observedAt)) ||
        typeof r.value !== 'number') continue;
    alerts.push({
      dedupKey: r.id + ':' + r.sourceRef, system: r.system, metric: r.metric,
      value: r.value, unit: r.unit, observedAt: r.observedAt,
      sourceRef: r.sourceRef, severity: (isDown || missingCollector || highPriority) ? 'attention' : 'watch',
      state: 'owner_review_only', delivered: false, executed: false,
    });
  }
  return alerts;
}

/** Check machine-structured claims, not arbitrary freeform prose. */
export function gateSpecialistOutput(draft, snapshot) {
  const fail = code => ({accepted:false,reason:code});
  if (!draft || !VALID_SKILLS.has(draft.skill) || draft.version !== '1.0.0' ||
      draft.mode !== 'analysis-only' || draft.actionsExecuted !== false ||
      draft.ownerApproved !== false || draft.customerDataIncluded !== false ||
      !Array.isArray(draft.claims) || draft.claims.length > 20 ||
      !Array.isArray(draft.proposals) || draft.proposals.length > 5 ||
      !draft.proposals.every(p=>p && p.state === 'owner_review_only' && safeId(p.id))) return fail('UNSAFE_OUTPUT');
  if (!snapshot || !verifiedSnapshots.has(snapshot) || !Array.isArray(snapshot.records)) return fail('UNVERIFIED_EVIDENCE');
  const byId = new Map(snapshot.records.map(r=>[r.id,r]));
  for (const c of draft.claims) {
    const r = byId.get(c?.evidenceId);
    if (!r || c.value !== r.value || c.unit !== r.unit ||
        c.observedAt !== r.observedAt || c.sourceRef !== r.sourceRef) return fail('UNSUPPORTED_CLAIM');
  }
  if (new Set(draft.claims.map(c=>c.evidenceId)).size !== draft.claims.length) return fail('DUPLICATE_CLAIM');
  return {accepted:true,reason:'VERIFIED_STRUCTURED_CLAIMS_ONLY',claims:draft.claims.length,proposals:draft.proposals.length};
}

/** Bounded local estimator; actual provider receipts must be independently validated. */
export function checkModelBudget({receipts, estimateUsd, budgetUsd=20, nowMs=Date.now(), receiptsComplete=false, verifyReceipt, verifyCompleteness}={}) {
  const block = reason=>({allowed:false,reason});
  if (!Array.isArray(receipts) || receipts.length>5000 || receiptsComplete!==true || typeof verifyReceipt!=='function' ||
      typeof verifyCompleteness!=='function' ||
      !isMoney(estimateUsd) || !isMoney(budgetUsd) || budgetUsd>20 || !Number.isFinite(nowMs))
    return block('BUDGET_EVIDENCE_UNAVAILABLE');
  // A claimed complete list is insufficient: the authoritative provider-side
  // usage inventory must be independently checked, including an empty month.
  let complete = false;
  try { complete = verifyCompleteness({receipts, windowStartMs:nowMs-30*24*3600_000, windowEndMs:nowMs})===true; }
  catch { complete = false; }
  if (!complete) return block('UNVERIFIED_USAGE_COMPLETENESS');
  let used = 0;
  const ids = new Set();
  for (const r of receipts) {
    if (!r || !safeId(r.id) || ids.has(r.id) || !isMoney(r.usd) ||
        !Number.isFinite(when(r.recordedAt))) return block('INVALID_RECEIPT');
    let authentic = false;
    try { authentic = verifyReceipt(r) === true; } catch { authentic = false; }
    if (!authentic) return block('UNVERIFIED_RECEIPT');
    ids.add(r.id);
    const age = nowMs - when(r.recordedAt);
    if (age < -60000) return block('FUTURE_RECEIPT');
    if (age < 30*24*3600_000) used += r.usd;
  }
  used = Math.round(used * 1000000) / 1000000;
  return {allowed:used+estimateUsd <= budgetUsd,reason:used+estimateUsd <= budgetUsd?'WITHIN_BUDGET':'BUDGET_CAP',
    usedUsd:used,estimatedAfterUsd:Math.round((used+estimateUsd)*1000000)/1000000,budgetUsd};
}
