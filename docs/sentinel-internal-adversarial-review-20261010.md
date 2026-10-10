# V79 Sentinel — Fresh adversarial technical review (internal)
Date: 2026-10-10 AST
Review type: AI-assisted internal adversarial review, NOT independent third-party approval.
Functional candidate reviewed: `1f90a23d72c6f85f9369daffae47c740b635b1e0`.
Current local branch adds only approval/attestation documentation; this assessment does not change deployable code.

## Scope and inspected files
- `server.ts` platform-operator identity, session-scoped MFA, Hub auth/origin middleware, live write fence, persisted sessions and Sentinel route registration
- `server/sentinel-qa-routes.mjs` creation/status/preview/cleanup authorization and flags
- `server/sentinel-qa-create.mjs` isolated synthetic organization/user generation
- `server/sentinel-qa-cleanup.mjs` exact manifest ownership, denial on unknown references, replay/preview hash, retained audit
- `server/sentinel-write-fence.mjs` HTTP write tracking and exclusive lock during async handling and transport disconnect
- `src/lib/sentinel-qa-client.mjs` and `src/components/SentinelQaAdmin.tsx` supervision and uncertain-outcome behavior
- Dedicated tests for full Hub lifecycle, browser orchestration, cleanup, HTTP routes and write-fence concurrency

## Repeatable local tests
- `V79_TEST_POSTGRES_BIN=/tmp/v79-sentinel-browser-pg17-1q8j9flb/runtime/usr/lib/postgresql/17/bin node --test tests/sentinel-qa-full-hub.test.mjs tests/sentinel-qa-browser.test.mjs tests/sentinel-qa-http.test.mjs tests/sentinel-qa-cleanup.test.mjs tests/sentinel-write-fence-http.test.mjs`
- Result: 38 passed, 0 failed, 0 skipped; disposable JSON and PostgreSQL fixture path; test log: `/tmp/v79-sentinel-internal-review-tests-20261010.log`.
- Historical full suite: 263 passed, zero failed or skipped at MFA-hardened stage (`/tmp/v79-sentinel-mfa-hardening-suite-20261010.log`). The latest test invocation was targeted, not a new complete suite.
- Previous staged npm production audit: zero known vulnerabilities; TypeScript lint and build passed (see preceding release record).
- No production account/organization creation, deletion, feature flag modification, database restore or Hub restart during this review.

## Security observations
- Reviewed route enforcement requires real platform operator identity, MFA completed on the individual session (when `V79_REQUIRE_ADMIN_MFA=1`), and same-origin protected writes. Live Hub has `V79_REQUIRE_ADMIN_MFA=1`.
- Feature gates default off; live QA create/cleanup flags absent, thus disabled. Live reminder leader active, blocking QA mutation during ordinary operation.
- Cleanup checks exact synthetic identity manifest, trusted creation marker and exclusions for billing, mappings, invitations, audit references and future-schema links; preserves deletion audit. Disposable tests verify session revocation and unrelated data.
- Write fence retains disconnected async handlers and refuses overlapping writes, but is single-process; multiple production writers/background jobs must remain quiesced during the maintenance window.
- No confirmed critical/high vulnerability discovered in the inspected code paths. This is NOT a penetration test or independent technical sign-off.

## Findings and release gates
- **P2 — Supervised login coverage:** Browser helper drops all one-time synthetic account passwords immediately (`src/lib/sentinel-qa-client.mjs:1-16`, `SentinelQaAdmin.tsx:48-62`). This is prudent for credential exposure, but the live browser panel by itself cannot run the planned three synthetic account login/permission checks. They passed in isolated full-Hub tests. For live acceptance, either explicitly separate login testing into a controlled isolated harness with secure one-time credentials, or narrow the supervised UI acceptance criterion to create/preview/delete and keep login testing isolated.
- **Release engineering — BLOCK:** Production image is pinned to deployed `1ebe335`, while the current GitHub integration branch/main has newer changes; PR #112 (GitHub integration review at `aa067e6...`) was closed without merge or recorded reviewer approval. Do not deploy Acer snapshot over latest Hub source, discard business-agent overrides, or trigger generic stack deployment. Independently reconcile and retest the immutable combined tree.
- **Governance — BLOCK:** The assistant helped develop this release; this internal review cannot count as an external/independent review. A distinct qualified reviewer should submit identity, exact reviewed SHA, verdict and findings if the release policy requires independence.
- **Operations — BLOCK:** Before a new production cutover, create current backups and validate restore/rollback, quiet reminder and other writers, use a Hub-only pinned image, preserve database/agent/secrets and confirm owner-MFA supervised QA lifecycle; no such new deployment has occurred.

## Disposition
**Internal technical review: completed, targeted tests passed; production promotion HOLD.**
No external independent approval or final release permission asserted. The owner remains the commercial release authority, but must not interpret this report as third-party security certification.
