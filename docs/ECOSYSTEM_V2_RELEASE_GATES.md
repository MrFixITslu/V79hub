# V79 Ecosystem v2 — code-first release gates

**State: code candidates in DRAFT pull requests. No production deployment authorised.**

- Hub event inbox: https://github.com/MrFixITslu/V79hub/pull/251
- Tiquet event/acknowledgement/client portal: https://github.com/MrFixITslu/V79Tiquet/pull/64
- Website CRM approval handoff: https://github.com/MrFixITslu/v79website/pull/86

## Architecture decision

Considered three approaches: direct cross-application mutation, a new external integration service, and **existing apps + dedicated signed contracts with durable local queues**. The third preserves existing SSO/billing apps and costs less. Cross-app mutations remain opt-in and tenant-scoped.

### Red-team conclusions

1. A duplicated website submission must never create two clients/jobs; reuse the original Tiquet intake UUID, require a persisted CRM ID mapping and use exact job/client IDs.
2. No service credential is reusable across Website, Tiquet and Hub. Canonical HMAC signs the raw HTTP body + timestamp and identifies the caller. Reject unsigned, expired and cross-tenant events.
3. Hub event receipts are not a finance settlement ledger. Never convert `job.paid` into revenue; only Tiquet's separately verified payment ledger can do that. Only bounded categorical events cross services.
4. Missing SMTP, ambiguous send result, processor crash, lost response or incomplete receipt is **not** email delivered. A sending/uncertain acknowledgement requires manual reconciliation, not automatic re-send.
5. A cancelled ticket must not delete history, reopen itself, process a manual payment, issue a refund, or silently ignore an in-flight externally verified WiPay settlement. Financial exceptions require operator review.
6. CRM leads predating the explicit mapping do not get guessed into a tenant using email/company matching. Reconcile these manually in staging.
7. Preserve current website visual identity, accepted Hub Google/MFA sign-in, Tiquet customer data, existing branding and favicon. No destructive schema changes.

## Implementation configuration — OFF by default

| App | Environment variable | Staging condition |
| --- | --- | --- |
| Hub | `V79_ECOSYSTEM_V2_EVENTS_ENABLED=0` | Enable only with PostgreSQL inbox and validated tenant mapping |
| Hub | `V79_TIQUET_EVENT_SECRET` | Dedicated, unique secret (32+ characters), paired with Tiquet's `V79_HUB_EVENT_SECRET` |
| Hub | `V79_WEBSITE_EVENT_SECRET` | Separate, unique secret, paired with Website's `V79_HUB_EVENT_SECRET` |
| Website | `V79_ECOSYSTEM_V2_REVIEW_MODE=0` | Enable only after historical lead mapping review |
| Tiquet | `V79_ECOSYSTEM_V2_INTAKE_ACK_ENABLED=0` | Verified SMTP credentials, explicit SMTP_FROM, mailbox delivery proof |
| Tiquet | `V79_ECOSYSTEM_V2_CANCEL_ENABLED=0` | Payment/portal race and refund exception acceptance |
| Tiquet | `V79_ECOSYSTEM_V2_FEEDBACK_ENABLED=0` | Client consent and tenant-isolated feedback acceptance |
| Tiquet | `V79_ECOSYSTEM_V2_INVOICE_SEND_ENABLED=0` | SMTP verified and invoice-link idempotency tested |
| Tiquet | `V79_TIQUET_INVOICE_CC_ACCOUNT_ID` | Exact owner workspace ID only; never another tenant |
| Tiquet | `V79_TIQUET_INVOICE_CC_EMAIL` | Set to `vision79slu@gmail.com` for the owner workspace before enabled sending |

No production secrets should enter GitHub, CI logs or the browser.

## Stage after all code is complete

**Stage 0: Code freeze and independent CI**

- All three draft branches pass complete build, lint, unit/integration and non-deploying security workflows at the **same exact SHAs**.
- Resolve failed checks instead of updating acceptance pins blindly. Hub's original protected `server.ts` SHA remains verifiable with the additive-core preservation test.
- Verify PR diffs contain no old UI versions, favicon regressions, unrelated routes or accidental changes to payment/MFA logic.
- Prepare a read-only release manifest showing exact commit SHAs, image digests, environment-flag diffs and rollback references.

**Stage 1: Isolated deployment — no customers and no external sends**

- Use disposable PostgreSQL and isolated networks, with flags OFF initially.
- Run fresh migrations, verify old data restore and prove a clean rolling rollback from each new schema.
- Verify website/homepage/CRM, Hub login via Google then MFA, Hub-to-Tiquet SSO, customer portal, quotes and invoices, due date editing, mobile layout, icons and themes.
- Confirm all three apps are independently healthy and routes give `404` or `unavailable` when gated OFF.

**Stage 2: Enable V2 in staging only**

- Create two realistic but synthetic organisations and independent service signing keys.
- Positive: website form → one website lead + one CRM task, staff reviews scope, approves once, Tiquet returns **real** client/job IDs; subsequent retry returns the same IDs; signed event receipts join by opaque correlation ID.
- Negative: duplicate request with changed content, missing mapping, inactive entitlement, wrong organisation, cross-tenant query, wrong HMAC, wrong service identity, expired signature, future event, PII in Hub payload, concurrent/out-of-order deliveries.
- Tiquet: one acknowledgement per ticket, test actual designated mailbox, SMTP absent, SMTP temporary failure, duplicate submission, process crash after mail may have sent, manual review queue. Never report `sent` for a skipped email.
- Invoice link: user-triggered send only, real invoiced job with a positive value, mandatory request idempotency, SMTP positive and skipped-negative checks, copy only to Vision79's own configured account and address, no CC for a second tenant. Confirm the portal presents the actual invoice and does not claim payment was received.
- Billing: no synthetic amounts reach Hub receipts; settled WiPay-only ledger; cancellation with unpaid request allowed, recorded payment/invoiced work blocked, in-flight gateway settlement recorded with human finance exception.
- Client feedback is one submission per job and account, only after review/completion, free-text stays in Tiquet, contact permission is not marketing opt-in.
- Repeat success and denial tests after container restart and database restore.

**Stage 3: Customer acceptance and disaster recovery**

- Browser verify website design + logos, no overlapping hero text, links, accessible controls, mobile and desktop.
- Check notification emails, admin audit, customer-facing wording, inactive links, approvals and permissions.
- Restore production-like encrypted backups to a separate host; confirm Hub, Tiquet and website data integrity.
- Perform rollback rehearsal with default-OFF flags; no queues should replay customer messages or money movements unexpectedly.
- Inspect error budgets, monitoring signals and hold/review queue; require explicit owner acceptance of residual risks.

**Stage 4: Production only after approval**

- Backup + confirm restore point and exact previous container/image IDs before any cutover.
- Promote previously tested immutable image digests one app at a time, initially with every V2 flag OFF. Preserve all icons and visual version pins.
- Re-check Hub Google/MFA + Tiquet launch, website lead intake, live receipt status and payment read-only state.
- Gradually enable the signed Hub inbox, Website approval mode, and separately the Tiquet mail/cancellation features only when their own staging acceptance was witnessed.
- Watch sign-in failures, client-specific errors, sent/unknown mail receipts, event lag and unexpected financial entries. Roll back flag first on regression, then container if required.

## Blockers to full acceptance

- Connected host remote-command usage limit prevents direct production/staging server execution from this ChatGPT session.
- A passing GitHub Action or disposable test is **not** an acceptance of live SMTP, Google/MFA, Tiquet reconciliation, payment processing or recovery on the actual deployment host.
- Do not merge drafts or enable flags from an automated CI success alone.

**Release state labels:** planned → coded → CI verified → isolated staging verified → browser/customer accepted → explicitly approved → deployed.
