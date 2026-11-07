# Hub owner verification and task UX release

The running Hub cleared visible actions on failed mutations, and background polling then cleared the error. Sensitive operations also required a recent MFA challenge without providing an in-place refresh flow.

This release adds a session-bound, rate-limited authenticator step-up with the existing five-minute window, token rotation, same-origin/owner checks and persistence rollback. The frontend preserves the last verified queue and keeps mutation errors visible. Exact action approval, signature checks and revision conflicts remain enforced.

## Scope and provenance

Deployed base: sha256:e605371a5ee8125fbaf73670fd6722811d9ac20eb3f870bbb339c4c5f0a83ecb.
Deployed candidate: sha256:c7f0982300f66a8dd704db113d81b603327dbafbe76f329dc2d6087e5907aad0.
Rollback container: v79-hub-rollback-readiness-20261107.

These files are a guarded exact-runtime patch recipe and supporting tests. They are NOT a complete reconciliation of main with all running Hub overlays. Do not rebuild production from this PR's main-derived tree; first reconcile the existing Google, MFA/SSO, support, skills and workforce work.

## Validation

- Nine isolated security checks pass, including session binding, expiry, invalid-code limits, token rotation, unchanged roles/expiry and failed-persistence rollback.
- Exact candidate boot and synthetic mandatory-MFA login pass in a networkless container with disposable data.
- Controlled synthetic clock verifies the stale-MFA challenge, real TOTP verifier, revoked old session, exact work approval, stale revision denial and no duplicate task.
- Browser synthetic transport checks pass: fresh reuse, one exact retry, cancellation with no retry, unrelated 403 without a challenge, focus restoration. Mobile overflow was corrected; final dialog fits 1440/390/320 CSS px.
- Candidate source and client syntax checks pass. Live health, assets and anonymous denial checks pass; live settings preserved, no database migration and no production task created.
- Encrypted PostgreSQL/config/session checkpoint independently decrypted and hash-verified on Acer. pg_restore list check passed. Prior full-restore evidence was not repeated; no schema migration.
- Owner's real authenticator/browser acceptance remains pending; no owner TOTP or seed was accessed.

## Controls

Never auto-approve a proposal or mint an owner session from an agent token. The step-up module requires an already authenticated MFA-verified founder, verifies a new bound authenticator code when stale, and rotates only that session. No new tenant, provider or deployment permissions are granted. Test clocks and test credentials are restricted to disposable containers.
