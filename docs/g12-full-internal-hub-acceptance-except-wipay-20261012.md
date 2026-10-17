# V79 Hub — Full Internal Functional Acceptance (WiPay Excluded)

**Founder requirement (2026-10-12):** The V79 Hub is an **internal test system** and must be fully usable, with **WiPay payment processing as the sole allowed functional exception**. This document is a *release acceptance contract*, not proof that its tests have passed or permission to expose customer data.

## Definition of DONE

The Hub passes only when the exact installed immutable build is usable in the founder's real authenticated desktop and mobile browsers, the approved owner and two isolated synthetic tenant accounts can complete every applicable workflow below, service/API authorization checks pass, and failures are observable and recoverable.

**NO-GO if any non-WiPay functional requirement fails.** A passing CI job, healthy container, mock screenshot, or HTTP 200 alone is not acceptance. Mark PASS only with evidence showing actual source SHA/image, environment, timestamp, test identity type, expected and observed behavior, and cleanup/rollback disposition.

## Mandatory full-functionality matrix

| ID | Area | Acceptance criteria | Current evidence/status |
|---|---|---|---|
| F01 | Login and MFA | Owner login, fresh MFA, denied invalid/replayed MFA, session expiration, refresh/logout, reset and no login-loop | NOT YET VERIFIED ON RECONCILED BUILD |
| F02 | Owner Admin | Owner dashboard, role-restricted navigation, organization/tenant management, accurate counters, user settings, audit, independent owner access | NOT YET VERIFIED |
| F03 | Invitations and trials | Invite-only onboarding, acceptance/password setup, resend/revocation/expiry, 14-day free trial, plan display and reminders | NOT YET VERIFIED |
| F04 | Security and tenant separation | Two disposable organizations; nonowner denied owner API and cross-tenant data, payment, agent and app access; no unauthorized changes | NOT YET VERIFIED ON RECONCILED BUILD |
| F05 | Hub-to-app SSO | Launch each assigned app directly into its dashboard without second login; direct unauthenticated visit still requires app authorization; logout/session behavior consistent | NOT YET VERIFIED ON RECONCILED BUILD |
| F06 | Connected apps | Tiquet, POS, FFPRO, Marketing, Academy and any other Hub-assigned app show the correct authorized destination, loading/error state, and working return navigation | NOT YET VERIFIED ON RECONCILED BUILD |
| F07 | Plans and Billing UI | Summary, plan/price/currency, billing history, invoice status, manual-payment request and owner reconciliation interface function without WiPay merchant activation | STAGED in draft PR #143 from PR #116; full integrated UI/browser acceptance not yet proven; no real settlement |
| F08 | Manual payment controls (synthetic) | In isolated staging: create pending invoice; no entitlement from request/screenshot; separate MFA-verified owner attests synthetic cleared-funds evidence; exact amount/currency, unique reference, idempotency, audit, cancellation/rejection and cross-tenant denial | **Disposable Hub HTTP synthetic owner MFA + two-tenant invoice/settlement/replay/duplicate-reference tests included in green CI at `bb88d7c`**; no bank funds verified; final browser/finance/security acceptance still OPEN |
| F09 | Trial/subscription state | Free trial, expiry, access revalidation, plan changes, renewal notices and restrictions use authoritative state; cannot mark real payment success without independently reconciled evidence | NOT YET VERIFIED |
| F10 | AI Workforce CEO/COO | Owner-accessible integrated executive panel; COO evidence-based operational summary, CEO priority handoff; actual provenance, stale/unavailable flags, approval boundaries, safe fallbacks, and documented limitations | **CI synthetic full-Hub MFA/CEO/COO signed-integration test passes at `bb88d7c`**; actual owner/browser integration and genuine Business Agent runtime evidence still OPEN |
| F11 | Approved agent workflows | Owner can review task/proposal state and approve/reject supported internal low-risk workflows; unsupported/financial/security actions remain disabled; no automatic sensitive execution or tenant leakage | PARTIAL source; operator E2E and implemented-scope review pending |
| F12 | Sentinel integration preservation | All running NOC/Sentinel-backed Hub modules and stored grants preserved; all three machine-grant flags remain OFF; no unsafe signed ticket creation | Three module source blobs MATCH live; reconciled state not yet deployed |
| F13 | Communications | Invitations, account recovery, trial notifications and available manual-invoice notifications pass authorized test-inbox delivery and failed-send handling | NOT YET VERIFIED ON RECONCILED BUILD |
| F14 | UX and accessibility | Desktop/mobile page layout, no unformatted startup flash, accessible error/permission messaging, forms/keyboard, reasonable performance and no failing navigation | NOT YET VERIFIED |
| F15 | Recovery and rollback | Current Hub/Tiquet/PostgreSQL state, secrets and app files backed up; integrity checked, isolated restore proven; active pinned WiPay overlay and exact rollback image retained; supervised rollback rehearsal | **PARTIAL PASS:** 14 encrypted archive checksums, 5/5 imported images and RootFS parity, Hub+Tiquet offline image-backed DB/file restore, health/401, full teardown and swap recovery PASS; exact Docker rollback, recovered Business Agent, original-owner MFA, and key/off-host recovery remain OPEN |
| F16 | Install/cutover | Immutable reconciled candidate; independent source/module/CI review; non-destructive isolated staging; supervised install; no dropped service/data/route; final smoke and rollback plan | DRAFT PR #143, NOT INSTALLED |

**WiPay-only permitted exception:** Live merchant enrollment, hosted checkout completion, webhook/return payment processing and financial settlement are not required for *internal functional acceptance*. Keep WiPay configuration, existing pinned running image and provider code recoverable; display a truthful `unavailable/testing` payment state. Do not let a WiPay redirect, demo checkout, unchecked manual receipt, or simulation grant live paid entitlements. Do not require an operational WiPay sandbox checkout to pass this specific functional requirement, although preserving source and rollback safeguards still applies.

## Functional blockers distinguished from commercial blockers

- **P0 internal functional blockers:** all F01–F16 non-WiPay acceptance; safe G1.2/Hub reconciliation, missing manual-payment flow from draft #116, independent security/authorization review, complete isolated restore and pinned rollback, real browser E2E.
- **Deferred commercial blockers:** merchant KYC, real payment settlement/refund, tax/financial/legal readiness, commercial registration, real customer onboarding, external/customer security certification. These are NOT reasons to leave internal Hub screens or approved synthetic workflows unusable.
- **No silent feature substitution:** Read-only CEO/COO advisory endpoints do not prove autonomous task execution. Only previously approved low-risk, supervised capabilities can be marked functional; planned capabilities remain explicitly GAP until implemented and tested.

## One consolidated evidence cycle (no repeated one-off probes)

1. Freeze the exact **draft** candidate, inventory dependency/runtime parity and all known UI/API flows; treat `main` as different from deployed Hub.
2. Reconcile preserved Sentinel+WiPay+owner billing source and independently review draft #116 then run security review of the now-staged **synthetic test-only** manual payment path. Run lint, all tests, Docker builds, CI and tenant denial.
3. Create and verify encrypted recovery checkpoint(s), safely restore isolated copies of Hub/Tiquet DB, sessions/data and key custody dependencies, then rehearse exact pinned-image rollback with all live accounts untouched.
4. Use an isolated staged environment with disposable test identities for one full F01–F14 acceptance pass, including synthetic manual invoices and no real payment. No public ingress, no real credentials pasted into logs.
5. After explicit internal-cutover authorization for **exact SHA + scope**, deploy one reversible preserved build, perform owner-led desktop/mobile acceptance and rollback if any F item fails. Existing production/test-server data must remain intact.
6. Record each F item PASS/FAIL/BLOCKED with evidence; do not hide failing functions behind the WiPay exception. No disposal of accounts without owner/org dependency proof and backup validation.

**Current honest release state (updated from owner Acer recovery, 2026-10-13):** Draft PR #143 at previously CI-passed SHA `bb88d7c` is unmerged and not deployed. The verified source CI includes a disposable real Hub HTTP synthetic CEO/COO and manual-billing journey and five-app staging; do not translate that into production approval or owner-browser UX acceptance. The five encrypted original images imported on Acer, 5/5 RootFS layers matched production, and archived Hub + Tiquet database/application snapshots successfully started offline with isolated local health, DB-shape and five anonymous 401 checks. Temporary recovery containers were removed and Acer swap restored. **Core old-build restore=PASS; recovered Business Agent, actual owner MFA and WiPay-pinned exact Docker rollback=OPEN; F01–F16 candidate/live acceptance=NOT YET COMPLETE. INTERNAL GO=NO; COMMERCIAL GO=NO.** Issue #138 has the operator transcript evidence. Never copy private keys or sensitive recovered data into this document.
