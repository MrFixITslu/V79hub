# G1 Development Worker v0.1 — internal supervised drafts

**Status:** DRAFT / disabled by default / owner-only / no repository or production writes.
**Stack:** G1 executive candidate `75291868e9392d82fdb31cfbc59ffb80b7d41d86`.
**Release posture:** Does not override Hub feature freeze, source parity, approval or customer security gates.

## What is implemented

- `POST /api/agent/development-proposal` under the **existing internal agent token guard**, with the existing owner-context check, local Ollama provider requirement, and separate `V79_DEVELOPMENT_PROPOSALS_ENABLED=1` opt-in. Default response: 404 (disabled).
- A validated work order pins one exact V79hub Git commit, one task ID and 1–3 exact `agent-service/src/*.ts` or `agent-service/tests/*.test.ts` files with source blob identifiers and short source excerpts.
- A local Ollama prompt proposes *unverified* single-file diffs plus test ideas, summary and risks. Model output is checked against the exact requested paths, size limits and a narrow diff envelope.
- Every accepted response explicitly reports `sourceVerifiedAgainstGitHub=false`, `diffApplied=false`, `testsExecuted=0`, `gitWrites=0`, `productionWrites=0`, `ownerApprovalRequired=true`.
- The module can be tested with an injected fake proposer without calling Ollama, a shell, GitHub or the running applications.

## What is intentionally NOT implemented

No background worker, issue polling, untrusted repository checkout, patch application, CI execution, PR creation, Sentinel scanning, customer email, deployment or owner approval automation. Work-order source hashes are **caller-supplied**, not independently verified. A passing JSON/diff validator does not establish that a patch applies, compiles, is safe or is useful. Exact source verification and isolated tests must happen in a later executor under separate authorization.

## Security constraints

Only `MrFixITslu/V79hub` agent-service code is in this first slice. The currently Acer-resident Sentinel NOC has not completed its independently reviewed source import to a dedicated repository, so no Sentinel code paths are permitted yet. Do not pass .env files, credentials, billing secrets, PII, customer exports or production logs as source excerpts. The adapter refuses nonlocal model endpoints; it never provides a model with API credentials, tools or shell access.

The existing `/api` token check executes before this route. Invalid owner context returns 403. Missing opt-in returns 404. Invalid task returns 400. Rejected or unavailable model drafts return 502. The route sets `Cache-Control: no-store`.

## Acceptance plan

1. Run `cd agent-service && npm ci && npm run lint && npm test` in a disposable checkout pinned to the exact draft SHA.
2. Verify disabled-by-default and missing-token requests fail closed against a fresh isolated agent process. Never use existing accounts to bypass the owner check.
3. Use a **synthetic** Hub source excerpt and fake Ollama first. Confirm valid draft returns zero writes, invalid paths/JSON are rejected and no unrequested files are included.
4. In approved internal-only staging, optionally enable flag for a bounded local Ollama call. Compare output against pinned GitHub file blobs before *considering* patch application.
5. Require a separate reviewed implementation for source authentication, isolated worktree construction, test execution, PR branch publishing, trusted CI, owner approval and rollback. Do not grant a general-purpose shell or GitHub token to the model.

## Progression toward full AI development operations

- v0.1: review-only proposals (this PR)
- v0.2: deterministic source fetch and SHA matching; isolated checkout and patch dry-run; no production access
- v0.3: supervised disposable branch + test runner + audited draft PR creation via narrow executor
- v0.4: CEO/COO backlog orchestration, deterministic quality gates, approval inbox and controlled release promotion
- Sentinel: separate source/privacy inventory and release lane, then allowlisted CI-backed proposals

Every step keeps CEO strategy/approval routing separate from COO engineering execution. The founder retains final authorization for deployment, security policy changes and customer-facing actions.
