# P1 CEO/COO owner workboard — G3 source candidate

**Date:** 2026-10-15. **Status:** DRAFT / NOT DEPLOYED / FEATURE FLAG OFF.

Commercial SaaS launch remains **Hub + Tiquet only**. This change does not turn V79 Academy, Marketing, POS, FFPRO, Sentinel or any other secondary app into a commercial offering.

## Brainstorm and REDTEAM — chosen path
1. Deploy a new autonomous management service: rejected; duplicates existing signed G2 work queue and introduces uncontrolled actions.
2. Show GitHub status directly in browser: rejected; risks exposing private Sentinel token and bypassing founder-only evidence controls.
3. **Selected:** add a disabled-by-default, owner-MFA-only, read-only adapter to the existing Hub Owner Assistant. Keep source register separate from trusted runtime monitoring.

REDTEAM residual risks: GitHub is not the system of record for runtime health; closed PR does not prove merged/deployed; public/private repository permissions can vary; redirect could leak tokens; GitHub fields can contain hostile prompts; API may be unavailable; repeated scans may hit rate limits; live G3 has a protected WiPay overlay. Fixed allowlisted URLs, GET only, redirects refused, one-megabyte streaming cap, timeouts, no GitHub-controlled title/body text, unknown states, and disabled default. No runtime rollout until review, restore and authorization.

## Source changes
- Server: server/owner-coo-workboard.mjs; fixed repo/issue/PR register, no mutations, bounded API fetch and no GitHub-controlled text passed through.
- Hub route: GET /api/agent/coo-workboard, gated by existing ownerApprovalContext requiring verified session MFA.
- UI: src/components/OwnerCooWorkboardPanel.tsx under existing OwnerAssistant beside executive review and separate signed work queue.
- Tests: tests/owner-coo-workboard.test.mjs using Node built-ins, negative checks for unauthorized, token missing, disabled, redirect, body overflow, pagination, prompt injection.
- Isolated CI: .github/workflows/coo-workboard-isolated.yml; no image publication, server deployment or release worker change.

## Configuration — DOCUMENTATION ONLY, NOT APPLY TO PRODUCTION NOW
- V79_COO_WORKBOARD_ENABLED=1: allow operator-initiated owner-only GitHub reads, default off.
- V79_COO_GITHUB_TOKEN_FILE: future protected path for a separate fine-grained read-only token, only with approved staging and safe custody.
- The token file must be a non-symlink regular file, 0400/0600 (not group/world-readable), 16–512 bytes, with a trimmed single-line token of 16–256 characters. Unreadable/malformed token fails closed.
- Never use admin credentials or broad classic PAT; no browser tokens; no customer PII.
- Flag off: DISABLED. Missing token: NOT_CONFIGURED. Denied private repo: UNKNOWN_SOURCE.
- Review egress, secret custody, source staleness, request rate, API availability, and owner browser staging acceptance.

## Base/reconciliation
This candidate branches from accepted G3 tracking source feature/marketing-production-20261014, not the older default main. Does not touch pinned WiPay, billing, Tiquet session rules, release worker, Sentinel collector, or Marketing publishing.

Separate [draft Hub #153](https://github.com/MrFixITslu/V79hub/pull/153) remains a CLI-only offline candidate based on main. Do not merge both unrelated baselines wholesale or maintain two live schedulers. This G3 owner UI is the native integration lane; reconcile curated tasks before any eventual merge.

## Required gates
1. Exact-head CI green, security/source diff review. Previous ECR 429 failure is not a pass.
2. Independent review of owner MFA route, token file permissions, GitHub network scope and task labels.
3. Compare installed G3 images to source, confirm encrypted restore and pinned WiPay rollback.
4. Explicit owner approval for an isolated staging run with flag enabled, test owner and unauthorized sessions.
5. Separate authorized immutable candidate release GO. No real customer invitation, payments or autonomous actions from this feature.

## Status semantics
OPEN_IN_GITHUB means only that an issue/PR appeared on queried open list. NOT_LISTED_AS_OPEN is **not** the same as closed, fixed or deployed. UNKNOWN states must stay visible. Runtime health, deployed revision, customer launch and Sentinel coverage remain UNKNOWN / NOT_ESTABLISHED and approval/execution false, regardless of GitHub state.
