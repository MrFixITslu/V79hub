# Customer package pricing and reviewed requests

## Commercial catalogue approved for implementation in this conversation

All authoritative amounts are XCD. Starter EC$149/month, one app allowance and three staff; Business EC$299/month, two apps and five staff; Business Plus EC$499/month, three apps and ten staff. Each standard app beyond the allowance adds EC$99/month. Selecting POS consumes one allowance and adds EC$100/month. Additional named staff cost EC$25/month each, once per workspace across selected apps. Annual recurring amounts are ten times monthly amounts; optional guided setup is EC$199 once, never annual-discounted or multiplied by app/user count. The USD display divides XCD by 2.70 and rounds only for presentation. It does not change settlement currency.

Examples: Starter + POS = EC$249/month; Starter + POS + twelve extra staff = EC$549/month for fifteen staff. Business Plus + POS + five extra staff = EC$724/month or EC$7,240/year, plus EC$199 setup if requested.

## What this release does

Customer Billing displays package/app/staff selection, exact server-reviewed quotes, USD equivalents, separate one-time setup, signed durable pricing requests and scoped request history. Existing invoice/payment history is displayed with empty/loading/error and pending/sandbox labels. A customer can submit a reviewed request; the platform operator can record commercial review or decline with a note. Retries use the same request key and exact digest. Editing selection invalidates the previous review.

Pricing requests are not orders, paid invoices, subscription grants or proof of service delivery. They do not change trial dates, plan price, entitlements, staff permissions, seat limits, billing orders or provider configuration. Marking commercially reviewed is an acknowledgement, not an activation or paid approval. The owner must verify actual app release and provisioning readiness, supported staff capacity, applicable setup work and an agreed invoicing route before configuring an offer. Existing verified bank-transfer settlement safeguards remain unchanged. There is no automatic billing or seat enforcement added by this release; capacity remains explicitly proposed until separately provisioned and accepted. Do not describe a request as a purchased seat allowance.

Only Tiquet has current customer acceptance in this workstream. POS, Finance and Marketing are selectable for a quote but visibly require release review before activation. This is not a launch of those apps or of customer AI Workforce.

## Persistence and security

A separate signed ledger at DATA_DIR/pricing-requests-v1.json records requests and review events. It avoids stale whole-Hub snapshot overwrites. The existing Hub security key authenticates canonical JSON. GET on an absent ledger performs no initialization. Atomic private-file replacement, file and parent-directory fsync, cross-router process lock and no stale-lock stealing protect writes. A leftover lock requires operator review. Metadata, signature or key failure blocks access; storage failure never claims successful save. Public routes require authenticated billing permission and same origin on mutations; review routes additionally require the platform operator. Tenant context is taken only from the verified session, never a request body.

The ledger is on the existing persistent app-data mount, independently of the Hub PostgreSQL store. Include it and the existing protected signing key in encrypted backups; do not print them. All code is offline-buildable without new dependencies.

## Preserved release inputs

Before this change: Hub sha256:dbf9c7a525bb6a720e3e71a17c4da041b75f0815cd1c4e95f2231fea5da12ff3 at 012a99c84e7f6ab39f065acf15887d146116ffbe; Agent sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b. Preserve the calendar refresh, owner-session MFA policy, Google credential mount, existing customer plans/prices, Tiquet and both database containers. WiPay must remain sandbox; preflight and post-cutover verification explicitly check this without contacting the payment provider.

## Acceptance

Local tests cover complete price combinations, malformed input and money injection, HMAC/file locking/tampering/restart, tenant isolation, duplicate requests, optimistic owner review, no Hub-store mutation, UI selection/currency/retry/history and a real disposable full-Hub owner/two-tenant session journey. These are synthetic tests, not real bank settlement or release approval for POS/other apps. The exact image must pass the Acer offline full-Hub rehearsal before guarded deployment. After deployment, test a customer quote and request and inspect it in Platform Admin. Do not create payments or change existing customer access to demonstrate the new request screen.
