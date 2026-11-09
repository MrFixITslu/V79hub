# V79 Hub organisation-name release candidate — 9 November 2026

**Status: Prepared only. NOT APPROVED, NOT DEPLOYED.**

This is a new candidate, not a change to the previously accepted R18 release. The accepted-blob gate in `tests/r18-reconciled-candidate.test.mjs` must remain intact until a separate reviewed release acceptance supersedes it.

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
- The main V79 CI/CD workflow fails the exact accepted-release blob gate **because the protected source changed**, not because that test was bypassed.
- Marketing PR #38: V79 CI/CD, REDTEAM, Studio browser/media journey and desktop/mobile acceptance passed at its validated feature commit.
- Tiquet PR #61: isolated security acceptance succeeded; integrated Hub-managed workflow tests are under CI verification.

## Required approval and safe release

1. Independently review the exact diff and tests (including concurrent write, same tenant but wrong owner, malicious names, downstream unavailable, same-origin and HMAC checks).
2. Reconcile the currently running Hub and Tiquet image/source provenance, environment variables, signing keys and persistent data volume without exposing secrets.
3. Sign off an immutable new release manifest by the responsible owner. Only then update the accepted-source policy/guard for a **new** release; never quietly replace the old R18 pins.
4. Back up Hub store, Tiquet DB and Marketing SQLite plus uploaded media; preserve the old pinned image/rollback checkpoint.
5. Run a real signed Marketing→Hub→Tiquet change with a disposable tenant and confirm no cross-tenant updates before production.
6. Deploy in order: Hub, Tiquet, Marketing. Fail closed if any dependency isn't ready. Perform post-deploy authenticated browser and tenant checks.

**Operational blocker:** Desktop Commander remote calls are paused due to the monthly account allowance. Do not infer an approved production deployment from passing CI.
