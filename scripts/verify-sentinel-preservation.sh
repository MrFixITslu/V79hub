#!/usr/bin/env bash
set -euo pipefail

# Refuse a source rollback that silently removes working Sentinel safeguards.
# This runs BEFORE the source rsync or any container restart. It never changes
# running services, data, releases, or Docker images.
incoming="${1:?Specify the extracted release directory}"
container="${2:-v79-hub}"
test -d "$incoming" || { echo "Hub release stage missing" >&2; exit 31; }
test -s "$incoming/server.ts" || { echo "Hub release server source missing" >&2; exit 32; }
if ! names="$(docker container ls --all --format '{{.Names}}')"; then
  echo "Existing Hub container inventory cannot be inspected: block release" >&2
  exit 35
fi
if ! printf '%s\n' "$names" | grep -Fxq -- "$container"; then
  # New installations have no live security modules to preserve.
  echo "No existing Hub container; source preservation guard not applicable"
  exit 0
fi
if ! state="$(docker inspect "$container" --format '{{.State.Status}}')"; then
  echo "Existing Hub state cannot be inspected: block release" >&2
  exit 35
fi
test "$state" = "running" || {
  echo "Existing Hub is not running: refuse an unsafe blind replacement" >&2
  exit 33
}
docker exec "$container" test -d /app/server || {
  echo "Existing Hub module directory cannot be inspected: block release" >&2
  exit 35
}
for file in \
  server/sentinel-qa-routes.mjs \
  server/sentinel-qa-cleanup.mjs \
  server/sentinel-write-fence.mjs \
  server/sentinel-audit-retention.mjs
do
  # Return an explicit result so Docker/exec failures, including exit 1, cannot
  # be mistaken for an absent module. A container disappearing also blocks.
  if ! presence="$(docker exec "$container" sh -c \
    'if test -s "$1"; then printf present; else printf absent; fi' sh "/app/$file")"; then
    echo "Existing Hub module cannot be inspected: $file; block release" >&2
    exit 35
  fi
  case "$presence" in
    present|absent) ;;
    *) echo "Invalid module inspection result: $file; block release" >&2; exit 35 ;;
  esac
  if [ "$presence" = present ]; then
    if [ ! -s "$incoming/$file" ]; then
      echo "BLOCKED: release would remove protected runtime module: $file" >&2
      exit 34
    fi
  fi
done
echo "Existing Hub Sentinel runtime modules preserved by incoming source"
