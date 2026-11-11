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
| Tiquet | `V79_ECOSYSTEM_V2_EVENT_DELIVERY=0` | Enable signed outbound outbox only with Hub receiver and mapping tested |
| Tiquet | `V79_ECOSYSTEM_V2_STRICT_INTAKE_IDENTITY=0` | Enable only with reviewed CRM-to-client reconciliation; no email/phone-based merge |
| Tiquet | `V79_ECOSYSTEM_V2_DELIVERY_ACCEPTANCE_REQUIRED=0` | Explicit customer delivery acceptance, audited and distinct from invoice payment |
| Tiquet | `V79_ECOSYSTEM_V2_CANCEL_ENABLED=0` | Payment/portal race and refund exception acceptance |
| Tiquet | `V79_ECOSYSTEM_V2_FEEDBACK_ENABLED=0` | Client consent and tenant-isolated feedback acceptance |
| Tiquet | `V79_ECOSYSTEM_V2_SCOPE_ENABLED=0` | Files path security, immutable scope PDF versions, client acknowledgement, document restore |
| Tiquet | `V79_ECOSYSTEM_V2_EVENT_ADMIN_ENABLED=0` | Tenant-only event evidence and reviewed replay after rejection |
| POS | `V79_ECOSYSTEM_V2_JOB_COST_READ_ENABLED=0` | Hub-signed read-only FIFO usage; staff-entered job linkage remains provisional |
| Hub | `V79_ECOSYSTEM_V2_POS_COST_READ_ENABLED=0` | Confirm signed Tiquet job receipt, both entitlements, POS HMAC and provisional response |

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

**New code contract gates before enabling stage flags**
- Upload a job PDF, publish immutable scope v1, verify hash and tenant, acknowledge exact version; publish v2 and prove v1 acknowledgement is NOT reused. Once delivery has been accepted, scope change must require a new ticket.
- Verify deleted/moved/symlink files cannot reach outside a tenant, and archived PDF remains readable after a customer display name changes. Back up and restore scope snapshots as part of the file restore.
- Force failed Hub events, inspect tenant-filtered status, re-enable delivery, and make an explicitly approved retry; receipt status cannot claim successful customer communication or settled payment.
- POS usage evidence returns real FIFO snapshots only; typed jobReference alone is not verified Tiquet association, so cost is provisional and margin remains null.
- Hub cost read must require a signed tenant-specific Tiquet job receipt, both app entitlements and POS HMAC; cross-tenant, absent source or cost corruption must fail closed.
- The cross-app material job association and complete expense/labour rate mapping are **OUTSTANDING** and cannot be called verified margin.

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

### Evidence from first combined three-app staging (11 Nov 2026)

- Passing run: https://github.com/MrFixITslu/V79hub/actions/runs/43017059324
- Exact initial candidate SHAs: Hub `fa7908a842b346b29cc9a09c91742fc40c1cfa70`, Tiquet `eb90d4581a8e5906cbe1ad3cd90b05188176ef61`, Website `c64d7ba1fbdd92b033d28e88608e464af941eefc` (same runtime source as later test-only Website SHA).
- Passed synthetic real HTTP/SQL checks: two isolated tenants; real Tiquet provisioning; website lead + CRM capture; request replay and duplicate review; zero unapproved Tiquet tickets; approved CRM conversion; one customer-linked Tiquet job; stable repeat conversion; signed Website and Tiquet events in Hub with correlation; second tenant cannot read the event.
- Previous failure was an erroneous CI assertion of `type`; the Hub SQL-backed receipt contract exposes `event_type`. This was corrected without changing the server output.
- **Not tested** by this run: external email, WiPay, Google OAuth/MFA, website owner SSO browser journey, actual production account mapping, or disaster recovery.
- The next exact-SHA rerun also pins the latest Website commit with a corrected source-only test. No customer data or production credentials used.

**Release state labels:** planned → coded → CI verified → isolated staging verified → browser/customer accepted → explicitly approved → deployed.


## Code-first reconciliation additions — 11 November 2026

The following are draft-source changes **after** the previously passing three-app stage. They are not live and require new exact-commit staging:

- **Tiquet PR #64**: existing file path boundary hardened; tenant+job-scoped immutable PDF scope versions, SHA-256 integrity, explicit portal acknowledgment, separate delivery acceptance; customer approval + audit + outbound Hub event committed in one database transaction; uncertain DB outcomes retain archived evidence; tenant-scoped signed event status and reviewed retries; separate read-only duration evidence with no fabricated historic labour costs. Feature switches `V79_ECOSYSTEM_V2_SCOPE_ENABLED`, `V79_ECOSYSTEM_V2_EVENT_ADMIN_ENABLED` and `V79_ECOSYSTEM_V2_WORK_EVIDENCE_ENABLED` default OFF. Scope portal acknowledgement is **not certified e-signature**.
- **Hub PR #251**: canonical versioned event catalogue; account-scoped UUID event correlation lookup; signed Tiquet job receipt required before provisional POS cost lookup; minimal `job.scope_acknowledged` event; read-only server image provenance script. `V79_ECOSYSTEM_V2_POS_COST_READ_ENABLED=0`.
- **POS PR #19**, based on existing technician candidate PR #17: signed, read-only FIFO technician usage evidence by exact job UUID; currency, quantities, immutable cost snapshots; marks human-entered job linkage UNVERIFIED and verified margin NULL. `V79_ECOSYSTEM_V2_JOB_COST_READ_ENABLED=0`. POS CI passed on commit `5cc2160008317165b4712435798d35f82eac10ea`.
- **Website PR #86** remains the prior approved-lead integration candidate. Deployed Website source/branding has not yet been reconciled against unmerged production overlays.

**Outstanding code / integration scope (RED):** proof of staff-entered POS stock usage association to a real tenant-scoped Tiquet job; historical labour-rate snapshots and project expenses, signed/verified true margin projection, authoritative business-name sync across app branches, reconciliation of the older Tiquet PDF invoice workflow, and owner-reviewed actual deployed baseline. These are not implied by CI success.

**Release hold:** No production merges, emails, stock movements, payment postings or site changes. Record current exact source SHA and test run before accepting any status as green. The earlier synthetic three-app PASS applies to the previously pinned release, not automatically to new modules.
