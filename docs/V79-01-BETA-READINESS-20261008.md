# V79-01 Beta Release Readiness — 8 October 2026

**Release mode:** Production-standard, invite-only beta. Not a commercial launch. No paid checkout or new customer onboarding authorised.

## Verified live operating state

| Gate | Verified result | Remaining caveat |
| --- | --- | --- |
| Core application HTTP | Hub, Academy, POS, FFPRO, Tiquet and Marketing HTTP 200 | An HTTP check is not a complete browser login |
| Container health | Hub, PostgreSQL, Marketing, POS, FFPRO and Tiquet healthy | Monitor future restarts |
| Academy launch address | Correct production runtime and served UI bundle use `https://academy.v79sl.com` | Founder browser test still needed |
| Marketing launch | Founder confirmed Hub-to-Marketing launch works | No further browser retest after provisioning-only configuration update |
| Marketing provisioning | Corrected live Compose mapping to use Hub's general platform signing key; signed malformed request rejected 400, invalid signature rejected 401 | Existing dedicated launch key intentionally unchanged |
| Tenant guard | Two organisations; one non-owner approved beta; exactly five enabled app entitlements and four active isolated app mappings | No additional customers authorised |
| Trial lifecycle | One 14-day beta ending 2026-10-22T21:20:02.148Z (17:20 AST); reminder worker leader enabled | Real reminder inbox/delivery still requires observation at reminder date |
| Founder permissions | Founder admin email configured; admin MFA required; unauthenticated private APIs denied | Founder must complete remaining browser acceptance |
| Release audit | `scripts/release-config-audit.mjs` passed with zero issues | Does not replace browser testing |

## Automated quality gates

- Hub V79-01 disposable five-real-application staging: GitHub run **37857045047**, passed. Synthetic organisation provisioning, 4 signed entitlement controls, Hub single-use launch tickets and authenticated app sessions succeeded; cancelled and cross-tenant access denied.
- Hub CI: run **37857045023**, passed. Production deployment and image publication were skipped on the draft PR.
- Marketing PR hotfix REDTEAM validation: run **37862323707**, passed.
- Marketing PR hotfix CI: run **37862323667**, passed. Production deployment and image publication were skipped.
- Isolated Marketing hotfix local TypeScript lint and Vitest **51/51** across **13** test files passed.
- No tests created a live customer or enabled billing.

## Configuration and security findings

1. **Resolved:** Marketing's dedicated provisioning env variable was receiving a value that did not match the Hub signer. Live Compose now maps it to the general platform key already used by Hub, without changing the Marketing launch key. Protected Compose rollback lives outside the project at `/home/firelion/v79-release-rollbacks/marketing-provisioning-fix-20261008`. The source change is isolated in draft Marketing PR **#24**.
2. **Resolved for new Hub image:** The prior Docker build context did not exclude `.env`. The Academy hotfix added exclusion rules before a new Hub image was built, and a disconnected image check confirmed that no `.env` was present.
3. **Follow-up required:** The old rollback Hub image tagged `v79-hub:academy-rollback-20261008` is known to contain an old local `.env`. Do not push it to any registry. Retain only until rollback window closes, then assess controlled credential rotation and image retirement. No unilateral rotation while live integrations depend on these shared keys.
4. **Email:** Resend domain has sending enabled; DKIM and sending CNAMEs are verified; two earlier transactional tests showed delivered. Domain displays **partially_failed** because custom tracking CNAME `email-links` is failed and a `hub` tracking record pending. Observed DNS for `email-links.v79sl.com` was an A record rather than Resend's requested CNAME. **Never change `hub.v79sl.com` to a Resend tracking CNAME**; it hosts customer authentication. Treat tracking as a separate scoped DNS change.
5. **Backups:** Workstation systemd daily backup timer active for 02:00 AST; Oct 8 backup reported success (five DB dumps, three protected app archives, nine volume archives). Retention encountered permission errors deleting an old Sep 14 snapshot. Do not delete any archive or change ownership without careful snapshot verification and administrator oversight. Offsite encrypted backup is explicitly deferred by founder.
6. **Billing:** Live Hub's WiPay and Stripe runtime keys were not configured in the audited environment. Leave commercial charging disabled.

## Source control gates — no unattended merges

- Hub full beta draft PR **#93** — feature lifecycle and staging, no merge.
- Hub Academy hostname and Docker credential-exclusion draft PR **#94** — already applied as a scoped live hotfix, source PR not merged. Confirm production/main parity and CI deploy implications before merging.
- Marketing provisioning-key draft PR **#24** — scoped change manually reflected in live Compose, not merged. The main Marketing working tree has significant unrelated modifications; do not overwrite them.
- All draft PR validations passed. A merge into `main` could trigger unattended image publication/deployment. Require a reviewed release plan and rollback check before merging.

## Final human acceptance required

1. Founder signs into `https://hub.v79sl.com` with MFA and verifies FFPRO, Tiquet, POS and Academy launches. Marketing launch was already confirmed.
2. Confirm app user identity/workspace scope and no visibility into other customers' data.
3. Decide whether to authorise clean source PR merges and any consequent production release.
4. Schedule controlled retirement of old credential-bearing local image and any coordinated rotation.
5. Repair backup-retention permissions only after old snapshots are identified and recoverability is confirmed.
6. Optional: fix the `email-links` tracking CNAME if link tracking becomes necessary; do not repurpose the Hub hostname.

**Release decision:** V79-01 remains in restricted beta. Automated integration/health gates are passing, but the full live MFA/browser acceptance and final commercial release controls are not complete.


## Supplemental live transport/security check — 8 October 2026 AST

- **Release blocker: HTTP downgrade exposure.** Public `http://hub.v79sl.com/` and `http://pos.v79sl.com/` currently return HTTP 200 instead of redirecting to HTTPS; Marketing, FFPRO, Tiquet and Academy return HTTP 301 redirects. Both Hub and POS must have Force SSL enabled in Nginx Proxy Manager, validated using actual HTTP-to-HTTPS requests, before commercial onboarding.
- A host-specific custom Nginx attempt passed syntax checks but did not affect public redirects; the added snippets were **removed immediately**, Nginx syntax rechecked and all six HTTPS sites remained HTTP 200. There is no active custom redirect override. Restore correct behavior via the managed Proxy Hosts SSL settings, not further global experiments.
- Hub public HTTPS currently lacks HSTS and CSP response headers, although other V79 apps expose both. Scoped HSTS/CSP hardening is isolated in **draft Hub PR #95** and passed lint, 143 local tests, build and GitHub CI. It has **not** been deployed and requires founder MFA/browser verification before production rollout. The planned CSP is deliberately conservative and needs further tightening later.
- Additional live signed read-only entitlement checks passed for POS, FFPRO, Tiquet and Marketing: active beta owner permitted and unknown user denied on each product. This does not replace actual browser login tests.
- **Current go/no-go:** restricted beta only, **no commercial or additional customer onboarding** until Force SSL and remaining browser/security gates pass.

## Verified remediation — Force SSL enabled, 8 October 2026 (20:40 AST)

- Founder enabled **Force SSL** in Nginx Proxy Manager for `hub.v79sl.com` and `pos.v79sl.com`. Read-only verification established each proxy config now includes the stock `conf.d/include/force-ssl.conf` rule.
- All six live HTTP origins (Hub, POS, Marketing, FFPRO, Tiquet and Academy) now return **301** with their corresponding HTTPS destination. HTTP requests with path and query are preserved for Hub and POS.
- All six corresponding HTTPS origins return **200**. Hub, Hub PostgreSQL, Marketing, POS, FFPRO and Tiquet remain healthy; Nginx `nginx -t` passed.
- Hub's protected APIs return HTTP **401** when called without a login; the live Academy runtime value remains `https://academy.v79sl.com`. The non-mutating release configuration audit returned `ready: true` with zero issues.
- **Status change:** the HTTP downgrade / Force SSL release blocker above is **resolved**. The previous section remains an audit trail and no longer represents the current proxy state.
- **Still open:** Hub HTTPS does not yet expose HSTS/CSP (draft PR #95); live founder MFA browser acceptance for FFPRO, Tiquet, POS and Academy; careful source-PR review before merging or triggering production; legacy rollback image secret handling; local-backup retention cleanup; optional Resend tracking DNS.
- **Go/no-go:** continue the one already authorised restricted beta; do not enable commercial billing or additional customer onboarding until final acceptance and remaining security release gates have been reviewed.

## Founder browser acceptance confirmation — 8 October 2026 (20:44 AST)

- Founder stated **all applications load as expected** after opening them through Hub. This completes the founder-level app launch acceptance for **Hub, Academy, FFPRO, Tiquet, POS and Marketing**. A prior explicit Marketing launch confirmation was also received.
- A follow-up check showed six public HTTPS origins returned **200**, six public HTTP origins returned **301** redirects to their HTTPS counterparts, and Hub, Hub PostgreSQL, Marketing, POS, FFPRO and Tiquet were healthy. The non-mutating release-config audit reported `ready: true, issueCount: 0`.
- **Acceptance scope:** browser application opening confirmed. Deep role-based and cross-tenant screens were not visually inspected with an authenticated beta customer session; those were verified at the signed-entitlement API layer and in disposable five-app staging.
- **Remaining controlled-release gates:** review draft PRs before merges and any automatic production deploy, deploy and verify Hub CSP/HSTS hardening draft PR #95 if approved, retire the legacy locally credential-bearing rollback image with coordinated secret review, resolve backup-retention permissions, keep Resend tracking-DNS issue optional, and decide commercial onboarding/billing separately.
- **Decision:** current V79-01 restricted beta can continue. Commercial launch and onboarding remain blocked pending final release/security approvals.
