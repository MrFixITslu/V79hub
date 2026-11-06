# Customer help feedback — development contract

Status: implemented and checked on the development branch; not deployed. No deployment or live configuration/data changes.

## Choice and design

The owner selected customer feedback as the next chatbot phase. Compared full conversation logging (too much private data), simple ratings (limited diagnostic value), and ratings with fixed reasons (chosen). UI alternatives: interrupting survey, separate feedback page, or inline response feedback with an expandable owner report (chosen). Preserve the existing readable Help page and V79 theme; no new navigation surface or dependency. The additional Impeccable package is unavailable here; use the existing project guidance.

## Acceptance and boundaries

- Every eligible help reply offers optional Helpful / Not helpful feedback. Negative feedback asks for a fixed reason; no free-text feedback or transcript is collected. A failure is retryable and does not remove the help answer.
- Server-issued tickets bind the actual answer metadata to the active user/workspace, expire after two hours and permit one durable vote per reply. Client-supplied article IDs, identity, status, version and URLs are rejected.
- Persist only aggregate day/workspace/app/topic/version/status counts and short-lived ticket digests for replay prevention. Never persist questions, answers, history, emails, user IDs, credentials or support drafts. Reports count submitted feedback, not all sessions or unique people.
- Workspace owners can read their workspace's report. Only the verified platform operator, with the existing required MFA checks, can read the aggregate platform report. Ordinary customers, revoked/suspended sessions and forged scopes cannot read reports or affect another user's ticket.
- Reports show helpfulness, fixed reasons, feedback on undocumented requests and topics needing attention; filter by 7/30/90 days and app. Empty, loading, retry, permission/session-expiry and narrow-screen states are required. No raw questions appear in the report.
- Use a separate signed, bounded, private JSON ledger in the existing DATA_DIR mount, with atomic writes and a cross-process lock. Reports exclude aggregates older than 90 calendar days in Saint Lucia and replay digests expire with tickets. Expired entries are physically pruned on the next accepted vote; no background deletion job is configured. Corruption/capacity/lock errors fail closed for feedback while ordinary help stays available. No database schema or new service.
- No guide edits, ticket submissions, local-AI changes, marketing events or external transmission follow from a vote. Development tests use disposable stores and identities.

## Red team and verification

Protect against ticket replay, manufactured topic/status reports, cross-tenant votes/reports, stale roles/MFA, prompt/PII persistence, double clicks and lost concurrent writes. Test meaningful service, file persistence, HTTP, full-Hub and React flows; inspect the isolated synthetic interface at desktop and phone widths. Previously passed unchanged behaviour is not repeated merely for a checklist. A sequential self-review is not an independent security audit.

Keep the new source on a separate branch based on deployed revision a093f11582eef29ef296647bd9c25209cc34603d. Ship a draft PR and evidence; deployment is excluded.


## Verification — 6 November 2026

| Check | Observed result |
|---|---|
| Focused help / feedback suites | 81 tests passed in the consolidated run, then the new report-concurrency test passed: 82 distinct focused tests. Affected router/UI paths were rechecked after the final read bound and copy changes. |
| Navigation | Eight existing navigation/refresh/authentication-boundary checks passed after the Help component gained workspace/owner-aware reset keys. |
| Persistence | Aggregates survive a real isolated Hub restart. Separate Node processes and concurrent callers preserve counts; repeated tickets count once. Expiration, calendar windows, corruption, file permissions, symlinks and write-fence refusal checked. |
| Privacy / authorisation | No question/answer/history/email/user IDs persisted. Workspace owners cannot read another workspace's report; only the verified platform operator with required MFA can read platform aggregates. Viewer, revoked, suspended, missing-MFA and forged-scope cases denied. |
| UI | Helpful and fixed-reason negative votes, retry, expiry and owner-only report controls checked in React DOM. Real synthetic browser exercised empty/populated reports, filtering, votes and save confirmation. |
| Rendered layouts | Desktop 1363px plus same-origin 320/390/768px frames; no page overflow. The report table scrolls within its region at 320px and accepts keyboard scrolling. Dark theme inspected at 768px. Frames are not physical-device tests. |
| Build | TypeScript and Vite build passed. Main client asset about 794 kB / 212 kB gzip; the existing bundle-size advisory remains. No new dependency or database migration. |

The screenshot in `docs/review/feedback/synthetic-feedback-report.jpg` shows three synthetic QA votes, not live customer statistics. Review was sequential self-review; no independent penetration test, screen-reader certification or production load measurement is claimed.

## Operations and limitations

- Configuration uses the existing Hub security key and the existing DATA_DIR mount. A missing/short key disables feedback without disabling help. The only new durable file is `help-feedback-v1.json` (private, signed, atomic replacement); include it in future encrypted DATA_DIR backups. No backup or deployment was run in this phase.
- Preserve the signing key across restarts. Key rotation requires an intentional ledger migration/re-signing plan; invalid integrity never resets the ledger silently.
- Feedback tickets last two hours. One vote per actual reply is enforced, not one vote per person/topic; these are advisory voluntary counts, not a survey of unique customers or a census of all questions.
- Reports cover at most 90 days. Older rows and expired replay digests are excluded immediately on reads and removed during the next accepted vote. There is no timer or scheduled physical-deletion guarantee.
- Limits: 25 MiB ledger, 50,000 buckets and 50,000 unexpired ticket digests; bounded voting counters/concurrency and four concurrent report reads. Capacity, corrupt storage or an orphaned lock produces a retryable feedback/report error; help remains usable. Inspect any orphaned `.lock` directory and remove it only with all Hub writers stopped.
- No raw unanswered-question text is collected. Gaps are grouped by app, known topic where present, answer status and fixed reason. The owner must review any guide changes separately.
- No ticket creation, email, local-model connection, analytics provider, publishing or production change was introduced.
