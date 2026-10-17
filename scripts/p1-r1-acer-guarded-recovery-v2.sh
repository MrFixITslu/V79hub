#!/usr/bin/env bash
# V79 R1 Acer-only guarded isolated recovery with temporary swapfile disable.
# Run as the regular Acer user, never on the production V79 server.
set -Eeuo pipefail
umask 077

REPO="$HOME/v79-r1-src.PnZUGsH9/repo"
BACKUP="$HOME/V79-P1-R1-Offhost/p1-r1-current-release-rmtdrog_"
COMMIT="6386d16f1abdac55a9c1a2eb4647f0fae66e1b22"
BRANCH="feature/p1-r1-offhost-capture-20261016"
WORK=""
SWAP_ATTEMPTED=0

declare -A EXPECTED=(
  [p1-r1-acer-four-image-boot.py]="c23e2f7bb758c9a5b93fa7b1d5907ddd852cb752"
  [p1-r1-acer-disconnected-db-rehearsal.py]="deb45ce7bd627a7d59c5a611715a18e55da32904"
  [p1-r1-acer-oci-pin-proof.py]="4e530500395864a30060e94667ac602436f68972"
  [p1-r1-acer-app-mount-preflight.py]="cf7c5ad2a33be1caa4405e1017fd3b5a8a8c23a3"
)

stop() { echo "STOP=$1"; exit 1; }
swap_names() { swapon --show=NAME --noheadings --raw; }
available_ram_kib() { awk '/^MemAvailable:/ {print $2}' /proc/meminfo; }

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "$SWAP_ATTEMPTED" == 1 ]]; then
    echo "=== CLEANUP ORIGINAL RECOVERY TEST ==="
    local fail=0 pods pod dir
    # pod ps includes stopped/created pods; unlike container ps it has no -a.
    pods="$(podman --remote=false pod ps --format '{{.Name}}' 2>/dev/null)" || fail=1
    while IFS= read -r pod; do
      [[ "$pod" =~ ^r1-closed-[0-9a-f]{10}$ ]] || continue
      podman --remote=false pod rm -f "$pod" >/dev/null 2>&1 || fail=1
    done <<< "$pods"
    # Never remove RAM data while any recovery pod may still be alive.
    pods="$(podman --remote=false pod ps --format '{{.Name}}' 2>/dev/null)" || fail=1
    if grep -Eq '^r1-closed-[0-9a-f]{10}$' <<< "$pods"; then fail=1; fi
    shopt -s nullglob
    if (( fail == 0 )); then
    for dir in /dev/shm/v79-r1-*; do
      if [[ -d "$dir" && ! -L "$dir" && "$(stat -c %u "$dir")" == "$(id -u)" ]]; then
        rm -rf -- "$dir" || fail=1
      else
        fail=1
      fi
    done
    fi
    local remaining=(/dev/shm/v79-r1-*)
    (( ${#remaining[@]} == 0 )) || fail=1
    pods="$(podman --remote=false pod ps --format '{{.Name}}' 2>/dev/null)" || fail=1
    if grep -Eq '^r1-closed-[0-9a-f]{10}$' <<< "$pods"; then fail=1; fi

    if (( fail != 0 )); then
      echo "STOP=RECOVERY_CLEANUP_UNVERIFIED_SWAP_NOT_REENABLED"
      echo "ACTION=INSPECT_R1_POD_AND_RAM_SCRATCH_BEFORE_REENABLING_SWAP"
      status=1
    else
      local swap_state
      swap_state="$(swap_names)" || swap_state="ERROR"
      if [[ "$swap_state" != "/swapfile" ]]; then
        sudo swapon /swapfile || status=1
      fi
      if [[ "$(swap_names)" == "/swapfile" ]]; then
        echo "R1_SWAP_RESTORED=YES"
      else
        echo "STOP=SWAP_REENABLE_NOT_VERIFIED"
        status=1
      fi
    fi
  fi
  if [[ -n "$WORK" && -d "$WORK" ]]; then rm -rf -- "$WORK"; fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ "$(hostname)" == "firelion-Aspire-A315-51" ]] || stop WRONG_HOST
[[ "$(id -u)" != 0 ]] || stop ROOT_USER_NOT_ALLOWED
[[ -z "${DOCKER_HOST:-}" && -z "${CONTAINER_HOST:-}" ]] || stop REMOTE_CONTEXT_REFUSED
[[ -d "$REPO/.git" && -f "$BACKUP/ciphertext-manifest.json" ]] || stop SOURCE_OR_BACKUP_NOT_FOUND

WORK="$(mktemp -d)"
echo "=== VERIFY FOUR PINNED SOURCES ==="
git -C "$REPO" fetch --no-tags origin "$BRANCH"
# This wrapper itself may be committed after the four immutable Python files;
# check the exact ancestor commit, not moving branch HEAD.
git -C "$REPO" merge-base --is-ancestor "$COMMIT" FETCH_HEAD || stop SOURCE_ANCESTOR_CHANGED
for filename in "${!EXPECTED[@]}"; do
  git -C "$REPO" show "$COMMIT:scripts/$filename" > "$WORK/$filename"
  [[ "$(git hash-object "$WORK/$filename")" == "${EXPECTED[$filename]}" ]] || stop SOURCE_FILE_HASH_MISMATCH
done
echo "R1_ALL_FOUR_SOURCES_VERIFIED=PASS"

# swapon --show=NAME is the supported util-linux display form.
echo "=== GUARD ORIGINAL SWAPFILE AND FREE MEMORY ==="
[[ "$(swap_names)" == "/swapfile" ]] || stop EXPECTED_ONLY_SWAPFILE
ram="$(available_ram_kib)"
[[ "$ram" =~ ^[0-9]+$ && "$ram" -ge 4194304 ]] || stop AVAILABLE_RAM_BELOW_4_GIB
swap_used="$(swapon --show=USED --bytes --noheadings --raw | awk '{s+=$1} END {printf "%.0f",s+0}')"
[[ "$swap_used" =~ ^[0-9]+$ && "$swap_used" -le 268435456 ]] || stop SWAP_IN_USE_ABOVE_256_MIB
[[ "$(stat -f -c %T /dev/shm)" == tmpfs ]] || stop RAM_SCRATCH_IS_NOT_TMPFS
scratch_free="$(df -B1 --output=avail /dev/shm | tail -n 1 | tr -d '[:space:]')"
[[ "$scratch_free" =~ ^[0-9]+$ && "$scratch_free" -ge 3221225472 ]] || stop RAM_SCRATCH_BELOW_3_GIB
shopt -s nullglob
prior=(/dev/shm/v79-r1-*)
(( ${#prior[@]} == 0 )) || stop PREEXISTING_PRIVATE_RECOVERY_SCRATCH
pods="$(podman --remote=false pod ps --format '{{.Name}}')" || stop PODMAN_POD_QUERY_FAILED
if grep -Eq '^r1-closed-[0-9a-f]{10}$' <<< "$pods"; then stop PREEXISTING_RECOVERY_POD; fi
[[ "$(podman --remote=false info --format '{{.Host.Security.Rootless}}')" == true ]] || stop LOCAL_ROOTLESS_PODMAN_NOT_VERIFIED
echo "R1_MEMORY_AND_SWAP_PREFLIGHT=PASS"

sudo -v
SWAP_ATTEMPTED=1
echo "=== TEMPORARILY DISABLE ACER SWAPFILE ==="
sudo swapoff /swapfile
[[ -z "$(swap_names)" ]] || stop SWAP_REMAINS_ACTIVE
ram="$(available_ram_kib)"
[[ "$ram" =~ ^[0-9]+$ && "$ram" -ge 4194304 ]] || stop RAM_BELOW_4_GIB_AFTER_SWAPOFF
echo "R1_DISK_SWAP_DISABLED=PASS"

RUNNER="$WORK/p1-r1-acer-four-image-boot.py"
echo "=== ORIGINAL BACKUP READ-ONLY PREFLIGHT ==="
python3 -B "$RUNNER" --backup "$BACKUP"
echo "=== FOUR-IMAGE NETWORK-DISCONNECTED APPLICATION SMOKE ==="
python3 -B "$RUNNER" --backup "$BACKUP" --execute
echo "R1_FOUR_IMAGE_SMOKE_COMMAND=COMPLETE"
