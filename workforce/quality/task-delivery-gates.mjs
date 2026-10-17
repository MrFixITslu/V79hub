/**
 * V79 A05: read-only work-item lifecycle projection.
 * Source-only library; never submits a queue action or accepts an LLM's claims.
 * G2 create_work_item success confirms task creation, NOT completed engineering.
 */
const SHA256 = /^[a-f0-9]{64}$/;
const SHA1 = /^[a-f0-9]{40}$/;
const ID = /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/;
const UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const STATES = new Set(['pending','approved','running','succeeded','failed','rejected','cancelled','uncertain']);
const SYSTEMS = new Set(['hub','tiquet','marketing','ffpro','pos','academy','website','games','sentinel','lasertag']);

function trusted(verifier, item) {
  if (typeof verifier !== 'function') return false;
  try { return verifier(item) === true; } catch { return false; }
}
function time(value, now) {
  if (typeof value !== 'string' || !UTC.test(value)) return NaN;
  const t = Date.parse(value);
  return Number.isFinite(t) && t <= now + 60_000 ? t : NaN;
}
const noTask = (state, reason) => Object.freeze({
  mode:'read-only',state,reason,created:false,delivered:false,
  jobId:null,taskId:null,system:null,evidenceRef:null,
});

/**
 * verifyQueueRecord must verify authentic owner-MFA queue provenance and scope,
 * NOT trust a JSON flag from the record or a generative model response.
 * verifyDeliveryEvidence must independently verify owner acceptance/test evidence,
 * e.g. signed founder acceptance + pinned integration CI + source/runtime parity.
 */
export function projectWorkItem({
  job, deliveryEvidence=null, nowMs=Date.now(),
  organizationId, verifyQueueRecord, verifyDeliveryEvidence,
}={}) {
  if (!Number.isFinite(nowMs) || typeof organizationId !== 'string' || !ID.test(organizationId))
    return noTask('unknown','NO_AUTHORIZED_OWNER_SCOPE');
  if (!job || !trusted(verifyQueueRecord,job) || job.operation!=='create_work_item' ||
      !ID.test(job.id ?? '') || !SHA256.test(job.digest ?? '') ||
      !SYSTEMS.has(job.system) || job.organizationId!==organizationId ||
      !STATES.has(job.status) || !Number.isSafeInteger(job.revision) || job.revision<0)
    return noTask('unknown','UNTRUSTED_OR_UNSUPPORTED_QUEUE');
  const base = {
    mode:'read-only',jobId:job.id,system:job.system,
    created:false,delivered:false,taskId:null,evidenceRef:null,
  };
  const result = (state,reason,extra={}) => Object.freeze({...base,state,reason,...extra});
  switch(job.status) {
    case 'pending': return result('awaiting_approval','OWNER_MFA_APPROVAL_REQUIRED');
    case 'approved': return result('awaiting_execution','APPROVED_ACTION_NOT_EXECUTED');
    case 'running': return result('execution_unconfirmed','WORKER_RECEIPT_PENDING');
    case 'rejected': return result('rejected','OWNER_DENIED_ACTION');
    case 'cancelled': return result('cancelled','ACTION_CANCELLED');
    case 'failed': return result('failed','ACTION_FAILED_NO_DELIVERY');
    case 'uncertain': return result('blocked_uncertain','RECONCILE_BEFORE_RETRY');
  }
  // Only a succeeded G2 create_work_item can be described as task created.
  if (!job.result || !ID.test(job.result.taskId ?? '') ||
      !SHA256.test(job.result.receiptSha256 ?? ''))
    return result('blocked_uncertain','CREATION_RECEIPT_MISSING');
  const created = result('work_item_created','ENGINEERING_OUTCOME_UNVERIFIED',{
    created:true,taskId:job.result.taskId,
    evidenceRef:job.result.receiptSha256,
  });
  if (!deliveryEvidence) return created;
  const d = deliveryEvidence;
  if (!trusted(verifyDeliveryEvidence,d) ||
      d.jobId!==job.id || d.taskId!==job.result.taskId || d.actionDigest!==job.digest ||
      d.organizationId!==organizationId || d.system!==job.system ||
      d.state!=='owner_accepted' || d.scope!=='v79-owned' ||
      !SHA1.test(d.commitSha ?? '') || !ID.test(d.independentTestRef ?? '') ||
      !ID.test(d.acceptanceRef ?? '') || !Number.isFinite(time(d.acceptedAt,nowMs)))
    return result('delivery_unverified','DELIVERY_PROOF_REJECTED',{
      created:true,taskId:job.result.taskId,evidenceRef:job.result.receiptSha256,
    });
  return result('delivery_verified','OWNER_ACCEPTED_INDEPENDENT_DELIVERY',{
    created:true,delivered:true,taskId:job.result.taskId,
    evidenceRef:d.acceptanceRef,
  });
}

/**
 * Returns only aggregate counts; does not import user task descriptions or
 * customer data. If any queue snapshot fails verification, do not assert totals.
 */
export function summarizeDeliveryBoard({jobs,organizationId,verifyQueueRecord,verifyDeliveryEvidence,
  deliveryEvidenceByJobId={},nowMs=Date.now()}={}) {
  const unavailable = () => Object.freeze({mode:'read-only',state:'unavailable',
    totals:{awaiting:0,created:0,delivered:0,blocked:0},rows:[]});
  if (!Array.isArray(jobs) || jobs.length>200 || !jobs.every(j=>j&&typeof j==='object') ||
      !deliveryEvidenceByJobId || typeof deliveryEvidenceByJobId!=='object' ||
      Array.isArray(deliveryEvidenceByJobId)) return unavailable();
  const seen = new Set(), rows=[];
  for(const job of jobs) {
    if (!ID.test(job.id??'') || seen.has(job.id)) return unavailable();
    seen.add(job.id);
    const projected=projectWorkItem({
      job,deliveryEvidence:Object.prototype.hasOwnProperty.call(deliveryEvidenceByJobId,job.id) ?
        deliveryEvidenceByJobId[job.id] : null,
      organizationId,verifyQueueRecord,verifyDeliveryEvidence,nowMs,
    });
    if(projected.state==='unknown') return unavailable();
    rows.push(projected);
  }
  const totals={awaiting:0,created:0,delivered:0,blocked:0};
  for (const row of rows) {
    if (row.delivered) totals.delivered++;
    else if (row.created) totals.created++;
    else if (['blocked_uncertain','delivery_unverified','failed'].includes(row.state)) totals.blocked++;
    else if (['awaiting_approval','awaiting_execution','execution_unconfirmed'].includes(row.state)) totals.awaiting++;
  }
  return Object.freeze({mode:'read-only',state:'verified_queue_projection',
    totals:Object.freeze(totals),rows:Object.freeze(rows)});
}
