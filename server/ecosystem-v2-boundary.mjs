/**
 * V79 ecosystem v2 — fail-closed, pure contract validation primitives.
 * DRAFT / NON-RUNTIME: these functions are not wired to a production route.
 * The caller MUST obtain actor, organisation, and transport verification from
 * authenticated server-side state; never accept them from browser/request JSON.
 */
const ORG = /^[A-Za-z0-9._:@-]{8,180}$/;
const ID = /^[A-Za-z0-9._:@-]{4,180}$/;
const EVENT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const CURRENCY = /^[A-Z]{3}$/;
const ALLOWED_PRODUCTS = new Set(['tiquet', 'pos', 'marketing', 'academy', 'sentinel', 'ffpro']);
const HIGH_RISK = new Set([
  'send_invoice', 'confirm_payment', 'close_ticket', 'change_contract_scope',
  'send_customer_message', 'publish_campaign', 'commit_stock_issue',
  'deploy_release', 'change_access', 'delete_customer_data',
]);
const FINANCIAL_OWNERSHIP = Object.freeze({
  tiquet: new Set(['invoice', 'invoice_draft', 'service_expense']),
  pos: new Set(['stock_cost', 'sales_total', 'stock_movement']),
  wipay: new Set(['provider_payment_event']),
  ffpro: new Set(['budget', 'forecast']),
});
function fail(message) { throw new Error(`V79_BOUNDARY:${message}`); }
function validId(value, pattern = ID) { return typeof value === 'string' && pattern.test(value); }
function safeFlatPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).length > 24) return false;
  for (const [key, value] of Object.entries(payload)) {
    if (!/^[A-Za-z][A-Za-z0-9_]{0,55}$/.test(key) ||
        /password|secret|token|email|phone|address|bank|card|private|access_key/i.test(key) ||
        (value !== null && typeof value === 'object') ||
        !['string', 'number', 'boolean'].includes(typeof value) && value !== null ||
        (typeof value === 'string' && (value.length > 180 || /@|bearer\s+|https?:\/\//i.test(value))) ||
        (typeof value === 'number' && !Number.isFinite(value))) return false;
  }
  return true;
}
function exactKeys(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join('|') === [...keys].sort().join('|');
}

/** Never merge customer records solely on email or business name. */
export function assertProductCustomerMapping(mapping, trusted) {
  if (!trusted || !validId(trusted.organizationId, ORG) ||
      !validId(trusted.localAccountId) ||
      !ALLOWED_PRODUCTS.has(trusted.product) ||
      !mapping || typeof mapping !== 'object' || Array.isArray(mapping) ||
      mapping.organizationId !== trusted.organizationId ||
      mapping.product !== trusted.product ||
      mapping.localAccountId !== trusted.localAccountId ||
      !validId(mapping.customerRef)) fail('customer_mapping_mismatch');
  return Object.freeze({
    organizationId: trusted.organizationId,
    product: trusted.product,
    localAccountId: trusted.localAccountId,
    customerRef: mapping.customerRef,
  });
}

/** Existing Tiquet outbound event envelope shape; verification is external. */
export function assertTenantEventBoundary(event, trusted, mapping) {
  if (!trusted?.transportVerified || !validId(trusted.organizationId, ORG) ||
      !ALLOWED_PRODUCTS.has(trusted.product) || !validId(trusted.localAccountId) ||
      !event || typeof event !== 'object' || Array.isArray(event) ||
      !validId(event.id, EVENT_ID) || event.version !== 1 ||
      !validId(event.organizationRef, ORG) ||
      event.organizationRef !== trusted.organizationId ||
      !validId(event.type) || !Number.isFinite(Date.parse(event.occurredAt)))
    fail('invalid_or_cross_tenant_event');
  assertProductCustomerMapping(mapping, trusted);
  const payload = event.payload;
  if (!safeFlatPayload(payload) || JSON.stringify(payload).length > 2048)
    fail('event_payload_disclosure');
  return Object.freeze({
    eventId: event.id,
    organizationId: trusted.organizationId,
    product: trusted.product,
    type: event.type,
    occurredAt: event.occurredAt,
  });
}

/**
 * Establish source-of-truth ownership, not the validity of a financial entry.
 * Money is an integer in minor units; payment settlement needs a separate,
 * verified provider receipt and idempotent ledger write.
 */
export function assertFinancialSource(input, trustedOrganizationId) {
  const owner = FINANCIAL_OWNERSHIP[input?.source];
  if (!validId(trustedOrganizationId, ORG) || !owner || !owner.has(input?.kind) ||
      input.organizationId !== trustedOrganizationId ||
      !validId(input.recordId) || !validId(input.currency, CURRENCY) ||
      !Number.isSafeInteger(input.amountMinor) || input.amountMinor < 0 ||
      !Number.isFinite(Date.parse(input.asOf))) fail('financial_source_untrusted');
  if (input.source === 'wipay' && input.providerStatus !== 'signature_verified')
    fail('payment_receipt_unverified');
  if (input.source === 'ffpro' && !['budget', 'forecast'].includes(input.kind))
    fail('ffpro_not_accounting');
  return Object.freeze({
    organizationId: input.organizationId,
    source: input.source, kind: input.kind, recordId: input.recordId,
    currency: input.currency, amountMinor: input.amountMinor, asOf: input.asOf,
  });
}

/**
 * Allow-list only. Approvals must already have been resolved from the
 * authoritative server-side ledger and their request digest verified there.
 */
export function assertApprovedAction(action, trusted) {
  if (!trusted || !validId(trusted.organizationId, ORG) ||
      !validId(trusted.actorId) || !action ||
      !validId(action.actionId) || !validId(action.organizationId, ORG) ||
      action.organizationId !== trusted.organizationId ||
      typeof action.type !== 'string' || !HIGH_RISK.has(action.type) ||
      trusted.approvalFromLedger !== true ||
      !exactKeys(trusted.approval, ['actionId', 'organizationId', 'type', 'approvedBy', 'status', 'digestVerified', 'expiresAt']) ||
      trusted.approval.actionId !== action.actionId ||
      trusted.approval.organizationId !== trusted.organizationId ||
      trusted.approval.type !== action.type ||
      trusted.approval.status !== 'approved' ||
      trusted.approval.digestVerified !== true ||
      !validId(trusted.approval.approvedBy) ||
      !Number.isFinite(trusted.nowMs) ||
      !(Date.parse(trusted.approval.expiresAt) > trusted.nowMs))
    fail('action_approval_missing_or_invalid');
  if (['confirm_payment', 'send_invoice', 'change_contract_scope', 'delete_customer_data', 'deploy_release'].includes(action.type) &&
      trusted.approval.approvedBy === trusted.actorId)
    fail('self_approval_rejected');
  return Object.freeze({ actionId: action.actionId, type: action.type,
    organizationId: trusted.organizationId, approvedBy: trusted.approval.approvedBy });
}

/** Payment does not imply delivery acceptance or ticket completion. */
export function canCloseServiceTicket({deliveryAccepted, customerAcceptanceRecorded, outstandingActions}) {
  return deliveryAccepted === true && customerAcceptanceRecorded === true &&
    Number.isSafeInteger(outstandingActions) && outstandingActions === 0;
}
