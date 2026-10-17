# V79 Hub manual bank-transfer payment — release and operating controls

Status: staged candidate for independent finance/security acceptance. NOT deployed.

## Scope
- WiPay remains the primary hosted electronic gateway, unchanged.
- Manual transfers are an optional, separately audited settlement method for an existing Hub subscription plan.
- Customers with billing permission can request a manual invoice reference; no bank account information is embedded into source code, the email or the web interface.
- Only an authenticated V79 owner/platform operator with a verified MFA session can reconcile a manual payment.
- A manual invoice never grants app access while pending, failed or unverified.

## Financial approval procedure (owner)
1. Configure each customer's monthly/annual plan price in XCD and subscription entitlement through the existing Hub Plan Administration interface. Do not activate a paid plan through ordinary plan editing.
2. Customer clicks **Request bank-transfer invoice**; Hub creates one pending order at the current plan amount and cycle. An existing pending order is reused rather than duplicated.
3. Send a real invoice and current verified receiving bank instructions **out of band**. Hub does not currently create a printable tax invoice or transmit bank account details; do not claim that it does.
4. Verify that funds **cleared** in V79 Digital's receiving bank statement. Confirm payer, invoice reference, exact gross amount, bank transaction ID and statement date. Customer screenshots or claims are not sufficient.
5. Platform operator logs into Hub with MFA, opens Plans & Entitlements → Manual Bank-Transfer Reconciliation, chooses the pending order, enters the bank reference and a non-sensitive evidence note, asserts that the statement was checked, then types the exact order-specific confirmation phrase.
6. The backend verifies exact amount/currency/plan cycle and current organization, rejects reused bank references, records the confirming operator and evidence in Hub billing/audit ledgers, sets the order paid and advances the monthly/annual entitlement period once.
7. If funds cannot be matched, reject the pending order with a documented reason. This does not grant access and allows a fresh invoice request.
8. Reconcile the ledger against bank settlement weekly. Issue formal receipts to customers outside the app until receipt generation is implemented.

## Security and integrity requirements
- WiPay callbacks reject manual invoices. A claimed bank transfer never directly modifies paid plans.
- Manual verification requires a successful MFA login no older than 15 minutes, measured from original challenge completion and never extended by browsing; older/historical sessions must sign out and sign in again. This is independent of the general MFA toggle.
- Only the V79 internal platform operator can confirm or reject; no customer may approve their own payment or see other tenants' manual requests.
- An approval cannot be replayed or reused for the same order or bank reference; another organization's bank reference is never accepted twice.
- Invalid/mismatched currency, amount, subscription cycle, organization or suspended plan are refused. Fractional-cent receipts fail rather than being rounded into payment.
- A single-process mutation lock reduces in-process duplicate approval races. For a horizontally scaled Hub, add a PostgreSQL uniqueness constraint and row-level transaction locks before production payment use.
- Evidence should never include full bank account numbers, customer passwords, card numbers or secrets. Store only reconciliation identifiers and a short verification note.
- Do not enable automatic invoice approval, refund, reversal or partial payments until independently designed, tested and audited.

## Release gates
- [x] Core contract tests: validation, replay, existing paid period and access enforcement.
- [x] Live-code isolated two-tenant Hub/Tiquet HTTP + disposable PostgreSQL bank settlement tests, no real bank transfer or customer account.
- [x] All tested routes require existing session and permissions; financial admin routes require MFA.
- [x] WiPay callback explicitly rejects manual orders.
- [x] TypeScript lint and client production build pass.
- [ ] Independent security and financial review of new routes, stored evidence, admin controls and potential concurrent writers.
- [ ] Verified real receiving bank details and operating instructions approved by V79 Digital.
- [ ] Confirmation of invoice tax/legal disclosures, payment receipt, disputes, refunds and reconciliation practices in Saint Lucia.
- [ ] Full staging UI/browser accessibility and mobile verification.
- [ ] GitHub Actions CI and reviewed immutable release with current Sentinel modules preserved.
- [ ] One supervised test payment using a small **real** settled bank transfer approved by owner, with no customer data modified.
- [ ] Production monitoring of rejected attempts and mismatched bank references.

Manual billing is not a replacement for a live WiPay merchant agreement; both systems remain controlled by the Hub's authoritative entitlements.
