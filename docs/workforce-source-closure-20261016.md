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
| A04 | Evening 19:00 AST report generated; 08:00 AST first unattended run unproven | Inspect several morning/evening runs, missed-slot behavior, uptime, reporting email if desired |
| A05 | Approved G2 queue and owner-only task UI exist; draft-to-approved path preserved | Real execution receipt, assignment follow-through and live task worker acceptance |
| A06 | Six v1 specialist skill packages, CEO/COO orchestration and adversarial test cases committed in this branch | Independently score *actual model responses*; bind trusted evidence only after review |
| A07 | Supervised create_work_item worker code exists, uncertainty latch documented | Independently inspect idle timer and one safe founder-approved action, exact audit and denial |
| A08 | Strict read-only metric schema, separate attestation gate, stale/tenant/synthetic rejection and tests in this branch | Implement independent *real* approved adapters per app; attest end-to-end source, collector, scope and freshness |
| A09 | Deterministic owner-review-only exception drafts and tests in this branch | Verify true incidents, dedup, owner delivery and no-dispatch negatives after source validation |
| A10 | Intentionally no new phone, voice, WhatsApp or email agent action privilege | Dedicated identity, consent, privacy and revocation design; separate integrations/approval |
| A11 | Structured numeric-claim gate, untrusted text projection and fail-closed $20 rolling-30-day spend checks in this branch | Verified provider receipts and actual model hallucination/security/cost evaluation |
| A12 | Autonomous actions still blocked | New separate risk assessment and affirmative founder approval; not authorized by workforce cleanup |

## Hard controls
No production images, settings, worker schedules, tokens, customer data, payments, probes or agent autonomy change through this branch. Failing or missing attestation yields UNKNOWN. Alert proposals do not notify anyone. Passing offline tests prove only source policy behavior, not deployed telemetry or AI expertise. Hub/Tiquet commercial release and Sentinel scanner/security gates remain independent NO-GO decisions.
