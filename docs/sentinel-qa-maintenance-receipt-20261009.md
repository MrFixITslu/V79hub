# Sentinel QA Hub-only maintenance receipt — 2026-10-09

## Approved scope
User approved controlled maintenance checks, isolated restore, full-Hub integration review, and eventual Hub-only Sentinel test-tenant deployment if all release gates pass. Mandatory condition: delete all test-only organizations/accounts once testing ends, preserving existing organizations and users.

## Environment and preconditions
- Acer development checkout: /home/firelion/V79-Sentinel/hub-cleanup-staging
- Candidate commit: a56b0bb877c48cbe6433a0696db09a5e961a37e3
- Server: 192.168.100.163, existing Hub Git HEAD: 1fae5211e187623b5a1e68eca1ac5aebb88f59e0
- Live Hub and v79-hub-postgres: running, healthy; public HTTP 200
- V79_SENTINEL_QA_CREATE_ENABLED and V79_SENTINEL_QA_CLEANUP_ENABLED: DISABLED on server

## Isolated PostgreSQL restore drill: PASS
- Input: /home/firelion/v79-backups/pre-copy-handoff-20261009/hub-db.pgcustom
- SHA256SUMS: verified.
- Docker image: postgres:17-alpine, matching backup database version 17.11.
- Temporary container: v79-sentinel-restore-20261009 with --network none, no published ports, no persistent volumes, tmpfs storage, read-only backup bind.
- pg_restore --no-owner --no-privileges --exit-on-error: completed successfully.
- Restored public.v79_hub_state: 1 row.
- Restored state JSON type: object.
- Restored revision: 52.
- Positive revision/state validation: 1 row.
- Temporary container: confirmed REMOVED.
- Production database: no writes or restore actions performed.
- An initial post-restore assertion and a second startup-readiness check failed before the successful isolated retry; the successful full restore and validation run completed with process exit code 0.

## Staging regression
- Candidate full Hub suite: 200 passed, 0 failed; TypeScript and patch checks passed.
- Separate PostgreSQL repository tests passed; full HTTP handler suite passed on disposable JSON store.
- Full Hub's existing MFA/session tests passed as part of regression suite.
- Live deployment of candidate: NOT PERFORMED.
- Real synthetic organization/users: NOT CREATED.

## Outstanding gate / tool safety restriction
The attempted creation of a new isolated full-Hub admin-login/MFA/tenant-lifecycle integration test script was blocked by remote tool safety checks. No alternate path was used to circumvent the restriction.
This gate remains UNVERIFIED. A reviewed, tool-supported isolated full-Hub integration process is necessary before deploying the feature.

## Release decision: HOLD
Do not enable Sentinel account features, deploy the staged Hub candidate, create a test organization, or attach external product tenants until the complete integration test and release review are authorized and verifiably successful.

## Follow-up hardening — 2026-10-09

- Added a fail-closed foreign-reference scan for **surviving** Hub user, organization and membership records. If any non-Sentinel record contains a Sentinel synthetic identifier, cleanup now refuses deletion.
- Discovered that eight independent Hub audit-trimming locations could previously discard a Sentinel creation marker after 5,000 events, making later deletion impossible.
- Added `server/sentinel-audit-retention.mjs`, a bounded audit retention helper that preserves Sentinel creation markers while trimming the oldest ordinary events. Applied it to server.ts and the onboarding, team invitation, POS, FFPRO, Tiquet, Marketing and Sentinel cleanup modules.
- Added `tests/sentinel-audit-retention.test.mjs` with 5 tests, including retention after over 5,200 subsequent audit events, multiple markers, malformed inputs, and a contract ensuring all known trimming locations use the helper.
- Added 3 foreign-reference rejection scenarios to `tests/sentinel-qa-cleanup.test.mjs`.
- New full Hub regression: **205 tests passed, 0 failed**; `npm run lint` and `git diff --check` passed.
- All work was performed on the Acer staging checkout. **No Hub deployment, test-account creation, or live user deletion occurred.**
- **Release status: HOLD.** The earlier full-Hub authenticated integration test was blocked by the remote tool safety checks and was not bypassed. A separately authorized integration workflow, independent security review, background-write quiescence verification, and verified test-tenant deprovision remain required before any account creation or deployment.
