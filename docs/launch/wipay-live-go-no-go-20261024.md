# Vision79 — WiPay Live launch readiness (24 Oct 2026)

**Mode:** planning and isolated verification only. **No provider activation, live environment change, customer charges, rollout or production deployment authorized by this document.** Hub and Tiquet controlled beta remains intact with WiPay sandbox. From Idea to Advantage is owner-approved at **EC$249 one-time**; Academy PR #29 is review-ready with all four GitHub PR workflows passing at its latest recorded SHA.

**Timing:** Owner anticipates WiPay merchant activation soon; the exact date is unverified. This checklist is not tied to an assumed onboarding day or week.

## Chosen option and /REDTEAM
Considered three approaches:
1. **Wait for WiPay before doing any work**: rejected because course publication, lead capture, current application QA and source reconciliation can proceed without live payments.
2. **Turn on live WiPay directly in all apps when credentials arrive**: rejected; would create live financial/security exposure and leave country, currency, refund, callback and tenant controls unverified.
3. **Chosen: prepare all non-payment release work now; use a single Hub-controlled merchant and a separately authorized, sequential low-value live checkout only after every gate passes.**

## A. Work that is NOT blocked by WiPay
- **Academy:** complete PR #29 independent review/merge only under repo rules; reconcile exact installed build; fix catalogue labels, verify portal-only publication mode on a non-customer test course, student signup/login, lesson/progress save, course certificate eligibility and reset/retry. Existing learner progress must not be lost. EC$249 is the *approved offer*, not yet a saved price in the live course database.
- **Marketing and website:** confirm current brand maps to **Vision79** and channels are correct; verify CTA for the approved course, free AI prompting guide, CAPTCHA, CRM/Tiquet records, newsletter consent, first-submit retry reproduction, and end-to-end UTM attribution. User confirms no current account-limit blocker; earlier provider-error rows still need individual disposition. Leave social drafts nonpublishing until their exact text/date/channel are authorized.
- **Hub/Tiquet:** continue *already-approved* 14-day invite-only beta, MFA, tenant separation and signed Hub SSO; use clean synthetic contacts. Resolve open My Apps 403, refresh/history and Tiquet session issues **only if reproduced**.
- **FFPRO:** finish signed-in hardened candidate financial workflow and denied-operation checks; hold production role and cutover changes for separate approval.
- **POS:** reconcile owner-accepted live UI with GitHub PR #15 and ECR 429-only unrelated image-build CI failure. Merge/redeploy are distinct decisions; preserve pinned existing live container and override.
- **Sentinel:** maintain private owner monitoring; planned host reboot and recovery evidence require a separately agreed maintenance window; no unattended invasive actions or customer ingress.

## B. WiPay-specific pre-live blockers
**Get written merchant answers, not credentials in chat or GitHub.**
1. **Saint Lucia availability confirmed (owner-provided official link, checked 24 Oct 2026):** [WiPay Saint Lucia](https://wipaycaribbean.com/st-lucia) explicitly offers local-business support, **XCD processing**, online card payments/API integration and Saint Lucia merchant onboarding. Its [St Lucia business signup](https://lca.wipayfinancial.com/v1/Sign_Up_Business) and [provider status](https://status.wipaycaribbean.com/) show an **`lca.wipayfinancial.com/v1/` service**. **These facts supersede the earlier assumption that Saint Lucia support was unconfirmed.** Still confirm V79 Digital's *verified business* merchant status, approved live API key/merchant account, payer currency, settlement account, and **exact Payments API production/sandbox checkout URL** in writing: the separate [WiPay developer platform endpoint table](https://docs.wipayfinancial.com/platforms-and-environments) lists **BB/GD/GY/JM/TT** but no LC API path; do **not** infer that `https://lca.wipayfinancial.com/plugins/payments/request` is functional from a signup URL or status check.
2. WiPay's [Saint Lucia page](https://wipaycaribbean.com/st-lucia) markets **XCD processing**, removing generic LC/XCD product-support uncertainty. Nevertheless require account-specific confirmation that **Vision79 can charge cards in XCD and receive payout/settlement in XCD**, including processing bank/country and receipt currency. Academy offer is EC$249 and Hub plans are XCD. If your specific merchant cannot charge and settle those amounts in XCD, **no automatic conversion or misleading EC$ checkout**; separately approve explicit FX quote, customer disclosure and refund rules first.
3. Confirm exact transaction fee structure `merchant_absorb`, taxes, settlement account, minimum/maximum amounts, refunds/chargebacks/disputes and notification procedure. Prepare clear course sales/refund terms and accurate receipts.
4. Review the **current provider request and response specification** against Hub source *before* any live credentials are applied:
   - Provider [Payment Request](https://docs.wipayfinancial.com/payments-api/payment-request) lists `credit_card_co` and `3co_simple`; `credit_card` is deprecated, while current Hub `server/wipay-provider.mjs` uses `method: "credit_card"`.
   - The provider currently lists **payer `email` as required**. Current Hub `createWipayCheckout` does not include an `email` field. Do not infer an email from the merchant or synthesize a payer.
   - Provider [Transaction Response](https://docs.wipayfinancial.com/payments-api/transaction-response) explicitly derives response hash from **original requested total formatted to exactly 2 decimals**. Current Hub `verifyWipayReturn` feeds the **callback `total` string** into `verifyWipayResponse`. Existing `merchant_absorb`/exact-total check may reject fee-adjusted results rather than misgrant access, but this is **not a verified implementation of current hash specification**. Implement and regression-test the correct signed order amount, preserving strict settlement checks. Never trust a browser-supplied amount.
   - The current Hub order ID format begins `v79_` and exceeds the API's **recommended** 16 characters. Ask WiPay whether long IDs are accepted for this merchant before changing persistent order identities.
5. For callbacks: enforce server-side status/hash verification, order ID, **original amount**, currency, merchant/environment and unique transaction, with duplicate/replay protection; browser return **never** directly grants access. Check session/user/course binding before Academy purchase grant. Ensure sandbox never extends subscriptions, course ownership or invoice cash.
   - **Environment parity is a mandatory pre-live test.** Current Hub verifier takes `expectedOrder.providerEnvironment` but does not reject when it differs from `config.environment`. A checkout begun in one environment must NEVER be paid/fulfilled using a return verification key or provider state from the other environment, even when the order's own source/currency/HMAC metadata remains intact. Verify order environment and supported callback route against the pinned order first; preserve any in-flight orders safely across a config cutover. Fail closed and reconcile uncertain payments with WiPay rather than silently retrying or switching secrets.
   - **Concurrent callback mutation is a mandatory pre-live test.** Current `/api/billing/wipay/return` clones the store and awaits `commitStore` without the single-node billing mutation exclusion already present on *manual* billing routes. Concurrent identical callbacks for one transaction, or two orders sharing a provider transaction ID, must not double-fulfil, extend access twice, lose another write or bypass transaction uniqueness. Add a serialized/transactional durable write design with rollback; test parallel requests and restart recovery before any actual merchant attempt.
   - **Sandbox endpoint parity:** `SANDBOX_DEFAULTS.endpoint` currently points to the `tt.wipayfinancial.com` live TT host, whereas WiPay's current public platform table documents `https://ttsb.wipayfinancial.com/plugins/payments/request` for TT sandbox. Confirm the exact checkout route with WiPay and independently verify that existing test orders/return URLs will not be disrupted before changing configuration.
6. Configure live API secrets **only on server** through protected environment/secret mounts; Academy and Tiquet receive only their dedicated HMAC *service secrets*, not the WiPay API key. Back up/recover **order ledger and secrets**, confirm restore/rollback, prevent mixed sandbox/live callback verification for existing in-flight orders.
7. Provider webhooks: agree whether webhook / transaction retrieve is required for later refunds, disputes and fraud; establish reconciliation and course access reversal/appeal policy. Do not assume a browser redirect covers later payment lifecycle events.
8. Independent acceptance for one approved **low-value real payment**: verify provider transaction in merchant portal, Hub order/payment audit, settlement currency, actual fees, receipt/refund policy and the exact entitled **test** product. Test replay, decline, interruption, cross-tenant requests and rollback. Explicit owner authorization and production evidence required before enabling customer checkout broadly.
9. Do not enable third-party Tiquet tenant collection until WiPay confirms appropriate merchant/submerchant settlement rights. Hub subscriptions, Academy one-time courses and V79-owned Tiquet invoices each need their own bounded release acceptance; Academy does not imply recurring billing is ready.


**Source clarification (24 Oct 2026):** The Saint Lucia marketing page and the developer platform API table serve different purposes. *Country presence + advertised currency support are confirmed; merchant-specific API checkout endpoint and live merchant activation remain unverified.* The St Lucia terms include example/placeholder-looking contact details; use onboarding correspondence or the merchant agreement for operational support contacts and pricing, not scraped telephone numbers alone.

## C. Sign-off and exact release sequence
**Non-payment work:** content and UI review → CI source checks → pinned image and rollback verification → authorized guarded non-payment acceptance.

**Payment release (later, explicitly approved):**
1. Provider confirms merchant country/currency/checkout schema/callback/fee support; record evidence without secrets.
2. Patch and test documented Hub provider compatibility gaps **off production**; source security review + CI; confirm exact current Hub overlay and data ledger persistence.
3. Confirm Academy service signature and scoped ownership controls, registered callback/website URL and course EC$249 policy; Hub/Tiquet beta controls unchanged.
4. Owner schedules and authorizes a controlled merchant configuration change with verified backups and rollback; no concurrent sandbox checkout in flight.
5. Perform separately approved one low-value live transaction and ledger reconciliation, including negative cases.
6. Owner explicitly signs off expanding checkout to one Academy course, then only later Hub paid plans or Tiquet owner-merchant invoices.

## D. Completion definition
- READY FOR NONPAYMENT PILOT: academy course and learner journey work, marketing CTA, existing beta and QA evidence with no payment credential changes.
- **PAYMENTS LIVE GO:** all gates in B and C supported by current provider and actual production evidence; never inferred from green code CI alone.
- WIPAY ARRIVAL ALONE IS NOT A GO SIGNAL.

## Source snapshots and references
- Academy offer and UI: https://github.com/MrFixITslu/V79acaedmy/pull/29
- Hub provider implementation: `server/wipay-provider.mjs` and `server.ts`
- Provider docs: https://docs.wipayfinancial.com/platforms-and-environments ; https://docs.wipayfinancial.com/payments-api/payment-request ; https://docs.wipayfinancial.com/payments-api/transaction-response
- Canonical completion register: https://github.com/MrFixITslu/V79hub/issues/194
