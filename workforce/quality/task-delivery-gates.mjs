/**
 * V79 A05: read-only work-item lifecycle projection.
 * Source-only library; never submits a queue action or accepts an LLM's claims.
 * G2 create_work_item success plus authenticated task state confirms task creation,
 * NOT completed engineering. There is NO receiptSha256 in this operation.
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
 * verifyQueueRecord / verifyTaskRecord must validate the authentic G2
 * owner-MFA HMAC ledger, not a JSON field or a generative model response.
 * verifyDeliveryEvidence must independently verify owner acceptance/test evidence,
 * e.g. signed founder acceptance + pinned integration CI + source/runtime parity.
 */
export function projectWorkItem({
  job, taskRecord=null, deliveryEvidence=null, nowMs=Date.now(),
  organizationId, verifyQueueRecord, verifyTaskRecord, verifyDeliveryEvidence,
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
  // G2 createApprovedWorkItem stores result:{taskId,at} and a separate
  // tasks[] row. The receiptSha256 belongs to release jobs, NOT task creation.
  const createdAt=time(job.result?.at,nowMs);
  if (!ID.test(job.result?.taskId ?? '') || !Number.isFinite(createdAt))
    return result('blocked_uncertain','G2_TASK_CREATION_RESULT_MISSING');
  const taskAt=time(taskRecord?.createdAt,nowMs);
  if (!taskRecord || !trusted(verifyTaskRecord,taskRecord) ||
      !ID.test(taskRecord.id ?? '') || taskRecord.id!==job.result.taskId ||
      taskRecord.jobId!==job.id || taskRecord.organizationId!==organizationId ||
      taskRecord.system!==job.system || taskRecord.assignedTo!=='coo' ||
      taskRecord.status!=='open' || !Number.isFinite(taskAt) || taskAt!==createdAt)
    return result('blocked_uncertain','G2_TASK_ROW_UNVERIFIED');
  const created = result('work_item_created','ENGINEERING_OUTCOME_UNVERIFIED',{
    created:true,taskId:job.result.taskId,
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
      created:true,taskId:job.result.taskId,
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
export function summarizeDeliveryBoard({jobs,tasks=[],organizationId,verifyQueueRecord,verifyTaskRecord,verifyDeliveryEvidence,
  deliveryEvidenceByJobId={},nowMs=Date.now()}={}) {
  const unavailable = () => Object.freeze({mode:'read-only',state:'unavailable',
    totals:{awaiting:0,created:0,delivered:0,blocked:0},rows:[]});
  if (!Array.isArray(jobs) || jobs.length>200 || !jobs.every(j=>j&&typeof j==='object') ||
      !Array.isArray(tasks) || tasks.length>200 ||
      !tasks.every(t=>t&&typeof t==='object'&&ID.test(t.id??'')) ||
      new Set(tasks.map(t=>t.id)).size!==tasks.length ||
      !deliveryEvidenceByJobId || typeof deliveryEvidenceByJobId!=='object' ||
      Array.isArray(deliveryEvidenceByJobId)) return unavailable();
  const taskById=new Map(tasks.map(t=>[t.id,t]));
  const seen = new Set(), rows=[];
  for(const job of jobs) {
    if (!ID.test(job.id??'') || seen.has(job.id)) return unavailable();
    seen.add(job.id);
    const projected=projectWorkItem({
      job,taskRecord:taskById.get(job.result?.taskId)||null,
      verifyTaskRecord,deliveryEvidence:Object.prototype.hasOwnProperty.call(deliveryEvidenceByJobId,job.id) ?
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
