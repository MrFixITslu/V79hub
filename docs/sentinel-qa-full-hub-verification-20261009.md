# V79 Sentinel full-Hub integration verification — 2026-10-09

## Decision

**Isolated development checks PASS. Production deployment remains HOLD.**

Continued from Acer staging commit 6f21a8d3a8252922aaf412c6315fba4fb05eabee in /home/firelion/V79-Sentinel/hub-cleanup-staging.
No push, merge, deployment, live feature-flag change, live synthetic organization, or live-account mutation was performed.

## Changes

- Added tests/sentinel-qa-full-hub.test.mjs. It starts the actual server.ts and exercises real Hub passwords, mandatory operator TOTP MFA, cookies, persisted sessions, and the actual Sentinel routes.
- Added explicit V79_HUB_BIND_HOST support; the isolated tests enforce and inspect a 127.0.0.1-only Hub listener. The existing deployment default is preserved.
- Fixed Sentinel reference scanning to include unknown schema fields retained by the persistence envelope. The full Hub tests demonstrate that a reference hidden in a persisted extension now blocks deletion.

## Results

| Check | Result |
| --- | --- |
| Final full regression suite with disposable PostgreSQL 17.11 | 207 passed, 0 failed, 0 skipped |
| Earlier full regression suite with disposable PostgreSQL 16.15 | 207 passed, 0 failed, 0 skipped |
| Full Hub JSON + PostgreSQL 17.11 verification | 2 passed, 0 failed, 0 skipped |
| TypeScript lint | PASS |
| Production build | PASS (existing bundle-size advisory) |
| git diff --check | PASS |
| Existing production Hub and PostgreSQL health | Healthy; source remains 1fae521 |
| Existing live Sentinel feature flags | Creation and cleanup both disabled |
| Production DB fingerprint before/after final verification | Exact equality; revision 52; 2 users; 2 organizations |
| Synthetic cleanup and process/datastore teardown | PASS; no isolated test processes or data directories remain |

PostgreSQL server packages were unpacked only beneath a temporary Acer directory; no operating-system package installation, persistent cluster, Docker change, or system service was created. Both disposable database instances listened only on a Unix socket in a private directory, with TCP listening disabled. Hub listeners were checked against ss and bound only to loopback.

PostgreSQL 17.11 matches the live database major/minor version; the disposable test distribution is Ubuntu, while the prior authorized restore drill used postgres:17-alpine. The previously documented PostgreSQL 17 isolated backup restore remains separate evidence; no customer backup or customer data was copied into these Acer fixtures.

## Full-Hub behaviors verified

- Anonymous requests cannot create or delete QA organizations.
- The platform operator cannot receive an authenticated session before mandatory MFA enrollment and correct TOTP verification.
- Invalid TOTP, reused MFA challenge, and treating a challenge ID as an authorization token are rejected. Mandatory operator MFA cannot be disabled.
- The operator's encrypted MFA enrollment and authenticated session survive restart. A subsequent login completes the existing-enrollment TOTP verification path without disclosing the setup secret; challenge replay is refused, and explicit logout revokes the new session.
- Default-disabled lifecycle routes return disabled responses to the authenticated operator.
- Real unrelated customer/workspace-owner sessions cannot invoke operator routes.
- Missing or foreign Origin headers are rejected for protected mutations.
- A tracked unfinished ordinary HTTP mutation prevents Sentinel creation.
- Exact confirmation creates one Hub-local organization and three accounts: owner, staff, viewer.
- All three accounts successfully log in through real password authentication, have overview-only permissions, and cannot access another workspace or operator routes.
- Synthetic passwords are hashed, omitted from persisted state, and not logged; persisted session files contain token hashes rather than usable cookie tokens.
- No app tenant, entitlement, plan, billing, email/invitation, or recovery records are created by the lifecycle.
- Duplicate QA creation and targeting an existing customer organization are rejected.
- Foreign external app mappings and unknown persisted schema references block both cleanup preview and deletion, preserving the entire state.
- Incorrect deletion phrase, stale preview hash, and invalid origin are rejected.
- A real PostgreSQL row lock holds the cleanup commit in flight. Ordinary login/logout requests return 423 and a second Sentinel mutation returns 409 until the lock is released.
- Successful cleanup removes the exact QA organization, memberships, three identities and their sessions, while preserving all unrelated persisted records and adding the deletion audit.
- All deleted account credentials and old synthetic cookies fail afterward, including after another Hub restart.
- Existing unrelated operator/customer cookies continue working. Creation and cleanup flags are returned to disabled in the isolated instance.
- Temporary Hub processes, database processes and fixture data directories are removed by teardown. An initial test helper incorrectly treated signal termination as a running process; this was fixed, and its abandoned synthetic-only directory was explicitly verified and removed.

## Production preservation evidence

Read-only PostgreSQL transactions observed identical values before and after verification:

- revision: 52
- user count: 2
- organization count: 2
- user JSON fingerprint: e8f71accb0a8c13f2c7de8d73037cb99
- organization JSON fingerprint: bdaf37b11278102a5c9eeb6dc473dce7
- full persisted state fingerprint: 4c1ae50c49b7baa2f89695e41b54a6ed

These fingerprints are equality checks, not a substitute for the previously verified SHA256 backup manifest. No user identities, passwords, MFA secrets, session tokens, or customer data appear in this receipt.

## Reproduction

From the staging checkout, point V79_TEST_POSTGRES_BIN at an available complete PostgreSQL server binary directory:

    V79_HUB_BIND_HOST=127.0.0.1 V79_TEST_POSTGRES_BIN=/absolute/postgresql/bin npm test
    V79_TEST_POSTGRES_BIN=/absolute/postgresql17/bin node --test --test-reporter=tap tests/sentinel-qa-full-hub.test.mjs
    npm run lint
    npm run build
    git diff --check

A PostgreSQL test skipped because binaries are unavailable does not satisfy the release gate. An explicitly supplied invalid binary directory fails immediately. Never supply the live DATABASE_URL or DATA_DIR: the harness deliberately generates an isolated environment and ignores inherited customer service credentials and addresses.

## Remaining production release gates

1. Separate security/release review of the final candidate and the preserved-field reference-scan change. This turn performed an implementation review and integration testing, not an independent sign-off.
2. Verify the production maintenance conditions immediately before any cutover: one Hub writer, background jobs and external provisioning quiescent, version-pinned rollback image, and a fresh verified pre-deploy snapshot. Acer concurrency tests do not prove live maintenance quiescence.
3. Keep FFPRO, Tiquet, Marketing and POS external tenant provisioning excluded. Their complete tenant deprovision workflows remain outside this Hub-only release and are not verified by these tests.
4. Only after the production gate passes, perform any approved Hub-only live lifecycle check and verify exact cleanup, then disable both flags immediately.

Existing backup restore and isolated full-Hub MFA/lifecycle testing are no longer outstanding blockers. Live deployment and live synthetic-account creation remain unperformed.
