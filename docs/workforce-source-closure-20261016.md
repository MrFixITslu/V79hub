# V79 AI workforce A01–A12 reconciliation, source versus live acceptance

16 October 2026 (America/St_Lucia). This branch is stacked on Hub draft PR #156 exact source commit 29007104d1a8fbd4639fac59275a7d645f108e73; it is **not a deployment**.

## Source reconciliation
PR #155 head f8e8cc14438c6357274f662c37a10925252d6c62 is an ancestor of PR #156 head 29007104d1a8fbd4639fac59275a7d645f108e73: 67 commits ahead, zero behind. Merge neither independently into main. #156 is the canonical integration candidate. Running Hub has a previously accepted report reader and later accepted UI-only update; Git head does not exactly name the running mixed-image build.

## Completion gates
| ID | Evidence | Remaining acceptance |
| --- | --- | --- |
| A01 | Founder-only COO draft Workboard recorded as accepted | Preserve existing owner-MFA enforcement |
| A02 | PR #155 is exact ancestor of #156; single canonical stack determined | Independent review of cumulative diff and final image/source parity |
| A03 | Owner-confirmed Hub private report history and latest owner workspace deployed in earlier operator session | Fresh live desktop/mobile acceptance and stale-report negative checks |
| A04 | Evening 19:00 AST run evidenced; offline three-day reliability auditor and 11 tests now pass | First unattended 17 Oct 08:00 AST run, complete signed inventory and sustained live acceptance remain unproven |
| A05 | Existing G2 queue + owner-only task UI; offline created-vs-delivered gate and 11 tests now pass | Trusted owner-MFA queue adapter, independent signed delivery evidence, actual safe worker acceptance and UI integration |
| A06 | Six v1 specialist skill packages, CEO/COO orchestration and adversarial test cases committed in this branch | Independently score *actual model responses*; bind trusted evidence only after review |
| A07 | Supervised create_work_item worker code exists, uncertainty latch documented | Independently inspect idle timer and one safe founder-approved action, exact audit and denial |
| A08 | Strict read-only metric schema, separate attestation gate, stale/tenant/synthetic rejection and tests in this branch | Implement independent *real* approved adapters per app; attest end-to-end source, collector, scope and freshness |
| A09 | Deterministic owner-review-only exception drafts and tests in this branch | Verify true incidents, dedup, owner delivery and no-dispatch negatives after source validation |
| A10 | Intentionally no new phone, voice, WhatsApp or email agent action privilege | Dedicated identity, consent, privacy and revocation design; separate integrations/approval |
| A11 | Structured numeric-claim gate, untrusted text projection and fail-closed $20 rolling-30-day spend checks in this branch | Verified provider receipts and actual model hallucination/security/cost evaluation |
| A12 | Autonomous actions still blocked | New separate risk assessment and affirmative founder approval; not authorized by workforce cleanup |

## Hard controls
No production images, settings, worker schedules, tokens, customer data, payments, probes or agent autonomy change through this branch. Failing or missing attestation yields UNKNOWN. Alert proposals do not notify anyone. Passing offline tests prove only source policy behavior, not deployed telemetry or AI expertise. Hub/Tiquet commercial release and Sentinel scanner/security gates remain independent NO-GO decisions.

## Source-only A04/A05 follow-up

At code head `3adf8d7a590cfa5bda9ce631cae392cbdf54bb7c`, isolated [CI #39000783586](https://github.com/MrFixITslu/V79hub/actions/runs/39000783586) passed **44/44** offline source tests. `workforce/quality/briefing-reliability.mjs` and `workforce/quality/task-delivery-gates.mjs` are not wired into production. Owner runbook: [workforce-a04-a05-readonly-acceptance-20261016.md](workforce-a04-a05-readonly-acceptance-20261016.md). A04's 17 October morning observation remains a future run as of this checkpoint, and A05's actual independent worker/delivery acceptance remains outstanding. Neither source code nor test success overrides the live production or Sentinel gates.


## 17 October — A07 operational evidence and A04 report-contract reconciliation

**A07 live evidence (not simulator):** The founder read the signed G2 ledger from the running Hub in a read-only Node command. One explicitly owner-approved harmless internal work item was created exactly once, assigned to COO, with `work_item_created` attributed to `coo-worker`; separate rejected task remained rejected with zero tasks and correct `proposed,rejected` audit. The installed G2 source was tested with in-memory replay/idempotency and refused duplicates; that particular replay check did not touch persistent production data.

**A07 additional isolated boundary test:** `tests/workforce-a07-tenant-boundary.test.mjs` exercises real G2 HTTP route and HMAC temporary ledger contracts with two synthetic organizations. It covers fresh/stale owner MFA, cross-origin denial, tenant-scoped queue/task reads and mutation denial, separate worker token, browser cookie/origin refusal, denied/rejected execution, worker enabled/ready guards and once-only execution. **Do not equate synthetic injected identity with independent live founder session or real cross-tenant evidence.** A07 final operator acceptance and recovery still need sign-off.

**A04 actual Python report coverage format:** the host emits `AVAILABLE` and `INCOMPLETE` uppercase. The draft reliability audit previously required lowercase, so valid independently authenticated host reports would not be recognized. It now normalizes those exact labels while continuing to **require independently authenticated report files and a complete private inventory**. Added tests ensure uppercase incomplete does not become complete and missing proof is denied. This is source only; no timer, report runner or Hub reader was deployed or changed.

**Isolated PR CI on application code:** [workforce specialist gates #39003964952](https://github.com/MrFixITslu/V79hub/actions/runs/39003964952) PASS: **56/56 safety/source tests + 32/32 inherited G2/G3 authorization/UI/report tests**, lint and production build PASS. The separate [scheduled briefings CI #39003964922](https://github.com/MrFixITslu/V79hub/actions/runs/39003964922) also passed. Subsequent documentation-only commit does not alter the application result.

**Next bounded, owner-required evidence:** at/after 17 October **08:30 AST**, collect the 08:00 morning report's status and systemd receipt with the read-only command in `docs/workforce-a04-a05-readonly-acceptance-20261016.md`. Continue a minimum of 3 days of actual morning/evening slots with independent private report provenance, evidence completeness and no-action validation. A05 actual engineering delivery after task creation, specialist model-run evaluations, live app metrics and notifications, and P1 commercial release are still outstanding. No new agent permissions, autonomous action, deployment or customer invites authorized by these source checks.
