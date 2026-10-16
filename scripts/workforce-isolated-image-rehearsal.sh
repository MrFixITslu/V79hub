#!/usr/bin/env bash
# Run on v79sl only. Builds a separate candidate and runs synthetic tests.
set -euo pipefail
umask 077
[[ "$(hostname)" == v79sl ]] || { echo 'STOP=RUN_ON_V79SL_ONLY'; exit 1; }
for tool in git docker python3 timeout; do command -v "$tool" >/dev/null || { echo "STOP=MISSING_$tool"; exit 1; }; done
python3 - <<'PY'
import shutil
from pathlib import Path
mem={line.split(':')[0]:line.split(':')[1].strip().split()[0] for line in Path('/proc/meminfo').read_text().splitlines()}
if int(mem['MemAvailable']) < 2*1024*1024: raise SystemExit('STOP=LESS_THAN_2_GIB_AVAILABLE_RAM')
if shutil.disk_usage(Path.home()).free < 5*1024**3: raise SystemExit('STOP=LESS_THAN_5_GIB_FREE_DISK')
PY
BASE='sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06'
COMMIT='5c13dc9612752f896ef5cb2e8c1da63c0cfd8e04'
[[ "$(docker inspect --format '{{.Image}}' v79-hub)" == "$BASE" ]] || { echo 'STOP=LIVE_HUB_IMAGE_CHANGED'; exit 1; }
for app in v79-hub v79-business-agent v79-tiquet-manager; do
 [[ "$(docker inspect --format '{{.State.Health.Status}}' "$app")" == healthy ]] || { echo "STOP=UNHEALTHY_$app"; exit 1; }
done
STAGE_DIR="$(mktemp -d "$HOME/v79-workforce-image-stage.XXXXXXXX")"
RUN_ID="$(basename "$STAGE_DIR" | tr '[:upper:]' '[:lower:]')"
BASE_TAG="v79-workforce-base:$RUN_ID"
CANDIDATE="v79-workforce-candidate:$RUN_ID"
TEST_CONTAINER="$RUN_ID-tests"
docker inspect --format '{{.Name}} {{.Image}} {{.State.Health.Status}}' v79-hub v79-business-agent v79-tiquet-manager > "$STAGE_DIR/live-before.txt"
cleanup() {
 local result=$?
 trap - EXIT
 if docker inspect --format '{{index .Config.Labels "v79.workforce.rehearsal"}}' "$TEST_CONTAINER" 2>/dev/null | python3 -c 'import sys;sys.exit(0 if sys.stdin.read().strip()==sys.argv[1] else 1)' "$RUN_ID"; then
  docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true
 fi
 docker image rm "$BASE_TAG" >/dev/null 2>&1 || true
 if docker inspect --format '{{.Name}} {{.Image}} {{.State.Health.Status}}' v79-hub v79-business-agent v79-tiquet-manager > "$STAGE_DIR/live-after.txt" && cmp -s "$STAGE_DIR/live-before.txt" "$STAGE_DIR/live-after.txt"; then
  echo 'LIVE_IMAGE_AND_HEALTH_RECHECK=PASS'
 else
  echo 'LIVE_IMAGE_AND_HEALTH_RECHECK=CHANGED_OR_UNAVAILABLE'; result=1
 fi
 echo "STAGE_DIRECTORY=$STAGE_DIR"
 exit "$result"
}
trap cleanup EXIT

echo 'STAGE=FETCH_PINNED_SOURCE'
git clone --quiet --single-branch --branch feature/p1-workforce-operations-g3-20261016 https://github.com/MrFixITslu/V79hub.git "$STAGE_DIR/source"
git -C "$STAGE_DIR/source" checkout --quiet --detach "$COMMIT"
[[ "$(git -C "$STAGE_DIR/source" rev-parse HEAD)" == "$COMMIT" ]]
python3 "$STAGE_DIR/source/scripts/workforce-source-parity.py"

echo 'STAGE=BUILD_FROM_EXACT_LIVE_IMAGE_NO_NETWORK'
docker tag "$BASE" "$BASE_TAG"
cat > "$STAGE_DIR/source/Dockerfile.workforce-rehearsal" <<DOCKER
FROM $BASE_TAG
WORKDIR /app
COPY . /app
RUN npm run build
DOCKER
# Existing lockfile/dependencies are identical to the verified live baseline.
timeout 600 docker build --network none --pull=false --label "v79.workforce.rehearsal=$RUN_ID" -f "$STAGE_DIR/source/Dockerfile.workforce-rehearsal" -t "$CANDIDATE" "$STAGE_DIR/source" > "$STAGE_DIR/build.log" 2>&1 || { echo 'BUILD=FAILED_SEE_PRIVATE_BUILD_LOG'; exit 1; }
IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$CANDIDATE")"
echo "CANDIDATE_IMAGE=$IMAGE_ID"

echo 'STAGE=NETWORK_ISOLATED_SYNTHETIC_TESTS'
# No host mounts, published ports, Docker socket, credentials or production DB.
timeout 300 docker run --rm --name "$TEST_CONTAINER" \
 --label "v79.workforce.rehearsal=$RUN_ID" \
 --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
 --memory 1536m --cpus 1 --pids-limit 256 \
 --tmpfs /tmp:rw,nosuid,nodev,size=384m --tmpfs /app/data:rw,nosuid,nodev,size=16m \
 -e NODE_OPTIONS=--import=./tests/isolated-env.mjs \
 -e V79_WORKFORCE_REPORTS_ENABLED=0 \
 --entrypoint node "$IMAGE_ID" --test \
 tests/admin-mfa-flow.test.mjs \
 tests/agent-executive-owner-proxy.test.mjs \
 tests/workforce-briefing-history-ui.test.mjs \
 tests/workforce-report-http.test.mjs \
 tests/workforce-python-report-reader.test.mjs \
 tests/workforce-briefing-route.test.mjs \
 tests/workforce-briefings.test.mjs \
 tests/owner-coo-workboard.test.mjs \
 > "$STAGE_DIR/tests.log" 2>&1 || { tail -n 45 "$STAGE_DIR/tests.log"; echo 'REHEARSAL=FAILED'; exit 1; }
tail -n 12 "$STAGE_DIR/tests.log"
printf '%s\n' "$IMAGE_ID" > "$STAGE_DIR/candidate-image.txt"
echo 'REHEARSAL=PASS_SYNTHETIC_IMAGE_TESTS'
echo 'PRODUCTION_DEPLOYED=NO'
echo 'BROWSER_ACCEPTANCE=OUTSTANDING'
