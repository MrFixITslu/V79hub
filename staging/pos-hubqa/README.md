# Isolated Hub → POS MFA/SSO staging

**Not a production deployment.** This is the candidate for [Hub issue #245](https://github.com/MrFixITslu/V79hub/issues/245) and [POS PR #17](https://github.com/MrFixITslu/V79POS/pull/17). It uses normal Hub's username/password + TOTP MFA and signed, single-use POS launch, but has independently generated accounts, private store, JWKS and service-signing keys.

Do not change \`v79-hub\`, \`v79-pos\`, \`v79-pos-db\`, live Hub's \`POS_BASE_URL\` or \`POS_PUBLIC_URL\`, Nginx Proxy Manager, public DNS, or production secrets. Do not share any stage password, MFA QR code, JWT, session cookie or launch ticket in ChatGPT, GitHub or logs.

## Architecture

- Hub stage: \`v79-hub-pos-hubqa\`, image \`v79hub:pos-hubqa-20261109\`; bind **only** \`127.0.0.1:18082\`.
- POS stage: existing \`v79-pos-hubqa-api\`, image \`v79pos:hubqa-2590623\`; bind **only** \`127.0.0.1:18081\`.
- Existing isolated POS stage PostgreSQL/Redis; \`v79pos_hubqa\` is a production-derived *private* test copy. Do not share or reset the volume.
- Hub stage uses its **own empty private JSON store** in \`/home/firelion/v79-hub-pos-hubqa-20261109/data\`. No copied production Hub accounts, MFA secrets, sessions or private JWKS.
- Only Docker network for **both Hub and POS stage API**: \`v79pos-hubqa-20261109_stage_internal\`, with \`internal: true\`. This removes stage POS's earlier \`proxy_network\` attachment. No live POS/Hub containers should appear on this staging network.
- No stage background worker, Resend, real payment provider, billing or marketing execution.
- Stage Hub's one-time POS launch provisions **only** stage POS and redirects **only** to the stage port.
- Staging Hub remains \`NODE_ENV=development\` solely to support HTTP loopback browser cookies. TOTP MFA is explicitly mandatory. **This does not prove production HTTPS Secure-cookie or Google OAuth behaviour.** A separate TLS and registered OAuth staging origin is needed for those gates.

The stage POS HMAC keys must be rotated away from copied live credentials. The preparation script generates new random keys and keeps them private on the server. The current POS launch-exchange contract uses the general HMAC key while entitlement uses the dedicated key, so **both stage keys intentionally have the same new stage-only value** for compatibility; they must NOT match production. A dedicated-key-only contract is a separate code/security improvement.

## A. Source checkout and read-only preflight

Run on the Acer. These commands copy or inspect only the named staging checkout; they do not alter running services:

\`\`\`sh
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
\`\`\`

Expected: \`ISOLATED_STAGE_PREFLIGHT=PASS\`, \`LIVE_POS_PRESERVED=PASS\`, \`DRY_RUN_ONLY=PASS\`. If the checkout is unavailable over HTTPS, use your existing authorised GitHub credential; **do not copy credentials into the command or chat**.

## B. Rotate only staging keys / prepare private Hub configuration

The stage POS API must first be **stopped, never the live POS**. Then rerun the guarded preparation with \`--apply\`:

\`\`\`sh
ssh -T firelion@100.73.248.30 'sh -eu' <<'REMOTE'
cd /home/firelion/v79-pos-hubqa-20261109
docker compose --env-file .env -f hubqa.compose.yml stop api

python3 /home/firelion/v79-hub-pos-hubqa-20261109/source/staging/pos-hubqa/prepare.py --apply
REMOTE
\`\`\`

This step is **one-time only**. It refuses to overwrite or rotate a previously initialised Hub stage; expects the original stage POS image, exact isolated DB and loopback port; rejects unfamiliar Compose or production images; generates a new staging service HMAC, Hub password and MFA encryption key; removes stage POS's access to production \`proxy_network\`; and redirects stage POS to the stage Hub JWKS, issuer and signed entitlement service. No live POS/Hub files are modified. The original stage **Compose file only** is retained as \`hubqa.compose.pre-hubqa.yml\` for review. Former staging copies of live signing keys are replaced rather than backed up.

Expected: \`ISOLATED_STAGE_CONFIG=PASS\`, \`FRESH_STAGE_ONLY_KEYS=PASS\`, \`MFA_REQUIRED=PASS\`.

## C. Build and start ONLY the new Hub stage and the existing POS stage

\`\`\`sh
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
\`\`\`

Expected: \`PRODUCTION_UNCHANGED=PASS\`, \`PRIVATE_STAGING_NETWORK=PASS\`, \`UNIQUE_KEYS_AND_MFA=PASS\`, \`ISOLATED_HUB_POS_ROUTING=PASS\`, \`STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS\`. Failure means **NO-GO**; inspect only the named staging containers and do not weaken authentication.

## D. Owner browser verification (requires the owner at the Acer)

Start a private two-port tunnel in **one separate Acer terminal**:

\`\`\`sh
ssh -N \
  -L 18082:127.0.0.1:18082 \
  -L 18081:127.0.0.1:18081 \
  firelion@100.73.248.30
\`\`\`

Open \`http://127.0.0.1:18082\` in Chrome. Login with the **new stage-only** administrator password from the stage Hub's mode-0600 \`.env\` (retrieve it locally into a password manager; do not paste the value here). Enrol and complete the staged account's fresh TOTP MFA. Launch POS using the **staging** Hub card, which must redirect to \`http://127.0.0.1:18081\`.

Never use \`https://hub.v79sl.com\` for this test; that launcher provisions against **production POS**. Do not copy the URL fragment containing the single-use ticket, access token, session cookie or TOTP code into messages.

Test both owner POS access and unauthorised/revoked access. A second test user must be deliberately created/invited inside the **stage Hub** and provisioned only into the stage POS tenant. Use only fake stock/jobs in a stage-only tenant, not other tenants from the restored production snapshot.

Record only redacted outcomes:
- MFA challenge and verified session; owner stage POS launch succeeds; a second use of the same launch ticket fails; expired ticket fails.
- POS \`/v1/me\` denies anonymous access, stale session, revoked membership or cancelled/expired entitlement, and mismatched tenant IDs; no data from the restored production tenants visible to the synthetic stage user.
- Technician visibility, minimum inventory location, stock request/receipt, stage-only job usage, role revocation and negative permissions.
- No calls from stage Hub or stage POS to live POS/Hub APIs, live billing, email or customer account changes.

**Do not claim Google OAuth or HTTPS production cookie parity from this HTTP loopback exercise.** These require separate, approved, secured staging callback domain and trusted TLS verification.

## E. Cleanup and remaining release gates

Stop **only** the staging containers to save resources, without deleting any volumes or backup files:

\`\`\`sh
ssh -T firelion@100.73.248.30 'sh -eu' <<'REMOTE'
cd /home/firelion/v79-hub-pos-hubqa-20261109
docker compose --env-file .env -f compose.yml stop hub
cd /home/firelion/v79-pos-hubqa-20261109
docker compose --env-file .env -f hubqa.compose.yml stop api
docker inspect v79-pos --format 'LIVE_POS={{.Config.Image}} STATUS={{.State.Health.Status}}'
REMOTE
\`\`\`

Do not use \`docker compose down -v\`; do not reset real customer data or restart production. Pending: secured HTTPS / OAuth validation, physical Android/iPhone/scanner use, network interruption, real Tiquet job mapping, customer-installed faulty equipment RMA, release security audit and explicit final production deployment approval.
