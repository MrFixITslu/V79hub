# V79 Hub + Tiquet — proposed 14-day invite-only pilot operating plan
Date: 15 October 2026 | Status: **DRAFT / NOT AUTHORIZED FOR LIVE CUSTOMER ENROLMENT**
Commercial customer-facing branding: **V79 Digital — From Idea to Advantage**

## Purpose and scope

Deliver one useful workflow to **3–5 Saint Lucian service businesses**: receive an approved Hub invitation, reach the Tiquet dashboard with no second login, manage their own support tickets and staff, and understand where to get help. Other V79 apps remain outside initial customer scope.

**Tier A (allowed now):** founder-only demonstration using synthetic data and the existing running Hub/Tiquet images. **Tier B (not yet allowed):** invite real prospects only after Tier B GO per [release decision packet](2026-10-15-release-decision-and-evidence.md). **Tier C (not allowed):** no actual billing until a separate payment GO.

## Customer selection and readiness

Target 3–5 service firms with a responsible contact, a clear ticket-management need, willingness to provide weekly feedback and a low-risk, nonregulated first-use dataset. Do not collect real prospects' private data in GitHub, CI, chat or public documents; track names and contacts only in an owner-approved restricted CRM.

Prospect tracking template (store privately):

| Private prospect ID | Sector and use case | Contact/consent in CRM | Invite eligible after GO? | First-session outcome | Feedback |
| --- | --- | --- | --- | --- | --- |
| P01 | e.g. ICT service company; helpdesk ticket workflow | Pending | NO | Not started | — |
| P02 | e.g. field maintenance; dispatch and assignment | Pending | NO | Not started | — |
| P03 | e.g. small facilities provider; incoming requests | Pending | NO | Not started | — |
| P04 | Optional; service support team | Pending | NO | Not started | — |
| P05 | Optional; local B2B provider | Pending | NO | Not started | — |

Selection rules: avoid regulated/highly sensitive data during beta; do not migrate an organization's complete historical dataset as its first step; explicitly agree what information is stored and who may view it. Pilot is **not** a security waiver because it is free.

## Technical pre-enrolment acceptance — one pass after B1/B2

Owner/QA performs the following against an approved restricted synthetic tenant after independent security and recovery gates have cleared; do not rerun the completed exact-image synthetic A/B journey:
- Verify invite reaches approved test inbox and link resolves to correct Hub organization (no second password screen in Tiquet).
- Validate initial credentials, owner/staff role assignment and MFA requirements appropriate to role; account recovery and a signed-out entry path.
- Check mobile viewport, keyboard usage and visible support/help details; record only outcome and no-secret screenshots.
- Confirm expired/revoked entitlement denies customer continuation within approved policy and logout/revocation behavior meets security sign-off.
- Confirm monitoring/backup alerts and a reachable support contact. No external provider publication or payment required for Tier B.

## Timeline: 14-day free trial

| Timing | Owner / COO action | Customer-visible experience | Evidence (no secrets/PII) |
| --- | --- | --- | --- |
| **Before Day 0** | Obtain founder Tier B GO, legal/privacy/security/recovery acceptance and explicit private invite list. Freeze exact images. | Opt-in outreach only; no live invitation until GO. | Dated go/no-go record, package version. |
| **Day 0** | Send one authorized invitation per approved organization; verify correct tenant association, assigned app and trial expiry timezone. | Welcome and acceptance instructions; Hub first, one-click Tiquet dashboard. | Invitation delivery status + pseudonymous org ID, timestamp. |
| **Day 1** | Supervised onboarding walkthrough: create one non-sensitive demonstration ticket, review role permissions and support contact. | Simple success: one ticket assigned and resolved in Tiquet. | Onboarding completed Y/N, first-ticket outcome. |
| **Days 2–4** | COO captures questions, categorizes defects by urgency and assigns owner; no broad code changes. | Normal daily ticket use; help available via stated pilot channel. | Issues, resolution ownership and safe timestamps. |
| **Day 7** | Check-in call or approved email: ease of use, login problems, role isolation, one desired improvement. | Product feedback and short help. | Structured 5-question survey, response rate. |
| **Days 10–12** | Review trial end date, continued access options and approved reminder policy. No automatic paid conversion. | Noncoercive notice of expiry and options. | Reminder sent only with consent/delivery approval. |
| **Day 14** | Confirm precise UTC expiration and deny unauthorized continued app access; data retention handling per signed terms. | Trial expiry clearly shown; option to request paid service after Tier C GO, otherwise export/deletion instructions. | Access-state observation, customer decision. |
| **Post-trial** | Evaluate five KPIs and decide extend/close/paid offer only with proper approvals. | Written next-step confirmation; no surprise charge. | One-page pilot conclusion. |

The technical trial spec in [V79-01 release draft](../V79-01-TRIAL-RELEASE.md) describes a 14×24-hour clock from accepted invitation. Confirm this is true of the exact live G3 image during targeted final acceptance; do not assume code from the historical development document is identical to the current runtime.

## Operating model

**Founder:** final security, finance, go/no-go and customer invitations approval. **COO:** daily monitoring, pilot support tracking, first-response coordination and weekly summary. **QA/engineering:** defects, screenshots with sensitive values redacted, scoped fixes and reviewed differential tests. **Customer admin:** their own authorized user access and feedback; never platform-wide admin.

Suggested support hours for founder approval (NOT a binding SLA): Monday–Friday, 09:00–17:00 **Atlantic Standard Time (UTC−4)** excluding local public holidays; track critical access incidents immediately where practical. The customer-facing pilot pack should advertise a response expectation only after the founder confirms staffing and availability.

Incident classes and actions:

| Severity | Example | Internal operational action |
| --- | --- | --- |
| P0 security/data boundary | Tenant A sees B, unknown admin, payment wrongly marked cleared, compromised account | Stop affected onboarding/feature, preserve logs/audit privately, isolate per runbook, notify founder for incident decision. No unreviewed destructive cleanup. |
| P1 service unavailable | Hub login/SSO broken, Tiquet down, lost ability to recover data | Escalate owner, verify six protected services and known image/digest, follow approved rollback only, communicate affected customers. |
| P2 workflow defect | Ticket creation or assignment error with workaround | Capture exact steps and impact, prioritize scoped fix; no emergency release without risk review. |
| P3 usability improvement | Confusing label or requested feature | Backlog for post-pilot; feature freeze remains. |

## Pilot metrics (small enough to use)

- **Onboarding completion:** approved invite accepted, correct business, first Tiquet ticket successfully created.
- **First-week engagement:** at least one purposeful Tiquet session or task per participating organization; no automated synthetic activity counted.
- **Reliability:** actual login/SSO failures, app downtime and support issues; distinguish user error from platform outage.
- **Customer understanding:** week-1 feedback on simplicity, usefulness and top pain point.
- **Commercial interest:** whether the organization would consider paying and what outcome it would pay for; record interview consent, not a marketing promise.

Track pilot success by verified business value and absence of critical incidents; **do not invent conversion percentages or auto-convert free trials to paid**.

## Data, consent, retention and exit — legal review required

- Customer should see a short privacy notice, processing purpose, support email, data-hosting/backup regions and roles **verified by the owner**. Do not assert compliance with an unreviewed specific legal statute.
- Minimize data stored; no payment card data, national IDs, health information or passwords in ticket descriptions; MFA/secret values are never placed in ordinary support tickets.
- Agree confidentiality, who can view support tickets, breach notification channel, withdrawal/export and a reasonable retention/deletion schedule with legal counsel **before** inviting customers.
- Trial expiration must never silently create a paid charge. Preserve legally required accounting/audit records separately from user-configurable trial content.
- Existing backups and audits may have different retention from live records. Never promise immediate deletion from immutable encrypted backups without validating a feasible retention cycle.

## Daily owner-only internal monitoring checklist

For Tier A only, reuse **existing** health checks and logs; do not create another full synthetic E2E loop:
- Hub / Tiquet and DB service healthy; no changed image IDs, restart loop, storage saturation or expired certificates.
- Any failed owner MFA/SSO and anonymous sign-in attempts triaged with safe logging.
- Off-host checkpoint freshness, custody, alarms and current single-server recovery risk acknowledged.
- Tiquet customer-data count stays synthetic; no new non-owner real users invited without Tier B GO.
- WiPay remains sandbox or merchant state as explicitly confirmed; manual orders do not activate paid access from customer statements.

## One-page weekly COO review

`Reporting period | exact image ids unchanged Y/N | invited businesses authorized 0–5 | active firms | first-ticket successes | critical security incidents | high-priority defects | recovery/backup alerts | support response issues | customer feedback themes | conversion interest (nonbinding) | owner decisions required`

**Pilot stop criteria:** any cross-tenant disclosure, compromised credential, lost restore path, repeated uncontained outages, unknown real account, unauthorized payment/entitlement or independent reviewer no-go. Owner alone signs any restart of customer activation.

Related sources: [Master launch board #113](https://github.com/MrFixITslu/V79hub/issues/113), [Release decision](2026-10-15-release-decision-and-evidence.md), [Customer materials](2026-10-15-pilot-customer-pack.md), [Security handoff](2026-10-15-external-review-handoff.md).
