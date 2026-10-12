# V79 AI Workforce G1 — Read-only evidence and release-acceptance matrix

**Created:** 2026-10-11  
**Applies to:** proposed CEO + COO G1/G1.1, [draft PR #123](https://github.com/MrFixITslu/V79hub/pull/123), base commit `4704638bc2e7c7241d33b2ce5c86db65c73fa848`  
**Release posture:** **DESIGN AND ISOLATED TESTING ONLY.** No customer usage, agent activation, production deploy, repository merge or autonomous actions. Follow [P0 freeze #127](https://github.com/MrFixITslu/V79hub/issues/127).

This matrix is based on inspected GitHub source code; it does **not** assert that G1 is built into the running Hub/agent-service image. The separate Hub/Tiquet release lane [#128](https://github.com/MrFixITslu/V79hub/issues/128) owns source parity, real DB backups, isolated restores, rollback and production controls.

## A. Evidence and decision boundaries

| Source / layer | Code contract | Verified by CI? | Live evidence proven? | Fail-closed disposition |
| --- | --- | --- | --- | --- |
| Founder context | `isValidOwnerContext` and owner-scoped Hub snapshot | Yes, synthetic HTTP token/owner/cross-org tests | No | Unauthorized 401; missing owner 403; inconsistent signed Hub owner context 502 |
| Hub internal read | `readBusinessSnapshot`: fixed internal Hub snapshot URL, shared service-token request; cross-check owner identity, organization **and 15-minute/120-second freshness bounds on the Hub envelope** | Yes, mock Hub integration plus synthetic envelope clock tests | No production source↔image parity | Missing token/source, HTTP error, mismatched org, stale/future/undated envelope → reject the whole snapshot before COO evidence construction |
| Hub admin counters | `hub_owner_summary` only numeric `users`, `activeSessions`; source time `generatedAt` | New future/stale/undated unit tests in this PR | No | Missing/older than 900s/over 120s future → unknown, not available |
| Product signed aggregates | `evidence.ts` allowlisted numeric metrics and timestamp chronology: product `sourceReportedAt` may not exceed collecting Hub `generatedAt` by >120s; exact 900s freshness limit in milliseconds | Yes, unit + isolated HTTP including 4 deterministic chronology cases | Live adapters currently unverified individually | Impossible source/envelope chronology, unknown, stale, absent, nonnumeric, unapproved fields → no actionable findings |
| COO → CEO report | `prepareExecutiveHandoff`: reviewed finding IDs with numeric source+timestamp evidence only | Yes | No deployed end-to-end workflow | If no verified findings, report incomplete and avoid invented risk |
| Local model preview | `runReadOnlyExecutiveCycle`, off by default via `V79_EXECUTIVE_MODEL_CYCLE_ENABLED !== "1"` | Yes; two mock Ollama model turns | No live model test/activation | Unknown/duplicate/new IDs rejected, dropped findings preserved; fallback deterministic |
| Specialist roster | Exactly CEO + COO; six existing specialist capabilities under COO; existing owner coordinator under CEO | Yes | Metadata not deployed | No third executive or self-issued authority |
| Sentinel trusted feed | No accepted signed production collector → CEO/COO adapter | No; G2 protocol draft #125 security hold | **No** | Entire source unavailable; historical 15 TCP handshakes and public HTTP checks not trusted collector data |
| Actions/approval | No executive action executor in G1; `ownerApprovalGranted=false`, `actionsExecuted=0` | Yes | Not activated | No writes, payments, customer messages, firewall changes, ticket dispatch or auto-deploy |

**Terminology note:** `verifySignedOwnerSnapshot` checks owner/organization context and a parseable Hub-reported timestamp **after** a token-protected internal Hub HTTP read. It does *not* itself perform a payload cryptographic signature verification. Do not claim a cryptographically signed per-record executive feed without validating the actual Hub↔agent trust boundary and source-specific signature contract.

## B. G1 failure-oriented acceptance scenarios

1. **No token:** /api/agent/executive-handoff and preview reject authorization; no Hub fetch or model calls.
2. **Forged / wrong owner flag:** no privileges, no calls, no report.
3. **Cross-org source conflict:** Hub response owner org differs; cannot deliver a report to the wrong tenant.
4. **Future clock drift:** a Hub `generatedAt` more than 120 seconds ahead → **reject the Hub snapshot before all product/owner metrics**; a raw ledger's Hub owner counters independently remain **unknown**, never available due negative age.
5. **Near-future clock skew:** owner-envelope/source timestamp ≤120 s ahead → preserve existing allowed behavior. Envelope timestamps older than 900 s or absent are rejected before any product finding; even a current nested product date cannot rescue a stale/future envelope.
6. **Older than 900 seconds:** product summaries stale; Hub owner counters unknown and not current.
7. **Missing timestamp:** source unknown, never default to "right now".
8. **Unknown or adversarial field:** embedded personal data and prompt strings excluded by numeric allowlist and cannot reach local model ranking.
9. **Ollama outage / invalid JSON / unknown finding ID / duplicate ID / omitted urgent ID:** deterministic safe fallback or permitted ranking; all trusted findings stay present, severity ordering remains priority.
10. **Flag disabled / wrong model provider:** preview 404; no model request or background scheduler.
11. **Integrity of output:** statuses `mode=read-only`, no approval generated, no action executor, external messages 0; never falsely report payments or ticket changes.
12. **Snapshot freshness vs collection freshness:** observation time must be source-originating, not simply the API request timestamp. A nested observation dated more than 120s after the Hub `generatedAt` envelope must not become a CEO/COO finding even if it is recent relative to the local clock. Age and stale boundaries are evaluated in milliseconds; direct calls with missing Hub envelope time fail closed.
13. **Protected baseline:** confirm actual running Hub/agent images include existing Sentinel modules and approval safeguards before considering staging; never substitute partial GitHub main or this isolated PR for production.
14. **Recovery:** fresh encrypted Hub/Tiquet DB backup, offline-recoverable key, actual isolated restore, rollback compatibility and health checks from Agent 2 lane #128.
15. **Human authentication:** genuine founder MFA, seamless Hub→Tiquet SSO, tenant denial, mobile sign-in, logout/session expiry and transactional emails remain independent P0 gates.
16. **Independent security:** GitGuardian finding on historical G2 PR #125 must be privately classified; passing clean PR #126 does not dismiss it. Customer launch additionally requires independent security signoff.
17. **Never re-authorize scans:** prior 15/15 owner-reported Acer→V79 TCP opens are historical, not continuous Edge integration; do not make more network attempts without new owner grant.

## C. Verified CI baseline and known limitations

- G1/G1.1 baseline [GitHub CI run 38096246144](https://github.com/MrFixITslu/V79hub/actions/runs/38096246144): exact G1 source `4704638bc2e7c7241d33b2ce5c86db65c73fa848`, successful validate/build/security and isolated agent tests; one constrained-job Hub suite skip and separate dedicated PostgreSQL approval-race check. No publish/deploy.
- This corrective nested draft PR must pass **exact-head** CI with synthetic tests. It temporarily adds the G1 feature base branch as an allowed pull_request validation target; it does **not** add any production deploy trigger.
- Synthetic tests alone do not certify signed customer metrics, local Ollama operational performance, correct production tenancy, email delivery, live payments or recoverability.

## D. No-input next steps

- Record exact-head CI results; do not call a test passed unless its job completed successfully.
- Document the corrected Hub owner timestamp classification in G0 issue #122 and this nested review PR.
- Reconcile whether any remaining G1 proposed source code has a safety-related logic gap, with a **test first**, and keep it separate from the live Hub/Tiquet release lane.
- Leave the optional model flag disabled. Owner explicitly approves any later exact-SHA G1 staging or production deployment **after** Agent 2's baseline/recovery work and risk review.
- Advance Hub/Tiquet customer discovery through its existing tracker without real customer data in unapproved demo accounts.

**Decision:** This document supplies testable evidence and a future runbook only. **NO-GO** for live executive activation, external Sentinel data, customer/public systems and payments.
