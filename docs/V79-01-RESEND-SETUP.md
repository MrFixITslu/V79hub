# CURRENT RESEND STATUS — 8 OCTOBER 2026

Resend now marks all 3 sending-specific records verified (one DKIM TXT and
two Forge routing CNAMEs). Sending is enabled. Overall status remains
partially_verified because optional tracking is not verified; open/click
tracking is disabled.

IMPORTANT: the Hub application must not be used as an email tracking
subdomain. DNS has intermittently returned BOTH A 199.223.249.193 and
CNAME links2.resend-dns.com for hub.v79sl.com, leading to normal HTTP 400
responses while direct origin HTTPS returned HTTP 200. A DNS administrator
must REMOVE the hub CNAME and preserve ONLY hub A 199.223.249.193.
Do not change the Resend DKIM, rsend or send records, or other apps.

The provider's ACTUAL verified sending DNS uses:
  resend._domainkey = DKIM TXT (account-generated public key)
  rsend = CNAME rsend.forge.rmta.net
  send = CNAME send.forge.rmta.net
Generic SPF TXT and MX instructions do not describe this domain's Forge
configuration and should not be applied.

Hub development integration now uses a shared transactional sender with
strict sender-domain checking, canonical reset links, consistent reply-to,
and hashed provider idempotency for trial reminders. Its mock-provider tests
passed. Real delivery has not been tested and production remains unchanged.

---

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

## Critical public DNS collision observed after Resend tracking setup

On 8 October 2026, the authoritative nameservers returned:
hub.v79sl.com CNAME links2.resend-dns.com
That hostname is reserved for the live V79 Hub customer application and
must NOT be assigned to an email tracking provider.

Independent origin discovery: v79sl.com, ffpro.v79sl.com,
tiquet.v79sl.com, marketing.v79sl.com, pos.v79sl.com, and
academy.v79sl.com resolve to public A address 199.223.249.193.
Direct HTTPS against hub.v79sl.com:443 with forced origin 199.223.249.193
returned HTTP 200 with V79 Hub's expected page. Restore hub as a Type A
record pointing to 199.223.249.193 in the DNS provider. Delete the
conflicting hub CNAME; do not create A+CNAME at the same hostname.
Confirm ingress address at the time of change if it has moved.

Resend domain had open/click tracking enabled with tracking subdomain hub.
Both tracking modes were disabled in Resend, and its subdomain setting
changed to email-links, reserving hub for the application.
Resend may still display the previously issued hub tracking record while
verification runs. Do NOT publish that CNAME at hub.v79sl.com.

Read-only scripts/resend-dns-preflight.mjs now warns when the live Hub
hostname points to email tracking; six targeted tests passed. The Hub
page returned HTTP 200 at test time but DNS caches/paths can change.

DKIM and SPF CNAMEs were present in authoritative public DNS. Provider
domain verification was restarted and was pending on last check.
