#!/usr/bin/env bash
set -euo pipefail
# Read-only release assessment. This script NEVER deploys, backs up, restores,
# rotates secrets, mutates users, or calls Docker Compose up/down.
root="${V79_HUB_DEPLOY_ROOT:-/opt/v79/hub}"
expected_host="${V79_EXPECTED_HOST:-v79sl}"
fail=0

require() {
  if ! "$@"; then fail=1; return 1; fi
}
echo "=== G1.2 LIVE READ-ONLY RELEASE PREFLIGHT ==="
if [[ "$(hostname -s)" != "$expected_host" ]]; then
  echo "BLOCKED: unexpected host"; exit 2
fi
command -v docker >/dev/null || { echo "BLOCKED: Docker unavailable"; exit 2; }
docker info >/dev/null || { echo "BLOCKED: Docker daemon unavailable"; exit 2; }
docker compose version >/dev/null || { echo "BLOCKED: Docker Compose unavailable"; exit 2; }

for name in v79-hub v79-hub-postgres v79-business-agent v79-tiquet-manager; do
  if ! docker inspect "$name" >/dev/null 2>&1; then
    echo "BLOCKED: missing critical container: $name"
    fail=1
    continue
  fi
  state="$(docker inspect "$name" --format '{{.State.Status}}')"
  health="$(docker inspect "$name" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  image_id="$(docker inspect "$name" --format '{{.Image}}')"
  printf '%s status=%s health=%s image=%s\n' "$name" "$state" "$health" "$image_id"
  if [[ "$state" != running || "$health" != healthy ]]; then fail=1; fi
done

compose_files="$(docker inspect v79-hub --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null || true)"
echo "Hub active Compose file locations: $compose_files"
expected_pin="$root/releases/wipay-return-585f701.pinned.yml"
if [[ "$compose_files" != *"$expected_pin"* ]]; then
  echo "BLOCKED: known pinned WiPay override is not active"; fail=1
fi
if [[ -f "$expected_pin" ]]; then
  echo "Pinned WiPay override exists; SHA256: $(sha256sum "$expected_pin" | cut -d ' ' -f 1)"
else
  echo "BLOCKED: pinned WiPay override file absent"; fail=1
fi
if [[ ! -f "$root/docker-compose.yml" ]]; then
  echo "BLOCKED: production base Compose file missing"; fail=1
fi
if [[ ! -s "$root/.env" ]]; then
  echo "BLOCKED: production environment file missing"; fail=1
fi
if [[ ! -d "$root/data" ]]; then
  echo "BLOCKED: production state directory missing"; fail=1
fi

# Print only metadata for sensitive mount; not secret path contents.
token="$root/data/agent-runtime.token"
if [[ -f "$token" ]]; then
  echo "Agent token metadata: $(stat -c 'uid=%u gid=%g mode=%a type=%F' "$token")"
else
  echo "BLOCKED: agent service token file missing"; fail=1
fi

echo "=== G1.2 RELEASE GATES NOT SELF-CERTIFIED ==="
echo "PENDING: independent encrypted backup+restore proof (Hub, Tiquet, WiPay state)"
echo "PENDING: pinned-overlay-preserving staged deployment and rollback rehearsal"
echo "PENDING: owner MFA, SSO, WiPay sandbox and executive end-to-end acceptance"
echo "PENDING: exact-ID dry-run of disposable test accounts (no deletion authorized)"
if ((fail)); then
  echo "NO-GO: infrastructure preflight failures observed"
  exit 2
fi
echo "HARD STOP: metadata inspection passed, but release gates above remain required"
exit 3
