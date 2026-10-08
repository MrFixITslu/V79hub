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
