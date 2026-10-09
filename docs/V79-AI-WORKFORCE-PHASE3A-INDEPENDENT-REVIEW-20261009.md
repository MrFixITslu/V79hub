# Phase 3A — Independent non-production security review (2026-10-09)

**Disposition: HOLD FOR RELEASE.** This document records review findings only. No app runtime, database, secrets, or production deployment is changed.

## Verified
- Development CI [run 408](https://github.com/MrFixITslu/V79hub/actions/runs/37922020664) succeeded for code SHA `70450c5f6a5c23791ca69ab40b7e26f1cf409622` (164/164 Hub tests, 42/42 agent tests, Docker verification; publishing/deployment skipped). Every subsequent documentation/code change requires another exact-head check.
- Decision-only ledger restricts operations to five fixed draft categories and fixes `executionStatus` to `disabled`.
- Tests include mandatory MFA happy path, same-origin rejection, idempotency, revision conflicts, expiry, cross-organisation isolation, and JSON/PostgreSQL persistence. Existing test results are not a substitute for a staging exercise.
- No PR review has been submitted yet.

## Outstanding security findings
1. **HIGH — Evidence provenance (PARTIAL MITIGATION; SOURCE AUTHENTICITY OPEN):** The authenticated Hub-to-agent response now mints *temporary, opaque, owner-and-organisation-scoped* receipts only when an investigation finding exactly matches an `available` read-only evidence-ledger metric and timestamp. Proposals claiming evidence must submit the bound receipt; expired, edited, cross-tenant, mismatched-system and forged receipts are rejected. The resulting proposal is labelled `proxy_attested`; manual proposals remain `unverified`. **This verifies consistency within one agent proxy response, NOT independent signature verification against each original application.** Receipt registry is per-process and expires after 10 minutes; restart, replica mismatch or other failure fails closed. Release requires authenticated source-side evidence provenance and multi-instance coordination.
2. **HIGH — MFA session binding (MITIGATED IN BRANCH; STAGING PENDING):** Session records now carry `mfaVerified` only after completing the server-side challenge. Approval routes reject password-only owner sessions and disabled MFA; previous sessions default unverified. Isolated negative-path and MFA success tests are included. Re-test restart, older-session and browser behavior during disposable staging.
3. **MEDIUM — Audit integrity and retention (KEYED DETECTION IN BRANCH, INDEPENDENT RETENTION OPEN):** Proposal events are now also written to a dedicated HMAC-SHA256 linked `agentProposalAuditTrail` alongside the proposal mutation. The owner inbox and both write endpoints verify event integrity **and** the signed event-to-proposal state linkage. Edited/reordered events, wrong signing key and missing decision tails with unchanged proposals fail closed. The audit is persisted in Hub JSON/PostgreSQL store; no audit records are silently truncated. Signing uses `V79_AGENT_AUDIT_HMAC_KEY` if set, otherwise the existing configured Hub security/platform key for development compatibility. The signer key MUST remain stable; rotation requires a separately tested migration. **Important:** The record chain and proposal snapshots remain in the same mutable store. This is keyed tamper detection, **not an independently anchored, immutable or write-once record**. An attacker with signing key access or an independently rewritten store can defeat it; protected external retention, checkpoint anchoring, backup and key management are release gates.
4. **MEDIUM — Multi-writer coordination (STALE-WRITER REJECTION TESTED; MULTI-PROCESS OPEN):** Proposal writes serialize within one Hub process. PostgreSQL store revision CAS rejects a second writer's stale snapshot rather than overwriting state; synthetic repository tests now exercise explicit reload+reapply and preservation of both signed proposals. These are independent persistence objects in one test process, **not** real multi-process simultaneous traffic. A multi-container PostgreSQL test, deployment strategy and crash/retry policy remain release gates. JSON file mode has no distributed writer lock; prohibit multi-replica JSON write deployment.
5. **MEDIUM — Data minimization (PARTIAL MITIGATION):** Normalized screening now applies to summary, rationale and decision notes, including fullwidth characters and zero-width formatting. Regex remains incomplete PII protection. Keep synthetic aggregate-only inputs; test adversarial obfuscation, account references and prompt injection independently.
6. **MEDIUM — Inbox completeness (PAGINATION IMPLEMENTED IN BRANCH):** Inbox sorts live pending proposals first (at most 80 per organisation), reports visible/total counts and now supports bounded 100-record history pages through an offset-validated owner-only GET API and a load-older UI control. The 500-record store cap and lifecycle/archival policy remain unresolved.
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
- Reject unrelated application prefixes, forged/missing/expired or other-owner evidence receipts, changed proposal fields and stale aggregate metrics. The UI displays `proxy_attested` with explicit source-verification limits, or `unverified` for manual drafts.
- Verify all live pending records remain in the bounded first page even when recently decided records exceed 100; subsequent pages expose all decisions without duplication.
- Exercise MFA negative path and successful plan-only approval under a mandatory-TOTP owner session.
- Verify simultaneous idempotent submissions result in one proposal and configured synthetic downstream application receivers observe **no unsafe HTTP methods** during proposal/decision tests. This is a targeted test, **not** a complete network-isolated staging proof.
- Reject obfuscated email/contact values and fullwidth secret labels, including in decision notes.
- Verify audit overflow refuses unaudited changes without truncating previous audit events. Additional tests now verify a dedicated keyed proposal-audit chain survives JSON/PostgreSQL reloads; mismatched HMAC, event insertion/reordering, altered proposal state and a removed decision tail fail verification.
- Hub CI [run 408](https://github.com/MrFixITslu/V79hub/actions/runs/37922020664) completed successfully on commit `70450c5f6a5c23791ca69ab40b7e26f1cf409622`, with **164/164 Hub tests** and **42/42 agent tests**. A separate synthetic agent proxy integration test checks decision-only approval with no downstream write methods. **Run CI again on the final head after any new commits.**

## Outstanding release steps
1. Fully isolated end-to-end staging on a disposable environment with outbound write detection and browser acceptance.
2. Introduce durable, independently verified, tenant-bound *source-issued* investigation evidence with application signatures and per-adapter freshness. Current `proxy_attested` receipts are not original-source attestation and do not coordinate between replicas.
3. External append-only audit retention and independently anchored signed checkpoint (current keyed chain is stored alongside mutable proposals), audit-signing key rotation, real multi-process atomicity, retention/archival policy for the 500-record cap and privacy classification.
4. Complete an actual successful isolated PostgreSQL restore following issue #104; preserve live beta data and avoid global Docker restarts or pruning.
5. Re-run full CI for the **final** exact commit SHA and obtain explicit founder approval separately before production merge/deployment.

**Hard guardrails:** Keep PR draft/unmerged. No production deploy, customer onboarding, billing, email or autonomous execution. Preserve beta data and credentials.
