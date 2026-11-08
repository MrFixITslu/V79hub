#!/usr/bin/env bash
# Build a staged MCP additive overlay from the exact reviewed 8 November Hub
# runtime source only. Does NOT touch or redeploy a live container.
set -Eeuo pipefail
source_file=${1:?Usage: prepare-exact-live-mcp-overlay.sh LIVE_SOURCE_FILE STAGED_OUTPUT_FILE}
target_file=${2:?Usage: prepare-exact-live-mcp-overlay.sh LIVE_SOURCE_FILE STAGED_OUTPUT_FILE}
[[ -f "$source_file" && ! -L "$source_file" ]] || { echo "SOURCE_MISSING" >&2; exit 2; }
[[ ! -e "$target_file" && ! -L "$target_file" ]] || { echo "TARGET_EXISTS_OR_IS_SYMLINK" >&2; exit 2; }
expected_source_blob="2e9aa16535edad85804ccda6697af57433e5501b"
source_blob=$(git hash-object "$source_file")
[[ "$source_blob" == "$expected_source_blob" ]] || { echo "LIVE_SOURCE_DRIFT: refusal" >&2; exit 3; }
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
temp=$(mktemp -d)
trap 'rm -rf -- "$temp"' EXIT
umask 077
cp -- "$source_file" "$temp/server.ts"
(cd "$temp" && git apply --check "$root/deploy/mcp/exact-live-mcp-additive-20261108.patch" && git apply "$root/deploy/mcp/exact-live-mcp-additive-20261108.patch")
expected_candidate_blob="67ef45a1a0d0f6aac01d9b558d2142f175a1b124"
actual_candidate_blob=$(git hash-object "$temp/server.ts")
[[ "$actual_candidate_blob" == "$expected_candidate_blob" ]] || { echo "CANDIDATE_DRIFT: refusal" >&2; exit 4; }
mkdir -p -- "$(dirname "$target_file")"
cp -- "$temp/server.ts" "$target_file"
chmod 0600 "$target_file"
echo "STAGED_ONLY_EXACT_LIVE_OVERLAY=VERIFIED"
echo "ORIGINAL_RUNTIME_UNTOUCHED=YES"
