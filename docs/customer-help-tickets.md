# App Help → high-priority V79 support tickets

Development only. Builds on feedback PR #229; no production release or test ticket.

Compared a contact link, a prefilled Tiquet handoff and direct submission. Choose direct submission from the existing reviewed summary: one flow, no separate Tiquet subscription, and a confirmed reference. UI alternatives were a modal, separate support page and inline submission; choose inline to retain the draft and guide context.

## Contract and acceptance

- Every active authenticated Hub member, including viewers without Tiquet entitlement, may explicitly send an unresolved issue or error report to V79 support.
- Summary is editable and reviewed, recent conversation opt-in. Clearly disclose that submission shares the summary and Hub contact/workspace with V79. Credentials should be removed by the customer; pattern redaction is a convenience, not a privacy guarantee.
- Browser supplies only app, issue kind, summary and an opaque UUID. Hub derives requester identity from its active session and namespace-binds the request ID with HMAC to that user and workspace. No browser choice of priority, destination, assignment, contact or owner IDs.
- Dedicated signed machine endpoint, separately enabled/configured. Tiquet verifies the fixed V79 account/Hub organisation and assigned Admin identity on every delivery. Server always creates priority `high`, status `request`, assigned to the configured V79 owner, with an in-app owner notification, tag and audit entry.
- Tiquet commits ticket, receipt and notification atomically. Durable receipts and a PostgreSQL advisory lock prevent duplicate retry/concurrent/restart delivery and reject changed payloads. Receipt survives ticket deletion: retry cannot recreate a deleted ticket. No customer access to the support tenant or other customer tickets.
- Retry an uncertain request with exactly the same key and payload. Lock editing after the first delivery attempt; enable editing only after definitive validation failure. Keep draft and retry information in memory only. Closing/reloading loses unsent text and uncertain-request recovery; warn before leaving during submission/uncertainty. No silent background submission.
- Bound body, request concurrency, Hub short-term rate and durable Tiquet per-requester hourly/daily quotas. Retry existing receipts before applying creation quota.
- Confirm success only for a matching committed Tiquet acknowledgement. No unsafe portal link, email, payment, client creation, AI action or entitlement mutation.

## Red team

Check forged identity/destination/priority, foreign origin, expired/revoked/suspended sessions, signature/body alteration, redirects, changed replay, simultaneous delivery, response lost after commit, process restart, rollback on notification/DB failure, wrong/suspended destination and owner demotion. Test isolated fake identities only; no production tickets. Review mobile/desktop render, keyboard, pending/error/expiry/success states. This is sequential self-review, not an independent penetration test.

## Release boundaries

Hub change stacks on the feedback branch. Tiquet change is based on the deployed security source branch `release/tiquet-p1-session-file-security-20261102` (9020030), rather than older main, preserving deployed session and file restrictions. Both features default off and need matching dedicated secret plus explicit verified V79 destination/owner configuration. Deployment requires both reviewed images and the feedback dependency; existing image/config and DB backup must be retained. New additive receipt table must not be dropped on rollback.

## Verification — 6 November 2026

- 31 distinct focused cases passed across Hub bridge/router, Help React UI, existing help and feedback routes, full Hub authentication, the cross-repository PostgreSQL integration and Tiquet ingress/config/schema tests. The affected Hub UI/bridge cases were rechecked after the final size guard and layout fixes; unchanged guide/feedback persistence suites were not repeated.
- The actual isolated Hub server, Tiquet receiver child process and disposable PostgreSQL 17.11 exercised a viewer without Tiquet entitlement, signed delivery, server-derived requester/contact, fixed V79 owner/High priority, one notification/tag/audit, an acknowledgement dropped after commit, parallel identical retries and real Hub/Tiquet process restarts. Both returned the original reference. No live database/container or customer ticket was used.
- Origin/session/schema/signature/expiry/redirect denial, cross-requester receipt isolation, changed replay, deleted-ticket tombstone, owner demotion/link mismatch, suspended destination, rollback after notification failure and durable hourly quota passed. The daily quota has implementation coverage within the same SQL path but no separate 24-hour boundary test; no load/security certification is claimed.
- TypeScript and production builds passed for both repositories. Existing bundle advisories remain: Hub ~799 kB / 213 kB gzip; Tiquet ~862 kB / 240 kB gzip. No dependency changes.
- Browser exercised the synthetic viewer's reviewed error report and confirmation, consent requirement and keyboard focus; desktop 1363px, 320px phone frame and 768px tablet frame (dark theme). No horizontal page overflow at 320/768px; reference text wraps. These are Chromium frames, not physical-device or screen-reader tests. One stretched-copy-button layout defect was found and corrected before the final inspection.
- `docs/review/help-tickets/synthetic-ticket-receipt.jpg` is a visual-only synthetic receipt from the disposable signed preview simulator. Actual database confirmation was tested separately in the PostgreSQL integration above. It is not a production ticket.

## Configuration and operations

Both services require `V79_HELP_SUPPORT_ENABLED=1` and the same dedicated `V79_HELP_SUPPORT_SHARED_SECRET` (at least 48 bytes). Hub also requires `V79_HELP_SUPPORT_TIQUET_URL`, an origin-only HTTPS URL or the exact internal Tiquet Docker hostname over HTTP. Loopback HTTP is allowed for isolated development. No redirect is followed. Keep service traffic on the private Docker network or authenticated TLS.

Tiquet requires explicit `V79_HELP_SUPPORT_ACCOUNT_ID`, `V79_HELP_SUPPORT_ORGANIZATION_ID`, `V79_HELP_SUPPORT_OWNER_USER_ID` and `V79_HELP_SUPPORT_OWNER_HUB_USER_ID`. Verify these against the actual V79 account/Neil identity before enabling; never copy a customer's tenant ID, infer an owner by name/email alone or reuse a Sentinel grant. No live values were written in this phase.

The additive `hub_help_support_receipts` table is created by the existing schema initialiser. Include it in encrypted PostgreSQL backups and retain it through image rollback. It stores requester hashes, semantic payload hashes, job IDs, destination IDs and timestamps; the reviewed issue/contact are saved on the support ticket, outside the anonymous feedback ledger. Receipts do not expire automatically: deleting them can permit an old request to be recreated. Treat retention/removal as a separate reviewed data policy.

Preserve the dedicated secret. Rotating it changes Hub-derived idempotency IDs and requires a deliberate migration/retry plan. Browser drafts and uncertain-request keys are memory-only: reloading, closing or navigating to another Hub page loses recovery context. The form warns on browser unload and disables its own reset/app/guide controls during uncertain receipt. Hub-wide navigation is not globally intercepted. Copy the summary and contact support when recovery is uncertain; there is no background queue or promised response time.

Hub limits ten delivery attempts/minute per user/workspace and eight in flight. Tiquet limits eight in flight and five new requests/hour, ten/day per requester across restarts; known receipts bypass creation quotas. A changed contact/workspace name on a retry is a semantic conflict, not permission to create a second ticket. In-app notification is atomic; no email/SMS is sent. Missing/invalid configuration fails closed while the help guide and copy/contact fallback remain available.

Run the cross-repository check explicitly from Hub with isolated binaries/source paths:

```sh
V79_TEST_POSTGRES_BIN=/absolute/path/to/postgres/bin \
V79_HELP_TIQUET_TEST_SOURCE=/absolute/path/to/V79Tiquet \
NODE_OPTIONS=--import=./tests/isolated-env.mjs \
node --test tests/customer-help-tickets.integration.mjs
```

The fixture binds PostgreSQL to loopback, uses a temporary trust-authenticated test cluster and removes it on completion. Never supply a production PG host/URL. The test does not load either application's production database adapter.
