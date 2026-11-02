# First controlled external business pilot — V79 Hub + Tiquet
**Prepared:** 2 November 2026, Saint Lucia AST  
**Scope:** Founder-directed, invite-only first batch of **3–5 consenting organisations**, starting in Saint Lucia; suitable for Caribbean expansion only after outcomes are understood. Free **14-day Tiquet-only** trial through V79 Hub. **No live payments, no public registration, no customer-portal release, no automated unsolicited invitations.**

## Decision and risk disclosure
The founder has **waived** an independent third-party security/privacy review for the next launch phase. This is an **explicit risk exception**, not proof of security assurance or a waiver of legal privacy duties. Prior internal Humble Bee test was reported successful, and a two-synthetic-tenant Tiquet isolation test using the installed image passed. Neither substitutes for testing every future business or all vulnerability classes.

**GO for preparation and owner-approved invitations to the first cohort; NO blanket approval for open registration, paid access, mass mailings or new features.** No additional external email address has been approved in this work order. Every invitation requires an individually selected recipient and an operator review of current Invited/Active records.

## Shortlist — select 3–5 before inviting
Seek organisations with a genuine recurring need to track and update service requests, preferably: small ICT support/maintenance companies, electricians and electrical contractors, building/property maintenance, office facilities providers and small field-service teams. **These are candidate categories, not actual vetted business endorsements.** Consider mix of mobile/desktop users, low and medium ticket volumes and ability to provide feedback. Do not invent customer names or collect personal contact information without an appropriate basis.

For each prospective organisation record privately (not in GitHub): approved owner contact, business name, industry, invitation consent, date authorised, support contact, opt-out, invitation status, trial start/expiry, Tiquet mapping status, feedback and incident status. Do not post invitation tokens, passwords, phone numbers, personal data or customer ticket contents into PRs or project issues.

## Operator onboarding — one organisation at a time
1. In Hub **Customers**, search **Invited** and **Active** first; do not duplicate existing organisations or reset previously started trial periods.
2. Confirm the recipient expressly wants to try Tiquet for 14 days, can access the chosen mailbox and has received a simple description of the free pilot, privacy notice and contact method.
3. Choose **Invite a new business owner**; expiry **72 hours**; select **V79Tiquet only** (`app-tiquet`). Send only to the approved recipient. Never share the token in a public discussion.
4. Confirm recipient inbox receipt (provider acceptance is not evidence of delivery), private invitation acceptance and the exact *14-day* trial start/end dates. Do not manually turn on a paid plan or extend an existing trial.
5. Use **Provision selected apps** after acceptance. Verify mapping **active** before asking the business to launch the app.
6. In an independent private browser, the tester opens Hub with its own account, sees only assigned Tiquet, accesses only its own customer/ticket records, creates one clearly marked trial ticket and signs out. Record only pass/fail evidence; immediately escalate any cross-tenant access.
7. Record onboarding completed, feature issues, support requests and chosen end-of-trial disposition. Do not delete customer data solely because a trial ends without confirming retention/deletion responsibilities.

## Customer-facing copy — draft for individual consent-based invitations only
**Subject:** Invitation to try V79 Tiquet for 14 days

Hello,

V79 Digital is inviting a small number of Caribbean businesses to try **V79 Tiquet**, our service-request and job-tracking application, through V79 Hub.

The pilot is free for 14 days. You can use it to see how requests and jobs are organised, share feedback and tell us what would make it more useful. No card details or payment are required.

If you would like to participate, reply to this message and we will send a private invitation with sign-in instructions, trial dates and a link to the pilot information.

Thank you,
V79 Digital
https://v79sl.com

**Note:** Send only after the owner selects and approves the actual recipient; this first expression-of-interest message is not the invitation token.

## Support and review cadence
- **Day 0:** Confirm invitation delivery, acceptance, Tiquet mapping, initial login and a basic ticket.
- **Day 1:** Check the customer can return, find its own ticket and understands how to report issues.
- **Day 7:** Ask what worked, what was confusing and whether Tiquet saved time; request permission before using any quote.
- **Day 12–13:** Communicate the actual trial end date and options; no implied auto-charge.
- **Day 14:** Record trial closure and user feedback, ensure subscription access is governed by configured expiry, determine next step only with consent.

Support within **V79 Digital's normal operating hours** through an agreed channel; do not invent a contractual 24/7 SLA. Security or privacy incidents: stop cohort expansion, preserve relevant non-sensitive evidence, review account/sessions and use existing rollback and backup controls.

## Metrics for a first-cohort review
Record true **invitations approved / delivered / accepted**, provisioned mappings, active trial accounts, test tickets created, failed sign-ins, repeat-logins, support requests, priority bugs, reported time saved and explicit continuation interest. Targets (if adopted) are proposals, not actual results. Do not make fictional marketing claims.

## Phase 2 remains separate
WiPay merchant verification is pending. Current installed Hub settings point to a **Trinidad and Tobago sandbox (TTD/TT)** with `V79_BILLING_PROVIDER=disabled`; WiPay's support confirmed **Saint Lucia USD-only** live processing. Do not flip live/sandbox switches, use public test credentials for real sales or activate entitlements from a browser redirect. Verify merchant account, API validation, replay/duplicate protection, refunds and settlement first.

## Red-team stopping conditions
Stop further invitations and escalate if: one business can see another's ticket; new user sees platform-owner functionality; an active copied session survives logout beyond documented enforcement; private invitation URLs leak; a payment/card request appears; personal data is sent to the wrong mailbox; or backups/rollback become unreliable. Invite-only is a smaller deployment scope, not a guarantee against breaches.

## Current status
**Cohort playbook prepared; no external recipients selected, no new invitations sent, no new public deployment needed.** Founder-provided first internal tester (Humble Bee) previously completed and accepted. Next execution dependency is the founder's approval of **3–5 actual businesses and addresses**, and acknowledgement of this limited, risk-accepted free pilot. Independent review is owner-waived; legal privacy and support obligations still apply.
