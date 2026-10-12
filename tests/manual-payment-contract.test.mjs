import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { manualInvoiceEligibility, manualReceiptDecision, recentManualPaymentMfa } from "../server/manual-payment-contract.mjs";
import { accessDecision } from "../server/subscription-access.mjs";

const now = new Date("2026-10-10T12:00:00.000Z");
function fixture() {
  return {
    order: { id:"v79_synthetic_1", provider:"manual", sourceApp:"hub", kind:"subscription",
      organizationId:"synthetic-customer-org", amount:199, currency:"XCD", billingCycleAtOrder:"monthly",
      status:"pending", createdAt:now.toISOString() },
    plan: { organizationId:"synthetic-customer-org", planName:"V79 Service", status:"trial", accessPolicyType:"trial",
      billingCycle:"monthly", priceXcd:199, trialStartedAt:"2026-09-01T12:00:00.000Z",
      trialEndsAt:"2026-09-15T12:00:00.000Z" },
    organization: {id:"synthetic-customer-org", status:"active"},
    orders: [],
    bankReference:"ABC-TRANSFER-10001",
    evidenceNote:"I independently verified the cleared deposit on the bank statement.",
    receivedAmount:199,
    bankStatementVerified:true,
    confirmation:"CONFIRM v79_synthetic_1",
    now,
  };
}
test("priced trial and paid plans are invoice eligible, never internal owner", () => {
  assert.deepEqual(manualInvoiceEligibility(fixture().plan),{ok:true,amount:199,currency:"XCD",billingCycle:"monthly"});
  assert.equal(manualInvoiceEligibility(fixture().plan,true).code,"owner_workspace");
  for(const billingCycle of ["custom","weekly",undefined]) {
    assert.equal(manualInvoiceEligibility({...fixture().plan,billingCycle}).ok,false);
  }
  for(const priceXcd of [0,-1,null,undefined,NaN,Infinity]) {
    assert.equal(manualInvoiceEligibility({...fixture().plan,priceXcd}).ok,false);
  }
  for(const status of ["paused","cancelled"]) {
    assert.equal(manualInvoiceEligibility({...fixture().plan,status}).ok,false);
  }
});
test("a separately verified exact bank receipt produces one paid month", () => {
  const f=fixture(),r=manualReceiptDecision(f);
  assert.equal(r.ok,true);
  assert.equal(r.paidReference,"manual:ABC-TRANSFER-10001");
  assert.equal(r.paidThroughAt,"2026-11-10T12:00:00.000Z");
  const activated={...f.plan,status:"active",accessPolicyType:"paid",paidThroughAt:r.paidThroughAt};
  assert.equal(accessDecision(activated,now,false).allowed,true);
});
test("unverified customer claim cannot activate access", () => {
  const f=fixture();
  assert.equal(accessDecision(f.plan,now,false).allowed,false);
  for(const changed of [{bankReference:""},{evidenceNote:"Too short"},{confirmation:"yes"},
      {receivedAmount:198.99},{receivedAmount:199.01},{receivedAmount:198.999},{bankStatementVerified:false},{bankReference:"!"},{now:"invalid"}]) {
    assert.equal(manualReceiptDecision({...f,...changed}).ok,false);
  }
});
test("bank reference cannot be reused for any existing paid manual order", () => {
  const f=fixture();
  f.orders=[{id:"prior_other_customer",provider:"manual",providerTransactionId:"manual:abc-transfer-10001",status:"paid"}];
  assert.equal(manualReceiptDecision(f).code,"bank_reference_already_used");
});
test("provider cannot be substituted: WiPay and foreign source orders cannot be manually approved", () => {
  for(const delta of [{provider:"wipay"},{sourceApp:"academy"},{kind:"invoice"},
    {status:"paid"},{status:"failed"},{organizationId:"other_org"}]){
    const f=fixture();f.order={...f.order,...delta};
    assert.equal(manualReceiptDecision(f).ok,false);
  }
});
test("never grant a customer after the company is suspended or mismatched", () => {
  const f=fixture();
  assert.equal(manualReceiptDecision({...f,organization:{...f.organization,status:"suspended"}}).ok,false);
  assert.equal(manualReceiptDecision({...f,organization:{...f.organization,id:"another_org"}}).ok,false);
  assert.equal(manualReceiptDecision({...f,plan:{...f.plan,organizationId:"another_org"}}).ok,false);
});
test("plan drift, pricing changes and billing-cycle changes reject stale invoices", () => {
  const f=fixture();
  for(const delta of [{priceXcd:249},{billingCycle:"annual"},{status:"cancelled"},{billingCycle:"custom"}]){
    assert.equal(manualReceiptDecision({...f,plan:{...f.plan,...delta}}).code,"plan_changed");
  }
  assert.equal(manualReceiptDecision({...f,order:{...f.order,amount:198}}).code,"plan_changed");
  assert.equal(manualReceiptDecision({...f,order:{...f.order,currency:"USD"}}).code,"plan_changed");
});
test("verified annual period and already prepaid month extend from trusted paid-through date",()=>{
  const annual=fixture();annual.order.billingCycleAtOrder="annual";annual.plan.billingCycle="annual";
  assert.equal(manualReceiptDecision(annual).paidThroughAt,"2027-10-10T12:00:00.000Z");
  const prepaid=fixture();prepaid.plan.accessPolicyType="paid";prepaid.plan.paidThroughAt="2026-11-10T12:00:00.000Z";
  assert.equal(manualReceiptDecision(prepaid).paidThroughAt,"2026-12-10T12:00:00.000Z");
  const leap=fixture();leap.now=new Date("2028-01-31T12:00:00.000Z");
  assert.equal(manualReceiptDecision(leap).paidThroughAt,"2028-02-29T12:00:00.000Z");
});
test("manual routes require an authenticated biller and fresh administrator MFA",()=>{
  const source=readFileSync(new URL("../server.ts",import.meta.url),"utf8");
  assert.match(source,/app.post\("\/api\/billing\/manual\/request", requireAuth, requirePermission\("billing"\)/);
  assert.match(source,/app.get\("\/api\/admin\/billing\/manual\/orders", requireAuth, requirePlatformOperator, requireManualBillingMfa/);
  assert.match(source,/app.post\("\/api\/admin\/billing\/manual\/orders\/:orderId\/confirm", requireAuth, requirePlatformOperator, requireManualBillingMfa/);
  assert.match(source,/if \(order.provider !== "wipay"\) return redirect\("error", "wrong_payment_provider"/);
  assert.match(source,/manualOrderApprovalLocks\.has\(orderId\)/);
  assert.match(source,/app.post\("\/api\/admin\/billing\/manual\/orders\/:orderId\/reject", requireAuth, requirePlatformOperator, requireManualBillingMfa/);
  assert.match(source,/app.post\("\/api\/billing\/manual\/request", requireAuth, requirePermission\("billing"\), async \(req, res\) => \{\n  if \(!sameOriginMutation\(req\)\)/);
  assert.match(source,/manualBillingMutationBusy = true/);
  assert.match(source,/recentManualPaymentMfa\(session\)/);
});


test("bank reconciliation requires recent genuine MFA, not indefinitely renewed sessions", () => {
  const t=Date.parse("2026-10-10T12:00:00.000Z");
  assert.equal(recentManualPaymentMfa({mfaVerified:true,mfaVerifiedAt:t},t),true);
  assert.equal(recentManualPaymentMfa({mfaVerified:true,mfaVerifiedAt:t},t+15*60_000),true);
  assert.equal(recentManualPaymentMfa({mfaVerified:true,mfaVerifiedAt:t},t+15*60_000+1),false);
  assert.equal(recentManualPaymentMfa({mfaVerified:true,mfaVerifiedAt:t+1},t),false);
  assert.equal(recentManualPaymentMfa({mfaVerified:true},t),false);
  assert.equal(recentManualPaymentMfa({mfaVerified:false,mfaVerifiedAt:t},t),false);
  assert.equal(recentManualPaymentMfa(null,t),false);
});
