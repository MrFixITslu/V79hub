#!/usr/bin/env python3
"""One isolated, networkless website startup; no production mutations."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
import uuid

ROOT = Path('/home/firelion/v79-lead-release-2pvsb2mo')
MANIFEST = '44c0625680f1dfb306aaa49d51f936a08eb76d67ba1e9c2fcddfd9b6be4f368e'
IMAGE = 'sha256:a5ef48c1b1a4dfd29fe33b19f689adae4ca1d1ed344e2bef8b6a16c1684a848c'


def require(ok, code):
    if not ok:
        raise ValueError(code)


def call(args, **kwargs):
    kwargs.setdefault('stdout', subprocess.PIPE)
    kwargs.setdefault('stderr', subprocess.PIPE)
    result = subprocess.run(args, timeout=kwargs.pop('timeout', 30), **kwargs)
    require(result.returncode == 0, 'PROBE_COMMAND_FAILED_REDACTED')
    return result.stdout


def snapshot_archive(data):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        member = tarfile.TarInfo('v79-probe-documents.json')
        member.size = len(data)
        member.uid = member.gid = 1000
        member.mode = 0o600
        archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def inspect(name):
    return json.loads(call(['docker', 'inspect', name]))[0]


def identity(row):
    return {key: row[key] for key in ('Id', 'Image', 'Config', 'HostConfig', 'Mounts')} | {
        'started': row['State']['StartedAt'], 'running': row['State']['Running']}


def signals(log):
    patterns = {
        'legacy_database_rejected': 'Legacy vision79_saas.db detected',
        'permission_denied': r'EACCES|EPERM|permission denied',
        'module_missing': r'MODULE_NOT_FOUND|ERR_MODULE_NOT_FOUND|Cannot find module',
        'database_busy': r'SQLITE_BUSY|database is locked',
        'database_corrupt': r'SQLITE_CORRUPT|database disk image is malformed',
        'database_readonly': r'SQLITE_READONLY|readonly database',
        'key_problem': r'Invalid encryption key|original ENCRYPTION_KEY|Storage key verification failed|Unsupported state or unable to authenticate data',
        'data_shape_problem': r'Invalid data shape|Empty data file|Malformed administrator credential',
        'server_listening': r'V79 Digital website running at',
        'startup_failed': r'\[Startup\] Server failed',
        'probe_snapshot_failed': r'PROBE_SNAPSHOT_FAILED',
    }
    return {key: bool(re.search(pattern, log, re.I)) for key, pattern in patterns.items()}


SNAPSHOT = r"""
const {DatabaseSync}=require('node:sqlite');
const db=new DatabaseSync('/app/data/website.db',{readOnly:true,timeout:5000});
db.exec('BEGIN');
const tables=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all();
if(tables.length!==1||tables[0].name!=='documents')throw Error('UNEXPECTED_SNAPSHOT_SCHEMA');
const rows=db.prepare('SELECT name,value FROM documents ORDER BY name').all();
db.exec('COMMIT');db.close();process.stdout.write(JSON.stringify(rows));
"""

BOOTSTRAP = r"""
const fs=require('fs'),{spawn}=require('child_process'),{DatabaseSync}=require('node:sqlite');
try {
 const rows=JSON.parse(fs.readFileSync('/tmp/v79-probe-documents.json','utf8'));
 for(const suffix of ['', '-wal', '-shm'])fs.rmSync('/app/data/website.db'+suffix,{force:true});
 const db=new DatabaseSync('/app/data/website.db');
 db.exec('CREATE TABLE documents(name TEXT PRIMARY KEY,value TEXT NOT NULL);BEGIN IMMEDIATE');
 const put=db.prepare('INSERT INTO documents(name,value) VALUES(?,?)');
 for(const row of rows)put.run(row.name,row.value);
 db.exec('COMMIT');db.close();fs.unlinkSync('/tmp/v79-probe-documents.json');
 const child=spawn('node',['dist/server/server.cjs'],{stdio:'inherit',cwd:'/app'});
 child.on('error',()=>{console.error('PROBE_CHILD_SPAWN_FAILED');process.exit(98)});
 child.on('exit',(code)=>process.exit(code===null?99:code));
 process.on('SIGTERM',()=>child.kill('SIGTERM'));
} catch(e) {console.error('PROBE_SNAPSHOT_FAILED',e);process.exit(97)}
"""


def main(*, image_override=None):
    os.umask(0o077)
    require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.stat().st_uid == os.geteuid()
            and ROOT.stat().st_mode & 0o077 == 0, 'PRIVATE_RELEASE_DIRECTORY_REQUIRED')
    lock = os.open(ROOT / 'binding.lock', os.O_RDWR | os.O_NOFOLLOW)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    data = (ROOT / 'transaction.json').read_bytes()
    require(hashlib.sha256(data).hexdigest() == MANIFEST, 'SEALED_PLAN_CHANGED')
    plan = json.loads(data)
    state = json.loads((ROOT / 'lead-release-state.json').read_text())
    require(state.get('phase') == 'ROLLED_BACK', 'ORIGINALS_MUST_BE_RESTORED')
    entry = plan['apps']['V79website']
    selected_image = image_override or IMAGE
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', selected_image), 'INVALID_PROBE_IMAGE')
    data = Path(entry['candidate_file']).read_bytes()
    require(hashlib.sha256(data).hexdigest() == entry['candidate_sha256'], 'SEALED_MODEL_CHANGED')
    service = json.loads(data)['services'][entry['service']]
    require(entry['candidate_image']['Id'] == IMAGE, 'CANDIDATE_CHANGED')
    require(service.get('command') is None and service.get('entrypoint') is None
            and service.get('working_dir') is None and service.get('user') is None,
            'STARTUP_OVERRIDE_NOT_REVIEWED')
    image = json.loads(call(['docker', 'image', 'inspect', selected_image]))[0]
    require(image['Config'].get('Cmd') == ['node', 'dist/server/server.cjs']
            and image['Config'].get('User') == 'node'
            and image['Config'].get('WorkingDir') == '/app'
            and image['Config'].get('Entrypoint') == ['docker-entrypoint.sh']
            and not image['Config'].get('Volumes'), 'IMAGE_STARTUP_CHANGED')
    originals = {name: inspect(name) for name in plan['apps']}
    for name, row in originals.items():
        require(row['Image'] == plan['apps'][name]['rollback_image']['Id']
                and row['State']['Running']
                and row['State'].get('Health', {}).get('Status') == 'healthy',
                'ORIGINAL_APP_NOT_HEALTHY')
    work = ROOT / ('website-startup-probe-' + uuid.uuid4().hex[:16])
    work.mkdir(mode=0o700)
    archive = work / 'data.tar'
    snapshot = work / 'documents.json'
    envfile = work / 'environment'
    cid = None
    result = None
    try:
        env = service['environment']
        require(all(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', k)
                    and v is not None and '\n' not in str(v) and '\r' not in str(v)
                    for k, v in env.items()), 'ENVFILE_VALUE_NOT_REPRESENTABLE')
        envfile.write_text(''.join(k + '=' + str(v) + '\n' for k, v in env.items()))
        # Archive remains private locally. No host extraction and no production writes.
        with archive.open('wb') as stream:
            call(['docker', 'cp', 'V79website:/app/data/.', '-'], stdout=stream, timeout=90)
        # SELECT gives a consistent SQLite document snapshot, replacing the copied DB/WAL.
        snapshot.write_bytes(call(['docker', 'exec', 'V79website', 'node', '-e', SNAPSHOT]))
        nonce = work.name
        cid = call(['docker', 'create', '--name', nonce, '--network', 'none',
                    '--restart', 'no', '--label', 'v79.startup.probe=' + nonce,
                    '--env-file', str(envfile), '--entrypoint', 'node',
                    selected_image, '-e', BOOTSTRAP]).decode().strip()
        row = inspect(cid)
        require(row['Image'] == selected_image and row['HostConfig']['NetworkMode'] == 'none'
                and not row.get('Mounts') and not row['HostConfig'].get('PortBindings'),
                'PROBE_ISOLATION_FAILED')
        with archive.open('rb') as stream:
            call(['docker', 'cp', '-a', '-', cid + ':/app/data'], stdin=stream, timeout=90)
        # Official node image's node user is 1000:1000; archive preserves private readability.
        call(['docker', 'cp', '-a', '-', cid + ':/tmp'],
             input=snapshot_archive(snapshot.read_bytes()))
        call(['docker', 'start', cid])
        print(json.dumps({'phase': 'ISOLATED_WEBSITE_STARTUP', 'network': 'none',
                          'production_mounts': False}), flush=True)
        deadline = time.monotonic() + 115
        last = 0
        while True:
            row = inspect(cid)
            health = row['State'].get('Health', {}).get('Status')
            if not row['State']['Running'] or health in ('healthy', 'unhealthy') or time.monotonic() >= deadline:
                break
            if time.monotonic() - last >= 25:
                print(json.dumps({'phase': 'WAITING_ISOLATED_STARTUP', 'health': health}), flush=True)
                last = time.monotonic()
            time.sleep(2)
        # Docker emits application stderr on its own stderr channel; capture both privately.
        captured = subprocess.run(['docker', 'logs', cid], capture_output=True, timeout=30)
        require(captured.returncode == 0, 'PROBE_LOG_CAPTURE_FAILED')
        logs = captured.stdout + captured.stderr
        (work / 'startup.log').write_bytes(logs)
        result = {'result': 'ISOLATED_STARTUP_CAPTURED', 'image': selected_image, 'running': row['State']['Running'],
                  'exit_code': row['State']['ExitCode'], 'health': health,
                  'signals': signals(logs.decode(errors='replace')),
                  'error_codes': sorted({code.decode() for code in re.findall(
                      rb'\b(?:ERR_[A-Z0-9_]+|SQLITE_[A-Z0-9_]+|EACCES|EPERM|ENOENT|EADDRINUSE)\b', logs)}),
                  'evidence_directory': str(work)}
    finally:
        if cid:
            row = inspect(cid)
            require(row['Image'] == selected_image
                    and row['Config']['Labels'].get('v79.startup.probe') == work.name
                    and row['HostConfig']['NetworkMode'] == 'none'
                    and not row.get('Mounts'), 'PROBE_CLEANUP_SCOPE_CHANGED')
            call(['docker', 'rm', '-f', cid])
        for file in (archive, snapshot, envfile):
            file.unlink(missing_ok=True)
        for name, before in originals.items():
            after = inspect(name)
            require(identity(after) == identity(before)
                    and after['State'].get('Health', {}).get('Status') == 'healthy',
                    'PRODUCTION_APP_CHANGED_DURING_PROBE')
    result.update(probe_removed=True, originals_unchanged=True, deployed=False)
    (work / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        code = str(error)
        print(json.dumps({'result': 'STOP_ISOLATED_PROBE',
                          'reason': code if re.fullmatch('[A-Z][A-Z0-9_]+', code)
                          else type(error).__name__, 'deployed': False}))
        raise SystemExit(1)
