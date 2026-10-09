# V79 Sentinel QA tenant — guarded release gate

**Review date:** 2026-10-09 (AST)
**Stage:** Acer-only Git checkout at `/home/firelion/V79-Sentinel/hub-cleanup-staging`
**Production Hub:** 192.168.100.163; source HEAD observed `1fae521`
**Deployment decision:** HOLD. Do not push/merge/deploy or enable live flags yet.

## Verified

| Gate | State | Evidence |
|---|---|---|
| Source TypeScript lint | PASS | `npm run lint` |
| Baseline Hub tests | PASS | Full `npm test` including existing login, MFA, sessions, subscriptions and tenant contract tests |
| Sentinel public route HTTP | PASS | 13 localhost-only integration checks using the shared production route handlers, disposable Hub JSON persistence |
| Sentinel PostgreSQL repository | PASS | Two in-memory PostgreSQL-compatible tests: persistence/teardown and revision CAS conflict with unrelated data preserved |
| Synthetic identity privileges | PASS | Only `overview` permission; strict operator identity required to create/delete |
| Synthetic state cleanup | PASS | Create→preview→delete, separate user sessions revoked, unique creation audit required |
| Unexpected references | PASS | Fail-closed if any other collection, billing item, app tenant, audit record or unknown future field references the test org/users |
| Staged request-level write fence | PASS | Global HTTP write tracking, pending-store-write guard, rejection of overlapping mutations; four unit tests plus HTTP test |
| Hub middleware ordering | PASS | Three source contract tests verify fence before API handlers and Sentinel routes after Hub authentication |
| Existing Hub health | PASS | Running healthy; public HTTP 200 |
| Live Sentinel feature flags | PASS | Both creation and deletion flags disabled in live Hub environment |
| Preexisting Hub backup integrity | PASS | 2026-10-09 `pre-copy-handoff` SHA256 manifest valid; PostgreSQL archive structurally readable; Hub data tar readable |

## Remaining release blockers

1. **Other Hub mutations:** A staged global HTTP write fence now tracks ordinary HTTP mutations and pending Hub store saves, refuses a Sentinel mutation if another write is active, and rejects new HTTP writes during the brief Sentinel commit. Tests pass. **Residual:** asynchronous background jobs, pre-existing external provisioning calls and any additional Hub processes must be quiescent; this must be verified under a supervised maintenance window. A fully integrated live-server concurrency/traffic test has not been performed.
2. **Full live-application integration:** Existing Hub mandatory MFA and persisted-session tests pass, but the new Sentinel routes have not been exercised against the complete real Hub auth and MFA stack under an isolated single-node deployment. Do not claim this passed based only on the loopback harness.
3. **Backup restore drill:** Archive integrity validated, but no isolated live-backup restore drill was performed as part of this release.
4. **Cross-application tenant teardown:** FFPRO, Tiquet, Marketing and POS provide partial platform/member provisioning APIs. Full org/workspace deprovision with verification is not established. **Do not provision external app tenants** during current Hub-only QA.
5. **Operational authorization:** A short supervised maintenance/test window is required before enabling either feature flag. Must preserve existing Hub owner and all existing customer/beta orgs.

## How to advance safely

- Independently review the staged global HTTP write fence, verify that async background jobs are quiescent, and test write isolation against the complete Hub application under maintenance conditions.
- Test full Hub auth/MFA+Sentinel route combination in an isolated and *explicitly loopback-bound* disposable Hub staging instance. No live customer data copied to the Acer.
- Run a true restore drill on isolated infrastructure using an authorized backup; preserve restore and SHA256 evidence.
- Run an independent code/security review and prepare a version-pinned rollback and pre-deploy DB snapshot.
- Once all are green and an approved maintenance window is active, enable only the Hub-local Sentinel routes briefly. Create one `Sentinel-QA-<uuid>` organization with one synthetic owner + two synthetic non-owner users. Run read-only authenticated smoke tests, **immediately delete these exact resources**, verify they are absent and invalidate synthetic sessions, then disable both flags.
- For later FFPRO/Tiquet/Marketing/POS tests, add **separate native cleanup verification** per application first.

## Safety contracts

- Neither a generic organization delete endpoint nor an automatic background deletion task may be introduced.
- Any unexpected reference or failure to complete safe cleanup stops the process for operator review.
- Never delete/migrate accounts, organizations, tickets, invoices, assets, training records or application tenants belonging to existing users.
- Do not store synthetic passwords in source control, Git patches, CI logs or dashboards.
- Existing Sentinel Acer public availability and unauthenticated QA monitoring remain unaffected.

## Final Acer development validation — 2026-10-09

- **200 Hub automated tests passed, 0 failed**, including dedicated guard tests, isolated HTTP JSON-store tests, PostgreSQL-compatible repository tests, and normal Hub MFA/session tests.
- TypeScript lint passed; `git diff --check` passed.
- The new staging module `server/sentinel-write-fence.mjs` tracks state-changing HTTP requests and in-flight Hub store saves. It holds a short exclusive window for Sentinel create/delete, rejects ordinary writes while active, and aborts if another write was already in progress. This has been tested in isolation, but background tasks/multi-instance deployment still need review.
- `tests/sentinel-qa-route-order.test.mjs` verifies that the global fence precedes routes and the guarded Sentinel endpoints come **after** Hub's authentication middleware.
- `tests/sentinel-qa-postgres.test.mjs` verifies one complete synthetic lifecycle with the Hub PostgreSQL repository against a `pg-mem` fixture; it does not connect to or restore the live PostgreSQL database.
- Synthetic owner/staff/viewer accounts have only `overview` permission in their own isolated organization. Only the existing genuine platform operator can invoke the lifecycle routes.
- The read-only review of linked apps found team-member deprovisioning paths, but **not** complete tenant deletion across all four apps. External app provisioning must stay disabled for Sentinel QA until explicitly verified.
- Live Hub remains at its original source revision; its Sentinel creation and cleanup flags have both been observed **disabled**.
- **Release decision remains HOLD.** The next irreversible boundary is live deployment and creation of an organization on the shared Hub; obtain a supervised maintenance window and complete the independently isolated restore drill first.

## Superseding isolated full-Hub verification — 2026-10-09 (AST)

See [full-Hub verification receipt](sentinel-qa-full-hub-verification-20261009.md). Full real Hub authentication, mandatory operator MFA, three synthetic logins, guarded creation/deletion, preserved-field cleanup refusal, session revocation across restart, and PostgreSQL commit contention are now verified using synthetic Acer fixtures. Full regression: **207 passed, 0 failed, 0 skipped**. Separate full-stack run on PostgreSQL 17.11: **2 passed, 0 failed, 0 skipped**. Lint, build and patch checks passed. This closes the full-Hub integration blocker above. The documented isolated PostgreSQL 17 restore drill closes the earlier restore blocker.

Live persisted state remains revision 52 with 2 users and 2 organizations; before/after fingerprints match exactly. Live flags remain disabled. No live QA records were created. Final production security/release review, fresh rollback/snapshot evidence and immediate maintenance-quiescence checks are still required; external app deprovision remains unverified and excluded. **Production deployment remains HOLD.**
