#!/usr/bin/env python3
"""READ-ONLY checkpoint readiness pinned to healthy V8 Hub/Tiquet, 2026-10-26.
Never pauses, captures or restores production. Fork of tested 2026-10-25 script;
only two pinned app images, sealed Hub config and informational source changed.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys

RECIPIENT = '484CF39CE37A02884497AD9C41A17102D2842ECE'
APPS = ('v79-hub', 'v79-tiquet-manager', 'v79-business-agent')
IMAGES = {
    'v79-hub': 'sha256:66caa099adf1321b72a90b22f8125981e5a6d99b5920cebae0454541cccd9fa7',
    'v79-tiquet-manager': 'sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0',
    'v79-business-agent': 'sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b',
    'v79-hub-postgres': 'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
    'tiquet-postgres': 'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685',
}
HOST_STATE = (
    '.config/v79-workforce/google',
    '.local/share/v79-workforce-operations',
    '.local/share/v79-approved-task-worker',
)
STAGE = 'START'

def stage(name):
    global STAGE
    STAGE = name

class Halt(Exception):
    pass

def need(ok, code):
    if not ok:
        raise Halt(code)

def call(args, data=None, timeout=45):
    try:
        p = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise Halt('READ_COMMAND_UNAVAILABLE') from None
    need(p.returncode == 0, 'READ_COMMAND_FAILED_NO_SECRET_OUTPUT')
    return p.stdout

def jcall(args):
    return json.loads(call(args))

def values(o):
    return dict(x.split('=', 1) for x in o['Config'].get('Env', []) if '=' in x)

def local_docker(host):
    need(not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'), 'DOCKER_OVERRIDE')
    ctx = jcall(['docker', 'context', 'inspect'])
    need(len(ctx) == 1 and ctx[0]['Endpoints']['docker']['Host'] in
         ('unix:///var/run/docker.sock', 'unix:///run/docker.sock'), 'DOCKER_NOT_LOCAL')
    need(call(['docker', 'info', '--format', '{{.Name}}']).decode().strip() == host, 'DOCKER_DAEMON_HOST_MISMATCH')

def memory_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    return 0

def overlap(a, b):
    return os.path.commonpath([a, b]) in (a, b)

def private_metadata(path):
    try:
        s = path.lstat()
        return {'present': True, 'regular': stat.S_ISREG(s.st_mode),
                'directory': stat.S_ISDIR(s.st_mode), 'owned': s.st_uid == os.getuid(),
                'private': not (stat.S_IMODE(s.st_mode) & 0o077)}
    except FileNotFoundError:
        return {'present': False}


EXPECTED_HUB_SOURCES={'/home/firelion/.v79-hardened-pair-releases/pair-20261026T003607Z-6e6006791f34/manifest-v79-hub-candidate.json':'e785277a3970476c214fade92763fac7a41a9151ece7365c67c8cb2b439023c6'}
EXPECTED_MOUNTS={
 'v79-hub':{'/app/data':('bind',True),'/run/v79-workforce-reports':('bind',False),'/run/secrets/v79-agent-token':('bind',False),'/run/secrets/v79-coo-github-token':('bind',False),'/run/secrets/v79-readonly-platform-token':('bind',False),'/run/secrets/v79-workforce-token':('bind',False),'/run/v79-google':('volume',False)},
 'v79-tiquet-manager':{'/app/data':('volume',True),'/app/uploads':('volume',True)},
 'v79-business-agent':{'/run/secrets/v79-agent-token':('bind',False)},
}
PRICING_PROBE=r"""
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
import {createPricingRequestStore} from './server/pricing-request-store.mjs';
import {getWipayConfig} from './server/wipay-provider.mjs';
try{
const raw=fs.readFileSync('/app/server.ts');if(crypto.createHash('sha1').update(Buffer.from('blob '+raw.length+'\0')).update(raw).digest('hex')!=='6784def9a38d018f87aa85e0d73ec10d65972daf')process.exit(2);
const file=path.resolve(process.env.DATA_DIR||'/app/data','pricing-requests-v1.json');const st=fs.lstatSync(file);
if(!st.isFile()||(st.mode&0o077)||fs.existsSync(file+'.lock')||getWipayConfig().environment!=='sandbox')process.exit(3);
const secret=String(process.env.V79_HUB_SECURITY_KEY||process.env.V79_PLATFORM_SHARED_SECRET||'').trim();
const state=await createPricingRequestStore({file,secret}).read();
console.log(JSON.stringify({present:true,private:true,signatureVerified:true,requests:state.requests.length,events:state.events.length,wipaySandbox:true,sourcePinned:true}));
}catch{process.exit(4)}
"""
def validate_final_scope(report,selected):
 for app,expected in EXPECTED_MOUNTS.items():
  row=selected[app];actual={m['Destination']:(m['Type'],m['RW']) for m in row['Mounts']}
  need(actual==expected,'FINAL_APPLICATION_MOUNT_SCOPE_DIFFERS')
  if app=='v79-hub':
   paths=row['Config']['Labels']['com.docker.compose.project.config_files'].split(',')
   need(set(paths)==set(EXPECTED_HUB_SOURCES),'FINAL_HUB_COMPOSE_CHAIN_DIFFERS')
   need(all(report['compose_input_hashes'].get(p)==digest for p,digest in EXPECTED_HUB_SOURCES.items()),'FINAL_HUB_COMPOSE_HASH_DIFFERS')
   google=next(m for m in row['Mounts'] if m['Destination']=='/run/v79-google')
   need(google.get('Name')=='v79-google-credentials-49f81377675a','GOOGLE_CREDENTIAL_VOLUME_DIFFERS')
 metadata=json.loads(call(['docker','exec','v79-hub','node','--input-type=module','-e',PRICING_PROBE]))
 need(all(metadata.get(k) is True for k in ('present','private','signatureVerified','wipaySandbox','sourcePinned')),'PRICING_LEDGER_OR_SANDBOX_CHECK_FAILED')
 need(isinstance(metadata.get('requests'),int) and metadata['requests']>=1,'ACCEPTED_PRICING_REQUEST_NOT_FOUND')
 report['pricing_ledger_metadata']=metadata
 report['mount_count']=sum(len(v) for v in EXPECTED_MOUNTS.values())
 report['expected_encrypted_artifacts']=5+report['mount_count']
 report['current_hub_source']='c12e54bdb52f8996fae19688d74354d731e7de27'
 report['mounted_google_credentials_contents_read']=False
 report['final_recovery_scope']='FIVE_CURRENT_IMAGES_TWO_DATABASES_TEN_MOUNTS_PRIVATE_HOST_STATE'

def server():
    stage('SERVER_IDENTITY_AND_DOCKER')
    need(socket.gethostname() == 'v79sl' and os.geteuid() != 0 and
         Path.home() == Path('/home/firelion'), 'WRONG_SERVER_USER')
    local_docker('v79sl')
    names = call(['docker', 'ps', '--all', '--format', '{{.Names}}']).decode().splitlines()
    rows = jcall(['docker', 'inspect', *names])
    all_rows = {r['Name'].lstrip('/'): r for r in rows}
    need(set(IMAGES) <= set(all_rows), 'REQUIRED_CONTAINER_ABSENT')
    selected = {n: all_rows[n] for n in IMAGES}
    blockers, pins, compose_inputs, mounts = [], {}, {}, []
    image_bytes = 0
    for name, o in selected.items():
        stage('SERVER_CONTAINER_' + name.replace('-', '_').upper())
        healthy = o['State'].get('Running') and o['State'].get('Health', {}).get('Status') == 'healthy'
        need(o['Image'] == IMAGES[name] and healthy, 'PINNED_IMAGE_OR_HEALTH_CHANGED')
        pins[name] = {'id': o['Id'], 'image': o['Image'], 'healthy': True}
        image_bytes += jcall(['docker', 'image', 'inspect', o['Image']])[0]['Size']
        labels = o['Config'].get('Labels') or {}
        paths = labels.get('com.docker.compose.project.config_files', '').split(',')
        need(all(p.startswith('/') for p in paths), 'COMPOSE_CHAIN_UNAVAILABLE')
        for text in paths:
            p = Path(text)
            s = p.lstat()
            need(stat.S_ISREG(s.st_mode) and s.st_size <= 2*1024**2 and
                 s.st_uid in (0, os.getuid()) and not s.st_mode & 0o002, 'COMPOSE_INPUT_UNSAFE')
            compose_inputs[text] = hashlib.sha256(p.read_bytes()).hexdigest()
        if name in APPS:
            for m in o.get('Mounts', []):
                need(m['Type'] in ('bind', 'volume') and m.get('Source', '').startswith('/'), 'MOUNT_TYPE_UNREVIEWED')
                source = m['Source']
                shared = []
                for other, foreign in all_rows.items():
                    if other in APPS or not foreign['State'].get('Running'):
                        continue
                    for fm in foreign.get('Mounts', []):
                        if fm.get('RW') and fm.get('Source') and overlap(source, fm['Source']):
                            shared.append(other)
                if shared:
                    blockers.append('SHARED_WRITER_' + name)
                mounts.append({'container': name, 'destination': m['Destination'],
                               'type': m['Type'], 'rw': m['RW'], 'other_writer_count': len(set(shared))})
    h, t = values(selected['v79-hub']), values(selected['v79-tiquet-manager'])
    stage('SERVER_SECURITY_AND_PRICE_INPUTS')
    need(h.get('V79_REQUIRE_ADMIN_MFA') == '1' and
         h.get('V79_HUB_TIQUET_SESSION_BINDING') == '1' and
         t.get('V79_TIQUET_SESSION_BINDING_ENABLED') == '1' and
         t.get('V79_ALLOW_LEGACY_AUTH') == '0' and
         t.get('V79_ENTITLEMENT_RECHECK_ENABLED') == '1', 'SECURITY_FLAGS_CHANGED')
    need(h.get('V79_TIQUET_LAUNCH_SECRET') and
         h['V79_TIQUET_LAUNCH_SECRET'] == t.get('V79_TIQUET_LAUNCH_SECRET'), 'SSO_SECRET_MISMATCH')
    price_inputs_present = all(t.get('PLAN_PRICE_' + x) for x in ('STARTER','PRO','ENTERPRISE'))
    if not price_inputs_present:
        blockers.append('FROZEN_PRICE_INPUT_ABSENT')
    db_versions = {}
    for db, major in [('v79-hub-postgres', '17'), ('tiquet-postgres', '16')]:
        stage('SERVER_DATABASE_' + major)
        version = call(['docker','exec',db,'pg_dump','--version']).decode()
        need(re.search(r'PostgreSQL\) '+major+r'\.', version), 'PG_DUMP_VERSION_CHANGED')
        call(['docker','exec',db,'sh','-c',
              'pg_isready -q -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}"'])
        db_versions[db] = {'major': major, 'ready': True}
    timers = []
    stage('SERVER_TIMERS_AND_HOST_STATE')
    listing = call(['systemctl','--user','list-units','--type=timer','--state=active','--no-legend','--plain']).decode()
    for line in listing.splitlines():
        unit = line.split()[0]
        if re.fullmatch(r'v79[-A-Za-z0-9@_.]+\.timer', unit) and re.search(r'workforce|release|task', unit):
            timers.append(unit)
    host_state = {p: private_metadata(Path.home()/p) for p in HOST_STATE}
    for p, meta in host_state.items():
        if not meta.get('present') or not meta.get('directory') or not meta.get('owned'):
            blockers.append('HOST_STATE_UNSAFE_' + p.rsplit('/',1)[-1])
    google = {n: private_metadata(Path.home()/HOST_STATE[0]/n) for n in ('client.json','credentials.json')}
    if not all(m.get('regular') and m.get('owned') and m.get('private') for m in google.values()):
        blockers.append('GOOGLE_CREDENTIAL_FILE_UNSAFE')
    # Inspect metadata only; do not read credentials or queue payloads.
    workforce_units = []
    unit_root = Path.home()/'.config/systemd/user'
    if unit_root.is_dir():
        workforce_units = sorted(p.name for p in unit_root.iterdir()
                                if p.is_file() and re.fullmatch(r'v79[-A-Za-z0-9@_.]+\.(service|timer)',p.name)
                                and re.search(r'workforce|release|task',p.name))
    lock = Path.home()/'.v79-portfolio-rollout.lock'
    if lock.exists():
        need(not lock.is_symlink() and lock.is_file(), 'OPERATION_LOCK_UNSAFE')
        with lock.open('rb') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
            except BlockingIOError:
                blockers.append('OTHER_RELEASE_OPERATION_RUNNING')
    for n in selected:
        current = jcall(['docker','inspect',n])[0]
        need(current['Id'] == selected[n]['Id'] and current['Image'] == selected[n]['Image'], 'RUNTIME_CHANGED_DURING_PREFLIGHT')
    result = {'mode': 'READ_ONLY_CHECKPOINT_READINESS', 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'pins': pins, 'compose_input_hashes': compose_inputs, 'app_mounts': mounts,
              'image_bytes': image_bytes, 'server_free_bytes': shutil.disk_usage(Path.home()).free,
              'server_available_memory_bytes': memory_available(), 'databases': db_versions,
              'active_timers_to_quiesce': sorted(timers), 'workforce_unit_files': workforce_units,
              'host_state_metadata': host_state, 'google_file_metadata': google,
              'frozen_price_inputs_available_not_printed': bool(price_inputs_present),
              'google_contents_read': False, 'production_changed': False,
              'blockers': sorted(set(blockers)), 'capture_performed': False, 'restore_performed': False}
    validate_final_scope(result,selected)
    result['inventory_sha256'] = hashlib.sha256(json.dumps(
        {'pins': pins, 'inputs': compose_inputs, 'timers': sorted(timers), 'mounts': mounts, 'final_scope':result['final_recovery_scope']},
        sort_keys=True).encode()).hexdigest()
    return result

def acer():
    stage('ACER_IDENTITY_AND_DOCKER')
    need(socket.gethostname() == 'firelion-Aspire-A315-51' and os.geteuid() != 0, 'RUN_ON_NONROOT_ACER')
    local_docker(socket.gethostname())
    stage('ACER_RECOVERY_KEY_METADATA')
    fingerprints = call(['gpg','--batch','--with-colons','--fingerprint',RECIPIENT]).decode()
    need('fpr:::::::::'+RECIPIENT+':' in fingerprints, 'RECOVERY_PUBLIC_KEY_UNAVAILABLE')
    keys = call(['gpg','--batch','--with-colons','--list-secret-keys',RECIPIENT]).decode()
    need(any(line.startswith('sec:') or line.startswith('sec#:') for line in keys.splitlines()), 'RECOVERY_PRIVATE_KEY_UNAVAILABLE')
    print('ACER_RECOVERY_KEY=PINNED_PUBLIC_AND_PRIVATE_PRESENT', flush=True)
    print('ACER_FREE_BYTES='+str(shutil.disk_usage(Path.home()).free), flush=True)
    print('ACER_AVAILABLE_MEMORY_BYTES='+str(memory_available()), flush=True)
    command = ['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
               '-o','ConnectTimeout=10','firelion@v79sl','python3 -B - --server']
    stage('SERVER_READ_ONLY_INVENTORY')
    try:
        process = subprocess.run(command, input=Path(__file__).read_bytes(),
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise Halt('SSH_READ_UNAVAILABLE') from None
    raw = process.stdout
    if process.returncode:
        try:
            error = json.loads(raw)
            for key in ('error_stage', 'error'):
                if re.fullmatch(r'[A-Z0-9_]+', str(error.get(key, ''))):
                    print('SERVER_' + key.upper() + '=' + error[key], flush=True)
        except (ValueError, TypeError):
            pass
        raise Halt('SERVER_READINESS_FAILED')
    report = json.loads(raw)
    need(report.get('mode') == 'READ_ONLY_CHECKPOINT_READINESS', 'REMOTE_REPORT_INVALID')
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    minimum = max(20*1024**3, 2*report['image_bytes']+10*1024**3)
    enough = shutil.disk_usage(Path.home()).free >= minimum and report['server_free_bytes'] >= minimum
    print('CHECKPOINT_DISK_HEADROOM='+('PASS' if enough else 'INSUFFICIENT'), flush=True)
    print('NEXT=PIN_FINAL_ENCRYPTED_CAPTURE_AND_ISOLATED_RESTORE', flush=True)
    print('CAPTURE_AND_RESTORE=NOT_RUN', flush=True)

def self_test():
    assert overlap('/a/b','/a/b/c') and not overlap('/a/b','/a/bc')
    assert len(IMAGES) == 5 and len(APPS) == 3
    assert all(re.fullmatch(r'sha256:[a-f0-9]{64}', x) for x in IMAGES.values())
    assert len(RECIPIENT) == 40
    assert not private_metadata(Path('/nonexistent-v79-test-path')).get('present')
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'test'; p.write_text('fixture'); p.chmod(0o600)
        assert private_metadata(p)['regular'] and private_metadata(p)['private']
        p.chmod(0o644); assert not private_metadata(p)['private']
        link=Path(tmp)/'link'; link.symlink_to(p); assert not private_metadata(link)['regular']
    print('SELF_TEST=PASS_SCOPE_PINS_OVERLAP_AND_PRIVATE_METADATA')


if __name__ == '__main__':
    try:
        report=server()
        print('DEMO_READINESS=PASS' if not report['blockers'] else 'DEMO_READINESS=BLOCKED')
        print('NEW_INVENTORY_SHA256='+report['inventory_sha256'])
        print('AVAILABLE_MEMORY_BYTES='+str(report['server_available_memory_bytes']))
        print('SERVER_FREE_BYTES='+str(report['server_free_bytes']))
        print('BACKUP_IMAGE_BYTES='+str(report['image_bytes']))
        print('ENCRYPTED_ARTIFACT_COUNT='+str(report['expected_encrypted_artifacts']))
        print('WORKFORCE_TIMERS='+','.join(report['active_timers_to_quiesce']))
        print('READINESS_BLOCKER_CODES='+','.join(report['blockers']))
        print('DEMO_READINESS_CHANGES=NONE')
    except (Halt,OSError,ValueError,KeyError,TypeError) as error:
        reason=str(error) if isinstance(error,Halt) and re.fullmatch(r'[A-Z0-9_]+',str(error)) else 'READINESS_METADATA_UNAVAILABLE'
        print('FAILED_STAGE='+STAGE)
        print('STOP='+reason)
        sys.exit(2)
