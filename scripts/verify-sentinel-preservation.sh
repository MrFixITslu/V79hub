#!/usr/bin/env bash
set -euo pipefail

# Release upgrades MUST prove the existing Hub runtime and all protected
# Sentinel/agent modules before replacing source or restarting containers.
# New installations are not authorized by this upgrade-only preservation gate.
incoming="${1:?Specify the extracted release directory}"
container="${2:-v79-hub}"
test -d "$incoming" || { echo "Hub release stage missing" >&2; exit 31; }
test -s "$incoming/server.ts" || { echo "Hub release server source missing" >&2; exit 32; }
if ! docker inspect "$container" >/dev/null 2>&1; then
  echo "BLOCKED: existing Hub container cannot be inspected; no new-install bypass" >&2
  exit 36
fi
state="$(docker inspect "$container" --format '{{.State.Status}}')" || {
  echo "BLOCKED: unable to obtain existing Hub state" >&2
  exit 36
}
test "$state" = "running" || {
  echo "Existing Hub is not running: refuse an unsafe blind replacement" >&2
  exit 33
}
docker exec "$container" test -d /app/server || {
  echo "Existing Hub module directory cannot be inspected" >&2
  exit 35
}
for file in \
  server/sentinel-qa-routes.mjs \
  server/sentinel-qa-cleanup.mjs \
  server/sentinel-write-fence.mjs \
  server/sentinel-audit-retention.mjs \
  server/agent-approval-ledger.mjs
do
  docker exec "$container" test -s "/app/$file" || {
    echo "BLOCKED: protected runtime module missing or inspection failed: $file" >&2
    exit 35
  }
  if [ ! -s "$incoming/$file" ]; then
    echo "BLOCKED: release would remove protected runtime module: $file" >&2
    exit 34
  fi
done
echo "Existing Hub protected modules preserved by incoming source"
