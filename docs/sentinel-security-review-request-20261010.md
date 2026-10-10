# V79 Sentinel — Independent security-review handoff

Date: 2026-10-10 UTC. Status: PENDING independent reviewer approval; deployment blocked.

## Candidate and scope

Base deployed Hub candidate: `1ebe3357983c6f75bfd95ffa76beeee20f12984d`.
Review the exact immutable HEAD of `review/sentinel-github-20261010` after integration with current GitHub main (record final SHA at review time); this includes UI/status, session-scoped MFA hardening, and updated npm lockfile patches.
Review the full PR diff against main, plus the candidate history from `1ebe335` through `1f90a23`, and the existing security contracts used by the new routes.
Review target is the public GitHub pull request branch. Production is not the test environment.

## Threat model and required independent challenges

1. Confirm operator authorization checks the *session's* completed MFA, not merely account enrollment, for status, create, preview and cleanup routes. Exercise expired/stolen/non-MFA, foreign-workspace and bearer-token scenarios.
2. Verify CSRF/same-origin protections for cookie-backed writes and that no synthetic passwords, MFA material or session tokens are logged, rendered or persisted unencrypted.
3. Check creation and deletion are serialized against every ongoing Hub write and reminder worker (including requests disconnected during upstream provisioning); test failure/retry uncertainty.
4. Prove deletion targets only exact marker-owned synthetic organization/users/memberships, with no shared identities, external mappings, billing/invite/agent history or future-schema references; ensure session revocation and retained audit.
5. Review UI read-only status reconciliation and no-retry logic under network failures, browser refresh, contaminated QA targets or unexpected JSON responses.
6. Assess dependency advisories and the minimal lockfile changes (`proxy-addr` 2.0.8; `source-map-js` 1.2.2); verify `npm audit --omit=dev` and relevant runtime exposure.
7. Check auth middleware ordering, cross-origin handling, failure responses, race conditions, irreversible operations, and whether the user can trigger unrelated production actions.

## Constraints

Read-only review against the isolated Acer working tree. Do not change secrets, run live destructive commands, deploy, start live synthetic test resources, modify real V79 users, or connect to the production database. Record file/line findings with severity and reproducible isolation-only evidence. Approval must expressly name the reviewed commit SHA. Findings should be remediated and the final SHA independently re-reviewed before release.

## Release gate

No reviewer sign-off has yet been obtained for this candidate. A complete automated green test run or the author checking the code is not equivalent to independent approval. Only after independent approval should an authorized operator perform maintenance-window preflight, backup verification, Hub-only deployment, supervised test organization create-preview-delete, cleanup reconciliation, worker restoration, and monitoring.
