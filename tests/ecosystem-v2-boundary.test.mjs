import test from 'node:test';
import assert from 'node:assert/strict';
import { assertProductCustomerMapping, assertTenantEventBoundary,
  assertFinancialSource, assertApprovedAction, canCloseServiceTicket
} from '../server/ecosystem-v2-boundary.mjs';

const org = 'org-vision79-001';
const trusted = {organizationId: org, product: 'tiquet', localAccountId:'account-local-001',transportVerified:true};
const mapping = {organizationId: org, product:'tiquet',localAccountId:'account-local-001',customerRef:'customer-local-001'};
const event = {id:'9c38f417-178c-4abb-99fb-120866596778',version:1,organizationRef:org,type:'ticket.status_changed',occurredAt:'2026-11-11T04:00:00.000Z',payload:{status:'in_progress'}};
const invoice = {organizationId:org,source:'tiquet',kind:'invoice',recordId:'invoice-0001',currency:'XCD',amountMinor:12500,asOf:'2026-11-11T04:00:00.000Z'};
const approvedAction = {actionId:'action-1001',organizationId:org,type:'send_invoice'};
const context = {organizationId:org,actorId:'agent-1001',approvalFromLedger:true,nowMs:Date.parse('2026-11-11T04:00:00Z'),approval:{actionId:'action-1001',organizationId:org,type:'send_invoice',approvedBy:'owner-1001',status:'approved',digestVerified:true,expiresAt:'2026-11-11T04:15:00Z'}};

test('matching canonical organisation and account passes',()=>assert.equal(assertProductCustomerMapping(mapping,trusted).customerRef,mapping.customerRef));
test('customer mapping from another tenant fails closed',()=>assert.throws(()=>assertProductCustomerMapping({...mapping,organizationId:'org-other-tenant'},trusted),/customer_mapping/));
test('email-like customer names are never used as canonical mapping',()=>assert.throws(()=>assertProductCustomerMapping({...mapping,customerRef:''},trusted)));
test('product mismatch fails',()=>assert.throws(()=>assertProductCustomerMapping({...mapping,product:'pos'},trusted)));
test('verified, mapped event allowed',()=>assert.equal(assertTenantEventBoundary(event,trusted,mapping).organizationId,org));
test('unsigned transport event rejected',()=>assert.throws(()=>assertTenantEventBoundary(event,{...trusted,transportVerified:false},mapping)));
test('event from another organisation rejected',()=>assert.throws(()=>assertTenantEventBoundary({...event,organizationRef:'org-other-tenant'},trusted,mapping)));
test('event with unmapped account rejected',()=>assert.throws(()=>assertTenantEventBoundary(event,{...trusted,localAccountId:'other-account-01'},mapping)));
test('event payload containing email rejected',()=>assert.throws(()=>assertTenantEventBoundary({...event,payload:{email:'secret@example.com'}},trusted,mapping)));
test('event payload containing bearer token rejected',()=>assert.throws(()=>assertTenantEventBoundary({...event,payload:{access_token:'x'}},trusted,mapping)));
test('nested event payload rejected until explicitly approved',()=>assert.throws(()=>assertTenantEventBoundary({...event,payload:{details:{email:'secret@example.com'}}},trusted,mapping)));
test('PII-like event value rejected even under harmless key',()=>assert.throws(()=>assertTenantEventBoundary({...event,payload:{status:'user@example.com'}},trusted,mapping)));
test('malformed event identifier rejected',()=>assert.throws(()=>assertTenantEventBoundary({...event,id:'x'},trusted,mapping)));
test('Tiquet invoice records are allowed financial source',()=>assert.equal(assertFinancialSource(invoice,org).amountMinor,12500));
test('POS stock cost records allowed',()=>assert.equal(assertFinancialSource({...invoice,source:'pos',kind:'stock_cost'},org).source,'pos'));
test('FFPRO forecasts allowed as plans',()=>assert.equal(assertFinancialSource({...invoice,source:'ffpro',kind:'forecast'},org).kind,'forecast'));
test('FFPRO may not claim invoice ownership',()=>assert.throws(()=>assertFinancialSource({...invoice,source:'ffpro',kind:'invoice'},org)));
test('negative and fractional currency amounts rejected',()=>{assert.throws(()=>assertFinancialSource({...invoice,amountMinor:-1},org));assert.throws(()=>assertFinancialSource({...invoice,amountMinor:125.5},org));});
test('financial cross-tenant records rejected',()=>assert.throws(()=>assertFinancialSource(invoice,'org-other-tenant')));
test('WiPay records need a signed provider receipt',()=>assert.throws(()=>assertFinancialSource({...invoice,source:'wipay',kind:'provider_payment_event'},org)));
test('verified WiPay envelope is allowed for further reconciliation',()=>assert.equal(assertFinancialSource({...invoice,source:'wipay',kind:'provider_payment_event',providerStatus:'signature_verified'},org).source,'wipay'));
test('ledger-derived human approval allows bounded action',()=>assert.equal(assertApprovedAction(approvedAction,context).approvedBy,'owner-1001'));
test('missing or forged approval context fails',()=>assert.throws(()=>assertApprovedAction(approvedAction,{...context,approvalFromLedger:false})));
test('expired approval fails',()=>assert.throws(()=>assertApprovedAction(approvedAction,{...context,nowMs:Date.parse('2026-11-11T04:17:00Z')})));
test('cross-tenant approval fails',()=>assert.throws(()=>assertApprovedAction(approvedAction,{...context,approval:{...context.approval,organizationId:'org-other-tenant'}})));
test('unverified digest fails',()=>assert.throws(()=>assertApprovedAction(approvedAction,{...context,approval:{...context.approval,digestVerified:false}})));
test('self-approved financial actions fail',()=>assert.throws(()=>assertApprovedAction(approvedAction,{...context,actorId:'owner-1001'})));
test('unknown high-risk action fails closed',()=>assert.throws(()=>assertApprovedAction({...approvedAction,type:'auto_send_everything'},context)));
test('settled payment does not automatically close a service ticket',()=>{assert.equal(canCloseServiceTicket({deliveryAccepted:true,customerAcceptanceRecorded:false,outstandingActions:0}),false);assert.equal(canCloseServiceTicket({deliveryAccepted:true,customerAcceptanceRecorded:true,outstandingActions:1}),false);assert.equal(canCloseServiceTicket({deliveryAccepted:true,customerAcceptanceRecorded:true,outstandingActions:0}),true);});
