# Vision79 Hub — premium workspace candidate v2

26 October 2026 · REVIEW ONLY · Production unchanged

## Problem and decision
The owner rejected the technically healthy deployed dashboard. The supplied screenshot shows an oversized dark hero, a disconnected pale app container, dark tiles, 7–11px text and poor hierarchy. PR #205 source confirms that layered theme overrides force dark cards inside a light section, including a nearly invisible section heading.

Three approaches considered: restyle existing elements; rebuild the presentation with shared tokens; replace the frontend. Selected the second: maximum visible improvement with existing business logic retained. The exact older illustrative design was not recovered; this candidate implements the owner's written visual direction and requires new visual approval.

## Candidate source and changes
Base: PR #205 head `796cea94e9b56d8fde023688a19a78adb40d0c2a`. Its release record identifies deployment revision `5b8db879b60a3eeb583b40ec8bda725dcb7c8201`. This relationship is historical evidence, not a fresh inspection of the server.

| File | Change |
| --- | --- |
| `src/components/HubOverview.tsx` | Semantic dashboard layout: compact blue hero, white app cards, performance cards, attention list and data availability panel. Existing fetching, metrics and app filtering unchanged. |
| `src/components/Sidebar.tsx` | Vision79 branding, grouped navigation, active states and readable mobile tabs. Existing permissions, navigation and logout handlers unchanged. |
| `src/App.tsx` | Header spacing and typography; mobile wordmark; light default for new sessions. Saved dark preference respected. Session and navigation logic unchanged. |
| `src/workspace.css` | Scoped light/dark tokens, responsive grids, typography, focus states and reduced-motion behavior. |
| `scripts/vision79-workspace-browser.mjs` | Local built-app browser checks and clearly labelled synthetic screenshots; external requests blocked. |
| `scripts/vision79-workspace-preflight.mjs` | Read-only source allowlist and hashes. No Docker, SSH or deployment. |
| `tests/vision79-workspace-boundary.test.mjs` | Fourteen protections for unchanged backend/auth/launch files, lifecycle/data logic and event callbacks. |
| This document | Audit, QA, release conditions and rollback plan. |

## REDTEAM and evidence
- **Mockup mistaken for reality:** screenshots come from the compiled React app in Chromium with synthetic API responses. Every delivered image is marked as sample data. They prove presentation, not production state.
- **Auth or SSO regression:** login, server, signed-launch helper, subscription logic and dependency/runtime files are untouched. Tests freeze protected files and all App/Sidebar event callbacks. Real production MFA and Tiquet acceptance remain required.
- **Theme collisions:** browser review caught washed-out mobile tabs. Scoped navy mobile navigation and computed-color checks now protect this.
- **Responsive currency wrapping:** browser review caught wrapped monetary totals. App and KPI values now fit on one line in the tested fixtures; full values retain titles. Extreme values may be ellipsized rather than overflow.
- **Missing data shown as healthy:** missing metrics remain dashes, failed refresh clears stale data, empty workspaces have an explicit empty state, and unavailable app links remain disabled. Status indicates data availability, never uptime.
- **Historical gates:** old UI hashes/class assertions are deliberately not rewritten to claim approval. Their six failures are expected and remain release blockers until this candidate is accepted.

## Verification
- TypeScript and production frontend build: PASS.
- Historical base: 635 tests, 630 pass, 5 skip, no failures.
- Initial candidate: 635 tests, 624 pass, 5 skip, six historical UI assertions fail (three old UI blob pins and three previous-design assertions).
- New presentation boundary checks: 14/14 PASS.
- Final full suite: **649 tests; 638 pass, 6 historical UI failures, 5 skipped**. No functional test failed.
- Chromium: 320, 390, 768, 1024, 1440 and 1920px; light and dark desktop, normal/failure/empty/restricted/missing-data scenarios; no page errors or external requests.
- Checks include signed Tiquet URL, disabled Academy link, CTA and reload navigation, saved theme, mobile More/Billing navigation, app-switcher search and signed link, login/recovery entry, overflow, one-line fixture totals, keyboard focus and sampled text contrast >=4.5:1.
- Full-page screenshots expand the scroll container for capture only; viewport screenshots retain the real app scrolling layout. No screenshot-only product styling is shipped.
- Full real Hub+Tiquet paired integration tests are among the skipped tests. Isolated backend MFA/session/launch tests pass; this is not real production MFA/SSO acceptance.
- Existing bundle-size warning remains. No new production dependency or remote asset was added.

## Release recommendation: HOLD for visual approval
First review the light desktop, dark desktop, tablet/mobile and full-page screenshots. Approval must identify this exact candidate. Do not merge, publish a Docker image as approved, or execute a live cutover yet.

After visual approval:
1. Verify the actual running Hub image/container, Tiquet and protected service identities, Compose configuration, mounts and active workforce timers. Desktop Commander was unavailable due to its monthly usage cap during this work, so this inspection is pending.
2. Review the presentation delta against the actual deployed source. Accept this candidate's new UI hashes through a new versioned release record; retain the old R18 evidence.
3. Build and pin the exact source/image digest. Run isolated boot and genuine MFA/login/logout/SSO acceptance, including invalid MFA and expired session cases. Preserve the already-working Tiquet release.
4. Capture a fresh encrypted off-host checkpoint and exact current rollback image/configuration. Do not reuse the former pre-visual Hub as the assumed rollback target.
5. Rehearse stopped profiles and inverse image-only restoration with the existing vetted transaction engine. Check mount/env/port/user parity. No schema or data migration belongs in this release.
6. Prepare a new sealed Hub-only plan with current baseline identities, protected-container checks, supervision, timer restoration, health checks and automatic failure rollback. Owner approval and checks must bind to the same candidate digest.
7. Only then issue the exact deployment and production rollback commands. After switching, check real owner MFA, Tiquet dashboard launch, subscriptions/app availability and browser visual parity. Roll back on failure.

## Rollback
**Source rollback:** revert the candidate commit on its review branch with `git revert <candidate-commit>`. The review handoff supplies the resolved commit. This is a code reversal, not a production rollback.

**Production rollback:** restore the immediately preceding Hub image using its sealed inverse runtime model, preserving all environment, mounts, networks, ports and user configuration. Verify health and auth/SSO, protected services and timer restoration. Never restore older application data for this UI-only change.

The current `V79_Vision79_Hub_Only_Guarded_Cutover_v2.py` offers prepare/deploy/status and internal automatic failure rollback; it has no public `--rollback` option. Its fixed identities refer to the previous release. Therefore inventing a manual rollback command or reusing it for this candidate would be unsafe. The exact production rollback command is pending the current-runtime inspection and new sealed plan. No production rollback was needed or attempted in this task.

## Reproduce the isolated review
Use the pinned package lock and Node 24. `npm ci`, `npm run lint`, `npm run build`, then install Playwright in a separate tool directory and expose it to the test script without changing the application lockfile. The browser runner serves only local built assets; defaults to `127.0.0.1:4178`. `V79_CHROMIUM_PATH` optionally selects a local Chromium executable. Run `node scripts/vision79-workspace-browser.mjs` and `node scripts/vision79-workspace-preflight.mjs`. Neither is a deployment command. `npm test` intentionally exposes the historical acceptance failures described above.
