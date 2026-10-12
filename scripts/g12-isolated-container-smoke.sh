#!/usr/bin/env bash
set -euo pipefail

# Deterministic, zero-trust smoke: no Hub/DB connectivity, no live credentials.
# Run only on a Docker engine explicitly approved for disposable CI testing.
command -v docker >/dev/null
command -v git >/dev/null
root="$(git rev-parse --show-toplevel)"
image="v79-g12-smoke:$(git rev-parse --short=12 HEAD)"
container="v79-g12-smoke-${RANDOM}-$$"
scratch="$(mktemp -d)"
started=0
cleanup() {
  if [ "$started" = 1 ]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT

printf '%s\n' '=== G1.2: isolated, non-root Docker smoke ==='
docker build --file "$root/agent-service/Dockerfile" \
  --tag "$image" \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  "$root/agent-service"

# Synthetic secret ONLY: never mount the server's actual Hub token.
printf '%s\n' 'SYNTHETIC_CI_SERVICE_TOKEN_DO_NOT_USE_IN_PRODUCTION' > "$scratch/token"
chmod 600 "$scratch/token"
chmod 755 "$scratch"
if [ "$(stat -c %u "$scratch/token")" != 1000 ]; then
  command -v sudo >/dev/null || { echo 'STOP: Cannot set synthetic token owner to UID 1000'; exit 1; }
  sudo chown 1000:1000 "$scratch/token"
fi

docker run -d --name "$container" \
  --network none \
  --read-only \
  --user 1000:1000 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 128 \
  --memory 512m \
  --cpus 0.5 \
  --tmpfs /tmp:rw,nosuid,nodev,size=32m,mode=1777 \
  --mount "type=bind,source=$scratch/token,target=/run/secrets/v79-agent-token,readonly" \
  --env NODE_ENV=production \
  --env V79_AGENT_MODEL_PROVIDER=ollama \
  --env OLLAMA_BASE_URL=http://127.0.0.1:19999 \
  --env V79_HUB_AGENT_SNAPSHOT_URL=http://127.0.0.1:19998/internal/agent/snapshot \
  --env V79_EXECUTIVE_MODEL_CYCLE_ENABLED=0 \
  "$image" >/dev/null
started=1

# No host-port publication, production network, or writable host mounts.
docker inspect "$container" --format '{{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}} {{.Config.User}}' |
  grep -Fx 'none true 1000:1000'
test -z "$(docker port "$container")"

docker exec -i "$container" node --input-type=module - <<'JS'
import assert from 'node:assert/strict';
import fs from 'node:fs';

assert.equal(process.getuid(), 1000, 'non-root runtime');
assert.equal(process.getgid(), 1000, 'non-root group');
assert.equal(fs.readFileSync('/run/secrets/v79-agent-token', 'utf8').trim(),
  'SYNTHETIC_CI_SERVICE_TOKEN_DO_NOT_USE_IN_PRODUCTION');
console.log('PASS: UID 1000 and synthetic 0600 token are readable');

const base = 'http://127.0.0.1:3055';
let ready = false;
for (let attempt = 0; attempt < 70; attempt++) {
  try {
    const r = await fetch(base + '/health', {signal: AbortSignal.timeout(500)});
    if (r.ok) { ready = true; break; }
  } catch { /* still starting */ }
  await new Promise(resolve => setTimeout(resolve, 200));
}
assert.ok(ready, 'health reachable on container loopback');

const token = fs.readFileSync('/run/secrets/v79-agent-token', 'utf8').trim();
const call = (path, options = {}) => fetch(base + path, {
  ...options,
  signal: AbortSignal.timeout(3000),
});
const structure = '/api/agent/executive-structure';
assert.equal((await call(structure)).status, 401, 'no token denied');
assert.equal((await call(structure, {headers: {'x-v79-agent-token':'incorrect'}})).status, 401, 'invalid token denied');
const authorized = await call(structure, {headers: {'x-v79-agent-token': token}});
assert.equal(authorized.status, 200, 'valid synthetic token accepted');
const body = await authorized.json();
assert.equal(body.mode, 'read-only');
assert.equal(body.actionsEnabled, false);
assert.equal(body.applicationWriteAdaptersEnabled, false);
assert.equal(body.roles.length, 2);
assert.deepEqual(body.roles.map(r => r.id), ['ceo','coo']);
assert.ok(body.roles.every(r => r.approvalAuthority === 'none'));
assert.equal(authorized.headers.get('cache-control'), 'no-store');

const preview = '/api/agent/executive-preview';
assert.equal((await call(preview,{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).status,
  401, 'no token denied before preview gate');
assert.equal((await call(preview,{method:'POST',headers:{'x-v79-agent-token':token,'content-type':'application/json'},body:'{}'})).status,
  404, 'preview disabled by default');
console.log('PASS: health, authentication, two-role read-only structure, preview disabled');
JS

status="$(docker inspect "$container" --format '{{.State.Status}}')"
test "$status" = "running"
echo "PASS: isolated smoke complete; ephemeral container and synthetic secret will be removed"
