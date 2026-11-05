import {createHash} from 'node:crypto';
import {chatRoleRoster,resolveChatRole} from './chat-roles.js';
import {buildEvidenceLedger,verifySignedOwnerSnapshot} from './evidence.js';
import type {AgentContext} from './context.js';
const LIMITATIONS:Record<string,string[]>={
 ceo:['Commercial readiness requires separate owner acceptance.'],
 coo:['Task creation, draft delivery and owner acceptance are separate.'],
 finance:['Currency, bank reconciliation and payment authorisation are not established by aggregate counters.'],
 strategy:['Forecasts, market claims and launch acceptance need separate evidence.'],
 marketing:['Provider publication receipts and customer attribution need separate evidence.'],
 'customer-service':['Ticket details, customer messages and SLA compliance are not exposed by aggregate counters.'],
 'technical-security':['App counters do not attest host security, backups or incident delivery. Sentinel remains deferred.'],
 sales:['Lead consent, contact details and deal stages are not exposed by aggregate counters.'],
};
export function specialistIntegrationReport(snapshot:unknown,context:AgentContext,nowMs=Date.now()){
 verifySignedOwnerSnapshot(snapshot,context,nowMs);
 const roles=chatRoleRoster().map(role=>{
  const selected=resolveChatRole(role.id+':');
  const ledger=buildEvidenceLedger(snapshot,selected.specialist,nowMs);
  const sources=ledger.records.filter(r=>r.source!=='signed_platform_admin_stats');
  const available=sources.filter(r=>r.state==='available').length;
  return {id:role.id,name:role.name,systems:role.systems,skillSha:role.skillSha,
   mode:'read-only',approvalAuthority:'none',status:available===sources.length&&sources.length>0?'available':available?'partial':'unavailable',
   sources:sources.map(r=>({system:r.system,name:r.name,source:r.source,state:r.state,reportedAt:r.reportedAt,
    collectedAt:r.collectedAt,ageSeconds:r.ageSeconds,metricKeys:r.metrics.map(m=>m.key)})),
   limitations:LIMITATIONS[role.id],tools:['read_scoped_aggregate_evidence','prepare_advisory_review'],
   requiresOwnerApproval:['queue_specialist_review','accept_task_deliverable']};
 });
 const receiptSha256=createHash('sha256').update(JSON.stringify({collectedAt:snapshot.generatedAt,roles})).digest('hex');
 return {mode:'read-only',kind:'specialist-integration-report',collectedAt:snapshot.generatedAt,roles,receiptSha256,
  provenance:'Authenticated Hub snapshot; existing signed product-summary contracts. This receipt is a content digest, not independent source attestation.',
  evidenceGateway:{status:'managed-separately',reason:'Standalone authenticated MCP Gateway is separate from these Hub integrations.'}};
}
