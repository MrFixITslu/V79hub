# Workforce completion review — 19 October 2026

## Decision
Three approaches were considered: manual ChatGPT operations, extend existing CEO/COO workforce, or a separate assistant. Extend the existing workforce and existing G2 ledger. Avoid a second task queue or a second Hub. Preserve owner-reviewed, owner-sent email replies.

This branch is **source preparation, not a running workforce or deployment**. ChatGPT Gmail/Calendar profiles were checked against vision79slu@gmail.com and the primary calendar was identified. That session access does not authorize or authenticate the server. No customer emails, drafts, invitations, appointments, worker schedules or production containers were changed.

Desktop Commander listed v79sl online, but the first read-only host command was refused because the account's monthly usage was reached. No host command ran through that attempt. Do not retry/reconnect to bypass the limit; host OAuth and service state remain unverified.

## Added source
- Email Assistant and Calendar Assistant packages; six specialists and two orchestrators retained. Catalog 1.1.0 records ten skills and keeps analysis/draft model permissions. Approved external effects belong to G2 and the restricted worker, never the skill prompt.
- Fixed Google API client for inbox/thread reads, reply draft creation, primary-calendar agenda, single-event creation, editing and cancellation.
- Existing G2 request validation and digest extended to bind Google recipient/body/event/time/attendees/version. Non-Google operations cannot target Gmail or Calendar.
- Google proposal/approval gate defaults disabled; existing release worker cannot propose or claim Google effects.
- Host-only worker consumes durable owner-approved G2 jobs once, stores provider receipts before final status, and leaves interrupted/uncertain effects for manual reconciliation.
- Original-thread MIME replies; no send API. Calendar account binding, bounded dates, availability checks, deterministic creation IDs, If-Match version protection, owner-organized single-event restriction.

## Red-team results and remaining limits
| Failure | Control / remaining work |
| --- | --- |
| Email tells agent to send secrets or book meetings | Treat all retrieved content as untrusted; no send tool; owner-originated concrete proposals only. Actual model injection evaluations still required. |
| Gmail draft token can also send | gmail.compose permits both. Keep tokens in fixed-operation host broker, inaccessible to the model; expose no general authenticated request tool. No claim of Google-enforced draft-only OAuth. |
| Duplicate after timeout / crash | Durable G2 claim, no automatic reclaim/retry, receipt before completion; calendar create has deterministic ID. Gmail ambiguous outcomes require manual draft reconciliation. |
| Wrong person / Reply-To diversion | Skill requires recipient verification and exact owner review. Adapter validates one mailbox but does not independently resolve identities. |
| Wrong calendar / event series damaged | Primary account only; owner-organized single-event mutation; recurring changes and RSVP unsupported. |
| Overbooking | Pre-write availability check and update overlap listing. Check-and-book is not atomic; concurrent calendar writers can race. Other calendars/attendee availability are outside default scope. |
| Stale approval or modified event | G2 digest, expiry, owner MFA at approval route, exact etag and If-Match. |
| Google revoked / rate-limited | Bounded provider errors and stop; never fabricate success. Broker refresh/revocation handling remains to implement and accept live. |
| Private data in work queue | Gmail draft bodies live in existing private G2 payloads; keep ledger/receipts encrypted in backups, owner-only and outside generic application logs. Review retention before activation. |

## Work still required for operation
1. Establish a server-owned Google OAuth app and authorization for the owner. Never copy ChatGPT connector credentials, paste refresh tokens in chat, or commit secrets. Verify OAuth production/testing lifetime and revocation behavior before unattended acceptance.
2. Implement isolated host credential broker with secure refresh-token storage, fixed Google endpoints, no model token access, fail-closed account verification, revocation and restricted egress. Expected permissions: Gmail reading + composing; Calendar reads + owner-event writes. Confirm exact scopes against the APIs used before consent.
3. Bind the existing trusted owner organization/MFA context to read routes. Add owner UI for inbox/thread selection, full draft review, agenda and exact event proposal. Existing generic G2 JSON confirmation supports reviewing queued payloads, but **Google proposal forms and reader UI are not implemented**.
4. Wire broker/client and durable G2 ledger to the host worker with a private, durable receipt store. The worker is an exported function only: no CLI, timer, HTTP mount or production enable flag is installed. Configure Google gate explicitly only after integration and acceptance.
5. Add bounded polling/scheduling, business-email classification and follow-up reminders. Owner must choose inbox scope and working-hours/buffer rules before unattended triage or scheduling. No scheduler was created here.
6. Run harmless real-account draft/appointment lifecycle tests, denial/revocation tests, readback reconciliation and restart recovery. Confirm Gmail Sent unchanged. Score actual model outputs against rubrics for all ten skills.
7. Close inherited workforce acceptance gates below before claiming complete.

## Whole-workforce acceptance
| Area | Evidence / required next proof |
| --- | --- |
| CEO/COO and six specialists | Packages exist. Actual model quality, supported live evidence and task delivery must still be accepted. |
| Reports | Prior owner report viewing/evening run recorded. Independently verified three-day AM/PM inventory still needed. |
| Task execution | Prior harmless COO task creation recorded. Task creation does not prove engineering delivery. |
| Live metrics and alerts | Source gates exist. Real app adapters, provenance, freshness and owner notification receipt required. |
| Budget and learning | Existing budget/evidence checks retained. Actual spend receipts and approved learning behavior remain runtime acceptance work. |
| Gmail/calendar | New adapter/worker/skill source tested offline. Server OAuth, broker, UI, scheduler and live acceptance outstanding. |
| Hub/Tiquet release | Separate R18 production acceptance, My Apps 403 and checkpoint evidence must be reconciled from current live artifacts; not certified by this branch. |

## Validation
Local full Hub suite: **553 tests, 549 passed, 4 skipped, 0 failed**. TypeScript lint and production build passed. After the final default-disabled route change, focused Google/G2/tenant regressions passed **22/22**. Separate source-only specialist/evidence/reliability tests passed **69/69**. These counts include synthetic HTTP/provider tests, not real Google or live-server tests.

Google references: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/create ; https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/send ; https://developers.google.com/calendar/api/guides/version-resources ; https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query .

## Follow-up after owner preflight — supersedes initial missing-source items

Owner supplied healthy Hub/Agent evidence and existing timer trigger times; see [authorization runbook](workforce-google-authorization-20261019.md). Google environment configuration was not observed in the two inspected containers; files and existing OAuth projects were not inspected.

Now implemented in source: private Desktop OAuth consent helper (PKCE/state/account/scope checks), Hub-side credential broker with automatic access-token refresh, owner-MFA read routes, private durable receipt writer, supervised execution route, owner email/calendar proposal panel and exact Google approval details. Default remains disabled. No deployment or real-account authorization took place.

Remaining: owner OAuth client/consent, isolated build/mount/runtime rehearsal, exact live-source/image reconciliation and guarded cutover, real-account lifecycle acceptance, automatic draft generation, bounded unattended triage and source-message deduplication, reminders, model evaluation and inherited workforce acceptance. An authorized Google connection alone will not complete these.

Follow-up local full suite: 560 tests, 556 passed, 4 skipped, zero failures. Final response-size hardening and metadata/partial-content cases: 31 focused Google/G2/tenant tests passed, five separate Python OAuth tests passed, TypeScript lint and production build passed. Google HTTP and credential tests are synthetic; no live OAuth or Google writes occurred.
