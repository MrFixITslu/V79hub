# Phase 3A — Independent non-production security review (2026-10-09)

**Disposition: HOLD FOR RELEASE.** This document records review findings only. No app runtime, database, secrets, or production deployment is changed.

## Verified
- Exact-head GitHub Actions run 37880604144 completed successfully for commit 2ef2fc91992d1949bb9f437f3d8b226e67ca9539.
- Decision-only ledger restricts operations to five fixed draft categories and fixes `executionStatus` to `disabled`.
- Tests include mandatory MFA happy path, same-origin rejection, idempotency, revision conflicts, expiry, cross-organisation isolation, and JSON/PostgreSQL persistence. Existing test results are not a substitute for a staging exercise.
- No PR review has been submitted yet.

## Outstanding security findings
1. **HIGH — Evidence provenance (OPEN):** references are now constrained to the declared application and always labelled **unverified** in the ledger and owner UI, but they remain client-supplied. Before treating a proposal as evidence-backed, validate against a server-side, tenant-bound, authenticated investigation record with freshness checks. Do not describe this partial mitigation as evidence authentication.
2. **HIGH — MFA session binding (MITIGATED IN BRANCH; STAGING PENDING):** Session records now carry `mfaVerified` only after completing the server-side challenge. Approval routes reject password-only owner sessions and disabled MFA; previous sessions default unverified. Isolated negative-path and MFA success tests are included. Re-test restart, older-session and browser behavior during disposable staging.
3. **MEDIUM — Audit integrity and retention (PARTIAL MITIGATION):** Proposal audit no longer truncates existing events; at 10,000 shared audit events it fails closed instead of deleting history. This is still a mutable application store, **not** a tamper-evident append-only audit. A protected durable audit table, retention/export strategy and operational capacity alerts are needed before actionable stages.
4. **MEDIUM — Multi-writer coordination:** The proposal queue serializes within one process. Verify multiple instances, shared store writes and crash/retry behavior; do not assume database revision checks alone provide distributed locking.
5. **MEDIUM — Data minimization (PARTIAL MITIGATION):** Normalized screening now applies to summary, rationale and decision notes, including fullwidth characters and zero-width formatting. Regex remains incomplete PII protection. Keep synthetic aggregate-only inputs; test adversarial obfuscation, account references and prompt injection independently.
6. **MEDIUM — Inbox completeness (PARTIAL MITIGATION):** Inbox now sorts live pending proposals first (at most 80 per organisation) and reports visible/total record counts. Older decisions remain outside the first 100 records; add paging, archival and retention before release. The store currently caps 500 proposals per organisation.
7. **BLOCKER — Restore evidence:** Issue #104 documents an isolated PostgreSQL restore rehearsal ending in exit 137. Do not claim rollback readiness until an isolated full restore passes without touching production workloads.

## Phase 2C / model tool calls
- Phase 2C issue #99: implement narrow read-only item-level contracts separately, with per-tenant authorisation, evidence timestamps, bounded fields, explicit unknown states, and no raw customer PII.
- Ollama issue #97: deterministic specialist routing avoids model-dependent tool calls. Keep native tool-call capability degraded/unverified until synthetic cold/warm benchmarks demonstrate reliability. Do not expose write tools to the model.

## Required tests before founder release review
- MFA-negative-path and role/cross-tenant tests; origin and CSRF checks.
- Concurrent duplicate submission and stale revisions across independent Hub processes.
- Expired/replayed proposal, audit saturation/fail-closed behavior, and evidence tampering.
- Disposable staging end-to-end workflow with outbound write/network call detection.
- Successful isolated backup restore, recovery verification and rollback rehearsal.
- Exact-SHA CI re-run after fixes, founder visual acceptance, and **separate explicit release approval**.

## Isolated automated checks added on the feature branch
- Reject unrelated application prefixes and unverified evidence claims; display unverified state clearly.
- Verify all live pending records remain in the bounded inbox even when recently decided records exceed 100.
- Exercise MFA negative path and successful plan-only approval under a mandatory-TOTP owner session.
- Verify simultaneous idempotent submissions result in one proposal and configured synthetic downstream application receivers observe **no unsafe HTTP methods** during proposal/decision tests. This is a targeted test, **not** a complete network-isolated staging proof.
- Reject obfuscated email/contact values and fullwidth secret labels, including in decision notes.
- Verify audit overflow refuses unaudited changes without truncating previous audit events.
- Hub CI run [389](https://github.com/MrFixITslu/V79hub/actions/runs/37917860392) completed successfully on commit `95c06245222a4f3ebadad35ebcce4c6d3c883bae`, with 159/159 Hub tests and 42/42 agent tests. Newer commits require a fresh exact-SHA pass before claiming branch readiness.

## Outstanding release steps
1. Fully isolated end-to-end staging on a disposable environment with outbound write detection and browser acceptance.
2. Design and test genuine tenant-bound investigation provenance; never equate a validated reference string with authenticated evidence.
3. Implement durable tamper-evident approval audit, multi-instance atomicity, proposal history paging and privacy classification.
4. Complete an actual successful isolated PostgreSQL restore following issue #104; preserve live beta data and avoid global Docker restarts or pruning.
5. Re-run full CI for the **final** exact commit SHA and obtain explicit founder approval separately before production merge/deployment.

**Hard guardrails:** Keep PR draft/unmerged. No production deploy, customer onboarding, billing, email or autonomous execution. Preserve beta data and credentials.
