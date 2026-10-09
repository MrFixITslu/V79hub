# Phase 3A — Independent non-production security review (2026-10-09)

**Disposition: HOLD FOR RELEASE.** This document records review findings only. No app runtime, database, secrets, or production deployment is changed.

## Verified
- Exact-head GitHub Actions run 37880604144 completed successfully for commit 2ef2fc91992d1949bb9f437f3d8b226e67ca9539.
- Decision-only ledger restricts operations to five fixed draft categories and fixes `executionStatus` to `disabled`.
- Tests include mandatory MFA happy path, same-origin rejection, idempotency, revision conflicts, expiry, cross-organisation isolation, and JSON/PostgreSQL persistence. Existing test results are not a substitute for a staging exercise.
- No PR review has been submitted yet.

## Outstanding security findings
1. **HIGH — Evidence provenance:** `evidenceRef` is accepted based on syntax alone. Before treating a proposal as grounded, validate evidence against a server-side, tenant-bound, signed or otherwise authenticated investigation record with freshness and source checks. Until then label it an unverified reference.
2. **HIGH — MFA negative-path coverage:** The integration test proves the MFA-complete path; add tests that older/non-MFA owner sessions and a session with MFA enrollment but no challenge completion cannot access proposal APIs. Review session enforcement in `server.ts` before asserting any vulnerability.
3. **MEDIUM — Audit integrity and retention:** `appendAgentProposalAudit` truncates audit events after 5,000 records. Provide durable append-only or tamper-evident retention before any actionable stage; document export and retention.
4. **MEDIUM — Multi-writer coordination:** The proposal queue serializes within one process. Verify multiple instances, shared store writes and crash/retry behavior; do not assume database revision checks alone provide distributed locking.
5. **MEDIUM — Data minimization:** Regex filtering is incomplete PII protection. Keep synthetic aggregate-only input and test adversarial Unicode, obfuscated secrets, multiline PII, and prompt injection.
6. **MEDIUM — Inbox completeness:** The API returns 100 newest records and stores at most 500 per organisation. Add paging/archival policy so pending approvals are never silently hidden or destroyed.
7. **BLOCKER — Restore evidence:** Issue #104 documents an isolated PostgreSQL restore rehearsal ending in exit 137. Do not claim rollback readiness until an isolated full restore passes without touching production workloads.

## Phase 2C / model tool calls
- Phase 2C issue #99: implement narrow read-only item-level contracts separately, with per-tenant authorisation, evidence timestamps, bounded fields, explicit unknown states, and no raw customer PII.
- Ollama issue #97: deterministic specialist routing avoids model-dependent tool calls. Keep native tool-call capability degraded/unverified until synthetic cold/warm benchmarks demonstrate reliability. Do not expose write tools to the model.

## Required tests before founder release review
- MFA-negative-path and role/cross-tenant tests; origin and CSRF checks.
- Concurrent duplicate submission and stale revisions across independent Hub processes.
- Expired/replayed proposal, audit completeness, and evidence tampering.
- Disposable staging end-to-end workflow with outbound write/network call detection.
- Successful isolated backup restore, recovery verification and rollback rehearsal.
- Exact-SHA CI re-run after fixes, founder visual acceptance, and **separate explicit release approval**.

**Hard guardrails:** Keep PR draft/unmerged. No production deploy, customer onboarding, billing, email or autonomous execution. Preserve beta data and credentials.
