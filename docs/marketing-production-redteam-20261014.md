# G3 marketing production: design, red-team review and rollout

The current agent draft handoff saves a planning brief. G3 turns an approved
brand and standing draft plan into actual campaign packages, with per-channel
copy, PNG assets, a captioned MP4, subtitles, newsletter HTML, and exact
publication approvals in Hub. It retains the CEO/COO organization: COO handles
production and dispatch; CEO review is currently an explicit deterministic
rule check; the founder retains publication authority. It does not claim an
independent human or model security sign-off.

## End-to-end path

1. The founder signs into Hub with MFA and approves verified service facts,
   original logo, brand colours, audience, tone, CTA and draft cadence. The
   first profile includes sample facts for review, not independently verified
   commercial claims. Automatic drafts are off by default.
2. A single Marketing worker generates one campaign at a time, rotating
   approved services. It uses the existing local Ollama model for two bounded
   creative strings; unavailable or malformed output falls back to an explicitly
   labelled brand template. There is no cloud model fallback or AI API spend.
3. Verified claims are inserted verbatim from the approved facts. CEO rule
   checks flag unsupported numbers/claims, foreign CTA links, channel length,
   missing brand/CTA, and missing newsletter footer/address. These rules do
   not prove every possible claim is accurate. Human review remains required.
4. FFmpeg renders original branded square/wide PNGs and a captioned portrait
   MP4, plus SRT and copy/HTML exports. The renderer invokes a fixed binary
   without a shell, URLs, model-generated filters or arbitrary filenames.
   It creates procedural visuals, not photorealistic AI images, narrated video
   or licensed stock footage. The actual supplied logo is composited when
   available; otherwise the review warns that a text wordmark was used.
5. The founder previews actual assets and each platform's copy in Hub. Each
   approval binds the package and asset hashes, channel, exact provider
   account, account metadata/legal choices, and an absolute schedule within
   fourteen days. Approval remains valid until one hour after that schedule.
   Changes to configuration cancel all unstarted approvals.
6. A worker claims a due approved delivery transactionally. It verifies every
   asset hash, checks the exact account, and obtains a fresh, uncached founder
   permission check from Hub. Pause and authorization are checked again after
   provider token refresh, immediately before the provider call.
7. Successful provider acceptance is recorded; it is not proof of final
   distribution, reach or conversions. Exceptions appear as next steps in the
   Hub panel. Running/uncertain jobs are never reclaimed or retried automatically.
   A lost process/receipt requires operator inspection and a new reviewed action.

## Channel readiness

| Channel | Adapter | Additional readiness |
| --- | --- | --- |
| Facebook | Existing official photo provider | One connected exact account; approval of copy/PNG/time |
| Instagram | Existing official photo provider | One connected exact account; valid permissions |
| LinkedIn | Existing official text provider | One connected exact account; visual export is available, automatic delivery is text-only |
| YouTube | Existing official video provider | Exact channel; explicitly selected private/unlisted/public visibility; HTTPS source ingestion |
| TikTok | Existing official photo provider | Current creator privacy choice, owner music confirmation, own-brand disclosure, AI-content label; MP4 remains exportable |
| Newsletter | Optional Resend broadcast adapter | Exact operator-configured sender/segment, mailing address, owner-confirmed opt-in scope, complete segment of at most 100 contacts |

Unconfigured channels remain private, exportable materials. The system does not
silently switch accounts, create provider credentials, register new services,
buy media, or bypass quotas/review requirements.

Newsletter approval covers the **current opted-in members of the exact approved
segment at send time**, not a permanently frozen list of individual recipients.
A preparation fingerprint/count is shown; membership is checked again before
dispatch and detected drift blocks sending. Provider membership may still change
between that read and provider acceptance; the approval's explicit live-segment
policy and Resend unsubscribe/suppression handling apply. Recipient records
remain outside model prompts and Hub responses. A checkbox is an owner
attestation, not automated proof of legal consent: configure only a segment
maintained through a verified opt-in process. Never import leads/purchased lists
as presumed subscribers. No recipient import or consent-override tool exists.

Approved PNG/MP4 sources become temporarily reachable over HTTPS for provider
ingestion, including for private YouTube uploads. Their immutable source URLs
expire one hour after scheduled time/provider receipt. Drafts, copy JSON,
newsletter HTML, credentials and ledger data never use these public routes.
The approval dialog explicitly discloses this ingestion behavior.

## Red-team findings and mitigations

| Attack/failure | Implemented control | Remaining limit |
| --- | --- | --- |
| Approve a brief, publish different copy or asset | Canonical content/asset/destination/schedule digests; verify bytes at dispatch and ingestion | Administrator holding signing/audit keys remains trusted |
| Worker/model approves itself | Only signed Hub requests from exact persisted founder mapping, with fresh genuine MFA, can decide | CEO checks are rules, not a substitute for owner review |
| Replay an old resume/approval packet | Dedicated signing secret plus persistent request nonce, bounded expiry and state transitions | Host administrator/key custody must be protected |
| Substitute another tenant/owner | Fixed founder org; persisted Hub linkage; per-business HMAC domain separation; scoped Hub user mapping | Ownership migration needs operator reconciliation |
| Revoke the owner but keep cached entitlement | Dedicated uncached Hub authorization checks exact current founder, active owner membership and MFA enabled | Pause/revocation cannot undo a provider call already accepted |
| Prompt injection from external content | No inbound email/web scraping/tools; two schema-validated creative strings only; claims from owner facts | Rule screening cannot detect all misleading wording |
| Shell/FFmpeg/template injection | Fixed `execFile` binary/args; literal text files with expansion disabled; escaped newsletter HTML | FFmpeg/fonts must pass real image smoke tests |
| Replaced logo, image, video or source URL | Bounded PNG input; owner review; immutable hashes; fixed owned media origin/path | Logo ownership/licensing is owner-confirmed |
| Lost provider receipt/duplicate publish | Transactional one-time claim; uncertain state; no retry or lease stealing | Operator must investigate uncertain outcomes |
| Customer data sent to model | Only audience/tone/service/angle sent; no customer contacts, provider tokens or private snapshots | Operator's brand text should contain public-safe facts |
| Newsletter spam/consent drift | Explicit opt-in segment/sender/address; member fingerprint/count; footer; provider suppression | This is not automated legal certification |
| Automatic ad spend/cloud generation | No ad adapter or cloud AI fallback; existing local model and procedural assets | Newsletter/provider plan charges remain operator-controlled |
| Resource exhaustion | One worker loop; bounded text, 200 packages, 4,000 events, at most 100 email contacts; one FFmpeg thread/timeouts | Configure container CPU/RAM limits and retention before sustained use |

## Deployment gates

The current live Hub is G2 image `sha256:26e959fbc07ace5cf20a1d3ea001229911014346c6eb1c89d629d88993bbca8a`.
G3 remains **disabled and not deployed** by this change. Both repositories need a
coordinated, exact-image upgrade. Do not merge to Marketing main merely to test:
its main workflow publishes and deploys.

1. Inventory the running Marketing image, Compose files/working directory,
   SQLite/data mounts, runtime source-map hashes, connected-account counts,
   current Hub scoped owner mapping, and model settings without printing keys.
2. Reconcile runtime source against the exact tested Marketing baseline before
   building. Preserve any live-only functionality; no blind main upgrade.
3. Back up Marketing using SQLite's online backup, data/assets and current
   config/secret material with the existing owner public recovery key. Keep the
   private key on Acer. Prove isolated restore and exact rollback; retain all
   current Hub G2 signing keys and immutable image/config overlays.
4. Create dedicated `V79_MARKETING_PRODUCTION_SHARED_SECRET` in Hub/Marketing
   and `V79_MARKETING_PRODUCTION_AUDIT_KEY` in Marketing; include both in encrypted
   backup and Acer decryption verification. Do not mount Docker into Marketing
   or Business Agent. Keep the two rollout flags `...ENABLED=0` initially.
5. Verify ordinary Hub/Marketing login, SSO, current accounts/billing/WiPay,
   actual FFmpeg renderer in network-none/read-only/non-root Docker, and source
   parity. The new Docker CI step performs the real renderer smoke.
6. Enable generation only for the exact founder organization. Supervise a
   brand approval, one generated package, original-logo preview, asset checks
   and rejection/cancellation. No provider calls yet.
7. Enable `V79_MARKETING_PRODUCTION_PUBLISH_ENABLED=1` only for the internal
   founder pilot after actual connected-account verification. Approve a single
   explicitly selected private/test destination; inspect its real provider
   receipt and verify duplicate prevention before approving broader publishing.

Environment: `V79_MARKETING_PRODUCTION_ENABLED`, `V79_MARKETING_PRODUCTION_OWNER_ORG_ID`,
`V79_MARKETING_PRODUCTION_SHARED_SECRET`, `V79_MARKETING_PRODUCTION_AUDIT_KEY`,
`V79_MARKETING_PRODUCTION_PUBLISH_ENABLED`, `V79_PRODUCTION_ASSET_DIR`.
Optional email: `V79_NEWSLETTER_RESEND_API_KEY`, `V79_NEWSLETTER_SEGMENT_ID`,
`V79_NEWSLETTER_FROM`. All secrets stay outside Git/chat.

## Validation evidence

Local new and existing Marketing tests include actual PNG/MP4/SRT/HTML rendering,
content/account/schedule drift, HMAC tampering and cross-tenant envelope copying,
request replay, stale MFA, CSRF/cookie rejection, account/entitlement rejection,
pause/expiry/config changes, uncertain outcomes, newsletter scope/consent checks,
and no duplicate provider dispatch. Provider tests use synthetic adapters and
mock transport; no live post or email was sent.

The first server candidate build completed both images but stopped before the
Hub smoke tests: a private build-directory umask also made copied public source
directories/files unreadable to the non-root test user. The candidate builder
now normalizes only public checkout directories/files to readable modes while
keeping its parent recovery/build directory private. CI runs the same exact
approval/marketing route tests inside the non-root, read-only, network-none image.

The Marketing lockfile additionally updates only `ip-address` 10.7.0 to 10.7.4,
`proxy-addr` 2.0.7 to 2.0.8, and `source-map-js` 1.2.1 to 1.2.2. Their reported
advisories were confirmed against maintainer/GitHub security notices. The patched
Marketing lockfile and current Hub lockfile both report zero known runtime npm
advisories at this check; this is not a guarantee against undisclosed issues.
Marketing CI now fails on known high/critical runtime dependency advisories.

Hub's full suite is run with a test-only preload which rejects every non-loopback
fetch, including child processes. This replaces an inherited Games destination
that automatic approval review rejected. PostgreSQL-specific CI checks, real
Docker build/render smoke and live founder/provider acceptance remain distinct
release gates; a local passing test is not a commercial launch claim.

Primary provider references: Resend [broadcast create](https://resend.com/docs/api-reference/broadcasts/create-broadcast),
[segment contacts](https://resend.com/docs/api-reference/segments/list-segment-contacts),
and the repository's existing official social-provider adapters.
