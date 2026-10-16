#!/usr/bin/env bash
# Acer-only runner; creates v3 from the checksum-verified v2, then runs it.
set -euo pipefail
umask 077
D="$HOME/Downloads"
OLD="$D/v79_p1_live_tiquet_security_cutover_v2_20261016.sh"
NEW="$D/v79_p1_live_tiquet_security_cutover_v3_20261016.sh"
PATCH_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/v2-to-v3-gzip-patch.b64"
OLD_SHA="29e4d8a1e95656ebe1e0e6958136a6fb610c3d3b8fe0c646f1cb3529325a8c59"
NEW_SHA="39c26de5269aed518433ba54d1a9225fc9ac5b211dc6dc5bcce617763112401b"
test -f "$OLD" && test ! -L "$OLD" || { echo 'STOP=VERIFIED_V2_REQUIRED'; exit 1; }
printf '%s  %s\n' "$OLD_SHA" "$OLD" | sha256sum -c -
test -f "$PATCH_FILE" && test ! -L "$PATCH_FILE" || { echo 'STOP=PATCH_NOT_FOUND'; exit 1; }
if [ -e "$NEW" ] || [ -L "$NEW" ]; then
  test ! -L "$NEW" || { echo 'STOP=V3_SYMLINK_REFUSED'; exit 1; }
  if ! printf '%s  %s\n' "$NEW_SHA" "$NEW" | sha256sum -c - >/dev/null 2>&1; then
    QUARANTINE="$D/failed-v3-patch-$(date -u +%Y%m%dT%H%M%SZ)-$$.sh"
    mv -- "$NEW" "$QUARANTINE"
    echo 'INVALID_INCOMPLETE_V3=PRESERVED_IN_QUARANTINE'
  fi
fi
if [ ! -e "$NEW" ]; then
  cp -- "$OLD" "$NEW"
  base64 -d "$PATCH_FILE" | gzip -dc | patch --batch --fuzz=0 -d "$D" -p0
fi
printf '%s  %s\n' "$NEW_SHA" "$NEW" | sha256sum -c -
bash -n "$NEW"
echo 'V3_CODE_INTEGRITY_AND_SYNTAX=PASS'
echo 'NEXT=FOUNDERS_AUTHORIZED_LIVE_TIQUET_ONLY_RELEASE'
bash "$NEW"
