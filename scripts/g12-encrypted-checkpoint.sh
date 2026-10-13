#!/usr/bin/env bash
# V79 G1.2: explicit-owner-gated, encryption-only checkpoint preparation.
# NEVER deploys, restores, removes, or restarts live resources.
# Each stream is encrypted without creating a local plaintext dump/archive.
# A successful backup STILL REQUIRES separate decrypt + isolated restore.
set -euo pipefail
umask 077

usage() {
  echo 'Usage: g12-encrypted-checkpoint.sh --plan | --execute PUBLIC_KEY_FILE PUBLIC_KEY_FINGERPRINT' >&2
  exit 2
}
[[ $# -eq 1 && "$1" == "--plan" ]] ||
  [[ $# -eq 3 && "$1" == "--execute" ]] || usage
mode="$1"
[[ "$(hostname -s)" == v79sl ]] || { echo "STOP: wrong host"; exit 2; }
for c in docker sha256sum gpg tar mktemp stat df; do
  command -v "$c" >/dev/null || { echo "STOP: missing $c"; exit 2; }
done
root=/opt/v79/hub
pin="$root/releases/wipay-return-585f701.pinned.yml"
hub_compose="$root/docker-compose.yml"
tiquet_compose=/home/firelion/V79-Sentinel/Tiquet-release-merge-20261010/docker-compose.yml
tiquet_overlay=/home/firelion/backups/v79-sentinel-tiquet-integration-premerge-20261010/tiquet-darklaunch-release.yml
# Tiquet's Compose uses env_file: .env; without this file a full restore
# loses its database credentials and application signing configuration.
tiquet_env=/home/firelion/V79-Sentinel/Tiquet-release-merge-20261010/.env
expect_pin=8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74
declare -A images=(
  [v79-hub]=sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30
  [v79-hub-postgres]=sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24
  [v79-business-agent]=sha256:ff64a76651a2b784474f5d7430d0d78515bc7b46b2d0d1f81c51c79958ef417b
  [v79-tiquet-manager]=sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b
)
fail(){ echo "STOP: $1; nothing has been deployed or restored" >&2; exit 2; }
for file in "$pin" "$hub_compose" "$root/.env" "$tiquet_compose" "$tiquet_overlay" "$tiquet_env"; do
  [[ -f "$file" && ! -L "$file" && -r "$file" ]] || fail "required configuration missing or unreadable"
done
[[ "$(sha256sum "$pin" | cut -d' ' -f1)" == "$expect_pin" ]] || fail "WiPay overlay changed"
for container in v79-hub v79-hub-postgres v79-business-agent v79-tiquet-manager; do
  actual="$(docker inspect --format '{{.Image}}' "$container" 2>/dev/null)" || fail "missing container"
  [[ "$actual" == "${images[$container]}" ]] || fail "image changed: $container"
  [[ "$(docker inspect --format '{{.State.Status}}' "$container")" == running ]] || fail "not running: $container"
  [[ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" == healthy ]] || fail "not healthy: $container"
done
[[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' v79-hub)" == v79-hub ]] || fail "Hub Compose project changed"
[[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' v79-tiquet-manager)" == v79tiquet ]] || fail "Tiquet Compose project changed"
for spec in \
  'v79-hub-postgres|/var/lib/postgresql/data|v79-hub_v79_hub_postgres_data' \
  'tiquet-postgres|/var/lib/postgresql/data|v79tiquet_tiquet_pg_data' \
  'v79-tiquet-manager|/app/data|v79tiquet_tiquet_data' \
  'v79-tiquet-manager|/app/uploads|v79tiquet_tiquet_uploads'; do
  IFS='|' read -r container dest expected <<< "$spec"
  live="$(docker inspect --format "{{range .Mounts}}{{if eq .Destination \"$dest\"}}{{.Name}}{{end}}{{end}}" "$container" 2>/dev/null)" || fail "required storage not present"
  [[ "$live" == "$expected" ]] || fail "storage identity changed: $container $dest"
done
for container in v79-hub-postgres tiquet-postgres; do
  [[ "$(docker inspect --format '{{.State.Status}}' "$container")" == running ]] || fail "DB stopped: $container"
  docker exec "$container" sh -c 'command -v pg_dump >/dev/null && command -v pg_restore >/dev/null && pg_isready -q -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}"' >/dev/null 2>&1 ||
    fail "DB export tools not ready: $container"
done
[[ -r "$root/data/agent-runtime.token" ]] || fail "Hub agent runtime key not readable"
[[ -r /home/firelion/.v79-secrets/owner-readonly-platform.token ]] || fail "owner platform key not readable"
[[ "$(stat -c '%a' "$root/data/agent-runtime.token")" == 600 ]] || fail "agent token permissions changed"
[[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' v79-hub)" == "$hub_compose,$pin" ]] || fail "Hub's running pinned Compose file list changed"
free_kib="$(df -Pk /home/firelion | awk 'NR==2 {print $4}')"
[[ "$free_kib" =~ ^[0-9]+$ && "$free_kib" -ge 20971520 ]] || fail "less than 20 GiB free"
if [[ "$mode" == --plan ]]; then
  echo "PLAN ONLY: exact live images, pinned overlay, databases, mounts, token and disk checks passed"
  echo "GPG recipient NOT YET VERIFIED; no backup/restore/deploy writes made"
  exit 3
fi

# --execute has independent owner authorization and an OFF-host private key.
[[ "${V79_G12_ENCRYPTED_BACKUP_APPROVED:-}" == "FOUNDER_APPROVED_ENCRYPTED_CHECKPOINT_ONLY" ]] ||
  fail "missing exact founder checkpoint authorization"
pub="$2"
fpr="${3^^}"
[[ "$fpr" =~ ^([0-9A-F]{40}|[0-9A-F]{64})$ ]] || fail "invalid GPG fingerprint"
[[ -f "$pub" && ! -L "$pub" && -r "$pub" ]] || fail "public key unavailable"
grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----$' "$pub" || fail "provide only an ASCII-armored PUBLIC key"
! grep -q 'PRIVATE KEY BLOCK' "$pub" || fail "private key cannot be on the server"
gpg_home="$(mktemp -d /home/firelion/.v79-g12-gpg.XXXXXXXX)"
chmod 700 "$gpg_home"
cleanup(){ rm -rf -- "$gpg_home"; }
trap cleanup EXIT
gpg --homedir "$gpg_home" --batch --quiet --import "$pub" >/dev/null 2>&1 || fail "public key import failed"
gpg --homedir "$gpg_home" --batch --with-colons --fingerprint --list-keys \
  | awk -F: '$1=="fpr" {print $10}' | grep -Fxq "$fpr" || fail "recipient fingerprint mismatch"
gpg --homedir "$gpg_home" --batch --with-colons --list-secret-keys 2>/dev/null \
  | grep -q '^sec:' && fail "STOP: private GPG key is present in checkpoint keyring"

# The root directory is not writable to other users. No external cloud access.
base=/home/firelion/.v79-g12-encrypted-recovery
mkdir -p -m 700 "$base"
chmod 700 "$base"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="$base/g12-$stamp-$$"
mkdir -m 700 "$dest"
# Distinguish interrupted checkpoint from validated COMPLETE manifest.
printf '%s\n' IN_PROGRESS > "$dest/STATUS"
encrypt_stream() {
  local label="$1"; shift
  local output="$dest/$label.gpg"
  # pipefail detects BOTH a failing Docker/tar producer and a failing GPG.
  if "$@" | gpg --homedir "$gpg_home" --batch --no-tty --quiet --yes \
    --trust-model always --recipient "$fpr" --compress-algo none \
    --encrypt --output "$output.partial"; then
    [[ -s "$output.partial" ]] || fail "empty encryption output: $label"
    mv -- "$output.partial" "$output"
    sha256sum "$output" | awk '{print $1}' > "$output.sha256"
    echo "ENCRYPTED: $label"
  else
    fail "encrypted capture failed: $label"
  fi
}
pg_export() {
  docker exec "$1" sh -euc \
    'exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" --format=custom --no-owner --no-acl'
}
inspect_runtime(){ docker inspect v79-hub v79-hub-postgres v79-business-agent v79-tiquet-manager tiquet-postgres; }
compose_resolved(){
  cd "$root"
  docker compose -f "$hub_compose" -f "$pin" config --format json
}
# Validate generator outputs INSIDE the encrypted stream only; never display them.
encrypt_stream hub-postgresql pg_export v79-hub-postgres
encrypt_stream tiquet-postgresql pg_export tiquet-postgres
encrypt_stream hub-data docker cp v79-hub:/app/data -
encrypt_stream tiquet-data docker cp v79-tiquet-manager:/app/data -
encrypt_stream tiquet-uploads docker cp v79-tiquet-manager:/app/uploads -
encrypt_stream owner-platform-token docker cp v79-hub:/run/secrets/v79-readonly-platform-token -
encrypt_stream live-inspect inspect_runtime
encrypt_stream hub-resolved-compose compose_resolved
encrypt_stream hub-and-tiquet-config tar -C / -cf - \
  "${hub_compose#/}" "${pin#/}" "${root#/}/.env" \
  "${tiquet_compose#/}" "${tiquet_overlay#/}" "${tiquet_env#/}"
# Capture exact rollback container images (includes the old Agent).
for name in v79-hub v79-hub-postgres v79-business-agent v79-tiquet-manager tiquet-postgres; do
  image="$(docker inspect --format '{{.Image}}' "$name")"
  encrypt_stream "image-$name" docker image save "$image"
done
# Never claim decryption or restore. This manifest is metadata only.
{
  printf 'checkpoint_utc=%s\n' "$stamp"
  printf 'recipient_fingerprint=%s\n' "$fpr"
  printf 'hub_image=%s\n' "${images[v79-hub]}"
  printf 'agent_image=%s\n' "${images[v79-business-agent]}"
  printf 'tiquet_image=%s\n' "${images[v79-tiquet-manager]}"
  printf 'hub_overlay_sha256=%s\n' "$expect_pin"
  printf 'database_snapshots_cross_service_atomic=NO\n'
  printf 'encrypted_payloads=%s\n' "$(find "$dest" -maxdepth 1 -name '*.gpg' -type f | wc -l)"
  printf 'decryption_verified=NO\nrestore_verified=NO\nrelease_approved=NO\n'
} > "$dest/MANIFEST.txt"
# Hash files whose names are fixed and validated; no raw data is included.
(cd "$dest" && sha256sum -- *.gpg > ENCRYPTED-SHA256SUMS)
printf '%s\n' ENCRYPTED_CHECKPOINT_CREATED_RESTORE_NOT_TESTED > "$dest/STATUS"
echo "ENCRYPTED CHECKPOINT CREATED; restoring/decrypting NOT VERIFIED"
echo "Output directory: $dest"
echo "DO NOT DEPLOY until isolated decryption and full app/database restore are independently verified"
exit 0
