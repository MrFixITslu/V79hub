import { createHash } from 'node:crypto';
import { claimWork, finishWork, workDigest } from './workforce-actions.mjs';
import { GOOGLE_OPERATIONS } from './workforce-google.mjs';

/** Host-only entry point; no HTTP mount or scheduler is enabled by importing it.
 * ledger must be the existing durable G2 ledger; context comes from host config,
 * never from email, model output, or browser parameters. */
export async function runGoogleWorkOnce({ ledger, client, enabled, ownerOrganizationId, storeReceipt, jobId = null, now = Date.now }) {
  if (!enabled() || !ownerOrganizationId || typeof storeReceipt !== 'function') return { status:'disabled' };
  const worker = 'v79-google-worker';
  const job = await ledger.transact(state => claimWork(state, {
    organizationId:ownerOrganizationId, worker, operations:GOOGLE_OPERATIONS, systems:['gmail','calendar'], jobId, now:now(),
  }));
  if (!job) return {status:'idle'};
  let status = 'failed', providerReceipt = null, code = 'GOOGLE_AUTHORIZATION_EXPIRED';
  try {
    const state = await ledger.read();
    const current = state.jobs.find(j=>j.id===job.id && j.organizationId===ownerOrganizationId);
    const request = Object.fromEntries(['operation','system','summary','payload','idempotencyKey'].map(k=>[k,job[k]]));
    if (!enabled() || state.paused || current?.status!=='running' || current.claim?.token!==job.claim.token ||
        current.digest!==workDigest(request) || current.approval?.digest!==current.digest || !(Date.parse(current.approval?.expiresAt)>now())) throw new Error(code);
    providerReceipt = await client.execute(job);
    status = 'succeeded'; code = 'GOOGLE_RECEIPT_AVAILABLE';
  } catch (error) {
    status = error?.uncertain ? 'uncertain' : 'failed';
    // Do not place provider errors, tokens, message bodies or attendees in audit events.
    code = /^GOOGLE_[A-Z_]+$/.test(error?.code || '') ? error.code : 'GOOGLE_EXECUTION_REJECTED';
  }
  const receipt = { jobId:job.id, digest:job.digest, status, code, providerReceipt, at:new Date(now()).toISOString() };
  // Durable receipt BEFORE final status. If storage fails, leave running for manual reconciliation.
  // Do not auto-reclaim or retry running, failed or uncertain jobs.
  await storeReceipt(receipt);
  const receiptSha256 = createHash('sha256').update(JSON.stringify(receipt)).digest('hex');
  await ledger.transact(state => finishWork(state, job.id, {
    claimToken:job.claim.token,digest:job.digest,status,receiptSha256,
  }, {organizationId:ownerOrganizationId,worker,now:now()}));
  return { jobId:job.id,status,code };
}

