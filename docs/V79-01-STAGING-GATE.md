# V79-01 Staging Release Gate — 8 October 2026

**Verdict: NO GO for production deployment.** This is an evidence report, not a deployment instruction.

## Evidence obtained

- Hub feature-branch full automated suite: **79 passed, 0 failed**. Hub TypeScript and frontend build passed. GitHub CI succeeded on Hub commit `4a40638`.
- POS feature-branch API suite: **15 passed, 0 failed** (test-only dummy DATABASE_URL). TypeScript check passed and GitHub CI succeeded on `68e5a29`.
- FFPRO after staging security hardening: **89 tests passed, 0 failed**; lint passed. Draft PR #39 contains the new tests and patch. No new GitHub workflow run was confirmed for this branch's latest commit.
- Marketing after staging security hardening: **33 tests passed, 0 failed**; lint passed. Draft PR #23. GitHub CI revalidation was running at last check.
- Tiquet: **13 isolated unit and contract tests passed, 0 failed**; lint and build passed. Its GitHub CI workflow provides an isolated PostgreSQL service and test server for the **full legacy integration suite** (prior CI run green). Updated draft PR #19 CI was running at last check.
- A local **loopback-only live HTTP contract rehearsal** using the four actual application client libraries, two synthetic tenants and distinct HMAC secrets passed for active trials, cross-tenant denial, revocation at the 30-second cache boundary, unaffected other-tenant access and upstream outage. This test did not instantiate the entire applications or access a production database.
- Read-only production PostgreSQL aggregate (no customer identifiers retained): **2 organisations; 0 explicit subscription plans; 13 app entitlements**, comprising 8 owner and **5 entitlements for one other active organisation**. The verified owner organisation was present.
- An isolated dry-run migration preview with synthetic data matching the observed counts yielded **1 protected internal owner**, **1 customer requiring review** and **0 unverified customer access approvals**.
- Production Hub, POS, FFPRO, Marketing and Tiquet containers remained healthy during these checks. No production databases, containers, source checkouts or feature flags were modified.

## Blocks to clear before merger/deployment

1. **P0 — Legacy entitlement migration.** One non-owner active organisation has five app entitlements but no subscription record. Deploying fail-closed subscription enforcement without an approved classification/migration could revoke access. The current migration CLI is strictly read-only. Obtain the owner's decision and rehearse a transactional migration against an isolated snapshot. Do not infer a verified payment from historic active status.
2. **P0 — Full application staging.** Rehearse authenticated customer sessions with all four downstream app implementations, the new Hub endpoint, distinct network/service secrets, simulated trial expiry, cancellation, outage and an unrelated tenant. The loopback contract rehearsal **does not** satisfy this gate by itself.
3. **P0 — Recovery test.** Restore production-style backups to isolated volumes/databases, verify application and secret-key restoration, and document an audited rollback path.
4. **P0 — Source/deployment reconciliation.** Preserve and reconcile existing locally modified FFPRO, Tiquet, Marketing and other production checkouts before any `main` merge or automated CI/CD deployment.
5. **P1 — Trial reminder lifecycle.** Implement idempotent reminders and validate recipients and unsubscribe/notification policy.
6. **P0 for paid launch — Payment entitlement proof.** V79-02 manual bank verification and live merchant checks are separate outstanding work. Do not allow unverified payment claims or sandbox checkout to activate paid plans.
7. **Approval.** Require founder sign-off, maintenance window, database backup and a no-loss rollback plan.

## Current draft PRs

- Hub: [#92](https://github.com/MrFixITslu/V79hub/pull/92)
- POS: [#6](https://github.com/MrFixITslu/V79POS/pull/6)
- FFPRO: [#39](https://github.com/MrFixITslu/FFPRO2/pull/39)
- Tiquet: [#19](https://github.com/MrFixITslu/V79Tiquet/pull/19)
- Marketing: [#23](https://github.com/MrFixITslu/V79Marketing/pull/23)

All five are intentionally **draft** and must remain unmerged until all required gates have passed.


## Recovery evidence — latest October 8 database snapshot

Actual compressed PostgreSQL dumps from the Acer's scheduled backup were restored
into a short-lived **PostgreSQL 17** container with Docker networking disabled,
resource limits, temporary in-memory data directories and no published ports.
`pg_restore --exit-on-error` succeeded for all five databases:

| Database | Restored public tables | Result |
|---|---:|---|
| FFPRO | 21 | PASS |
| Tiquet | 20 | PASS |
| Hub | 1 | PASS |
| POS | 78 | PASS |
| Academy | 8 | PASS |

Hub state was queryable after restore, including 2 organisations and 0 explicit
plan records, matching the observed production aggregate. Temporary database
copies and disposable restore containers were removed after the exercise.
The original laptop backups were retained untouched.

**Limitations:** full application boot, encrypted-file/key recovery, external
integrations, time-to-recovery and other non-PostgreSQL persistence remain
untested. PostgreSQL 16 could not read the dump generated by 17; use a 17+
`pg_restore` for this backup generation.

## Legacy organisation staging analysis

Read-only counts verified one separate active non-owner organisation with
one active owner membership and five enabled app entitlements. It does *not*
share the platform owner's Hub user identity. No real customer identifiers
are included here and no billing evidence was inferred.

A pure offline approval helper, `approveReviewedLegacyTrial`, now models either
a founder-approved first trial (14 days from an explicit approved-at timestamp)
or continued restricted review. It refuses to grant a paid plan without a
separately verified V79-02 payment workflow; refuses unverified approvers,
owner-organisation reclassification, repeated trial activation and inadequate
reasons. Neither the migration-preview CLI nor this helper can write to
PostgreSQL. **No actual customer classification or migration was applied.**

### Release blockers still outstanding

- Founder must approve the existing customer's classification before any
  live migration or fail-closed policy activation.
- Independently verify that each connected app enforces the entitlement
  decision on authenticated HTTP and real-time/background work as applicable.
- Reconcile production-local source modifications and rehearse deployment
  and rollback on restored application data (including required secret keys).
- Implement and test trial reminders, billing fallback and customer
  communications. Do not merge draft PRs without the release decision.

## Recovery key-presence and backup confidentiality review

The October 8 protected Hub runtime archive was checked without extracting or
printing secret values. It contains the POS owner-identity JSON, Ed25519 signing
private key and Hub .env. The laptop rsync snapshot also includes the owner's
.v79-secrets directory. This is file-presence evidence only, not a tested
application boot after restoring all credentials.

Hardening gap: the current backup script does not set a restrictive umask.
The latest PostgreSQL dumps and Hub runtime archives are mode 0644; snapshot
directories are commonly 0755. The laptop home/firelion directory is currently
0750, limiting traversal to its owner/group, but copied archives could be
read by unintended local users. Raw .env and database dumps are not encrypted
within the backup tar/gzip archives.

A hardening-only copy of the laptop backup script was prepared at:
/home/firelion/v79-staging-backup-hardening/v79sl-backup.sh
It sets umask 077 and owner-only permissions on snapshot directories.
Bash syntax and dummy-file permission checks passed (0600 files, 0700 dirs).
The active timer and backup script were NOT changed. Applying the patch,
tightening historical snapshots and encrypted offsite backup require a
separate approved backup-maintenance step. Do not delete existing snapshots
until their retention and recovery dependencies have been reviewed.


## Founder-approved existing-customer cutover — 8 October 2026

**Explicit decision:** The one currently active, non-owner customer organisation
is approved to receive one fresh **14-day beta trial**, beginning **only when
V79-01 is activated**. This is not a confirmation of historical payment,
does not grant an immediate trial, and does not authorise production deployment.

The development-only pure planner, `prepareApprovedLegacyCutover`, enforces:
- The protected Vision79 organisation and active founder-owner membership match.
- Exactly one separate, active customer organisation exists, with precisely
  one active customer-owner membership.
- Five distinct, enabled customer app entitlements are preserved without
  widening their bundle.
- Already paid/activated plans are never replaced; duplicate plans are refused.
- New trial dates are computed at the **actual cutover timestamp** in UTC,
  not the date of this approval, and the expiry is exactly 14 days later.
- Repeating the migration cannot reset or prolong a trial.
- Changed customer/owner records or changed entitlement counts abort safely.

**Production read-only preflight (8 October):** One active internal owner
organisation/membership, one other active customer organisation, one customer
owner membership, five distinct enabled app entitlements, and zero explicit
subscription plans. Only aggregates were printed; no customer identifiers,
emails, credentials or financial details were displayed.

**Transaction rehearsal:** A temporary PostgreSQL 17 cluster with
`--network none`, one deliberately synthetic Hub state document, and
an explicit staging-only marker was used to test the repository's
revisioned JSONB update approach. The staging runner required a fixed
staging database name, local Unix-domain socket, explicit operator flag and
matching sentinel record. A dry run caused no changes. Simulated activation
at 16 Oct 2026 09:30 UTC produced expiry at 30 Oct 2026 09:30 UTC, preserving
the customer's five test entitlements; replay two days later returned
`alreadyApplied=true` and left the database at revision 2, not 3.
Those dates are **synthetic rehearsal values only**.

The runner, `scripts/rehearse-approved-cutover.mjs`, is deliberately
restricted to the staging database; it is not a production migration tool.

**Remaining production controls:** A separately reviewed cutover procedure
and database writer, approved maintenance window and rollback; source
reconciliation; product-level authenticated HTTP and real-time checks;
backup of application secrets and full recovery rehearsal; trial reminders
and customer communications; and final founder GO/NO-GO decision. If the
live database changes from the observed baseline, migration must stop
pending re-review.

## Authenticated downstream application staging — 8 October 2026

This iteration validated real application authentication middleware with
synthetic identities and isolated transport/data fixtures. All development
code remains on its own unmerged feature branch. No production revalidation
feature flag was enabled.

| Product | Staging evidence | Local result |
|---|---|---|
| FFPRO | Actual Express Hub-session guard and signed mock Hub checks; existing session, different scoped user, cancellation, Hub outage, expiry, and public health route | 90 tests passed; TS and build passed |
| Tiquet | Actual JWT-authenticated Express route with mocked data adapter; tenant mismatch, suspended/deleted accounts, cancellation, outage, invalid JWT | 8 HTTP/contract tests passed |
| Tiquet staff WebSocket | Admission/heartbeat guard verifies JWT expiry, current staff account and signed Hub access; isolated policy tests | 5 WS policy tests passed; TS and build passed |
| Marketing | Actual JWT-authenticated Express middleware, isolated SQLite, signed local Hub simulation, two tenant mappings, revocation and outage | 39 tests passed; TS and build passed |
| POS | Actual Fastify authentication hook, real signed POS sessions, isolated Prisma membership fixture; tenant scope, entitlement revocation, error path, membership deactivation | 21 tests passed; TS and build passed |

Two additional integration defects were fixed on their feature branches:
- FFPRO rejected health requests carrying an expired Hub session cookie; public
  health/liveness/logout no longer depend on customer trial validity.
- POS turned an unexpected Hub-entitlement-check exception into HTTP 500;
  it now returns controlled access denial.

All connected app updates were pushed as drafts, not merged. The isolated
tests are NOT equivalent to a five-service environment backed by independent
real databases and full queue/worker/WebSocket production routes.

### Residual release gates

1. Current unlinked native/local customer sessions can bypass Hub revalidation
   in some products; decide and implement an explicit migration/enforcement
   policy without inadvertently blocking authorised internal owner operations.
2. Marketing publisher and platform-event workers, Tiquet non-HTTP paths,
   and POS offline/payment/outbox jobs require cancellation and expiry policy
   verification. A customer session guard does not automatically revoke
   asynchronous work already queued.
3. Tiquet WS heartbeat runs every 15s and shares the standard up-to-30s
   positive Hub cache; revocation is bounded but is not instantaneous at the
   millisecond expiry boundary. Confirm the maximum permissible revocation SLA.
4. Full feature-enabled service-to-service tests must verify actual secret
   mapping, DNS/Docker routing, callback URLs, existing sessions, account
   mappings, customer app entitlements, and operator-only admin isolation.
5. Reconcile dirty production working trees, prove full app/key/file recovery,
   confirm backup confidentiality and trial messaging, and obtain a separate
   final founder GO/NO-GO decision.

## Trial reminders and cutover-mode legacy session/worker enforcement — 8 October 2026

Founder-approved 14-day customer beta starts only at the future activation instant.
V79 Hub now has an opt-in reminder scheduler, disabled by default and requiring
both V79_TRIAL_REMINDERS_ENABLED=1 and one designated
V79_TRIAL_REMINDERS_WORKER_LEADER=1. It delivers operational emails via the
existing Resend configuration to the verified owner membership of the customer
organisation. Reminder stages are seven days remaining, one day remaining and
expiry. Durable store events record sending, delivered and failed outcomes,
plus backoff and at most four retries; a crashed sending claim requires manual
review rather than blindly resending duplicate messages. The planner suppresses
cancelled/invalid trials, owner organisations, invalid recipients and stale
notices when the scheduler resumes after downtime. Outbound production delivery
has not been activated or tested with a real customer email.

The connected product draft branches now reject legacy local-only authenticated
sessions when subscription enforcement is enabled:
- FFPRO: still-valid Passport login without a Hub-managed session is not an
  entitlement, even if a previous local authentication succeeded.
- Tiquet: standalone local user JWTs without a Hub org/user mapping are denied.
- Marketing: local JWTs without a Hub business/user mapping are denied.
Their existing login and auth configuration remains unchanged while the
feature flag is disabled. Existing internal-only accounts must be migrated
or explicitly reviewed for Hub linkage before activation.

Marketing scheduled publishing now rechecks a stored author-to-Hub identity
before processing, and immediately before irreversible provider submission.
It leaves queued posts untouched while access is paused; no publish attempt
is made without a valid signed Hub grant. The isolated SQLite + real worker
test passed paused -> entitled -> revoked, including a zero-delivery check
while paused. The worker does not use a browser-supplied author identity.
Audit/payment event outboxes are not identical to discretionary customer
publishing: they may require delivery for accounting consistency after a
subscription expires; blocking them globally could lose required records.

Local tests: Hub 94 passed, Marketing 47 passed, FFPRO 90 passed, Tiquet
authenticated/WebSocket targeted regression tests 10 passed. Hub and Marketing
TypeScript validation and Marketing application build passed. These are
feature-development results, not a production deployment approval.

**Additional blockers**: verify live sender identity/domain and trial
communications; ensure exactly one Hub scheduler leader; reconcile legacy
internal accounts before enforcing Hub-only sessions; full five-service
networked staging and rollback remain outstanding.

## Current-main reconciliation and deployment configuration audit

All isolated V79-01 feature branches were updated with the latest GitHub
origin/main without touching the production working trees. FFPRO required
one conflict resolution in env.example (upstream file preserved, disabled
entitlement flag restored). Its 33 intervening main commits are incorporated
into the feature branch. No production main merge or deployment occurred.

Regression tests following reconciliation:
- Hub: 94 tests, TypeScript and Vite build passed.
- FFPRO: 99 tests, TypeScript and Vite/esbuild build passed.
- Tiquet: 10 targeted authenticated/WS checks, TypeScript and Vite build passed.
- Marketing: 50 tests, TypeScript and Vite/esbuild build passed.
- POS: 21 API tests, TypeScript and build passed on its up-to-date branch.
GitHub CI subsequently succeeded for all five feature commits, including
Marketing RED TEAM and FFPRO production-readiness checks.

The read-only scripts/release-config-audit.mjs checks signing secret
consistency, application networks, Hub internal endpoints and email sender
presence. Unit tests cover mismatched keys, fallback semantics, missing mail
and misrouted Hub URLs. It does not print secrets and never modifies Docker.

Important correction: the general Hub and POS platform secrets are different,
but Hub's DEDICATED V79_POS_PLATFORM_SHARED_SECRET matches POS's current
platform secret. Therefore POS's effective signing key is aligned; an earlier
simple general-secret comparison was misleading.

Current configuration blocker: the running Hub has no RESEND_API_KEY or
V79_HUB_EMAIL_FROM configured, so its feature-flagged beta-trial reminders
cannot yet send. A verified sending-domain identity, provider configuration,
test inbox delivery and opt-in review are required before activation. The
Hub/FFPRO/Tiquet/Marketing signing secrets match their configured counterparts,
and the application containers share proxy_network with valid Hub URLs.

This audit validates configuration prerequisites, not full deployment
readiness: real service-to-service staging, production cutover/rollback,
application assets and key recovery, queued background-job policy, founder
login migration and founder final go/no-go remain outstanding.
