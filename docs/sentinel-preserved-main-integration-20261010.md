# V79 Sentinel — Preserved-current-main integration

Date: 2026-10-10 AST. **Staging only: not merged to GitHub main and not deployed.**

## Basis
- Latest fetched GitHub main: `080d293` (manual immutable-SHA release gates, agent and billing fixes included)
- Existing safer Sentinel review branch: `ff4b069` (integrated Sentinel supervised browser controls from `1f90a23`, explicitly retained the newer agent modules)
- Isolated worktree: `/home/firelion/V79-Sentinel/hub-sentinel-preserved-integration-20261010`
- Branch: `review/sentinel-preserved-integration-20261010`

## Release-blocking merge trap caught
A direct merge of the older Acer Sentinel candidate into current GitHub main applied automatically but would have deleted `server/agent-proposal-inbox.mjs`, `server/agent-proposals.mjs`, both corresponding tests, and a Stage3A document. That attempt was **aborted before commit**; it was not pushed or deployed. Do not use that direct merge.

## Corrected preservation-first integration
Started from reviewed preservation branch `ff4b069`, then merged latest GitHub main `080d293` without committing pending validation. The merge had no conflicts and preserved the agent modules and tests, Sentinel QA routes, plus the release-deployment safety changes in `.github/workflows/v79-ci-cd.yml`, `scripts/deploy-server.sh`, `scripts/deploy-ecosystem-release.sh`, and `scripts/verify-sentinel-preservation.sh`.

The merge affects only the isolated worktree. No source tree was copied over `/opt/v79/hub`. Live Hub image `v79-hub:sentinel-1ebe335` and existing accounts/data remain unchanged.

## Review status and gates
- This is a combined integration staging artifact, **not independent third-party security approval**.
- Functional Sentinel code is based on `1f90a23`; GitHub's closed PR #112 contains an older integration SHA. An independent reviewer must review the exact final integrated tree, not rely on sign-off for the Acer SHA alone.
- The in-chat internal adversarial assessment on candidate `1f90a23` passed 38 targeted tests on synthetic JSON/real disposable PostgreSQL fixtures and found a P2 live-account-login UI coverage gap. See separate local report `docs/sentinel-internal-adversarial-review-20261010.md` in the original staging worktree.
- Latest combined full run: **295 pass, 0 fail, 1 skipped**; the one omitted independent-process PostgreSQL approval race test then **passed separately** on a fresh loopback-only isolated database. Thus 296 distinct tests passed across both runs; this is not a literal zero-skip full-suite run. Logs: `/tmp/v79-sentinel-preserved-full-suite-20261010.log` and `/tmp/v79-approval-ci-result-20261010.log`. Combined TypeScript lint/build passed; production dependency audit: 0 known advisories. Passing tests do not authorize live flags or deployment.
- Before production: independent review of exact final commit; fresh backup and restore exercise, quiescent worker/HTTP writes, pinned Hub-only deployment, no lost modules, synthetic create–preview–exact cleanup under genuine MFA supervision, full account/session preservation, worker restoration.
