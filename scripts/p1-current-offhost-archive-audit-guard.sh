#!/usr/bin/env bash
# Acer-only format audit. Never connects to production or creates containers.
set -Eeuo pipefail
umask 077
stop() { echo "STOP=$1"; exit 1; }
(( $# == 0 )) || stop ARGUMENTS_REFUSED
REPO="$HOME/v79-r1-src.PnZUGsH9/repo"
COMMIT="cb27597cab49efed1c8f2df264180e565c569c83"
BLOB="03e9b4db4246bbf5aae300b0762270571b05ab38"
WORK=""; CHILD=""; SWAP_ATTEMPTED=0
swap_names() { swapon --show=NAME --noheadings --raw; }
cleanup() {
  local status=$? state group_clear=1
  trap - EXIT INT TERM
  set +e
  if [[ -n "$CHILD" ]]; then
    # setsid gives this audit and its GPG processes a private process group.
    if kill -0 -- "-$CHILD" 2>/dev/null; then
      kill -TERM -- "-$CHILD" 2>/dev/null
      kill -KILL -- "-$CHILD" 2>/dev/null
    fi
    wait "$CHILD" 2>/dev/null
    if kill -0 -- "-$CHILD" 2>/dev/null; then group_clear=0; fi
  fi
  if [[ "$SWAP_ATTEMPTED" == 1 && "$group_clear" != 1 ]]; then
    echo "STOP=AUDIT_PROCESSES_NOT_ABSENT_SWAP_HELD_OFF"; status=1
  elif [[ "$SWAP_ATTEMPTED" == 1 ]]; then
    state="$(swap_names)" || state="ERROR"
    if [[ -z "$state" ]]; then sudo swapon /swapfile || status=1; fi
    if [[ "$(swap_names)" == /swapfile ]]; then
      echo "R1_SWAP_RESTORED=YES"
    else
      echo "STOP=SWAP_RESTORE_NOT_VERIFIED"; status=1
    fi
  fi
  if [[ -n "$WORK" ]]; then rm -rf -- "$WORK"; fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[[ "$(hostname)" == firelion-Aspire-A315-51 && "$(id -u)" != 0 ]] || stop ACER_NONROOT_ONLY
[[ -d "$REPO/.git" ]] || stop SOURCE_CHECKOUT_MISSING
for tool in setsid timeout python3 sudo swapon git flock; do command -v "$tool" >/dev/null || stop REQUIRED_TOOL_MISSING; done
WORK="$(mktemp -d)"
git -C "$REPO" show "$COMMIT:scripts/p1-current-offhost-archive-audit.py" > "$WORK/audit.py"
[[ "$(git hash-object "$WORK/audit.py")" == "$BLOB" ]] || stop AUDITOR_SOURCE_HASH_CHANGED
# Avoid overlap with an existing recovery operation. This audit itself creates none.
shopt -s nullglob
prior=(/dev/shm/v79-r1-* /dev/shm/v79-p1-*)
(( ${#prior[@]} == 0 )) || stop PREEXISTING_PRIVATE_RECOVERY_RAM
[[ -d "${XDG_RUNTIME_DIR:-/nonexistent}" && ! -L "$XDG_RUNTIME_DIR" && "$(stat -c %u "$XDG_RUNTIME_DIR")" == "$(id -u)" ]] || stop PRIVATE_RUNTIME_DIRECTORY_REQUIRED
[[ ! -L "$XDG_RUNTIME_DIR/v79-p1-format-audit.lock" ]] || stop AUDIT_LOCK_UNSAFE
exec 9>"$XDG_RUNTIME_DIR/v79-p1-format-audit.lock"
flock -n 9 || stop AUDIT_ALREADY_RUNNING
[[ "$(swap_names)" == /swapfile ]] || stop EXPECTED_ONLY_SWAPFILE
ram="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$ram" =~ ^[0-9]+$ && "$ram" -ge 4194304 ]] || stop AVAILABLE_RAM_BELOW_4_GIB
used="$(swapon --show=USED --bytes --noheadings --raw | awk '{s+=$1} END {printf "%.0f",s+0}')"
[[ "$used" =~ ^[0-9]+$ && "$used" -le 268435456 ]] || stop SWAP_USE_ABOVE_256_MIB
sudo -v
SWAP_ATTEMPTED=1
sudo swapoff /swapfile
[[ -z "$(swap_names)" ]] || stop SWAP_REMAINS_ACTIVE
echo "R1_DISK_SWAP_DISABLED=PASS"
setsid timeout --kill-after=10s 300s python3 -B "$WORK/audit.py" &
CHILD=$!
if wait "$CHILD"; then STATUS=0; else STATUS=$?; fi
# The audited Python waits/reaps GPG on both success and ordinary errors.
# Timeout terminates its process group before returning to this parent.
exit "$STATUS"
