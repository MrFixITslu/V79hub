#!/usr/bin/env bash
# Run on Acer: encrypted streams only, no live container changes or host chmod.
set -euo pipefail
umask 077
[[ "$(hostname)" != v79sl ]] || { echo "STOP=RUN_ON_ACER_NOT_V79SL"; exit 1; }
RECIPIENT='484CF39CE37A02884497AD9C41A17102D2842ECE'
for tool in ssh gpg tar sha256sum python3; do
 command -v "$tool" >/dev/null || { echo "STOP=MISSING_$tool"; exit 1; }
done
gpg --batch --list-secret-keys "$RECIPIENT" >/dev/null 2>&1
BACKUP_DIR="$(mktemp -d "$HOME/v79-workforce-recovery.XXXXXXXX")"
COMPLETE=0
trap 'if [[ "$COMPLETE" != 1 ]]; then echo "BACKUP=INCOMPLETE_DO_NOT_USE_FOR_RELEASE"; echo "BACKUP_DIRECTORY=$BACKUP_DIR"; fi' EXIT
encrypt() { gpg --batch --quiet --trust-model always --encrypt --recipient "$RECIPIENT" --output "$BACKUP_DIR/$1"; }
check_live() {
 ssh firelion@v79sl 'python3 -B -' <<'PY'
import json,subprocess
expected={'v79-hub':'sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06','v79-business-agent':'sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f','v79-tiquet-manager':'sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42'}
for item in json.loads(subprocess.check_output(['docker','inspect',*expected])):
 if item['Image']!=expected[item['Name'].lstrip('/')] or item['State'].get('Health',{}).get('Status')!='healthy':
  raise SystemExit('STOP=LIVE_BASELINE_CHANGED')
print('LIVE_IMAGE_AND_HEALTH_RECHECK=PASS')
PY
}
check_live
echo "BACKUP_DIRECTORY=$BACKUP_DIR"
echo 'STAGE=ENCRYPT_DATABASE'
ssh firelion@v79sl 'docker exec v79-hub-postgres sh -c '\''exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'\''' | encrypt hub-pg.dump.gpg

echo 'STAGE=ENCRYPT_HUB_DATA_USING_EXISTING_CONTAINER_READ_ACCESS'
# Existing Hub runs as root; this reads its existing data mount, not host permissions.
ssh firelion@v79sl 'docker exec v79-hub tar -C /app -czf - data' | encrypt hub-data.tar.gpg

echo 'STAGE=ENCRYPT_HOST_CONFIGURATION_AND_REPORTS'
ssh firelion@v79sl 'python3 -B -' <<'PY' | encrypt hub-config.tar.gpg
import json,os,subprocess
from pathlib import Path
hub=json.loads(subprocess.check_output(['docker','inspect','v79-hub']))[0]
if hub['Image']!='sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06': raise SystemExit('STOP=HUB_IMAGE_CHANGED')
files=hub['Config']['Labels']['com.docker.compose.project.config_files'].split(',')
if len(files)!=9: raise SystemExit('STOP=COMPOSE_BASELINE_CHANGED')
data_mount=next((m for m in hub['Mounts'] if m['Destination']=='/app/data'),None)
if not data_mount: raise SystemExit('STOP=HUB_DATA_MOUNT_UNAVAILABLE')
data_source=Path(data_mount['Source'])
# Data and embedded tokens are already captured through the root container reader.
def covered(name):
 p=Path(name)
 return p==data_source or data_source in p.parents
paths=files+['/opt/v79/hub/.env']+[m['Source'] for m in hub['Mounts'] if not covered(m['Source'])]+[str(Path.home()/'.local/share/v79-workforce-operations/reports')]
for name in paths:
 if not os.path.exists(name) or os.path.islink(name) or not (os.path.isfile(name) or os.path.isdir(name)): raise SystemExit('STOP=UNSUPPORTED_CONFIG_SOURCE')
subprocess.run(['tar','-C','/','-czf','-','--',*sorted(set(p.lstrip('/') for p in paths))],check=True)
PY

echo 'STAGE=ENCRYPT_RUNTIME_CONFIGURATION'
ssh firelion@v79sl 'docker inspect v79-hub v79-business-agent v79-tiquet-manager' | encrypt runtime-config.json.gpg

echo 'STAGE=ENCRYPT_ORIGINAL_ROLLBACK_IMAGE'
ssh firelion@v79sl 'docker image save sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06' | encrypt hub-original-image.tar.gpg

echo 'STAGE=VERIFY_ALL_FIVE_ENCRYPTED_STREAMS'
gpg --quiet --decrypt "$BACKUP_DIR/hub-pg.dump.gpg" |
 ssh firelion@v79sl 'set -eu; PG_IMAGE="$(docker inspect --format={{.Image}} v79-hub-postgres)"; docker run --rm -i --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 256m --cpus 1 --pids-limit 64 --entrypoint pg_restore "$PG_IMAGE" --list >/dev/null' 
for archive in hub-data.tar.gpg hub-config.tar.gpg; do
 gpg --quiet --decrypt "$BACKUP_DIR/$archive" | tar -tzf - >/dev/null
done
gpg --quiet --decrypt "$BACKUP_DIR/runtime-config.json.gpg" | python3 -c 'import json,sys; assert len(json.load(sys.stdin)) == 3'
gpg --quiet --decrypt "$BACKUP_DIR/hub-original-image.tar.gpg" | tar -tf - >/dev/null
(
 cd "$BACKUP_DIR"
 sha256sum ./*.gpg > SHA256SUMS
 sha256sum -c SHA256SUMS
)
check_live
printf '%s\n' 'STREAM_AND_ARCHIVE_VERIFICATION_ONLY_NOT_RESTORED' > "$BACKUP_DIR/verification-scope.txt"
COMPLETE=1
echo 'ENCRYPTED_OFFHOST_BACKUP=PASS_5_STREAMS'
echo 'RESTORE_REHEARSAL=OUTSTANDING'
echo 'PRODUCTION_DEPLOYED=NO'
