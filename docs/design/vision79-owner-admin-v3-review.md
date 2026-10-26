# Vision79 Owner Assistant and Platform Admin — candidate v3

Date: 26 October 2026 (Saint Lucia). Status: REVIEW ONLY — NO PRODUCTION DEPLOYMENT.

## Problem and selected approach

Owner Assistant retained a nearly black interior, faint helper text and a large empty conversation area. Platform Admin mixed dark KPI tiles with light sections, tiny labels and decorative counters. More importantly, missing statistics became zero, a successful statistics response was labelled Healthy, and a failed refresh retained green labels without marking the snapshot stale.

Three approaches were reviewed: visual-only polish; a focused redesign using existing capabilities; and a full platform rebuild. The focused redesign was selected to improve clarity and information accuracy while preserving the existing backend and authorization boundary.

## Red-team findings and response

- Avoid implying agent autonomy: CEO/COO and specialist controls prepare prompts. Sending chat remains explicit. Planning proposals and executable actions are grouped visually but retain distinct labels and handlers.
- Never equate a statistics response with service health: cards now say Statistics available, Partial statistics or Statistics unavailable. The page explicitly explains this boundary.
- Unknown is not zero: missing, nonnumeric, negative or nonfinite counts show a dash. Confirmed numerical zero remains zero.
- Retained data must be visibly historical: failed refresh or a snapshot older than five minutes marks all cards stale. A 401/403 clears the retained private snapshot. Aborted requests cannot restore it.
- Preserve exact approval: task creation, digest/revision approval, expiry, confirmation, worker execution and idempotency implementations are unchanged.
- Avoid wrong customer scope: provisioning attention opens Customers rather than POS. Customer selection and typed confirmation controls are unchanged.
- Prevent cosmetic theme regressions: changes are scoped to the two workspace roots. Browser QA checks light/dark contrast and small-screen overflow.

## Implemented

Owner Assistant opens on Today, a read-only summary of the existing owner action queue. Counts distinguish pending approvals, approved/running work and failed/uncertain/expired follow-up. No count is shown until the response is verified. Empty, unavailable and paused/disabled states remain explicit. Briefing history is available here through its existing manual read control.

Primary navigation is Today, Ask Assistant, Tasks & approvals and Delivery board. Tools & reports groups Email & calendar, Marketing, Tiquet evidence and Executive review. Visited views stay mounted to preserve drafts; task polling remains tied to its active view. Draft handoff opens the existing editor and never queues or approves work automatically. The planning approval inbox is now under Tasks & approvals with a separate explanation.

Platform Admin uses Overview, Customers, Applications, Plans & entitlements and Audit & security. Academy remains accessible through Applications and its overview card, with a return action. The static MFA decoration and admin-area counts are removed. Attention signals appear before application cards. The existing backend activeCustomers calculation is labelled Not suspended because it includes provisioning customers.

No new backend API, dependency, schema, permission, subscription rule, auth flow, launch behavior or execution capability was introduced. The new Today view uses the existing authenticated GET action queue.

## Files

Runtime:
- `src/components/OwnerAssistant.tsx`
- `src/components/OwnerToday.tsx` (new read-only summary)
- `src/components/AdminConsole.tsx`
- `src/components/PlatformAdminOverview.tsx`
- `src/workspace.css`

Validation and review:
- `tests/owner-workspace-ui.test.mjs` (updated initial-view expectations; existing action tests retained)
- `tests/vision79-admin-owner.test.mjs`
- `scripts/vision79-owner-admin-browser.mjs`
- `scripts/vision79-workspace-browser.mjs` (wait for the theme shell after reload before asserting)
- `scripts/vision79-workspace-preflight.mjs` (explicit expanded source allowlist)
- this document

## Verification

- TypeScript and production Vite build: PASS. Existing large-chunk warning remains; no dependencies added.
- Focused component, safety-boundary and action tests: 35/35 PASS.
- Full suite: 659 tests, 647 PASS, 7 FAIL, 5 SKIP. Four failures are the historical accepted Git blobs for App, Sidebar, AdminConsole and HubOverview; three assert the superseded visual-v1 structure/classes. These historical gates were not weakened. They prevent treating this new candidate as the previously accepted release.
- Chromium: 25 primary screenshots and 49 checks, zero page errors and zero external requests. Sizes: 1440, 1024, 768, 390 and 320 pixels, plus desktop dark theme. Sampled body/label/navigation contrast meets 4.5:1; this is not a full accessibility certification.
- Browser checks include prompt preparation without automatic send, chat draft retention, task prefill, delivery navigation, Academy reachability, provisioning destination, stale refresh, admin access denial, owner MFA denial and missing metrics. The only POST in the browser run is the explicitly simulated chat request. No approval, execution, provisioning or deployment requests occur.
- Two additional previous-implementation screenshots and two mobile full-page screenshots support visual review. Previous-implementation renders use source at 7bd2e8234dc4bb4ee36af4d83f9e292d6c5ffb31 and sample data. They are not live production captures.
- Hub regression browser checks: PASS, including persisted theme after reload, signed Tiquet launch href, disabled app behavior, mobile navigation and unauthenticated login/recovery. The harness now waits for the theme shell to render after reload before asserting, avoiding a timing race.
- Server/auth/SSO, subscription handlers, typed customer confirmations, task execution and approval panels are protected by source-boundary tests. Real private-session production MFA and Tiquet SSO acceptance remain pending.

## Evidence provenance

All new screenshots are browser captures of the compiled candidate with loopback fixtures. Every screenshot is labelled SAMPLE DATA / NOT PRODUCTION. Figures are illustrative test inputs, not business results. The earlier production Hub screenshot was reviewed in the previous task; current production Owner Assistant/Admin were not accessed. No illustrative image is used as deployment evidence.

The work environment was replaced during this task. Source was restored from the saved Hub v2 draft PR, changes reapplied, then build, tests and browser verification rerun. The runtime changes are saved in commit 29bd900a6166511b3c13baa13e8edc382fd21d93 on the existing review branch.

## Release recommendation

HOLD production. Next action: the owner reviews desktop Today, Ask Assistant and Platform Admin, then mobile and dark variants. Visual approval must name this candidate and does not itself attest real MFA/SSO behavior.

After approval, prepare a new release acceptance record for the exact reviewed commit and image. Reconcile the historical UI pins against that reviewed source; do not bypass the old release gate or reuse its sealed plan. Capture current production image/config identity, create and verify a fresh encrypted rollback checkpoint, and rehearse the exact Hub-only image switch and rollback with unchanged configuration. Complete private-session sign-in/MFA and Hub-to-Tiquet SSO checks. Keep other apps, database migrations, workforce timers and backend images outside this UI cutover unless the reviewed transaction explicitly requires them.

No production deployment command is issued with this candidate. A safe exact command depends on visual approval, current production identity, the new immutable image and a sealed release plan. Existing production rollback parameters are not assumed from historical receipts.

Source rollback for the runtime redesign is `git revert 29bd900a6166511b3c13baa13e8edc382fd21d93`; the accompanying validation commit must also be reverted when restoring the whole branch. This is source control rollback, not a production container rollback. Production rollback must restore the captured prior image/config from the guarded transaction.
