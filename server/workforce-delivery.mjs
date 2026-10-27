import { summarizeDeliveryBoard } from '../workforce/quality/task-delivery-gates.mjs';

// Called only after ledger.read() authenticates the entire HMAC envelope.
// Membership in this exact snapshot is the trust boundary, never model fields.
export function projectAuthenticatedWorkDelivery(state, organizationId, nowMs = Date.now()) {
  if (!state) return { mode: 'read-only', state: 'unavailable',
    totals: {awaiting:0,created:0,delivered:0,blocked:0}, rows: [],
    window: 'latest-200-work-items', independentDeliveryVerification: 'not_configured' };
  const jobs = state.jobs.filter(j => j.organizationId === organizationId && j.operation === 'create_work_item').slice(-200);
  const taskIds = new Set(jobs.map(j => j.result?.taskId).filter(Boolean));
  const tasks = state.tasks.filter(t => t.organizationId === organizationId && taskIds.has(t.id));
  const trustedJobs = new Set(jobs), trustedTasks = new Set(tasks);
  const board = summarizeDeliveryBoard({ jobs, tasks, organizationId, nowMs,
    verifyQueueRecord: item => trustedJobs.has(item),
    verifyTaskRecord: item => trustedTasks.has(item),
    // No independent delivery attestor is installed. Never turn creation into delivery.
    verifyDeliveryEvidence: () => false,
  });
  return { ...board, window: 'latest-200-work-items', independentDeliveryVerification: 'not_configured' };
}
