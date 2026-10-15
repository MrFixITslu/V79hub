# V79 Hub + Tiquet — focused release decision packet
Date: 15 October 2026 | Revision: v1.0 | **DRAFT — NOT CUSTOMER RELEASE AUTHORIZATION**

**Owner direction:** focus only on Hub and Tiquet. Reuse completed tests; no redundant full E2E or DB restore unless relevant code, image, configuration, schema or credible incident changes. WiPay remains primary; verified manual bank transfers remain available after finance approval. Preserve Sentinel/CEO/COO/Marketing modules, all real accounts and the live WiPay pinned overlay.

## Decision in one minute

| Tier | Audience | Current disposition | Change allowed |
| --- | --- | --- | --- |
| A — internal owner pilot | Existing founder account; demo/synthetic data, no new customer, no real charges | **CONTINUE NOW** using unchanged running services | Operate, observe, record defects. No new deployment necessary. |
| B — 14-day invitation-only beta | 3–5 independently selected real service businesses; actual personal/business information | **NO-GO until B gates signed** | Draft content, shortlist interested prospects, agree terms; **do not issue live invitations, create real orgs, or process real customer data**. |
| C — paid commercial service | Customers whose entitlements derive from WiPay/manual payments | **NO-GO until B + C gates signed** | No live payment claims, manual approvals, merchant gateway change or automatic paid entitlement. |

## Locked evidence — reuse; do not request reruns without a named delta

| Evidence ID | Established result | Source / precise limit |
| --- | --- | --- |
| E01 | **PASS** real exact installed-image Hub + Tiquet dual-tenant functionality | Owner V4 isolated run `v79x-0c27ad9a7b` (15 Oct); authenticated Hub, provisioned A/B, actual SSO, replay rejection, tenant client isolation, anonymous and legacy-login denial all `true`; scratch cleanup PASS and all six protected container identities unchanged. [Issue #113](https://github.com/MrFixITslu/V79hub/issues/113). Synthetic only; not independent security certification. |
| E02 | **PASS** owner browser positive path | Founder completed real Hub MFA, Hub→Tiquet direct dashboard, correct org, no second login. Signed-out direct access pointed to Hub login. This does **not** certify other browser roles, reset, MFA expiry or mobile journey. [Issue #113](https://github.com/MrFixITslu/V79hub/issues/113). |
| E03 | **PASS** current source-only CI negative contracts | [Hub draft #149](https://github.com/MrFixITslu/V79hub/pull/149) at `95315ac462aadd5431ca359a5f52713103d0d9cb`: [PR run 38781495458](https://github.com/MrFixITslu/V79hub/actions/runs/38781495458) passed synthetic tenant suspension A=402/B=200, logout cookie clearance, shared-token negatives and mock WiPay/manual/Resend. **Cookie clearance does not prove copied-JWT revocation**. No production source change. |
| E04 | **PASS, DB only** | Oct 12 issue #128 actual encrypted Hub/Tiquet PostgreSQL backups decrypted and restored in temporary databases; Hub 1 state table/1 row, Tiquet 24 tables/44 rows; zero invalid constraints and exact cleanup. Not a full live-system rollback. [Issue #128](https://github.com/MrFixITslu/V79hub/issues/128). |
| E05 | **PASS, historical off-host recovery scope** | Oct 13 14/14 encrypted checkpoint checksums; 5/5 saved image imports into Acer Podman; Hub/Tiquet restored application files + DB and booted offline with health/anonymous denial. **Older checkpoint, not necessarily exact latest G3**, and not a Docker Compose/WiPay original-identity rollback. Full encrypted checkpoint remained on Dell at last reported status. [G1.2 recovery report](../g12-recovery-and-reversible-cutover-20261013.md). |
| E06 | **PASS, deployed release guard** | [Tiquet PR #34 merged](https://github.com/MrFixITslu/V79Tiquet/pull/34) as `190fc20f92416cae9fb0c97f90982b01507ac4eb`. [Main-push CI 38784353601](https://github.com/MrFixITslu/V79Tiquet/actions/runs/38784353601) SUCCESS; image publish and server deploy SKIPPED. Hub production CI already requires owner-approved manual exact SHA. No automatic production image switch occurred. |
| E07 | **Read-only confirmed 15 Oct** Resend sender domain | One connected domain `v79sl.com`, sending ENABLED; DKIM + both sender SPF records verified. Overall `partially_failed` due to tracking DNS; click/open tracking disabled. **Do not point `hub.v79sl.com` to Resend tracking**. Real invite/reset/welcome/receipt delivery is still unverified. |
| E08 | **Source present, financial activation unapproved** | Accepted G3 Hub source contains manual invoice request, owner MFA confirm/reject + audit. Prior PR #116 diverged and must not be merged wholesale. WiPay mock contracts PASS; actual merchant settlement/bank reconciliation NOT established. [Issue #113](https://github.com/MrFixITslu/V79hub/issues/113). |

**Runtime identifiers at last confirmed live preflight:** Hub `sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06`; Tiquet `sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b`. These are acceptance identifiers, **not permission to redeploy or rebuild**. Current Tiquet tree/lockfile differs from published GitHub main; avoid reconstructing its production image from `main`.

## Minimum NEW evidence for Tier B — not a replay of E01–E06

| Priority | Required sign-off | Already covered | Specific missing evidence / responsible party |
| --- | --- | --- | --- |
| B1 — P0 | **Independent Hub+Tiquet security assessment** tied to exact installed images and effective configuration | E01–E03 | External reviewer, legal permission / rules of engagement, findings severity + retest. Focus on copied JWT after logout, stale/revoked entitlement with active sessions, MFA/roles, cross-tenant files and WebSockets, secret handling and CSRF. Hub+Tiquet scope only; Sentinel Edge/customer NOC remains separate release gate. Owner commissions reviewer. |
| B2 — P0 | **Current recoverable checkpoint including files/config/key dependencies** plus realistic return-to-service procedure | E04, E05 | Confirm a **current** encrypted complete checkpoint copied off the Dell, separate off-device recovery key, checksum/decrypt feasibility and signed manifest including distinct Hub/Tiquet Compose + WiPay override. Oct 13 Acer boot evidence counts; do not rebuild/re-run prior DB restore. One narrowly scoped restored original-identity/MFA and targeted rollback verification if reviewer requires it; owner-controlled access only. |
| B3 — P1 | **Single human customer-browser acceptance session** after security review | E01/E02 | Approved test inbox invitation+password reset delivery; MFA role/journey, mobile view, clear help/error message, one reviewed cross-org denial. Only synthetic test subjects until B1/B2 pass; no broad regression. Owner + QA. |
| B4 — P1 | **Pilot-facing customer terms/privacy/support documents** reviewed | Draft in this packet | Written privacy/data-retention/location, terms, incident response and trial policy reviewed by local qualified counsel as appropriate; support ownership and any advertised response target approved. |
| B5 — P1 | **One explicit Tier B founder GO** | No GO currently | Signed date, exact image IDs/effective runtime configuration, independent reviewer finding disposition, recovery proof and allowed 3–5 named business accounts. No implicit beta permission from green CI. |

## Additional NEW evidence before Tier C (paid)

- WiPay merchant registration/KYC and correct Saint Lucia merchant/currency, authorized callback/webhook/settlement audit and refund path validated with merchant, no redirect=payment assumption.
- Manual bank-transfer SOP: independently verify cleared funds from bank records (not screenshots), tenant/amount/reference, recent authorized MFA, duplicate reference/idempotency, audit ledger and refunds. In-memory single-process locking is **not sufficient** as a durable multiwriter guarantee.
- Local finance/legal approval of invoices, tax and payment/refund terms, plus explicit founder Tier C GO. Until then all trial entitlements remain nonpaid.

## Exact change-control and STOP rules

1. Do not merge old Hub PR #130/Tiquet #32 or manual-payment PR #116 wholesale; retain current installed images and scripts. Tiquet automatic main-push deployment was disabled by PR #34, but a manually dispatched ecosystem deployment still exists and main branch is not protected.
2. Any code/config/image change requires a **differential** regression focused on changed behavior and a verified rollback. Do not re-run E01 or E04 solely for ceremony.
3. STOP on confirmed tenant leak, unauthorized access, missing current off-host backup/key, high/critical unresolved security finding, unexplained image drift, payment uncertainty or loss of original rollback assets.
4. No real customer data, invitations, provider email send, account cleanup, merchant charge/refund or server mutation is authorized by these documents.
5. Keep [Issue #113](https://github.com/MrFixITslu/V79hub/issues/113) as the single launch command board; this packet is an editable draft, not an autonomous workflow.

## Release-decision record (blank until separately signed)

- Decision: **NO-GO for Tier B and C** as of 15 October 2026.
- Exact Hub/Tiquet image IDs and effective configurations at approval: __________
- Independent security reviewer/report/date and critical/high dispositions: __________
- Off-host encrypted checkpoint ID + private key custody verified (no secrets in record): __________
- Human browser/email acceptance date/approved identity: __________
- Pilot legal/privacy/support approval: __________
- Approved business invite list: __________
- Founder Tier B decision and signed date: __________
- Later finance/WiPay Tier C evidence, founder decision and signed date: __________
