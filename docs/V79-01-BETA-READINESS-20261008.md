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
