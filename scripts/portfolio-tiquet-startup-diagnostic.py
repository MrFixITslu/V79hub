#!/usr/bin/env python3
"""Cached Tiquet startup diagnosis. Synthetic resources only; never deploys apps."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import time

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
    return json.loads(result.stdout)[0] if result.returncode == 0 else None

def classify(text):
    categories = sorted(k for k, pattern in RULES.items() if re.search(pattern, text, re.I))
    codes = sorted(set(re.findall(r"\b(?:EACCES|EPERM|ECONNREFUSED|ENOTFOUND|ETIMEDOUT|EADDRINUSE|ERR_MODULE_NOT_FOUND|ERR_DLOPEN_FAILED|28P01|42703|42P01|42830|42501|42601)\b", text)))
    locations = sorted(set(re.findall(r'\bserver/[A-Za-z0-9_-]+\.js:\d+(?::\d+)?', text)))[:12]
    return {'categories': categories or ['UNCLASSIFIED'], 'error_codes': codes, 'source_locations': locations}

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
        need(row.get('Config', {}).get('Labels', {}).get(LABEL) == identity, 'REFUSE_CLEANUP_FOREIGN_CONTAINER')
        run(['docker', 'rm', '-f', '-v', name])
        need(inspect(name, optional=True) is None, 'SYNTHETIC_CONTAINER_CLEANUP_FAILED')
    p = run(['docker', 'network', 'inspect', network], check=False)
    if p.returncode == 0:
        row = json.loads(p.stdout)[0]
        need(row.get('Labels', {}).get(LABEL) == identity, 'REFUSE_CLEANUP_FOREIGN_NETWORK')
        run(['docker', 'network', 'rm', network])
        need(run(['docker', 'network', 'inspect', network], check=False).returncode != 0, 'SYNTHETIC_NETWORK_CLEANUP_FAILED')

def validate_synthetic(row, identity, network):
    need(row['Config']['Labels'].get(LABEL) == identity, 'SYNTHETIC_IDENTITY_INVALID')
    need(not row['HostConfig'].get('PortBindings'), 'SYNTHETIC_PUBLISHED_PORTS')
    need(set(row['NetworkSettings']['Networks']) == {network}, 'SYNTHETIC_NETWORK_INVALID')
    need(all(m['Type'] == 'tmpfs' for m in row['Mounts']), 'SYNTHETIC_UNEXPECTED_PERSISTENT_MOUNT')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
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
    user = before['v79-tiquet-manager']['Config'].get('User', '')
    need(re.fullmatch(r'[A-Za-z0-9_:-]{1,80}', user), 'LIVE_EXECUTION_USER_UNREVIEWED')
    need(all(before[n]['Image'] == value for n, value in manifest['source_images'].items()), 'ORIGINAL_APP_IMAGES_NOT_RESTORED')
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
        metadata_code = "const fs=require('fs');console.log(JSON.stringify({uid:process.getuid(),gid:process.getgid(),paths:Object.fromEntries(['/app/data','/app/uploads','/app/logs'].map(p=>{try{const s=fs.statSync(p);return[p,{uid:s.uid,gid:s.gid,mode:s.mode&511}]}catch{return[p,{missing:true}]}}))}))"
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
        env = {'NODE_ENV': 'production', 'PORT': '3050', 'DB_HOST': pg, 'DB_PORT': '5432',
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
        probe = "fetch('http://127.0.0.1:3050/health',{signal:AbortSignal.timeout(2500)}).then(r=>console.log(r.status)).catch(()=>console.log(0))"
        for _ in range(25):
            state = inspect(app)['State']
            if not state.get('Running'):
                break
            p = run(['docker', 'exec', app, 'node', '-e', probe], check=False, timeout=8)
            raw = p.stdout.decode().strip()
            status = int(raw) if re.fullmatch(r'[0-9]{1,3}', raw) else 0
            if status == 200:
                break
            time.sleep(2)
        result = report(app)
        result['synthetic_health_http'] = status
        result['same_execution_user_spec'] = inspect(app)['Config'].get('User') == user
        print(json.dumps(result, sort_keys=True), flush=True)
        print('TIQUET_SYNTHETIC_STARTUP=' + ('PASS' if status == 200 else 'FAIL'), flush=True)
        need(status == 200, 'SYNTHETIC_CANDIDATE_STARTUP_FAILED')
    finally:
        owned_cleanup(owned, network, identity)
        print('SYNTHETIC_RESOURCE_CLEANUP=PASS', flush=True)
        for name, old in before.items():
            now = inspect(name)
            need(now['Id'] == old['Id'] and now['Image'] == old['Image']
                 and now['State'].get('Health', {}).get('Status') == 'healthy', 'LIVE_CONTAINER_CHANGED')
        print('LIVE_FIVE_ORIGINAL_CONTAINERS=UNCHANGED_HEALTHY', flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO', flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STOP=' + (str(error) if isinstance(error, Stop) else 'DIAGNOSTIC_ERROR_REDACTED'))
        sys.exit(1)
