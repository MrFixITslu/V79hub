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

## Correct 9 November login: frontend-only overlay (supersedes whole-image sync)

**New owner evidence (9 November):** all staging services are healthy after rollback. The running live `v79-hub` is immutable image `sha256:5d11cfdb...` (tagged `v79-hub-sales-review:20261107-r1`), but the server also has a **different** image `localhost/v79-hub-login-connected:20261109-r1` (image ID `43a19e4ec9b4...`). The latter is also tagged `localhost/v79-hub-sales-review:20261107-r1` in the repository listing, indicating different tag/image histories than the *running* live container. The previous attempt to switch the entire Hub to `5d11cfdb...` failed in staging; the owner confirmed `OLD_STAGE_HUB_IMAGE_RESTORED=PASS` and the checkpoint was retained. Do not repeat that whole-image update.

**Three reviewed options:** (1) Continue testing with the old login (rejected: not representative). (2) Reuse the complete running live image (rejected: failed staging start, pre-Version 3 image). (3) **Preferred:** extract only the login component, its required local component dependencies and referenced public assets from the *9 November Connected Login candidate*, apply them to the exact known-good stage Hub base image, rebuild its frontend offline, keep the existing backend, and promote **only** the staging Hub service. The candidate image **is not yet visually verified as the user's exact approved Version 3**, so the operator must still check its login and Hub icon before MFA/SSO acceptance.

`staging/pos-hubqa/overlay-approved-login.py` is read-only by default. It validates the exact Connected Login image and its alias point to the same immutable image ID; verifies image env contains no baked credentials; checks staging Hub/POS/PostgreSQL and live Hub/POS are healthy; ensures the staging network remains internal-only; checks loopback port **declarations**, stage MFA/service signing, stage JSON store, disabled outbound integrations, stage-only source/template and private file modes. It then creates a *disposable non-running Docker container* to extract **only** the login sources/assets for a dry-run inspection; removes the disposable container. Dry-run does not touch a running service or a staging image.

On `--apply`, it checks the login source differs from the old stage; builds a **new** image `v79hub:pos-hubqa-ui-v3-20261109` from the original `v79hub:pos-hubqa-20261109`, injecting **only** the login files and running `npm run build` offline (no new dependencies, no backend copy from production). It snapshots stage data and Compose privately, replaces **only** the stage Hub Compose image, and recreates **only** the stage Hub. If health/identity verification fails, it automatically attempts a **stage image-only rollback** and retains the checkpoint. No production container, app image, SSO signing key, database, network, DNS, favicon in production or service env is changed. The staging store remains intact.

On the Acer, use this command for a guarded preflight and stage-only application:

```bash
ssh -T firelion@100.73.248.30 'bash -se' <<'REMOTE'
set -Eeuo pipefail
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
test -z "$(git -C "$HUB/source" status --porcelain)"
git -C "$HUB/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109

python3 "$HUB/source/staging/pos-hubqa/overlay-approved-login.py"
python3 "$HUB/source/staging/pos-hubqa/overlay-approved-login.py" --apply
python3 "$HUB/source/staging/pos-hubqa/check.py"
REMOTE
```

Expected: `STAGING_LOGIN_OVERLAY=PASS`, `PRIVATE_STAGE_HEALTH=PASS`, `ORIGINAL_STAGE_BACKEND_PRESERVED=PASS`, `PRODUCTION_UNCHANGED=PASS`, then five security checks ending with `STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS`. The script blocks automatically if the image is not suitable or a different stage state is observed: **do not bypass the guard**.

**After the stage image is promoted:** close any earlier Acer SSH tunnel, rediscover the staging container's new private Docker IPv4 address and reopen the tunnel using the script in the previous section. Open `http://127.0.0.1:18082`, perform an unauthenticated visual review of the new Connected Workspace Version 3 layout and correctly approved Hub icon. Do **not** test MFA/SSO until visual acceptance; HTTP loopback does not verify Google OAuth provider registration, HTTPS Secure cookies or production OAuth re-auth prompts.

## Correct the approved login presentation: matching CSS and missing app icons

**Owner browser result:** the 9 Nov login component loaded with the correct source, but the page appeared as mostly unstyled stacked text and the Tiquet/FFPRO/POS/Marketing/Academy images were broken. A read-only comparison confirmed that stage and candidate `Login.tsx` have the **same** SHA-256 `cb250f0...`, as do both `index.html` files (`6ea2022...`). However the stage `src/index.css` is `cb3417c...`, whereas the approved Connected Login candidate has `ea182c2...`. Stage Vite served a CSS endpoint with HTTP 200, but that does **not** prove the CSS matches the new component or contains its classes. Stage Hub, stage POS, PostgreSQL and live POS remain healthy.

**Three choices /REDTEAM:** (1) Browser refresh only: rejected, source stylesheets differ. (2) Swap the entire Hub/backend image: rejected, this already failed staging startup and would risk MFA/SSO. (3) **Selected:** layer the exact pinned 9 Nov candidate stylesheet and its referenced **public** image/font files onto the **current healthy staging UI+backend**, build offline and replace **only** the private staging Hub after taking a private checkpoint. The source Login component and HTML are intentionally **not** rewritten.

The guard `staging/pos-hubqa/repair-login-presentation.py` checks all stage and live health, stage-only networking, MFA, service keys, the exact existing frontend-only stage image, the pre-repair CSS/login hashes, existing immutable image pin, private stage data and loopback port declarations. The candidate image and CSS SHA must match the exact hashes observed by the owner. It obtains only public CSS/images/fonts from a disposable nonrunning Docker container, not the production Hub. Stage-only offline build precedes any Compose change. Apply preserves `.env`, Hub JSON store, stage POS/database and other images, snapshots stage data/Compose and changes only the Hub staging image. A failed start or asset/health check attempts a **staging image-only rollback**. It checks image content and HTTP CSS/image media types, preserves original stage runtime environment and rejects anonymous POS API access. No production service, domain, credentials, backups or database is modified.

On the Acer:

```bash
ssh -T firelion@100.73.248.30 'bash -se' <<'REMOTE'
set -Eeuo pipefail
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
test -z "$(git -C "$HUB/source" status --porcelain)"
git -C "$HUB/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109
python3 "$HUB/source/staging/pos-hubqa/repair-login-presentation.py"
python3 "$HUB/source/staging/pos-hubqa/repair-login-presentation.py" --apply
python3 "$HUB/source/staging/pos-hubqa/check.py"
REMOTE
```

Expected `DRY_RUN_ONLY=PASS`, `STAGING_LOGIN_STYLE_AND_ASSETS=PASS`, `V3_STAGING_STYLESHEET=PASS`, `V3_STAGING_ASSETS=PASS`, `STAGING_POS_ANONYMOUS_DENIAL=PASS`, followed by the previous stage health/isolation gates. **If blocked, do not rerun `--apply` or bypass a guard.** Reset the owner-only SSH tunnel to the new Hub container IP, open `http://127.0.0.1:18082` in a private browser window and visually verify layout, products and favicon. **MFA/SSO browser acceptance remains unverified** until visual review passes.

## Maintenance window: fix confirmed product-image directory permissions (9 November)

The owner confirmed the previous CSS/image staging candidate passed extraction and build, **but did not pass runtime image validation**, and its automatic stage-only rollback succeeded. A separate, non-root, network-disabled probe of that already-built candidate confirmed `/app/public/assets/login-products` has mode **0644** (a directory must have `x`/traverse access). All five PNGs yielded `EACCES`; Vite returned **HTTP 200 text/html fallback**, not image/png. The current private Hub/POS/PostgreSQL and production POS remain healthy. Do not rerun the prior `repair-login-presentation.py --apply`, loosen permissions on any live host volume, or use `chmod -R`.

**Three options /REDTEAM:** (1) change permissions in the currently running stage or production (reject: wrong filesystem and security impact), (2) rebuild the entire old-to-new frontend from scratch (reject: unnecessary time and new dependencies), (3) **chosen:** derive a *new, uniquely tagged, private stage-only image* from the already-built, immutable styled candidate and run only `chmod 0755 /app/public/assets/login-products`. The Dockerfile changes no file contents, favicon, app backend, stage credentials or PostgreSQL data. Recheck accessible PNG magic bytes **as UID 1000 before recreation** and HTTP `image/png` with actual PNG bytes **after** staging starts. If validation fails, restore the previous healthy stage Hub image only.

The script `staging/pos-hubqa/recover-login-image-permissions.py` defaults to **read-only**. It requires the known healthy stage Hub, a unique failed styled image derived from its base, exact owner-observed login and CSS SHA-256, valid PNG bytes, isolated Docker bridge, protected stage .env/data, exact previous image pin, current separate stage POS health, live Hub/POS health, and a unique unused output tag. It refuses re-running after successful promotion. Apply builds the new image offline, verifies non-root PNG reads, checkpoints **only** the private stage data and Compose, recreates **only** `v79-hub-pos-hubqa`, and checks per-product image responses, stage CSS, unchanged stage security configuration and unchanged production/POS container IDs. An exception triggers a stage-only rollback attempt. The immutable image pin is consumed by `check.py`.

**Interrupted maintenance window recovery:** The owner observed the corrected image already exists (immutable ID `sha256:30ee063ae29b77ab09629ae09a361fa80ba78bd5e773c3d97064ed1a557706bf`), while the running Hub stage is still the healthy old image and no completed promotion record exists. Earlier code would reject any preexisting output image. The updated script accepts **only that exact image ID**, verifies the image contains exactly one additional filesystem layer based on the known failed styled image, checks Docker history for the approved one-directory `chmod 0755` command, verifies no runtime configuration changes, and tests non-root PNG reads. It can then reuse the already-built image without overwriting it. Any mismatch **blocks** deployment; never remove the existing image to bypass the guard. Run from an existing Acer terminal rather than a temporary shell; a remote nonzero exit must not close the Acer window.

**Second interrupted run, 9 November:** the owner confirmed the prebuilt image identity and non-root PNG reads passed. Its stage Hub was recreated healthy, but the earlier equality check rejected `Config.Env`/non-root user/`HostConfig.PortBindings` as **one combined mismatch** without identifying the field. Script automatically restored the old healthy stage image (`OLD_STAGE_HUB_IMAGE_RESTORED=PASS`) and retained `checkpoints/before-product-icon-permissions-20261109T234934Z`. The original guard compared raw ordered Docker environment arrays, which can differ in order across container recreation even when all key/value pairs are unchanged. The corrected verification now compares **all effective key/value pairs** without order dependence, still fails closed on any actual changed/missing/added key, validates **UID/GID 1000:1000** and **the sole 127.0.0.1:18082 port binding** separately, and prints only differing variable **names** (never values). The fixed Docker image remains pinned by immutable ID and provenance. If a real configuration difference exists, the stage is rolled back again; do not circumvent it or repeat blindly.

On the Acer, during the approved **staging-only** maintenance window:

```bash
ssh -T firelion@100.73.248.30 'bash -se' <<'REMOTE'
set -Eeuo pipefail
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
test -z "$(git -C "$HUB/source" status --porcelain)"
git -C "$HUB/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109
python3 "$HUB/source/staging/pos-hubqa/recover-login-image-permissions.py"
python3 "$HUB/source/staging/pos-hubqa/recover-login-image-permissions.py" --apply
python3 "$HUB/source/staging/pos-hubqa/check.py"
REMOTE
```

Expected `DRY_RUN_ONLY=PASS`, `NONROOT_PRODUCT_IMAGE_READ=PASS`, `STAGE_LOGIN_PRODUCT_PNG_HTTP=PASS`, `STAGE_LOGIN_CSS=PASS`, `STAGING_LOGIN_ASSETS_FIXED=PASS`, `STAGING_LOGIN_PRODUCT_IMAGES=PASS`, `STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS`, and `PRODUCTION_UNCHANGED=PASS`. **If any preflight or health test fails, do not bypass or repeat `--apply`.** The script retains the previous stage image and checkpoint.

Browser check comes afterwards: close old Acer SSH tunnels, rediscover the new stage-only Docker IPs, open the private localhost Hub and review the Version 3 layout, five icons and favicon. Only after the visual review passes should the owner proceed to private staging password/MFA and signed POS launch acceptance. Public OAuth and HTTPS production behaviour remain separate gates.

## Version 3 login and POS accepted; dashboard source alignment (9 November)

**Owner browser evidence:** private staging Version 3 Connected Workspace login visual approved; password sign-in and MFA accepted; owner reports POS access works, but there is **no explicit evidence yet** of *zero additional login challenges* or one-time launch-ticket replay denial. Staging Hub dashboard screenshot was visibly the **older overview**. The source comparison on the main server found **exactly three differing requested dashboard files** relative to the newer Connected Login candidate: `src/App.tsx`, `src/components/HubOverview.tsx` and `src/components/Sidebar.tsx`. For those three, running production Hub equals candidate and staging differs; `src/components/AppSwitcher.tsx`, `src/components/WorkspaceConnections.tsx` and `src/lib/dashboardTruth.ts` already match. **No production change is needed to obtain the currently running frontend design.**

**Three approaches /REDTEAM:** (1) ship the entire live image (previously failed stage startup and could change backend/MFA), (2) copy the complete source tree (unreviewed auth and API changes), (3) **chosen:** overlay only these three dashboard frontend components from the **same exact 9 Nov candidate image already approved for login**, on top of the known-good private staging image `v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1`. Fail closed if *any recursively imported frontend dependency* differs from stage beyond those three; never silently copy dependency changes or production secrets. Ensure all three candidate files match the **running** live Hub versions byte-for-byte. Build offline, checkpoint private stage data/Compose and change only the staging Hub with automatic stage-image rollback for failed health/CSS/PNG/anonymous POS checks.

**Preflight blocked safely, 9 November:** owner's dashboard-only run stopped with `STAGING_DASHBOARD_ALIGNMENT_BLOCKED: Duplicate or invalid runtime environment variable` **before** any build, container recreation or production change. This was caused by the dashboard script using Python's `str.isidentifier()` on Docker environment keys, which is stricter than the names Docker accepts, and rejecting even identical repeated entries. Corrected `env_map()` now accepts nonempty Docker environment keys (even those with a dot or hyphen), compares complete key/value mappings regardless of ordering, accepts identical duplicate entries, and still rejects conflicting repeats, missing/added/changed values or malformed entries without logging secret values. The hardened stage/production separation, MFA, nonroot user and loopback-port checks are unchanged. **Rerun read-only preflight before apply**; if another gate blocks, do not bypass it.

**Read-only dry-run first (on Acer):**

```bash
ssh -T firelion@100.73.248.30 'bash -s' <<'REMOTE'
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
if [ -n "$(git -C "$HUB/source" status --porcelain)" ]; then
  echo "BLOCKED: staging source has local edits"
  exit 1
fi
git -C "$HUB/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109 || exit
python3 "$HUB/source/staging/pos-hubqa/align-dashboard-ui.py"
REMOTE
echo "SSH_EXIT_CODE=$?"
```

Expected dry-run: `PRIVATE_STAGE_DASHBOARD_PREFLIGHT=PASS`, SHA-256 for each `APPROVED_LIVE_DASHBOARD_COMPONENT`, `ALL_OTHER_IMPORTS_AND_LOGIN_UNCHANGED=PASS`, `STAGING_DASHBOARD_DRY_RUN=PASS`. **Do not use `--apply` if this fails; report the differing imported file names for an explicit separate compatibility review.** No deployment is authorised merely by this dry-run.

**Additional read-only diagnostic failure (owner, 9 November):** after updating to the all-differences inventory, preflight returned `PRIVATE_STAGE_DASHBOARD_PREFLIGHT=PASS` followed by `STAGING_DASHBOARD_ALIGNMENT_BLOCKED: Candidate dependency unavailable: index.html`. This was **a diagnostic path-resolution bug**, not missing image bytes: earlier owner file comparison confirmed exact candidate/stage `index.html` exists and matches. The scanner's extension list omitted `.html`, mistakenly trying paths such as `index.html.ts`. The new `dependency_paths()` preserves explicit HTML paths, with an executable regression test verifying `index.html` is resolved directly. No staging image was built and neither staging nor production changed. **Rerun the read-only diagnostic only**, collect the complete mismatch inventory, and do not run `--apply` if it reports any differences.

**Dashboard dependency blocked safely (owner evidence):** the previous read-only run passed `PRIVATE_STAGE_DASHBOARD_PREFLIGHT=PASS`, verified the three proposed UI components against the running live Hub and then reported `Additional frontend dependency differs: src/components/AdminConsole.tsx`. The command exited 1 without building, recreating or modifying anything. `AdminConsole.tsx` is a platform-admin component, and indiscriminately copying it or suppressing its mismatch would increase the change scope to authorisation-sensitive workflows. Considered choices: (1) copy it (rejected: expanded administrative-change risk); (2) ignore it (rejected: unverified compatibility); (3) **chosen:** retain read-only fail-closed dependency policy but **collect a complete list of changed imports** in one pass, listing *only file paths and SHA-256s* and then blocking deployment. This avoids repeatedly changing guards to reveal one difference at a time and prevents accidental transfer of admin code.

After updating the checkout, use the **read-only diagnostic only**:

```bash
ssh -T firelion@100.73.248.30 'bash -s' <<'REMOTE'
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
test -z "$(git -C "$HUB/source" status --porcelain)" || exit 1
git -C "$HUB/source" pull --ff-only origin feature/isolated-pos-hubqa-20261109 || exit 1
python3 "$HUB/source/staging/pos-hubqa/align-dashboard-ui.py"
REMOTE
echo "SSH_EXIT_CODE=$?"
```

On a mismatch, expect `NON_DASHBOARD_DEPENDENCY_DIFFERENCES=N` plus `DIFFERING_NON_DASHBOARD_DEPENDENCY=...` paths and hashes followed by `STAGING_DASHBOARD_ALIGNMENT_BLOCKED`. These lines are **expected diagnostic evidence, not deployment success**. Do **not** run `--apply` if any mismatches exist. Review the actual differences and component prop/API contracts separately, and continue to preserve the stage-only login, MFA, POS and production.

**Stage-only apply, only after the read-only gate passes:**

```bash
ssh -T firelion@100.73.248.30 'bash -s' <<'REMOTE'
HUB=/home/firelion/v79-hub-pos-hubqa-20261109
python3 "$HUB/source/staging/pos-hubqa/align-dashboard-ui.py" --apply || exit $?
python3 "$HUB/source/staging/pos-hubqa/check.py"
REMOTE
echo "SSH_EXIT_CODE=$?"
```

Expected after stage-only apply: `STAGING_UPDATED_DASHBOARD_FILES=PASS`, `STAGING_LOGIN_ICONS_AND_CSS=PASS`, `STAGING_MFA_AND_POS_RUNTIME_PRESERVED=PASS`, `PRODUCTION_AND_STAGE_POS_UNCHANGED=PASS`, `PRIVATE_STAGING_DASHBOARD_ALIGNED=PASS`, then all stage acceptance checks. **Browser dashboard visual approval and password→MFA→Hub→POS one-click SSO remain unverified until retested.** Refresh the Acer tunnel after any Hub staging recreation; never use production accounts or publish the private staging domain.

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
