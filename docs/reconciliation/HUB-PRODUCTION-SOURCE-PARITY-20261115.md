# Hub source reconciliation gate — 15 November 2026

**Review only. No source merge, live cutover, forced history graft, or feature removal.**

## Confirmed discrepancy

The preserved production-derived worktree at commit 11f1f8a and repository main at commit afefdb9 have **unrelated Git histories** (different root commits, no merge base). A direct merge, rebase, reset or replacement may overwrite newer GitHub features or the preserved runtime source. The two trees differ in **159 files: 110 added, 18 deleted and 31 modified in the preserved tree relative to current main**, with 16,650 insertions and 810 deletions. These are snapshot differences, **not** evidence that every changed line is live or ready to deploy.

The current Hub container reports healthy, with image revision a7cfeb3141e103ee4ee7d88d14d32f50eac48b8c. Neither old worktree HEAD nor GitHub main has been independently proven byte-for-byte equivalent to the image at every path.

## Three approaches / risk review

1. Force the local captured branch onto main: **REJECT**. Could delete new features, tests and security work.
2. Merge unrelated histories with union strategy: **REJECT** as a release shortcut. Conflict resolution is not tenant/auth/financial compatibility evidence.
3. **SELECTED:** maintain the proven container unchanged, preserve its verified encrypted source bundle, compare source by feature and add only reviewed contracts to new branches based on current main. Test each port in isolated Hub+Tiquet+FFPRO+Website staging before deployment.

## Reconciliation order and objective evidence

1. **Source provenance:** extract production image build/tree manifest, hash selected canonical modules, compare with preserved source and main. Export recovery bundle off host and verify decrypt + restore (local encrypted archive is not off-host DR).
2. **Authentication:** preserve owner rails, Google first login, MFA step-up, session expiry/revocation, CSRF, signed SSO redirect to Website/Tiquet/FFPRO/POS/Academy. Run a fresh browser login chain and cross-org negative cases.
3. **Persistence:** enforce PostgreSQL store revision guards, atomic writes/outbox, no JSON fallback for migrated workspaces, tenant-bound organisation renames and preserve unknown fields. Run transaction-race, migration and rollback tests.
4. **CRM and work delivery:** Website lead remains CRM-only until conversion; converted customer/job becomes a Tiquet job; approval creates tenant-safe FFPRO project; review shares only explicitly approved customer files. No silent duplicate ticket creation.
5. **Payments and pricing:** preserve existing subscription, tax and currency rules; do not enable paid Academy membership without signed live merchant proof and approved US$35/EC$94 model; WiPay sandbox is not a live settlement.
6. **Files/Knowledge and Workforce:** project folders, attachments, version controls, approvals and least-privilege agent permissions; no independent unsupervised destructive task dispatch.
7. **Deployment gate:** combined source tests, accepted build, QA browser/device acceptance, complete encrypted off-host backups, tested restore, public checks, rollback and owner-authorised cutover.

## Explicit status

- Local source-preservation Git bundle: AES-256-GCM encrypted, verified on host 15 November. Off-host transfer **NOT VERIFIED**.
- Current production Hub: healthy at review. Production **UNCHANGED**.
- Cross-application live real-payment acceptance: **NOT VERIFIED**.
- Source-level merge into current GitHub main: **NOT DONE**. This draft document is the safety baseline; it does not claim code reconciliation complete.
