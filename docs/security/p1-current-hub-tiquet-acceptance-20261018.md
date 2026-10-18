# P1 Hub + Tiquet current-source release gate — 18 October 2026

**Status: ISOLATED SOURCE TEST ONLY / PR DRAFT / NO PRODUCTION CHANGE / NO CUSTOMER GO**

## Reconciled source

- Hub `main` base: `df1046151a02dd27db746a2ec5b928f03dcb9b1d`.
- Tiquet current `main`: `7da53ebb71530366168bd72a7efd52b57d34a23c`.
- Tiquet #37 and #40 were merged. #38 `3f0c6587578fb47a34cbacb7420d87793a219240` and #39 `59b8e51fd1c267baecbeb7e42481caaf1eeb05fc` are ancestors of current `main`, despite their draft status. **Do not cherry-pick/merge them again.**
- Existing Hub paired test `tests/paired-hub-tiquet-real-app.test.mjs` pins **older** Tiquet `6f4d93c2f6ed2002eca6fb88bcba0e8bceacdd10`; its pass is not acceptance of today's source.

## Three possible paths and REDTEAM

1. Rerun older pinned pairing: cheap but cannot close source parity.
2. Test the live server: blocked from this connection; risks confusing running source, no owner-approved release or recovery parity.
3. **Chosen:** run full current pinned Hub+Tiquet sources on an ephemeral CI runner with disposable PostgreSQL and two wholly synthetic tenants. Exact sources and network scope are asserted before test. No production interfaces or data.

## Acceptance matrix

1. Hub onboarding/provisioning and signed launch ticket for two independent organizations.
2. One-use Tiquet signed ticket replay is denied without setting a new session.
3. A/B Tiquet customer read isolation and denial of forged cross-organization JWT.
4. A's own client edit allowed, A editing B denied (404), B editing A denied (404); records remain tenant-specific.
5. Synthetic account suspension denies only affected tenant.
6. Tiquet explicit logout invalidates an already-copied JWT through both cookie and bearer headers, without breaking unrelated tenant B.
7. Legacy local login and anonymous access stay rejected.

## Deliberately still UNVERIFIED

- **Hub-only global single logout**: A user clicking Hub logout is not equivalent to an explicit Tiquet logout. Existing reviewer notes indicate Tiquet's previously issued JWT can remain valid up to its expiration. Decide policy and implement coordinated invalidation separately; do not call this passed.
- Real staff/portal WebSocket revocation and reauthorization on the **exact full deployed image**, although source/module plus disposable PostgreSQL checks exist.
- Exact currently running production Hub + Tiquet OCI image, session/mount/Compose configuration parity, independent encrypted restore/rollback.
- Real customer identity, payment eligibility, WiPay mode, or unrestricted AI-agent privileges.

## No-merge/no-deploy boundary

Only source test, CI workflow and this review document may change. No `server.ts`, Tiquet app or database source, IAM permissions, environment, Docker, live endpoints, customer data, billing, release automation or deployments.

Do not merge this test-only PR or any UI branch until the owner separately authorizes and final security/recovery acceptance is established. **Customer release remains NO-GO.**
