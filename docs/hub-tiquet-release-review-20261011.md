# Hub + Tiquet release reconciliation review

Status: NO-GO. Feature freeze; source-only drafts and read-only inspection only.
This is an internal release-engineering review, not independent security certification.

## Exact reviewed candidates

| Candidate | Head | Verified PR run | Result |
| --- | --- | --- | --- |
| Hub #129 | `40e7d4fb0306299f82811d9591384934b2937862` | [38166287572](https://github.com/MrFixITslu/V79hub/actions/runs/38166287572) | Validation/build and isolated PostgreSQL race passed; approval/publish/deploy skipped |
| Tiquet #31 | `0d74bee6d1ab92b1aebbb46016b378dc0a989322` | [38166116147](https://github.com/MrFixITslu/V79Tiquet/actions/runs/38166116147) | Validation/build passed; approval/publish/deploy skipped |
| Tiquet #30 | `9b4c71b5498004bd6713d621c97669caa580f543` | [38164724791](https://github.com/MrFixITslu/V79Tiquet/actions/runs/38164724791) | Validation/build passed; approval/publish/deploy skipped |

Published Hub main is `c45d305b98d6080c07a5d2e35f7941a8ef15f4ce`;
published Tiquet main is `1edae1033d349d0dc99e7cb5fadaf84c39018a33`.
PR checks use GitHub's generated merge ref, associated with each exact head and
the recorded base. They are not tests of the currently running private images.

Recommend **#31 as canonical for the Tiquet immutable-commit approval gate**.
#30 and #31 diverge from the same published baseline: #30 adds two static
workflow assertions; #31 adds 17 checks including executable acceptance/denial
of both approval blocks, rechecks the variable before production access, and
serializes deployments. Neither pins a registry digest or verifies restore.
The follow-up HOLD draft builds on #31; its cumulative diff must be reconciled
with #31 before any future merge. Leave #30/#31 open until owner decides which
PRs to consolidate or close. No closure or merge was authorized.

## Review findings

| Priority | Finding | Evidence and consequence | Safe disposition |
| --- | --- | --- | --- |
| P0 | Hub deployment changes unrelated services | #129 deploy script builds all Compose services, removes three named collisions with `docker rm -f`, and force recreates the entire project | Replace legacy entry point with unconditional HOLD; future apply must target only the verified existing Hub service with no dependency recreation |
| P0 | Coordinated script can remove containers and affect four apps | Existing ecosystem script removes unlabelled containers and deploys Hub, Tiquet, Marketing and FFPRO | Disable the coordinated entry point before any command; no other app source changes |
| P0 | Tiquet target still starts dependencies and builds on host | #31 retains `compose up -d --build service`, without `--no-deps`; no digest binding | HOLD before source copy, dependency start or production access |
| P0 | Restore/rollback is not a release prerequisite | None of the reviewed entry points validates an isolated restore receipt or compatible old image/database pair | HOLD until signed-off, exact-image restore/rollback evidence exists |
| P0 | Source freeze does not equal runtime parity | Local Hub `585f701...` and Tiquet `81f4659...` differ from published main; samples are incomplete | Run redacted audit; retain all unpublished functionality; no partial checkout/archive replacement |
| P0 | Commit approval does not bind image bytes | Tags `latest` and 12-character SHA remain mutable; remote builds can differ from CI-published image | Future release record must bind approved commit + build run + registry digest + platform image ID and verified revision/provenance |
| P1 | #129 guard checks presence of four modules only | Docker inventory/state/exec failures are blocked, but a changed nonempty module is accepted; shell `test -s` can confuse inaccessible files with absence | No claim of complete preservation; compare all server/auth/billing/SSO/tenant modules and modes against an approved manifest before future apply |
| P1 | Tiquet startup itself performs writes | `server/db.js` runs schema DDL, possible SQLite migration, default-account insertion and template seeding during initialization | Never import it for an audit; verify schema compatibility and restored migration behavior before any authorized restart |
| P1 | Credential creation precedes old Hub source guard | Old script may generate token files before preflight | HOLD removes that path; preserve all existing secrets and modes |
| P1 | Old failure diagnostics may expose sensitive values | Tiquet failure path forwards Docker logs/health output | HOLD removes this path; audit suppresses raw diagnostics and health logs |
| P1 | Production protection is unverified | Branch-protection reads returned 403 integration-access denial; environment protection is not available through this connector | Owner inspect current settings read-only; absence of access is not absence of protection |

#129's Docker error handling and parsing repair are correct within their limited
scope; existing application files are unchanged and CI passed. #31's full SHA,
manual-main dispatch and operator variable comparisons deny absent/mismatched
approval. Neither closes the deployment, source preservation or independent
security gates. The follow-up HOLD is a temporary safety barrier, not a finished
immutable deployment implementation. Main/running services remain unchanged.

## Runtime evidence and preservation inventory

These are **owner-reported earlier observations**, not a new server inspection:

| App | Running tag / image ID | Local source object |
| --- | --- | --- |
| Hub | `v79hub-wipay-return:585f701`; `sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30` | Commit `585f70160d74c06cf745adeaee7f418e89be9cf7`, tree `a288e9ab831193605ecd9cff6598e31b18a5a1a7` |
| Tiquet | `v79tiquet-sentinel-dark:81f4659`; `sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b` | Commit `81f46592fa0f3d43d103bcc5202c492918c1b9b7`, tree `d57c61de0892b2943db507527d101e519aa82ea2` |

Both were healthy. Hub seven sampled runtime files match its local commit.
Tiquet five sampled server/schema files match its local commit. Its runtime
lockfile differs only in package-entry `dev` flags: 535 entries each, no added or
removed entries, no compared version/resolved/integrity/dependency differences.
This does not verify installed dependencies, top-level lock equivalence or builds.
Tiquet ingestion and legacy-auth probes were OFF, entitlement recheck ON; probes
did not verify application dotenv overlays. Fresh evidence is still required.

Hub's owner-confirmed main-to-runtime-commit stat has **15 files, 871 additions,
12 deletions**. Preserve pending semantic review:

- `server.ts`, `server/platform-owner-billing.mjs`, `server/wipay-provider.mjs`:
  authentication/authorization, session MFA, SSO launch/consume, tenant-bound
  billing and WiPay return behavior must be reviewed as a combined release.
- `server/sentinel-grant-operator.mjs`, `server/sentinel-service-entitlement.mjs`,
  `server/sentinel-service-grants.mjs`: existing Hub-local service/grant modules;
  preserve bytes and disabled/approved configuration. Names alone do not prove
  routes are active or authorize changing them. Do not edit these modules here.
- `src/App.tsx`, `src/components/Login.tsx`: preserve the running login/navigation
  experience and guards; generated `dist` still needs build provenance.
- Five corresponding tests and two staging docs preserve evidence; a diff stat
  does not establish their semantics or coverage.

Tiquet's sampled entry point/schema match draft #29 bytes, while three Hub-auth,
access and provisioning files match the released core. This is not proof that
all #29 was promoted, that its schema was applied, or that ingestion is enabled.
The local published baseline object was missing despite a non-shallow repository.
Do not fetch/reset/rebuild to repair that gap; compare Git blob manifests without
changing the repository. Core Tiquet release readiness does not depend on enabling
pending Sentinel ingestion.

Fresh server execution is currently blocked by Desktop Commander's monthly quota.
Device listing and ping worked; the read-only command was rejected before execution.
The supplied audit is therefore **prepared and fixture-tested, not run on production**.
No credential, source contents or customer record is needed in the returned report.
Report exact unpublished behavior only after comparing the full source inventory
and reviewing private local diffs; do not assume this inventory is exhaustive.

## Test evidence distinctions

- Hub #129 main suite: 309 passed, 0 failed, 1 skipped; isolated PostgreSQL
  race tested separately 1/1, 0 skipped; additional project suite 42/42.
- Tiquet #31: release approval suite 17/17 and core suite 26/26, no skips;
  integration commands and frontend/Docker builds passed.
- Tiquet #30: workflow run green; counts are not independently extracted here.
- Approval, publishing and deploying jobs were **skipped**, not successful releases.
- The new audit uses synthetic Docker/Git responses and redaction assertions;
  its PostgreSQL metadata probes are syntax checked, not live schema verification.
- Live restore/rollback, real MFA/SSO/tenant human QA, current Resend/provider/KYC,
  legal/finance acceptance and independent security certification are **not performed**.

Follow-up source-only drafts keep every application and Sentinel module unchanged.
No merge, deployment, restart, credential/setting change, live fixture, outbound
customer message or payment activation was performed. See issue #128 for current
draft heads and their final CI evidence; do not treat this static review as approval.
