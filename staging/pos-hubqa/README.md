# Isolated Hub → POS MFA/SSO staging

**Not a production deployment.** This is the candidate for [Hub issue #245](https://github.com/MrFixITslu/V79hub/issues/245) and [POS PR #17](https://github.com/MrFixITslu/V79POS/pull/17). It uses normal Hub's username/password + TOTP MFA and signed, single-use POS launch, but has independently generated accounts, private store, JWKS and service-signing keys.

Do not change `v79-hub`, `v79-pos`, `v79-pos-db`, live Hub's `POS_BASE_URL` or `POS_PUBLIC_URL`, Nginx Proxy Manager, public DNS, or production secrets. Do not share any stage password, MFA QR code, JWT, session cookie or launch ticket in ChatGPT, GitHub or logs.

## Architecture

- Hub stage: `v79-hub-pos-hubqa`, image `v79hub:pos-hubqa-20261109`; bind **only** `127.0.0.1:18082`.
- POS stage: existing `v79-pos-hubqa-api`, image `v79pos:hubqa-2590623`; bind **only** `127.0.0.1:18081`.
- Existing isolated POS stage PostgreSQL/Redis; `v79pos_hubqa` is a production-derived *private* test copy. Do not share or reset the volume.
- Hub stage uses its **own empty private JSON store** in `/home/firelion/v79-hub-pos-hubqa-20261109/data`. No copied production Hub accounts, MFA secrets, sessions or private JWKS.
- Only Docker network for **both Hub and POS stage API**: `v79pos-hubqa-20261109_stage_internal`, with `internal: true`. This removes stage POS's earlier `proxy_network` attachment. No live POS/Hub containers should appear on this staging network.
- No stage background worker, Resend, real payment provider, billing or marketing execution.
- Stage Hub's one-time POS launch provisions **only** stage POS and redirects **only** to the stage port.
- Staging Hub remains `NODE_ENV=development` solely to support HTTP loopback browser cookies. TOTP MFA is explicitly mandatory. **This does not prove production HTTPS Secure-cookie or Google OAuth behaviour.** A separate TLS and registered OAuth staging origin is needed for those gates.

The stage POS HMAC keys must be rotated away from copied live credentials. The preparation script generates new random keys and keeps them private on the server. The current POS launch-exchange contract uses the general HMAC key while entitlement uses the dedicated key, so **both stage keys intentionally have the same new stage-only value** for compatibility; they must NOT match production. A dedicated-key-only contract is a separate code/security improvement.

## A. Source checkout and read-only preflight

Run on the Acer. These commands copy or inspect only the named staging checkout; they do not alter running services:

```sh
ssh -T firelion@100.73.248.30 'sh -eu' <<'REMOTE'
root=/home/firelion/v79-hub-pos-hubqa-20261109
mkdir -p "$root"
chmod 700 "$root"
test ! -e "$root/.env"
test ! -e "$root/compose.yml"
test ! -e "$root/data"
if test -d "$root/source/.git"; then
  git -C "$root/source" status --short
  test -z "$(git -C "$root/source" status --porcelain)"
  git -C "$root/source" fetch origin feature/isolated-pos-hubqa-20261109
  git -C "$root/source" checkout feature/isolated-pos-hubqa-20261109
  git -C "$root/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109
else
  git clone --depth 1 --branch feature/isolated-pos-hubqa-20261109 \
    https://github.com/MrFixITslu/V79hub.git "$root/source"
fi
python3 "$root/source/staging/pos-hubqa/prepare.py"
REMOTE
```

Expected: `ISOLATED_STAGE_PREFLIGHT=PASS`, `LIVE_POS_PRESERVED=PASS`, `DRY_RUN_ONLY=PASS`. If the checkout is unavailable over HTTPS, use your existing authorised GitHub credential; **do not copy credentials into the command or chat**.

## B. Rotate only staging keys / prepare private Hub configuration

The stage POS API must first be **stopped, never the live POS**. Then rerun the guarded preparation with `--apply`:

```sh
ssh -T firelion@100.73.248.30 'sh -eu' <<'REMOTE'
cd /home/firelion/v79-pos-hubqa-20261109
docker compose --env-file .env -f hubqa.compose.yml stop api

python3 /home/firelion/v79-hub-pos-hubqa-20261109/source/staging/pos-hubqa/prepare.py --apply
REMOTE
```

This step is **one-time only**. It refuses to overwrite or rotate a previously initialised Hub stage; expects the original stage POS image, exact isolated DB and loopback port; rejects unfamiliar Compose or production images; generates a new staging service HMAC, Hub password and MFA encryption key; removes stage POS's access to production `proxy_network`; and redirects stage POS to the stage Hub JWKS, issuer and signed entitlement service. No live POS/Hub files are modified. The original stage **Compose file only** is retained as `hubqa.compose.pre-hubqa.yml` for review. Former staging copies of live signing keys are replaced rather than backed up.

Expected: `ISOLATED_STAGE_CONFIG=PASS`, `FRESH_STAGE_ONLY_KEYS=PASS`, `MFA_REQUIRED=PASS`.

## C. Build and start ONLY the new Hub stage and the existing POS stage

```sh
ssh -T firelion@100.73.248.30 'sh -eu' <<'REMOTE'
root=/home/firelion/v79-hub-pos-hubqa-20261109
cd "$root/source"
ionice -c3 nice -n 10 docker build --progress=plain \
  -t v79hub:pos-hubqa-20261109 .

cd "$root"
docker compose --env-file .env -f compose.yml up -d --wait hub

cd /home/firelion/v79-pos-hubqa-20261109
docker compose --env-file .env -f hubqa.compose.yml \
  up -d --no-deps --force-recreate --wait api

python3 "$root/source/staging/pos-hubqa/check.py"
REMOTE
```

Expected: `PRODUCTION_UNCHANGED=PASS`, `PRIVATE_STAGING_NETWORK=PASS`, `UNIQUE_KEYS_AND_MFA=PASS`, `ISOLATED_HUB_POS_ROUTING=PASS`, `STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS`. Failure means **NO-GO**; inspect only the named staging containers and do not weaken authentication.

## D. Owner browser verification (requires the owner at the Acer)

Start a private two-port tunnel in **one separate Acer terminal**:

```sh
ssh -N \
  -L 18082:127.0.0.1:18082 \
  -L 18081:127.0.0.1:18081 \
  firelion@100.73.248.30
```

Open `http://127.0.0.1:18082` in Chrome. Login with the **new stage-only** administrator password from the stage Hub's mode-0600 `.env` (retrieve it locally into a password manager; do not paste the value here). Enrol and complete the staged account's fresh TOTP MFA. Launch POS using the **staging** Hub card, which must redirect to `http://127.0.0.1:18081`.

Never use `https://hub.v79sl.com` for this test; that launcher provisions against **production POS**. Do not copy the URL fragment containing the single-use ticket, access token, session cookie or TOTP code into messages.

Test both owner POS access and unauthorised/revoked access. A second test user must be deliberately created/invited inside the **stage Hub** and provisioned only into the stage POS tenant. Use only fake stock/jobs in a stage-only tenant, not other tenants from the restored production snapshot.

Record only redacted outcomes:
- MFA challenge and verified session; owner stage POS launch succeeds; a second use of the same launch ticket fails; expired ticket fails.
- POS `/v1/me` denies anonymous access, stale session, revoked membership or cancelled/expired entitlement, and mismatched tenant IDs; no data from the restored production tenants visible to the synthetic stage user.
- Technician visibility, minimum inventory location, stock request/receipt, stage-only job usage, role revocation and negative permissions.
- No calls from stage Hub or stage POS to live POS/Hub APIs, live billing, email or customer account changes.

**Do not claim Google OAuth or HTTPS production cookie parity from this HTTP loopback exercise.** These require separate, approved, secured staging callback domain and trusted TLS verification.

## Recovery: staging Hub exited with `EACCES` writing `v79_store.json.tmp`

The owner's first attempt confirmed `ISOLATED_STAGE_CONFIG=PASS`, `FRESH_STAGE_ONLY_KEYS=PASS` and `MFA_REQUIRED=PASS`, then `v79-hub-pos-hubqa` exited (1). Logs confirmed permission denied opening `/app/data/v79_store.json.tmp`, because the host-owned stage data mount was 0700 and the original container did not run as that owner. Production POS stayed healthy and unchanged.

**Never rerun `prepare.py --apply` at this point.** It is intentionally one-time and the newly created stage keys must be preserved. Do not use `chmod 777`, `chown -R`, `docker compose down -v`, rebuild POS or copy production Hub credentials.

Repair: `repair-permissions.py` checks the exact stopped stage Hub container, expected stage image, loopback binding, production POS image+health, private data owner+0700 mode, existing stage keys and known Compose contents. It only adds the host stage owner numeric UID/GID to the **private Hub stage** `.env`, and replaces **only** that Hub stage's Compose file with an unprivileged `user:` and in-memory writable Vite caches. It never changes the staging POS API, production Hub, production POS or the backup.

```sh
ssh -T firelion@100.73.248.30 'bash -se' <<'REMOTE'
set -euo pipefail
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
POS=/home/firelion/v79-pos-hubqa-20261109

test -z "$(git -C "$HUB/source" status --porcelain)"
git -C "$HUB/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109

# First, read-only preflight. Requires the original Hub stage to be exited.
python3 "$HUB/source/staging/pos-hubqa/repair-permissions.py"

# Apply to stage Hub Compose and its existing env only; no secret rotation.
python3 "$HUB/source/staging/pos-hubqa/repair-permissions.py" --apply

# Recreate only stage Hub; use the already-built image.
cd "$HUB"
docker compose --env-file .env -f compose.yml   up -d --no-deps --force-recreate --wait hub

# Resume the previously interrupted staging POS API start.
cd "$POS"
docker compose --env-file .env -f hubqa.compose.yml   up -d --no-deps --force-recreate --wait api

python3 "$HUB/source/staging/pos-hubqa/check.py"
REMOTE
```

Expected: `STAGE_PERMISSION_CONFIGURATION=PASS`, `NON_ROOT_STAGE_RUNTIME=CONFIGURED`, and all five `check.py` PASS lines. If Hub still exits, do not repeat `--apply`; gather a **redacted** `docker logs --tail 70 v79-hub-pos-hubqa` and compare running user versus `stat -c '%u:%g %a' /home/firelion/v79-hub-pos-hubqa-20261109/data`. Protect secrets and session tokens.

## Private-network browser access when Docker does not publish port 18081

Owner evidence: restored stage DB, private stage Hub and POS API all became healthy. POS `/ready` returned HTTP 200 from inside its own container **and** from the server to the container's private network IPv4 address. The Compose `api.ports` and Docker HostConfig both declared `127.0.0.1:18081:8080`, but `docker port` returned no published port and the server's `127.0.0.1:18081` returned HTTP 000. This is a **Docker host-port forwarding discrepancy**, not a failed POS API. Preserve the isolated bridge; don't attach stage POS to the shared proxy network or expose port 18081 publicly.

The Acer owner can use SSH port forwarding directly to the two stage container addresses, with no additional Docker changes. First verify both containers are healthy and connected **only** to `v79pos-hubqa-20261109_stage_internal`. Obtain the dynamic IPv4 addresses by named Docker network lookup; never hardcode an older private container IP.

On the **Acer** in a dedicated terminal:

```bash
set -euo pipefail

NETWORK=v79pos-hubqa-20261109_stage_internal
SERVER=firelion@100.73.248.30

POS_IP=$(ssh -T "$SERVER" \
  "docker inspect -f '{{with index .NetworkSettings.Networks \"$NETWORK\"}}{{.IPAddress}}{{end}}' v79-pos-hubqa-api")
HUB_IP=$(ssh -T "$SERVER" \
  "docker inspect -f '{{with index .NetworkSettings.Networks \"$NETWORK\"}}{{.IPAddress}}{{end}}' v79-hub-pos-hubqa")

[[ "$POS_IP" =~ ^[0-9]+(\.[0-9]+){3}$ ]] || { echo "Invalid POS stage IP"; exit 1; }
[[ "$HUB_IP" =~ ^[0-9]+(\.[0-9]+){3}$ ]] || { echo "Invalid Hub stage IP"; exit 1; }

ssh -N -o ExitOnForwardFailure=yes \
  -L "127.0.0.1:18081:$POS_IP:8080" \
  -L "127.0.0.1:18082:$HUB_IP:3040" \
  "$SERVER"
```

Keep that terminal open. In the browser open **`http://127.0.0.1:18082`** for the *private staging Hub*; a successful POS launch should redirect to the other locally forwarded port `http://127.0.0.1:18081`. Keep the tunnel bound to Acer's `127.0.0.1` and avoid real public Hub launches. Press Ctrl+C to disconnect. Never share password, MFA QR, one-time ticket, token, browser cookies or URL fragments. HTTP loopback does not prove production HTTPS Secure-cookie or Google OAuth parity.

## Repair old Hub login presentation before acceptance: pin private staging to the real running Hub image

The owner approved Hub **Login Version 3 (Connected Workspace)** on 8–9 November. The isolated Hub staging image was built from GitHub `main` and displayed the **old login**, so it is not suitable for final UX acceptance. Do not rebuild from `main`, merge an unrelated draft Google-login branch, copy production Hub store, or touch the live production container.

**Three options considered:** (1) leave old staging UI: fails owner's UX acceptance; (2) cherry-pick latest GitHub login components: risks losing unmerged live overlays, the approved logo and OAuth session changes; (3) **chosen:** pin the entire stage Hub image to the immutable image ID of the **currently running healthy production Hub**, while running it with the **existing private staging Compose, secrets, data and isolated network**. Version 3 appearance still requires owner visual verification.

**REDTEAM gates:** `sync-live-ui.py` is dry-run by default. It checks live Hub and POS health and identity, stage Hub/POS/DB health, sole internal-only bridge, loopback port declarations, the exact trusted stage Compose, stage file permissions, isolated MFA and signed POS keys, and that the production image does not embed live credentials in Docker image environment. If a check fails, it **does not switch images**. `--apply` first snapshots **only the existing private stage data and Compose** into a 0700 private checkpoint; creates a uniquely named staging tag **pointing to the exact running production Hub image ID**, does not rebuild from GitHub, changes **only** the private Hub Compose image reference and recreates **only** `v79-hub-pos-hubqa`. If the new stage does not become healthy, it attempts to roll back **only** the stage image. It never restores production data, rotates keys, restarts production or changes the network/ports. Review the error and checkpoint before retrying; do not automatically restore a data snapshot over a running Hub.

On the **Acer**, first perform a read-only preflight. It prints the currently deployed Hub image tag and immutable ID, without printing credentials:

```bash
ssh -T firelion@100.73.248.30 'bash -se' <<'REMOTE'
set -euo pipefail
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
test -z "$(git -C "$HUB/source" status --porcelain)"
git -C "$HUB/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109
python3 "$HUB/source/staging/pos-hubqa/sync-live-ui.py"
REMOTE
```

Only after the preflight returns `PRODUCTION_AND_STAGE_ISOLATION_PREFLIGHT=PASS` and `DRY_RUN_ONLY=PASS`, stage the exact running image:

```bash
ssh -T firelion@100.73.248.30 'bash -se' <<'REMOTE'
set -euo pipefail
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
python3 "$HUB/source/staging/pos-hubqa/sync-live-ui.py" --apply
python3 "$HUB/source/staging/pos-hubqa/check.py"
REMOTE
```

Expected `STAGING_HUB_EXACT_LIVE_IMAGE=PASS`, `STAGING_HUB_HEALTH=PASS`, `STAGING_DATA_AND_KEYS_PRESERVED=PASS`, and five existing security checks. `check.py` verifies that staging Hub **really runs the pinned image ID** and uses the stage-only Docker bridge for health and anonymous POS denial, because this host's Docker loopback forwarding may be absent despite HostConfig port declarations. This changes **no** production system. Prior to browser review, **close and reopen the Acer SSH tunnel** to refresh the stage Hub's newly assigned Docker private IP; otherwise the old tunnel could still target the replaced container.

Visual acceptance: in the updated private Hub check that the user-approved Version 3 layout, **distinct Hub shield-and-orbit logo/favicon**, Google button, password fallback, MFA challenge and POS app icon match the live approved design. The localhost Google OAuth redirect may be incompatible with provider callback registration; this acceptance does not claim Google OAuth production behaviour. Confirm the private Hub→POS signed launch, entitlement and access denial without using production accounts or launching the live POS.

## E. Cleanup and remaining release gates

Stop **only** the staging containers to save resources, without deleting any volumes or backup files:

```sh
ssh -T firelion@100.73.248.30 'sh -eu' <<'REMOTE'
cd /home/firelion/v79-hub-pos-hubqa-20261109
docker compose --env-file .env -f compose.yml stop hub
cd /home/firelion/v79-pos-hubqa-20261109
docker compose --env-file .env -f hubqa.compose.yml stop api
docker inspect v79-pos --format 'LIVE_POS={{.Config.Image}} STATUS={{.State.Health.Status}}'
REMOTE
```

Do not use `docker compose down -v`; do not reset real customer data or restart production. Pending: secured HTTPS / OAuth validation, physical Android/iPhone/scanner use, network interruption, real Tiquet job mapping, customer-installed faulty equipment RMA, release security audit and explicit final production deployment approval.
