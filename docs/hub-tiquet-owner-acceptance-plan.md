# Owner-assisted Hub + Tiquet acceptance plan

Status: PREPARED / NOT PERFORMED. No production/customer/payment state change is
authorized by this plan. Independent security certification remains a separate
review. Use the exact reconciled source commit, pinned image pair, restored
isolated workspace and approved fixture manifest from the release runbook.

## Fixture and evidence contract

- Owner approves exactly two synthetic Hub organizations A/B, one owner and one
  limited staff identity per organization, and specified test inboxes. Preserve
  all existing accounts and organizations. Never use/delete a real tenant.
- Choose an isolated restored environment with outbound provider calls blocked
  by default. Separately authorize each provider sandbox email/payment action.
  No live payment, subscription activation, refund, account reset or production
  test-resource cleanup occurs in this lane.
- Record case, exact Hub/Tiquet commits and image IDs/digests, time, browser,
  viewport, expected/actual status and redacted evidence URL/hash. No cookies,
  JWTs, password/MFA/reset codes, bank details, customer records or payment
  screenshots in GitHub. Retain private security evidence separately.
- Stop on an unexpected organization, permission, payment state, outbound send,
  unknown side effect or uncertain response. Reconcile read-only; no automatic
  retry of provisioning, reset, payment confirmation or cleanup.
- Retain exact IDs of only authorized fixtures and references. Cleanup requires
  its own approved manifest, dependency review, retained audit evidence and
  before/after account/organization/membership checks. Do not use Sentinel QA
  create/delete controls or modify its independent audit workstream.

## Cases

| Case | Owner action in approved workspace | Required result / evidence | Current status |
| --- | --- | --- | --- |
| A01 Signup policy | Request public Hub registration; use approved owner invitation to onboard synthetic A; try expired/replayed/foreign invite | Published main deliberately returns 403 invite-only for public registration; valid invitation creates only exact intended membership; wrong/expired/replayed invite denied; no existing account duplicated | NOT PERFORMED |
| A02 Owner MFA | Genuine owner completes current MFA challenge; isolated stale/non-MFA owner session attempts protected administrative operations | MFA enrollment/session requirement enforced; no privilege before challenge; current session-specific MFA verified; account-level enrollment alone insufficient | NOT PERFORMED |
| A03 Staff authorization | Log in as A staff, inspect accessible billing/admin pages and Tiquet launch | Limited staff sees only authorized pages; denied requests stay denied at API; no owner privilege from client role changes | NOT PERFORMED |
| A04 Hub-to-Tiquet SSO | From fresh valid A owner/staff Hub session launch Tiquet and watch redirect/history | Exact A Tiquet dashboard opens without a second login screen or credential prompt; B information absent; no transient logout/redirect loop; provisioning occurs only for approved fixture | NOT PERFORMED |
| A05 Direct access and ticket replay | Open direct Tiquet in fresh signed-out browser; reuse consumed/expired launch ticket only in isolated fixture | Correct Hub signup/login guidance; legacy local auth remains disabled; used/expired/wrong-product/wrong-tenant launch ticket denied; no open redirect/token disclosure | NOT PERFORMED |
| A06 Cross-organization denial | Separate A/B browser profiles; A attempts known B fixture ticket/client/file/user/account/SSO identifiers | 403/404 or empty authorized result; no B body/metadata/download/WebSocket event; server authorization cannot be bypassed by query/body/client role; audit reflects denied access without secrets | NOT PERFORMED |
| A07 Logout and expiration | Logout each app, revisit protected pages/API; test expired Hub/launch/Tiquet session in isolated clock-controlled fixtures | Local cookies cleared; expired tokens denied; no silent renewal. Record residual stateless bearer validity separately: cookie logout alone does not prove server revocation | NOT PERFORMED |
| A08 Entitlement/session recheck | Isolated fixture loses entitlement or becomes suspended, with existing Tiquet HTTP and WebSocket session | Existing access and socket are denied within documented configured recheck/cache bound; published managed launch JWT is 30 minutes, optional recheck cache may be up to 30 seconds; confirm actual reconciled runtime behavior | NOT PERFORMED |
| A09 Password recovery | Reset only a synthetic test identity via approved inbox, try expired/used token, log in with old/new password | Generic account enumeration response; exact identity only; one-use/time-bound token; old credential denied; documented session invalidation verified. Never reset founder or existing production account | NOT PERFORMED |
| A10 Mobile/accessibility | 390x844 phone, 768x1024 tablet, 1440x900 desktop, keyboard, 200% zoom; signup/MFA/recovery/launch/billing pages | Readable labels/errors, usable focus/dialogs/touch targets, no obscured controls/horizontal clipping, no unformatted flash or second-login flash | NOT PERFORMED |
| A11 WiPay negatives | In isolated fixture, exercise disabled/unconfigured provider, forged/expired/wrong-order/hash/amount/currency/reference returns | Fail closed; no entitlement/order activation, tenant change or provider call on rejected input; redirect/screenshot cannot establish payment success | NOT PERFORMED |
| A12 WiPay sandbox | Only after provider sandbox authorization, use exact approved synthetic order/merchant/country/currency and verify server-confirmed callback | Actual provider evidence binds account, order, amount, currency, reference and signature/hash; repeated callback cannot duplicate payment/entitlement. Sandbox success is not cleared live funds or merchant/KYC approval | NOT PERFORMED |
| A13 Manual transfer negatives | Isolated fixture only: ordinary staff, stale/missing MFA, wrong org/amount/currency/reference, empty/duplicate payment reference, missing cleared-funds evidence | Every case denied; pending manual order remains pending with no entitlement/paid event; same-origin/CSRF defense enforced; audit retains rejection and preserves other tenant | NOT PERFORMED |
| A14 Manual transfer positive/concurrency | Disposable restored store only, independent bank-cleared-funds verification represented by an explicit synthetic fixture; same and different operator concurrent/replay attempts | Fresh actual owner/operator MFA, exact order/tenant/plan/cycle/currency/amount/reference and cleared-funds assertion required; one durable atomic payment/entitlement/audit result; replay stable; conflicting retry denied; restart/multiwriter races verified | NOT PERFORMED |
| A15 Provider/mail workflow | After separately authorized test send, inspect invite/reset/reminder delivery and deduplication to approved inbox | Current domain authentication/provider status and received redacted message evidence; correct canonical links and tenant; no repeat/out-of-scope send; provider delivery receipt alone is not full workflow acceptance | NOT PERFORMED |

## Important scope decisions

Public signup is not currently an open feature in published Hub main. Confirm
invite-only internal pilot expectations before A01; do not introduce new public
signup work or interpret intentional registration denial as permission to change
the production policy. Returning a paid-user login screen during Hub SSO is a
defect if the approved user already has valid access; never bypass access gates
to make the screen disappear.

Hub logout and Tiquet JWT expiry are distinct. The existing Tiquet cookie logout
does not itself prove a previously captured bearer token is revoked. The acceptance
record must state actual TTL, recheck policy, cache bound and WebSocket behavior.
Isolated expiry/revocation tests cannot change the live server clock, environment
or subscription. No immediate global session-revocation feature is introduced.

Manual bank transfer implementation is still a separate unmerged Hub #116 draft
(`7155a5fd3a67d95537dfd06ed5e48229a5cd50f0`), with unresolved release integration,
durable payment idempotency/restart/multiwriter and financial-audit evidence.
Do not deploy that standalone older-base branch over current Hub safeguards.
Use separately reviewed code in an isolated combined candidate for A13/A14.
Existing store revision locking is evidence against stale snapshot writes, not
proof of immutable financial audit or end-to-end bank-cleared-funds correctness.

Live manual transfer remains HOLD until an independent finance/legal-reviewed
procedure covers cleared bank funds verified outside the app, invoice/receipts,
exact tenant/amount/currency/reference, fresh operator MFA, durable audit and
duplicate/reversal handling. A payment screenshot, redirect, pasted reference or
self-attested software boolean cannot independently establish cleared funds.
Do not change payment logic or add bank integration/features in this assignment.

## External dependencies / owner actions

| Dependency | Required evidence | Current classification |
| --- | --- | --- |
| Independent security reviewer | Exact combined runtime/release candidate, auth/SSO/tenant/payment safeguards and current findings reviewed; retained signed scope/results | NOT PERFORMED / external gate |
| WiPay | Current merchant/KYC status, Saint Lucia account/country routing, supported currency, callback/hash/amount/refund/settlement requirements in provider writing | Historical sandbox account work only; current status UNVERIFIED |
| Finance/legal | Cleared-funds, duplicate-reference, receipts, disputes/refunds and manual-transfer control procedure | UNVERIFIED; requires owner-appointed specialist |
| Resend/DNS | Current domain verification, approved sender/test recipients, delivery and app link/deduplication evidence | Historical verification/delivery only; current workflows NOT PERFORMED |
| Owner | Approve isolated workspace, exact fixtures, inboxes and each outbound sandbox action; provide genuine MFA and final acceptance | REQUIRED; no production mutations authorized |

All cases stay NOT PERFORMED until actual recorded execution. Automated CI source
tests are supporting evidence, not owner human acceptance. After any code/config
change, repeat the affected exact-candidate checks and keep the launch NO-GO until
the full release matrix and separate founder approval are satisfied.
