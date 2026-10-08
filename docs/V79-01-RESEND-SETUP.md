# V79-01 — Resend onboarding and public DNS staging gate

**Status (8 October 2026):** No Resend key or sender configured on the running Hub. Sending remains disabled. No production DNS, server environment, service, or database was modified.

## Current V79 public DNS observations

- Authoritative nameservers resolved as `ns1.domain.com` and `ns2.domain.com`. Edit records in the DNS service controlling these nameservers, not automatically at the domain registrar.
- `v79sl.com` TXT currently carries Google site verification; no domain-apex SPF or DMARC TXT found.
- No inbound domain-apex MX found, and no default `send.v79sl.com` return-path SPF/MX found.
- Existing `vision79slu@gmail.com` is an external Gmail mailbox, not a mailbox at the domain.
- Do **not** change nameservers, delete A/CNAME records, overwrite existing TXT verification, or change MX for `v79sl.com` in an attempt to use Resend.

## Founder-managed Resend setup

1. Register at https://resend.com/signup and enable MFA.
2. In https://resend.com/domains, add the sending domain `v79sl.com`.
3. Add exactly the DNS records returned by Resend (DKIM TXT with generated public key; SPF TXT and return-path MX on the host shown, usually `send.v79sl.com`; optionally recommended DMARC). The values are domain-specific and must **not** be guessed. Ensure a single SPF record per hostname.
4. Verify Sending in the Resend dashboard. Domain ownership verification may be a separate preceding step if the domain is currently claimed elsewhere.
5. In Resend API Keys create `V79-Hub-Transactional` with **Sending access**, limited to the verified domain where possible. Keep the key private.
6. Intended V79 Hub sending identity: `V79 Digital <notifications@v79sl.com>`. Reply-To: `vision79slu@gmail.com`. Sender address is not an inbound mailbox.
7. On a later, separately approved staging instance only, configure:
   - `RESEND_API_KEY` with the secret value through a private environment or secret mount
   - `V79_HUB_EMAIL_FROM=V79 Digital <notifications@v79sl.com>`
   - `V79_HUB_RECOVERY_EMAIL=vision79slu@gmail.com`
   - `V79_TRIAL_REMINDERS_ENABLED=0`
   - `V79_TRIAL_REMINDERS_WORKER_LEADER=0`
8. Verify delivery to a designated *test* inbox and that the From, Reply-To, DKIM/SPF/DMARC alignment, reset-link host and expiry all behave correctly; check Resend's delivery activity. Do not test a real customer before approval.
9. Test idempotent seven-day, one-day and trial-expiry reminders, then approve single-leader scheduler activation separately.

Hub Compose source `/opt/v79/hub/docker-compose.yml` already passes `RESEND_API_KEY`, `V79_HUB_EMAIL_FROM`, and `V79_HUB_RECOVERY_EMAIL` from `/opt/v79/hub/.env`. The notification flags can pass through its `env_file`. None is yet enabled in production.

## Read-only DNS checks

Current defaults:

```bash
cd /home/firelion/v79hub-trial-dev
node scripts/resend-dns-preflight.mjs
```

After adding the exact records from the Resend dashboard:

```bash
node scripts/resend-dns-preflight.mjs \
  --dkim-host=resend._domainkey.v79sl.com \
  --return-path=send.v79sl.com
```

**Replace both sample hostnames with the actual DKIM and return-path hostnames shown in Resend.** This tool only performs public DNS lookups, prints summary status and **does not assert Resend account verification**. It never requires or prints an API key.

## Remaining V79-01 release gates

The following remain strict **NO GO** conditions: verified sender/API credentials and a real *test-only* email; five-app staged service networking and authentic requests with real isolated tenant databases; worker policies; source checkout reconciliation; full application recovery and rollback rehearsal; explicit founder cutover approval. No draft PR should be merged before completion.
