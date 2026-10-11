# Prioritized Hub + Tiquet launch blockers

Status: NO-GO. Snapshot 2026-10-11; exact new draft heads/CI results are in issue #128.
P0 blocks any release; P1 must also close before customer/commercial onboarding.
Independent security review is a separate gate from this internal review.

| Priority / gate | Verified evidence | Missing evidence | Owner | Next safe action | Release impact |
| --- | --- | --- | --- | --- | --- |
| P0 Runtime/source reconciliation | Earlier owner image IDs/healthy state; Hub 7 samples match local commit; Tiquet 5 source/schema samples and 535-entry lock comparison | Fresh full manifests, local working tree/overrides, full image/frontend/package build provenance; exact local semantics | Owner runs supplied audit; release agent compares | Redacted read-only audit; private local diff review | No replacement by GitHub main/candidate until all current behavior preserved |
| P0 Unpublished Hub changes | Owner stat: 15 files, 871 additions/12 deletions; entry/billing/WiPay/login/grant modules | Semantic and combined-candidate review, preservation of auth/MFA/SSO/tenant/financial safeguards | Owner controls local source; release agent reviews permitted evidence | Retain current commit/tree; no partial public source export or checkout | Old public archive could remove existing functionality |
| P0 Deployment isolation | #129/#31 CI passed but old scripts have whole-project/dependency/collision behavior | New HOLD draft exact CI/review/owner decision; future immutable single-service apply path | Release agent drafts; owner controls later merge/apply | Test HOLD before all mutation and prod access; leave running services unchanged | Legacy deployment must remain unavailable |
| P0 Immutable image approval | Main-only manual exact 40-char SHA + owner variable in Hub/#31; PR gating tested | Registry digest/build attestation tied to approved tree/run/platform; protected approval/environment evidence | Owner + independent release reviewer | Record digest/ID/provenance read-only; owner inspect settings | Mutable tags and local rebuilds are not approved image identity |
| P0 Backup/restore/rollback | Historical backup work only; audit can list possible file metadata | Fresh consistent encrypted DB/files/secrets snapshots; actual isolated candidate/old-image restores; schema compatibility; RPO/RTO | Owner/operator + independent reviewer | Approve isolated workspace and backup/restore scope after audit | No release without proven recovery; list/hash alone insufficient |
| P0 Migration and data preservation | Tiquet published code runs startup DDL/migration/default/template writes; Hub optimistic revisions/transaction locks exist | Actual catalog/migration state, legacy SQLite migration evidence, restored startup compatibility | Owner/operator | Catalog-only probe; no app module import or live restart | Image rollback alone might be incompatible with migrated DB |
| P0 Human acceptance | Automated CI source tests + prepared A01–A15 plan | Genuine owner MFA, invite-only signup, no-second-login SSO, two-tenant denial, logout/expiry/recovery/mobile checks on exact candidate | Owner approves workspace/fixtures and performs QA | Authorize only isolated synthetic tests first | No customer onboarding based on unit tests alone |
| P0 Independent security | Earlier internal review/limited internal-pilot owner acceptance | External exact combined candidate certification and remediation acceptance | Owner appoints independent reviewer | Supply permitted source/evidence; keep Sentinel audit separate | Customer/free/paid release blocked; own review is not independent |
| P0 Payment/provider and cleared funds | Historical WiPay sandbox work; manual transfer #116 unmerged; source origin/MFA/order controls reviewed earlier | Current merchant/KYC/country/currency/callback/settlement evidence; durable idempotency/restart/multiwriter; finance/legal-reviewed receipts/audit | Owner + WiPay + finance/legal specialist | Documentary confirmation; disposable negative/positive cases with explicit scope | No paid activation, live confirmation or commercial approval |
| P1 Recovery/email | Historical Resend verification/delivery; app source reset/invite flows | Current DNS/provider status and approved actual invite/reset/reminder receipt/deduplication | Owner + provider | Read-only status or separately authorized test inbox send | No claim of deliverable recovery/email workflow |
| P1 Rules and overlapping PRs | #30 and #31 exact CI green; #31 stronger checks/serialization; branch protection API returned 403 | Owner settings evidence and choice to consolidate/close duplicate/overlapping drafts | Owner | Recommend #31 gate baseline; leave all PRs open/unmerged | No automatic merge/closure/settings change |

## Precise owner decisions required

1. Execute/return the already-authorized **read-only** audit. This is the only
   immediate intervention needed because remote execution is quota-blocked.
2. Review the complete private local source/config divergence and select the
   preserved combined candidate; do not publish protected original source by
   assumption. #129/#31 do not match the running local commits in full.
3. Choose #31 as Tiquet approval-gate baseline; authorize any later consolidation,
   closure or merge separately. New HOLD drafts include those earlier heads in
   their ancestry; avoid independently merging overlapping copies blindly.
4. Approve exact isolated restore/acceptance workspace, fixtures, test inboxes,
   backup handling, outbound sandbox scope and teardown manifest. No live tenant,
   founder reset, email, bank-confirmation or payment activation approved now.
5. Appoint independent security and finance/legal reviewers, obtain current
   provider/merchant evidence, and provide read-only protection/settings proof.
6. Only once the whole matrix is verified closed, separately approve an exact
   final release SHA/tree/digest, tested rollback pair and single-service plan.
   Production dispatch/settings/activation remain outside current authorization.

## What the source-only HOLD does and does not prove

It prevents legacy scripts and production CI entry points from reaching source
copy, token creation, dependency/container recreation/removal or remote transfer.
It has no apply/force bypass. It does not manufacture missing runtime provenance,
restore/rollback, genuine MFA acceptance or independent certification. It is a
temporary reviewed barrier while the final release path is designed from verified
live evidence. No application/Sentinel source or production settings are changed.
