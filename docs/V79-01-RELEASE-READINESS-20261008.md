# V79-01 release-readiness evidence — 8 October 2026

This document records what was actually verified. **Production deployment / subscriptions remain NO GO.** No `main` merge, production cutover, production email configuration, customer plan modification or public-app code rollout has been performed.

## Completed staging checks

1. **Email domain:** Resend identifies `v79sl.com` with Sending enabled; DKIM and both Forge SPF CNAME records marked verified. Overall provider status remains partially verified because optional tracking records are pending. Open/click tracking is disabled.
2. **Restricted credential:** New Resend API key `V79-Hub-Transactional-Staging-20261008` created with **sending_access**, restricted to the verified sending domain. Its secret is held exclusively in a `0600` staging file under the `0700` staging secrets directory on the authorised server; not in Git or the live Hub environment.
3. **Real Hub-originated mail:** Standalone staging invocation of the development `createResendTransactionalSender` sent one neutral diagnostic message from `V79 Digital <notifications@v79sl.com>` to the founder's designated Gmail test inbox. Resend later reported **delivered**. This tests the real V79-01 transport code but does **not** test clicking a password reset link or scheduled delivery inside a live customer account.
4. **Cutover baseline:** A new `scripts/read-only-live-cutover-preflight.mjs` queried the running Hub's production PostgreSQL with a `BEGIN READ ONLY` transaction and `ROLLBACK`; result: two active organisations, one verified internal founder organisation, one existing active customer with one owner, five distinct enabled app entitlements, **zero plans**, no reminder events and no live email/reminder activation. No IDs, secrets or personal data were printed. The read-only baseline passed.
5. **Trial safety:** `prepareApprovedLegacyCutover` accepts only exact unambiguous UTC ISO activation times; unclassified older plans cannot be silently converted. All added negative tests passed. The approved 14-day clock will start only at later explicit activation.
6. **Shared revalidation:** Four real application signer/checker libraries passed signed loopback HTTP with two synthetic tenants: valid grant, tenant isolation, expiry/revocation and fail-closed outage. Prior actual application JWT/Express/Fastify/WebSocket tests also passed and remain in their own draft branches.
7. **Nightly laptop backup:** Applied the pre-tested backup script hardening, with `umask 077`, protected snapshot/log folders and shell-syntax validation. Preserved a local owner-only copy of the preceding script. The 02:00 AST systemd timer remained enabled and active. A future actual scheduled run must still be observed.
8. **Latest database backup recovery:** All five dumps from the latest completed nightly snapshot restored with `pg_restore --exit-on-error` in a disposable PostgreSQL 17 container limited to 768 MiB, with `--network none`, no published ports, temporary in-memory PostgreSQL files and no persistence. Public table counts: FFPRO 21, Tiquet 20, Hub 1, POS 78, Academy 8. All three application-data tar archives passed archive integrity inspection. Temporary restored databases, Docker container and staging dump copies were removed.
9. **Source safety:** App code remains on unmerged draft PRs, no customer trial state changed and production apps were reported healthy.

## Outstanding production release requirements

- **DNS:** `hub.v79sl.com` authoritative A must consistently point to `199.223.249.193`, with no CNAME to `links2.resend-dns.com`. Local stale IPv6 CloudFront answers returned HTTP 400 despite correct IPv4 HTTP 200; demonstrate reliable public HTTPS over normal address selection before enabling password-reset links.
- **Full application staging:** No all-five simultaneous, fully production-equivalent deployment with independent restored databases, internal secrets, background workers and live tenant sessions has yet been completed. Signed HTTP integration and database restore exercises do **not** substitute for that release gate.
- **Complete recovery:** PostgreSQL dumps and application-data archive integrity are proven. Restore and boot each app with its assets/secrets and verify callback/launch/key recovery; rehearse the full coordinated rollback.
- **Backup encryption:** Owner-only filesystem permissions are improved, but older snapshots still contain unencrypted sensitive content. Select independent off-device encryption key custody before enabling off-site encrypted backups. The next scheduled backup should be checked for success and private permissions.
- **Email production readiness:** Verify founder-approved sender, test recovery link in a controlled account when Hub DNS is stable, ensure one opted-in reminder leader and enter the restricted key using protected environment/secret files after release approval.
- **Production cutover:** Only after all gates pass and a separate founder **GO** should the audited, revision-checked production writer be used to grant the existing one customer a fresh 14-day trial. Do not claim paid access without verified payment.

## Repeatable preflight commands

From `/home/firelion/v79hub-trial-dev`:

```sh
node scripts/read-only-live-cutover-preflight.mjs
node scripts/resend-authoritative-dns.mjs
node --test tests/legacy-cutover.test.mjs tests/resend-transactional.test.mjs
npm test
npm run lint
npm run build
```

All commands above are read-only or build/test against the isolated feature worktree; **none applies a production database migration**.

## Invitation email workflow — completed in draft

The customer-owner invitation creation route (platform administrator only)
and team invitation creation route (workspace owner only) now try to send
the generated one-time invitation URL through the same domain-restricted
Resend sender when the approved mail configuration is present. The
invitations are committed to Hub state before mail delivery is attempted;
provider failure leaves the link available for manual sharing, and the
API reports `emailDeliveryStatus` as `not_configured`,
`accepted_by_provider`, `provider_rejected` or
`delivery_unavailable`. Provider acceptance is not a delivery
confirmation. The URL fragments, expiry, invite IDs and hashed Resend
idempotency keys are validated in isolated tests. No customer invitation
was sent. Latest Hub test suite: 129 tests passed, TypeScript and
application build passed. The actual live Hub mail key remains unset.


## Five-app synthetic GitHub staging — passed, 8 October 2026

[Successful GitHub Actions run #37838312344](https://github.com/MrFixITslu/V79hub/actions/runs/37838312344)
tested commit 09dbf085. All five image builds and the integrated job succeeded.
Hub, POS, FFPRO, Tiquet and Marketing responded healthy. POS, FFPRO,
Tiquet and Marketing each passed active-trial grant, cancellation denial,
cross-tenant denial and invalid-signature denial. Real Hub login of two
synthetic customer owners passed: sessions stayed within their
organisations, customer accounts could not view platform-admin customer
records, and anonymous /api/auth/me was rejected.

The runner deleted its private PostgreSQL/SQLite data, Redis, application
containers, Docker volumes and network. No customer data, production
application changes, subscription activation or outbound emails occurred.

Still outstanding: test product-to-Hub session flows and launches in a
fully restored app stack; coordinated restart and rollback; encrypted
off-site backup key custody; final founder production approval.
