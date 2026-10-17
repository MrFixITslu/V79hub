#!/usr/bin/env python3
"""Cached Tiquet startup diagnosis. Synthetic resources only; never deploys apps."""
import argparse
import fcntl
import json
import tempfile
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

RUN = Path('/home/firelion/v79-portfolio-rollout.W8DQrYJI')
LABEL = 'v79.synthetic-startup-diagnostic'
IMAGE = re.compile(r'sha256:[a-f0-9]{64}\Z')
RULES = {
    'FILESYSTEM_PERMISSION': r'\b(?:EACCES|EPERM)\b|permission denied',
    'MISSING_MODULE': r'ERR_MODULE_NOT_FOUND|MODULE_NOT_FOUND|Cannot find package',
    'DATABASE_AUTH': r'28P01|password authentication failed',
    'DATABASE_CONNECT': r'ECONNREFUSED|ENOTFOUND|ETIMEDOUT',
    'SCHEMA_COLUMN': r'42703|column .{0,120} does not exist',
    'SCHEMA_RELATION': r'42P01|relation .{0,120} does not exist',
    'SCHEMA_FOREIGN_KEY': r'42830|no unique constraint matching',
    'SCHEMA_PERMISSION': r'42501|must be owner of',
    'SCHEMA_SYNTAX': r'42601|syntax error at',
    'NATIVE_MODULE': r'ERR_DLOPEN_FAILED|NODE_MODULE_VERSION|invalid ELF',
    'ADDRESS_IN_USE': r'EADDRINUSE',
    'MISSING_NAMED_EXPORT': r'does not provide an export named',
    'UNDEFINED_REFERENCE': r'ReferenceError|is not defined',
}

class Stop(Exception):
    pass

def need(value, code):
    if not value:
        raise Stop(code)

def run(args, *, timeout=45, check=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOCKER_', 'COMPOSE_'))}
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, env=env)
    if check:
        need(p.returncode == 0, 'COMMAND_FAILED_REDACTED')
    return p

def inspect(name, image=False, optional=False):
    result = run(['docker', 'image' if image else 'container', 'inspect', name], check=not optional)
    if result.returncode == 0:
        rows = json.loads(result.stdout)
        need(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict), 'INSPECT_SHAPE_INVALID')
        return rows[0]
    # A daemon/query error must never be treated as proven resource absence.
    need(optional and not image, 'IMAGE_INSPECT_FAILED')
    remaining = run(['docker', 'container', 'ls', '--all', '--quiet', '--filter', 'name=^/'+name+'$'])
    need(not remaining.stdout.strip(), 'CONTAINER_INSPECT_FAILED_NOT_ABSENCE')
    return None

def classify(text):
    categories = sorted(k for k, pattern in RULES.items() if re.search(pattern, text, re.I))
    codes = sorted(set(re.findall(r"\b(?:EACCES|EPERM|ECONNREFUSED|ENOTFOUND|ETIMEDOUT|EADDRINUSE|ERR_MODULE_NOT_FOUND|ERR_DLOPEN_FAILED|28P01|42703|42P01|42830|42501|42601)\b", text)))
    locations = sorted(set(re.findall(r'\bserver/[A-Za-z0-9_-]+\.js:\d+(?::\d+)?', text)))[:12]
    return {'categories': categories or ['UNCLASSIFIED'], 'error_codes': codes, 'source_locations': locations}

def safe_health_command(test):
    # Never execute arbitrary copied shell code, headers, credentials or URLs.
    if not isinstance(test, list) or len(test) != 4 or test[:3] != ['CMD', 'wget', '-qO-']:
        return None
    try:
        url = urlparse(test[3])
        if (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost', '::1')
            and not url.username and not url.password and not url.query and not url.fragment
            and url.path in ('/health', '/api/health', '/health/ready')):
            return test[1:]
    except ValueError:
        pass
    return None

def http_status(app, port):
    code = "fetch('http://127.0.0.1:%d/health',{signal:AbortSignal.timeout(2500)}).then(r=>console.log(r.status)).catch(()=>console.log(0))" % port
    p = run(['docker', 'exec', app, 'node', '-e', code], check=False, timeout=8)
    raw = p.stdout.decode().strip()
    return int(raw) if re.fullmatch(r'[0-9]{1,3}', raw) else 0

def report(name):
    row = inspect(name)
    state = row['State']
    # stdout and stderr of docker logs both contain application messages.
    # Fetch combined logs without ever forwarding them to the terminal.
    proc = subprocess.run(['docker', 'logs', '--tail', '100', name], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=20)
    info = classify(proc.stdout.decode('utf8', 'replace'))
    status = state.get('Status', '')
    info.update(state=status if status in ('running', 'exited', 'created', 'restarting', 'dead') else 'UNKNOWN',
                exit_code=state.get('ExitCode'), oom_killed=bool(state.get('OOMKilled')),
                captured_output_bytes=len(proc.stdout))
    return info

def owned_cleanup(names, network, identity):
    for name in reversed(names):
        row = inspect(name, optional=True)
        if row is None:
            continue
        need((row.get('Config', {}).get('Labels') or {}).get(LABEL) == identity, 'REFUSE_CLEANUP_FOREIGN_CONTAINER')
        run(['docker', 'rm', '-f', '-v', name])
        need(inspect(name, optional=True) is None, 'SYNTHETIC_CONTAINER_CLEANUP_FAILED')
    p = run(['docker', 'network', 'inspect', network], check=False)
    if p.returncode != 0:
        remaining = run(['docker', 'network', 'ls', '--quiet', '--filter', 'name=^'+network+'$'])
        need(not remaining.stdout.strip(), 'NETWORK_INSPECT_FAILED_NOT_ABSENCE')
    if p.returncode == 0:
        row = json.loads(p.stdout)[0]
        need((row.get('Labels') or {}).get(LABEL) == identity, 'REFUSE_CLEANUP_FOREIGN_NETWORK')
        run(['docker', 'network', 'rm', network])
        remaining = run(['docker', 'network', 'ls', '--quiet', '--filter', 'name=^'+network+'$'])
        need(not remaining.stdout.strip(), 'SYNTHETIC_NETWORK_CLEANUP_FAILED')

def reap_previous():
    rows = run(['docker', 'container', 'ls', '--all', '--quiet', '--filter', 'label='+LABEL]).stdout.decode().split()
    groups = {}
    for container in rows:
        row = inspect(container)
        identity = (row.get('Config', {}).get('Labels') or {}).get(LABEL, '')
        need(re.fullmatch(r'[a-f0-9]{12}', identity), 'PREVIOUS_IDENTITY_INVALID')
        network = 'v79-tqdiag-' + identity
        name = row.get('Name', '').lstrip('/')
        need(name in [network+'-'+suffix for suffix in ('pg', 'metadata', 'app')], 'PREVIOUS_NAME_INVALID')
        validate_synthetic(row, identity, network)
        groups.setdefault(identity, []).append(name)
    networks = run(['docker', 'network', 'ls', '--quiet', '--filter', 'label='+LABEL]).stdout.decode().split()
    verified_networks = set()
    for network_id in networks:
        row = json.loads(run(['docker', 'network', 'inspect', network_id]).stdout)[0]
        identity = (row.get('Labels') or {}).get(LABEL, '')
        need(re.fullmatch(r'[a-f0-9]{12}', identity) and row.get('Name') == 'v79-tqdiag-'+identity
             and row.get('Internal') is True, 'PREVIOUS_NETWORK_INVALID')
        verified_networks.add(identity)
        owned_names = set(groups.get(identity, []))
        need(all(v.get('Name') in owned_names for v in (row.get('Containers') or {}).values()), 'PREVIOUS_NETWORK_FOREIGN_ENDPOINT')
        groups.setdefault(identity, [])
    need(set(groups) <= verified_networks, 'PREVIOUS_NETWORK_OWNERSHIP_UNPROVEN')
    for identity, names in groups.items():
        owned_cleanup(names, 'v79-tqdiag-'+identity, identity)
    for kind in ('container', 'network'):
        query = ['docker', kind, 'ls', '--quiet', '--filter', 'label='+LABEL]
        if kind == 'container':
            query.insert(3, '--all')
        need(not run(query).stdout.strip(), 'PREVIOUS_CLEANUP_INCOMPLETE')
    print('PREVIOUS_SYNTHETIC_RESOURCE_CLEANUP=PASS', flush=True)


def validate_synthetic(row, identity, network):
    need(row['Config']['Labels'].get(LABEL) == identity, 'SYNTHETIC_IDENTITY_INVALID')
    need(not row['HostConfig'].get('PortBindings'), 'SYNTHETIC_PUBLISHED_PORTS')
    need(set(row['NetworkSettings']['Networks']) == {network}, 'SYNTHETIC_NETWORK_INVALID')
    need(all(m['Type'] == 'tmpfs' for m in row['Mounts']), 'SYNTHETIC_UNEXPECTED_PERSISTENT_MOUNT')

REVISION = '7da53ebb71530366168bd72a7efd52b57d34a23c'
MODE_REPAIR_JS = r"""
const fs=require('fs'),crypto=require('crypto');
const rows=JSON.parse(fs.readFileSync('/tmp/v79-public-modes.json','utf8'));
const dirs=new Set(['/app']); const snapshots=[];
for(const r of rows){
 if(!/^(package(?:-lock)?\.json|(?:server|scripts)\/[A-Za-z0-9_./-]+)$/.test(r.path)||r.path.split('/').some(x=>x==='..'||x==='.')||![420,493].includes(r.mode))throw Error('MANIFEST_INVALID');
 const p='/app/'+r.path; const st=fs.lstatSync(p);if(!st.isFile())throw Error('NOT_REGULAR');
 for(let dir=require('path').dirname(p);dir!=='/';dir=require('path').dirname(dir)){
  if(!fs.lstatSync(dir).isDirectory())throw Error('PARENT_NOT_DIRECTORY');dirs.add(dir);
 }
 const data=fs.readFileSync(p);const sha=crypto.createHash('sha1').update(Buffer.from('blob '+data.length+'\0')).update(data).digest('hex');
 if(r.path!=='package-lock.json'&&sha!==r.blob)throw Error('PUBLIC_BYTES_DIFFER_FROM_GIT');
 snapshots.push([p,crypto.createHash('sha256').update(data).digest('hex'),r.mode]);
}
for(const dir of dirs)fs.chmodSync(dir,493);
for(const [p,hash,mode]of snapshots){fs.chmodSync(p,mode);if(crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')!==hash)throw Error('BYTES_CHANGED');}
fs.unlinkSync('/tmp/v79-public-modes.json');fs.unlinkSync('/tmp/v79-public-mode-repair.js');
"""

def public_mode_inventory(stage):
    need(run(['git', '-C', str(stage), 'rev-parse', 'HEAD']).stdout.decode().strip() == REVISION, 'PUBLIC_SOURCE_REVISION_CHANGED')
    raw = run(['git', '-C', str(stage), 'ls-tree', '-r', '-z', REVISION, '--', 'package.json', 'package-lock.json', 'server', 'scripts']).stdout
    rows = []
    for record in filter(None, raw.split(b'\0')):
        metadata, path = record.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        path = path.decode('ascii')
        need(kind == 'blob' and mode in ('100644', '100755') and
             re.fullmatch(r'(?:package(?:-lock)?\.json|(?:server|scripts)/[A-Za-z0-9_./-]+)', path)
             and all(part not in ('.', '..') for part in path.split('/')), 'PUBLIC_MODE_INVENTORY_INVALID')
        rows.append({'path': path, 'mode': 0o755 if mode == '100755' else 0o644, 'blob': blob})
    need({'package.json', 'package-lock.json', 'server/index.js'} <= {r['path'] for r in rows}, 'PUBLIC_MODE_INVENTORY_INCOMPLETE')
    return rows

def repair_public_modes(candidate, metadata):
    paths = metadata.get('paths', {})
    need(any(paths.get(p, {}).get('readable') is False for p in ('/app/package.json', '/app/server')), 'PUBLIC_PERMISSION_CAUSE_NOT_PROVEN')
    tag = 'v79-portfolio/v79tiquet:' + REVISION
    base = inspect(tag, image=True)
    need(base['Id'] == candidate, 'CACHED_BASE_TAG_CHANGED')
    user = base['Config'].get('User', '')
    need(re.fullmatch(r'[A-Za-z0-9_:-]{1,80}', user) and user not in ('root', '0', '0:0'), 'REPAIR_USER_INVALID')
    inventory = public_mode_inventory(RUN/'V79Tiquet')
    repaired_tag = tag + '-public-modes-v1'
    with tempfile.TemporaryDirectory(prefix='v79-public-mode-repair.') as tmp:
        root = Path(tmp)
        (root/'manifest.json').write_text(json.dumps(inventory))
        (root/'repair.js').write_text(MODE_REPAIR_JS)
        (root/'Dockerfile').write_text('FROM '+tag+'\nUSER root\nCOPY manifest.json /tmp/v79-public-modes.json\nCOPY repair.js /tmp/v79-public-mode-repair.js\nRUN node /tmp/v79-public-mode-repair.js\nUSER '+user+'\nLABEL v79.public-source-modes="git-v1" v79.mode-repair.base="'+candidate+'"\n')
        print('PHASE=REPAIR_PUBLIC_CODE_PERMISSIONS_ONLY', flush=True)
        run(['docker', 'build', '--pull=false', '--network=none', '--tag', repaired_tag, str(root)], timeout=240)
    repaired = inspect(repaired_tag, image=True)
    need(IMAGE.fullmatch(repaired['Id']), 'REPAIRED_IMAGE_ID_INVALID')
    # Image build provenance fields may change; every execution setting must match.
    old = dict(base['Config']); new = dict(repaired['Config'])
    old.pop('Image', None); new.pop('Image', None)
    old['Labels'] = dict(old.get('Labels') or {})
    labels = dict(new.get('Labels') or {})
    need(labels.pop('v79.public-source-modes', None) == 'git-v1' and
         labels.pop('v79.mode-repair.base', None) == candidate, 'REPAIR_LABELS_INVALID')
    new['Labels'] = labels
    if old != new:
        print(json.dumps({'repair_runtime_changed_fields': sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))}), flush=True)
    need(old == new, 'REPAIRED_RUNTIME_CONFIGURATION_CHANGED')
    print('PUBLIC_CODE_PERMISSION_REPAIR=IDENTICAL_BYTES_RUNTIME_CONFIG_PRESERVED', flush=True)
    print('REPAIRED_CANDIDATE_IMAGE='+repaired['Id'], flush=True)
    return repaired['Id']


def diagnostic_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--repair-public-modes', action='store_true', help='Derive a cached image with verified public source permissions, then synthetic startup only')
    parser.add_argument('--permissions-only', action='store_true', help='Clean prior diagnostic resources and read cached image permissions; no app startup')
    args = parser.parse_args()
    if args.self_test:
        result = classify("password=PRIVATE_MARKER code: '42703' column PRIVATE_MARKER does not exist server/db.js:219:2")
        need('PRIVATE_MARKER' not in json.dumps(result) and 'SCHEMA_COLUMN' in result['categories'], 'REDACTION_TEST_FAILED')
        print('TIQUET_DIAGNOSTIC_SELF_TEST=PASS')
        return
    need(socket.gethostname() == 'v79sl' and os.getuid() != 0, 'RUN_ON_V79SL_NON_ROOT')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Stop('TERMINATED')))
    signal.signal(signal.SIGHUP, lambda *_: (_ for _ in ()).throw(Stop('DISCONNECTED')))
    memory = {x.split(':')[0]: int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines()}
    need(memory['MemAvailable'] >= 1024*1024, 'SYNTHETIC_TEST_MEMORY_INSUFFICIENT')
    manifest = json.loads((RUN/'checkpoint/manifest.json').read_text())
    candidate = manifest['candidates']['v79-tiquet-manager']
    need(IMAGE.fullmatch(candidate), 'CANDIDATE_ID_INVALID')
    image = inspect(candidate, image=True)
    need(image['Config'].get('Labels', {}).get('org.opencontainers.image.revision') == '7da53ebb71530366168bd72a7efd52b57d34a23c', 'CANDIDATE_REVISION_CHANGED')
    need(not image['Config'].get('Volumes'), 'CANDIDATE_AUTO_VOLUMES_UNREVIEWED')
    names = ('v79-hub', 'v79-tiquet-manager', 'v79-hub-postgres', 'tiquet-postgres', 'v79-business-agent')
    before = {n: inspect(n) for n in names}
    need(all(v['State'].get('Health', {}).get('Status') == 'healthy' for v in before.values()), 'LIVE_SERVICES_NOT_HEALTHY')
    pg_image = before['tiquet-postgres']['Image']
    need(pg_image == 'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685', 'POSTGRES_IMAGE_CHANGED')
    original_config = before['v79-tiquet-manager']['Config']
    original_env = dict(x.split('=', 1) for x in original_config.get('Env', []) if '=' in x)
    raw_port = original_env.get('PORT', '3050')
    need(re.fullmatch(r'[0-9]{1,5}', raw_port) and 1024 <= int(raw_port) <= 65535, 'LIVE_PORT_UNREVIEWED')
    port = int(raw_port)
    frozen_probe = safe_health_command(original_config.get('Healthcheck', {}).get('Test'))
    user = original_config.get('User', '')
    need(re.fullmatch(r'[A-Za-z0-9_:-]{1,80}', user), 'LIVE_EXECUTION_USER_UNREVIEWED')
    need(all(before[n]['Image'] == value for n, value in manifest['source_images'].items()), 'ORIGINAL_APP_IMAGES_NOT_RESTORED')
    reap_previous()
    print('PHASE=SYNTHETIC_CACHED_IMAGE_STARTUP_ONLY', flush=True)
    identity = secrets.token_hex(6)
    network = 'v79-tqdiag-' + identity
    pg = network + '-pg'
    app = network + '-app'
    owned = []
    try:
        run(['docker', 'network', 'create', '--internal', '--label', LABEL+'='+identity, network])
        net = json.loads(run(['docker', 'network', 'inspect', network]).stdout)[0]
        need(net.get('Internal') is True, 'NETWORK_NOT_INTERNAL')
        if not args.permissions_only:
            password = secrets.token_urlsafe(32)
            owned.append(pg)
            run(['docker', 'create', '--name', pg, '--label', LABEL+'='+identity, '--pull', 'never',
                 '--network', network, '--memory', '384m', '--memory-swap', '384m',
                 '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev,noexec,size=160m',
                 '-e', 'POSTGRES_DB=synthetic', '-e', 'POSTGRES_USER=synthetic', '-e', 'POSTGRES_PASSWORD='+password, pg_image])
            validate_synthetic(inspect(pg), identity, network)
            run(['docker', 'start', pg])
            ready = False
            for _ in range(30):
                if run(['docker', 'exec', pg, 'pg_isready', '-U', 'synthetic', '-d', 'synthetic'], check=False).returncode == 0:
                    ready = True; break
                time.sleep(1)
            if not ready:
                print(json.dumps({'synthetic_postgres': report(pg)}, sort_keys=True), flush=True)
            need(ready, 'SYNTHETIC_POSTGRES_NOT_READY')
        metadata_code = "const fs=require('fs');console.log(JSON.stringify({uid:process.getuid(),gid:process.getgid(),paths:Object.fromEntries(['/app/package.json','/app/server','/app/server/index.js','/app/data','/app/uploads','/app/logs'].map(p=>{try{const s=fs.statSync(p);let readable=true;try{fs.accessSync(p,fs.constants.R_OK)}catch{readable=false}return[p,{uid:s.uid,gid:s.gid,mode:s.mode&511,readable}]}catch{return[p,{missing:true}]}}))}))"
        current_metadata = json.loads(run(['docker', 'exec', 'v79-tiquet-manager', 'node', '-e', metadata_code]).stdout)
        meta = network + '-metadata'
        owned.append(meta)
        run(['docker', 'create', '--name', meta, '--label', LABEL+'='+identity, '--pull', 'never',
             '--network', network, '--read-only', '--user', user, '--entrypoint', 'node',
             '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--memory', '64m',
             '--memory-swap', '64m', '--pids-limit', '32', candidate, '-e', metadata_code])
        validate_synthetic(inspect(meta), identity, network)
        candidate_metadata = json.loads(run(['docker', 'start', '--attach', meta]).stdout)
        print(json.dumps({'execution_metadata': {'original': current_metadata, 'candidate': candidate_metadata}}, sort_keys=True), flush=True)
        if args.repair_public_modes:
            candidate = repair_public_modes(candidate, candidate_metadata)
        if args.permissions_only:
            print('TIQUET_PERMISSION_INVENTORY=COMPLETE', flush=True)
            return
        env = {'NODE_ENV': 'production', 'PORT': str(port), 'DB_HOST': pg, 'DB_PORT': '5432',
               'DB_NAME': 'synthetic', 'DB_USER': 'synthetic', 'DB_PASSWORD': password,
               'JWT_SECRET': secrets.token_urlsafe(48), 'SUPER_ADMIN_JWT_SECRET': secrets.token_urlsafe(48),
               'V79_TIQUET_LAUNCH_SECRET': secrets.token_urlsafe(48), 'V79_ENTITLEMENT_RECHECK_ENABLED': '1',
               'V79_ALLOW_LEGACY_AUTH': '0', 'V79_HUB_INTERNAL_URL': 'http://127.0.0.1:9',
               'V79_HUB_EVENT_URL': 'http://127.0.0.1:9', 'APP_BASE_URL': 'http://127.0.0.1:3050'}
        args = ['docker', 'create', '--name', app, '--label', LABEL+'='+identity, '--pull', 'never',
                '--network', network, '--user', user, '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                '--memory', '512m', '--memory-swap', '512m', '--pids-limit', '96',
                '--tmpfs', '/app/data:rw,nosuid,nodev,noexec,mode=1777,size=32m',
                '--tmpfs', '/app/uploads:rw,nosuid,nodev,noexec,mode=1777,size=32m']
        for key, value in env.items():
            args += ['-e', key+'='+value]
        owned.append(app)
        run([*args, candidate])
        validate_synthetic(inspect(app), identity, network)
        run(['docker', 'start', app])
        status = 0
        for _ in range(25):
            state = inspect(app)['State']
            if not state.get('Running'):
                break
            status = http_status(app, port)
            if status == 200:
                break
            time.sleep(2)
        result = report(app)
        result['synthetic_health_http'] = status
        result['live_port'] = port
        result['frozen_health_probe_supported'] = frozen_probe is not None
        probe_exit = run(['docker', 'exec', app, *frozen_probe], check=False, timeout=12).returncode if frozen_probe else None
        result['frozen_health_probe_exit_code'] = probe_exit
        if status != 200 and inspect(app)['State'].get('Running'):
            result['alternate_loopback_health_http'] = {str(p): http_status(app, p) for p in (3000, 3050) if p != port}
        result['same_execution_user_spec'] = inspect(app)['Config'].get('User') == user
        print(json.dumps(result, sort_keys=True), flush=True)
        passed = status == 200 and probe_exit in (0, None)
        print('TIQUET_SYNTHETIC_STARTUP=' + ('PASS' if passed else 'FAIL'), flush=True)
        need(passed, 'SYNTHETIC_CANDIDATE_STARTUP_FAILED')
    finally:
        print('PHASE=SYNTHETIC_CLEANUP', flush=True)
        owned_cleanup(owned, network, identity)
        print('SYNTHETIC_RESOURCE_CLEANUP=PASS', flush=True)
        for name, old in before.items():
            now = inspect(name)
            need(now['Id'] == old['Id'] and now['Image'] == old['Image']
                 and now['State'].get('Health', {}).get('Status') == 'healthy', 'LIVE_CONTAINER_CHANGED')
        print('LIVE_FIVE_ORIGINAL_CONTAINERS=UNCHANGED_HEALTHY', flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO', flush=True)

def main():
    if '--self-test' in sys.argv:
        return diagnostic_main()
    need(socket.gethostname() == 'v79sl' and os.getuid() != 0, 'RUN_ON_V79SL_NON_ROOT')
    os.umask(0o077)
    with (Path.home()/'.v79-portfolio-rollout.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('OTHER_ROLLOUT_OR_DIAGNOSTIC_RUNNING')
        return diagnostic_main()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if not isinstance(error, Stop):
            frames = []
            trace = error.__traceback__
            while trace:
                if trace.tb_frame.f_code.co_filename == __file__:
                    frames.append(trace.tb_lineno)
                trace = trace.tb_next
            print(json.dumps({'diagnostic_exception_type': type(error).__name__, 'diagnostic_source_lines': frames}))
        print('STOP=' + (str(error) if isinstance(error, Stop) else 'DIAGNOSTIC_ERROR_REDACTED'))
        sys.exit(1)
