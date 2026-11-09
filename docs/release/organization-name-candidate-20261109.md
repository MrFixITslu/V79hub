# V79 Hub organisation-name release candidate — 9 November 2026

**Status: R19 source fingerprints OWNER-APPROVED on 9 November 2026; NOT MERGED, NOT DEPLOYED.**

This is a new candidate, not a change to the previously accepted R18 release. Owner approved the **two** proposed R19 source fingerprints in the project conversation. The accepted-blob gate in `tests/r18-reconciled-candidate.test.mjs` now records the complete previous R18 pin set and overlays only those two explicitly approved new source hashes; two new R19 guard/test files are also pinned. Every file remains checked with an exact Git blob SHA-1; no fingerprint check was disabled.

## Scope

- Signed, tenant-bound `POST /api/platform/organizations/rename`, called from V79 Marketing only by the authenticated workspace owner.
- Hub remains authoritative for organisation names; the current slug, tenant mapping, permissions, subscriptions and MFA remain unchanged.
- Persist a scoped audit record and broadcast an `ORGANIZATION_UPDATED` message to the active organisation.
- Hub frontend refreshes its displayed organisation name when that tenant-scoped message arrives.
- Tiquet companion PR #61 refreshes both account and Settings labels on the next Hub SSO launch.
- Marketing exact-source PR #39 adds the owner-controlled save flow and consistent theme, FAQ CSV and profile images.

## Exact protected-source hashes (Git blob SHA-1)

| File | Previously accepted | Proposed candidate |
|---|---|---|
| `server.ts` | `6784def9a38d018f87aa85e0d73ec10d65972daf` | `9e0022b0fb83288dc2162e3ffd5a0b49bd4556bd` |
| `src/App.tsx` | `37815fc308b2fc52da7e6c1533a7180a6adb312f` | `d7f2f681ed2afa2858ff9ed31e6605e47ec43c1f` |

New support files: `server/organization-name.mjs` (`9135a55ace25a742e4d416d4c62171e251fcbb23`) and `tests/organization-name.test.mjs` (`ecc6692dd824da32ef9dde59501ee1d548810b63`).

## Evidence available at candidate commit

- Hub isolated staging, workspace onboarding, Tiquet bound-session logout and workforce safety workflows completed successfully.
- Before owner approval, main V79 CI/CD failed solely at the two old R18 accepted-release fingerprints for changed `server.ts` and `src/App.tsx`. At approval, the old fingerprints were retained as history and R19 exact-hash pins introduced; CI must run again and pass before any release is considered.
- Marketing PR #38: V79 CI/CD, REDTEAM, Studio browser/media journey and desktop/mobile acceptance passed at its validated feature commit.
- Tiquet PR #61: isolated security acceptance succeeded; integrated Hub-managed workflow tests are under CI verification.

## Required approval and safe release

1. Independently review the exact diff and tests (including concurrent write, same tenant but wrong owner, malicious names, downstream unavailable, same-origin and HMAC checks).
2. Reconcile the currently running Hub and Tiquet image/source provenance, environment variables, signing keys and persistent data volume without exposing secrets.
3. **Completed for source acceptance only:** owner explicitly approved the two proposed R19 source fingerprints. The approved-hash overlay and historical R18 fingerprints are present in the strict CI guard. Production deployment has **not** been approved.
4. Back up Hub store, Tiquet DB and Marketing SQLite plus uploaded media; preserve the old pinned image/rollback checkpoint.
5. Run a real signed Marketing→Hub→Tiquet change with a disposable tenant and confirm no cross-tenant updates before production.
6. Deploy in order: Hub, Tiquet, Marketing. Fail closed if any dependency isn't ready. Perform post-deploy authenticated browser and tenant checks.

**Rollback checkpoint completed:** production Docker images, Hub and Tiquet PostgreSQL dumps, Marketing SQLite, and application-data snapshots at `/home/firelion/v79-release-checkpoints/20261109-163704` (424 MB) all passed SHA-256 checks; AES-256-GPG encrypted off-host archive on the Acer at `~/V79-backups/V79-release-20261109-163704.tar.gpg` (422 MB) passed decryption and archive-listing verification. This is not a completed bare-metal restore drill.

**Release blockers:** New R19 CI, exact-production-source build compatibility, isolated end-to-end tenant rename, and guarded rollout remain. Desktop Commander remote calls are paused due to the monthly usage allowance; SSH on the Acer was used for checkpoint verification. Do not infer production deployment approval from this source approval or from passing CI.
