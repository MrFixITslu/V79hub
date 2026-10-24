import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const server = fs.readFileSync(new URL("../server.ts", import.meta.url), "utf8");
const billing = fs.readFileSync(new URL("../src/components/WorkspaceBilling.tsx", import.meta.url), "utf8");
const admin = fs.readFileSync(new URL("../src/components/PlatformPlansAdmin.tsx", import.meta.url), "utf8");
const reconcile = fs.readFileSync(new URL("../src/components/PlatformManualPaymentsAdmin.tsx", import.meta.url), "utf8");

test("non-WiPay Hub billing pages expose customer invoice request and owner reconciliation",()=>{
  assert.match(billing,/manualPaymentAvailable\?: boolean/);
  assert.match(billing,/fetch\("\/api\/billing\/manual\/request"/);
  assert.match(billing,/Request bank-transfer invoice/);
  assert.match(admin,/import \{ PlatformManualPaymentsAdmin \}/);
  assert.match(admin,/<PlatformManualPaymentsAdmin \/>/);
  assert.match(reconcile,/\/api\/admin\/billing\/manual\/orders/);
});

test("manual invoice request remains authenticated and cannot confirm payment",()=>{
  assert.match(server,/app\.post\("\/api\/billing\/manual\/request", requireAuth, requirePermission\("billing"\)/);
  const start=server.indexOf('app.post("/api/billing/manual/request"');
  const end=server.indexOf('app.get("/api/admin/billing/manual/orders"',start);
  assert(start>=0&&end>start);
  const request=server.slice(start,end);
  assert.match(request,/sameOriginMutation\(req\)/);
  assert.match(request,/status: "pending"/);
  assert.doesNotMatch(request,/status: "paid"/);
});

test("manual settlement requires separate platform owner, fresh MFA, same-origin, ledger and one-time reference",()=>{
  assert.match(server,/function requireManualBillingMfa/);
  assert.match(server,/recentManualPaymentMfa\(session\)/);
  assert.match(server,/app\.post\("\/api\/admin\/billing\/manual\/orders\/:orderId\/confirm", requireAuth, requirePlatformOperator, requireManualBillingMfa/);
  assert.match(server,/app\.post\("\/api\/admin\/billing\/manual\/orders\/:orderId\/reject", requireAuth, requirePlatformOperator, requireManualBillingMfa/);
  assert.match(server,/mfaVerifiedAt: mfaVerified \? Date\.now\(\) : undefined/);
  const confirmStart=server.indexOf('app.post("/api/admin/billing/manual/orders/:orderId/confirm"');
  const rejectStart=server.indexOf('app.post("/api/admin/billing/manual/orders/:orderId/reject"',confirmStart);
  assert(confirmStart>0&&rejectStart>confirmStart);
  const confirm=server.slice(confirmStart,rejectStart);
  assert.match(confirm,/sameOriginMutation\(req\)/);
  assert.match(confirm,/manualReceiptDecision/);
  assert.match(confirm,/manualBillingMutationBusy/);
});

test("WiPay return can never settle a manual order and existing Sentinel G1.2 boundaries remain",()=>{
  const p=server.indexOf('app.get("/api/billing/wipay/return"');
  assert(p>0);
  const end=server.indexOf('app.get("/api/security/mfa/status"',p);
  assert(end>p,"must identify entire WiPay callback handler");
  const route=server.slice(p,end);
  assert.match(route,/reconcileWipayInPostgres/,"PostgreSQL payments must use transactional reconciliation");
  assert.match(route,/if \(order\.provider !== "wipay"\)/,"sandbox JSON fallback cannot settle manual payments");
  const atomic=fs.readFileSync(new URL("../server/wipay-atomic-ledger.mjs",import.meta.url),"utf8");
  assert.match(atomic,/order\.provider !== "wipay"/,"PostgreSQL transaction cannot settle manual payments");
  assert.match(server,/sentinelServiceGrants: validateSentinelGrantCollection/);
  assert.match(server,/app\.get\("\/api\/agent\/executive-structure"/);
  assert.match(server,/app\.post\("\/api\/agent\/executive-handoff"/);
});

test("manual billing persistence failure returns fail-closed operator status in Express 4",()=>{
  const boundaries=[
    ['app.post("/api/billing/manual/request"', 'app.get("/api/admin/billing/manual/orders"'],
    ['app.post("/api/admin/billing/manual/orders/:orderId/confirm"', 'app.post("/api/admin/billing/manual/orders/:orderId/reject"'],
    ['app.post("/api/admin/billing/manual/orders/:orderId/reject"', 'function billingServiceFromRequest('],
  ];
  for(const [begin,end] of boundaries) {
    const i=server.indexOf(begin),j=server.indexOf(end,i);
    assert.ok(i>=0 && j>i, "must locate financial mutation boundary: "+begin);
    const route=server.slice(i,j);
    assert.match(route,/await commitStore\(nextStore\)/);
    assert.match(route,/}\s*catch\s*\{/,"unhandled async rejection can crash Express 4");
    assert.match(route,/if \(res\.headersSent\) return/);
    assert.match(route,/res\.status\(503\)/);
    assert.match(route,/}\s*finally\s*\{/,"advisory busy lock must still be released");
  }
  const confirm=server.slice(
    server.indexOf('app.post("/api/admin/billing/manual/orders/:orderId/confirm"'),
    server.indexOf('app.post("/api/admin/billing/manual/orders/:orderId/reject"')
  );
  assert.match(confirm,/outcome is uncertain/);
  assert.match(confirm,/manualOrderApprovalLocks\.delete\(orderId\)/);
});

test("manual reconciliation UI never autofills bank receipt amount from invoice",()=>{
  assert.match(reconcile,/const \[receivedAmount, setReceivedAmount\] = useState\(""\)/);
  assert.match(reconcile,/Amount actually received \(XCD\)/);
  assert.match(reconcile,/receivedAmount: receivedAmount\.trim\(\)/);
  assert.doesNotMatch(reconcile,/receivedAmount:\s*selected\.amount/);
  assert.match(reconcile,/Number\(receivedAmount\) !== selected\.amount/);
  assert.match(reconcile,/setReceivedAmount\(""\)/);
});

test("WiPay success banner requires authenticated order, never trusts URL query",()=>{
  const marker=billing.indexOf('Browser query parameters are untrusted');
  assert.ok(marker>0);
  assert.match(billing,/fetch\("\/api\/billing\/orders", \{ cache: "no-store" \}\)/);
  assert.match(billing,/row\?\.id === orderId && row\?\.provider === "wipay"/);
  assert.match(billing,/row\?\.sourceApp === "hub" && row\?\.status === "paid"/);
  assert.match(billing,/typeof row\?\.providerTransactionId === "string"/);
  assert.match(billing,/typeof row\?\.paidAt === "string"/);
  assert.match(billing,/verifiedReturn === "live"/);
  assert.match(billing,/verifiedReturn === "sandbox"/);
  assert.match(billing,/Payment not verified\./);
  assert.match(billing,/Checkout returned an unsuccessful status\./);
  assert.doesNotMatch(billing,/Payment was not applied\./);
  assert.match(billing,/No paid subscription access was granted by the sandbox test\./);
  assert.doesNotMatch(billing,/<strong>Payment verified\.<\/strong>/);
});
