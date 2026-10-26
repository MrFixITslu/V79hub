#!/usr/bin/env bash
# Build the owner-approved Hub source on the Acer. Never contacts production.
set -euo pipefail
umask 077

[[ "${1:-}" == --build && $# -eq 1 ]] || { echo 'Usage: script --build' >&2; exit 2; }
[[ "$(hostname -s)" == firelion-Aspire-A315-51 ]] || { echo 'STOP=ACER_HOST_REQUIRED'; exit 2; }
[[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || { echo 'STOP=DOCKER_OVERRIDE_REFUSED'; exit 2; }
for tool in git docker curl sha256sum python3 mktemp sed; do
  command -v "$tool" >/dev/null || { echo "STOP=MISSING_TOOL_$tool"; exit 2; }
done

SOURCE=114841271d4f8b9c4b63df6aedfd55bde2e82f40
RECORD=ab1fc171c709153da85a9451e7c9145908e52d54
MANIFEST_SHA=9fa9d30978fe8457e37a2afc588ff8737d54cd3286ba019816ec7e6214b9e19f
ROOT="$(mktemp -d "$HOME/v79-v3-approved-build.XXXXXXXX")"
echo "ACER_BUILD_DIRECTORY=$ROOT"
curl --fail --silent --show-error --location --proto '=https' \
  "https://raw.githubusercontent.com/MrFixITslu/V79hub/$RECORD/docs/release/vision79-v3-approved-source.json" \
  -o "$ROOT/approved-source.json"
printf '%s  %s\n' "$MANIFEST_SHA" "$ROOT/approved-source.json" | sha256sum -c - >/dev/null || { echo 'STOP=MANIFEST_HASH'; exit 3; }

mkdir "$ROOT/source"
git -C "$ROOT/source" init --quiet
git -C "$ROOT/source" remote add origin https://github.com/MrFixITslu/V79hub.git
git -C "$ROOT/source" fetch --quiet --depth=1 origin "$SOURCE"
git -C "$ROOT/source" checkout --quiet --detach FETCH_HEAD
[[ "$(git -C "$ROOT/source" rev-parse HEAD)" == "$SOURCE" ]] || { echo 'STOP=SOURCE_COMMIT'; exit 3; }
[[ -z "$(git -C "$ROOT/source" status --porcelain)" ]] || { echo 'STOP=DIRTY_SOURCE'; exit 3; }

python3 -B - "$ROOT/approved-source.json" "$ROOT/source" "$SOURCE" <<'PY'
import hashlib,json, pathlib,sys
manifest=json.loads(pathlib.Path(sys.argv[1]).read_text())
root=pathlib.Path(sys.argv[2]);source=sys.argv[3]
assert manifest['approved_visual_source']==source and manifest['owner_visual_approval']['instruction']=='approved'
files=manifest['runtime_files_sha256']
assert len(files)==133
for name,digest in files.items():
    p=root/name
    assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==digest, name
print('APPROVED_RUNTIME_FILES=PASS_133')
PY

# Pull mutable tags once, resolve immutable registry digests, then build using
# only those digest references. These operations affect Acer local images only.
docker pull node:22-alpine >"$ROOT/pull-node.log" 2>&1 || { echo 'STOP=NODE_BASE_PULL'; exit 3; }
docker pull alpine:3.24 >"$ROOT/pull-alpine.log" 2>&1 || { echo 'STOP=ALPINE_BASE_PULL'; exit 3; }
NODE_BASE="$(docker image inspect node:22-alpine --format '{{range .RepoDigests}}{{println .}}{{end}}' | sed -n '/^node@sha256:/ {p;q;}')"
RUNTIME_BASE="$(docker image inspect alpine:3.24 --format '{{range .RepoDigests}}{{println .}}{{end}}' | sed -n '/^alpine@sha256:/ {p;q;}')"
[[ "$NODE_BASE" =~ ^node@sha256:[a-f0-9]{64}$ && "$RUNTIME_BASE" =~ ^alpine@sha256:[a-f0-9]{64}$ ]] || { echo 'STOP=BASE_DIGEST_UNRESOLVED'; exit 3; }
TAG="v79-hub:v3-approved-${SOURCE:0:12}"
docker build --pull=false --file "$ROOT/source/Dockerfile" \
  --build-arg "NODE_BASE=$NODE_BASE" --build-arg "RUNTIME_BASE=$RUNTIME_BASE" \
  --label "org.opencontainers.image.revision=$SOURCE" \
  --tag "$TAG" "$ROOT/source" >"$ROOT/build.log" 2>&1 || { echo 'STOP=BUILD_FAILED_PRIVATE_LOG'; exit 3; }
IMAGE="$(docker image inspect "$TAG" --format '{{.Id}}')"
[[ "$IMAGE" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'STOP=IMAGE_ID'; exit 3; }
python3 -B - "$ROOT/build-receipt.json" "$SOURCE" "$NODE_BASE" "$RUNTIME_BASE" "$IMAGE" "$TAG" <<'PY'
import datetime,json,os,pathlib,sys
path=pathlib.Path(sys.argv[1]);data=dict(schema='vision79-v3-acer-candidate-build',
  built_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_commit=sys.argv[2],
  node_base=sys.argv[3],runtime_base=sys.argv[4],candidate_image_id=sys.argv[5],local_tag=sys.argv[6],
  production_changes='NONE',isolated_boot_verified=False,rollback_rehearsed=False)
with path.open('x') as f: os.chmod(path,0o600);json.dump(data,f,indent=2);f.write('\n')
print(json.dumps(data,sort_keys=True))
PY
