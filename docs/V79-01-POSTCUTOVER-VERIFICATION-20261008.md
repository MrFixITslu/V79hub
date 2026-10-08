# V79-01 — Post-cutover verification (8 October 2026)

## Scope

Verification of the existing, authorised one-organisation 14-day beta activation and the V79 nightly backup. This audit did not activate paid subscriptions, edit customer data, bypass MFA, or initiate any new production deployment.

## Verified

- Five application containers (Hub, POS, FFPRO, Tiquet, Marketing) healthy; public HTTPS smoke tests returned HTTP 200.
- Hub release configuration audit: `ready: true`, `issueCount: 0`.
- Hub live state queried through PostgreSQL `BEGIN READ ONLY`: two organisations, exactly one non-founder customer organisation, one active customer trial, five enabled customer entitlements, founder internal access preserved, zero reminders presently due, zero reminder events.
- Existing approved trial expires **22 October 2026 21:20:02 UTC**. Reminder stages are 7 days prior, 1 day prior and expiry, with idempotency and bounded retries covered by tests.
- Anonymous API access: Hub `/api/auth/me`, `/api/admin/customers`, `/api/billing/summary`; POS `/v1/me`; Tiquet and Marketing `/api/auth/me` all rejected unauthenticated requests with HTTP 401. FFPRO session-state returned HTTP 200 but `authenticated:false` with no user.
- Hub administrator password-only login yielded HTTP 202 MFA challenge, no authenticated session. This blocked an automated **live privileged launch** check; it was **not** bypassed.
- Hub source test suite: **142/142 passed** after strengthening isolated MFA test-server readiness handling. `npm run lint` and `npm run build` passed; build reports a nonblocking large-client-chunk warning.
- Authoritative DNS: `hub.v79sl.com` resolves to the intended IPv4 address with no conflicting CNAME; provider sending DNS (DKIM and the two SPF CNAME records) verified. Resend is enabled for sending and two prior diagnostic messages were delivered. The provider domain is *partially_failed* because optional tracking CNAME records remain incomplete; open/click tracking is disabled. Do not replace Hub's A record with a Resend tracking CNAME.
- Fresh post-cutover recovery point on the separate backup workstation: snapshot `2026-10-08_17-52-11`, completed 17:56:06 AST. Five PostgreSQL custom-format dumps, three protected app-data archives, twelve Docker volume archives, and home-directory copy. All 20 archive SHA-256 checksums verified. The backup script now checks volume counts and writes a manifest before the success marker.
- Isolated, no-network PostgreSQL restore: **all five dumps restored**; FFPRO 21 tables, Tiquet 20, Hub 1, POS 78, Academy 8. Disposable test container/volume and staging copies were removed.
- Latest Laser Tag SQLite archive passed `PRAGMA integrity_check` with 33 tables; Foundation data JSON parsed. Production applications were not stopped.
- Incomplete backup attempt `2026-10-08_17-36-57` was deleted after confirming it had no success marker and the new snapshot passed verification.
- The 02:00 AST systemd timer remains enabled on the separate backup workstation; next scheduled invocation is 9 October 2026 at approximately 02:01 AST.

## Open safeguards / intervention needed

1. **MFA-protected browser launch:** end-to-end live owner sign-in and app launch require an authorised person to complete MFA in the browser, or a sanctioned non-admin beta test login. Do not collect OTPs in logs or disable admin MFA to automate it.
2. **Backup retention — resolved after report:** historic snapshot ownership was corrected on the independent backup workstation; the expired 14 September snapshot was removed and surviving snapshot root directories restricted to owner-only access. The latest verified snapshot was retained.
3. **Encrypted off-site recovery — explicitly deferred by founder:** future implementation only; no B2 account, restic installation, repository, keys, upload, or scheduled off-site run. The protected off-site script is staged but intentionally inactive. Local workstation backups and restore tests remain the active beta recovery method. This leaves loss/theft/fire of the backup workstation as a residual disaster-recovery risk. Reassess before any commercial launch; do not represent the off-site gate as passed.
4. **Delivery tracking:** optional Resend tracking CNAMEs remain pending/failed; they are not required for transactional sending while tracking is disabled.
5. **Backup restore coverage:** PostgreSQL and selected data integrity are tested; a complete restored multi-app stack, login/MFA, callbacks, and disaster recovery rehearsal have not yet been proven.
6. **Recurring alerts — partially resolved:** independent local workstation monitor now runs at 08:15 and 20:15 AST, verifies success marker, freshness, permissions, file counts, SHA-256 checksums, and systemd result, and logs failures. Positive and intentional archive-tampering negative tests passed. External failure email notifications remain unconfigured and must not be represented as complete.

## Release boundary

No additional production deployment, financial payment activation, public customer onboarding expansion, or security downgrade is authorised by this record. Keep the one existing approved trial and production-level safeguards intact.
