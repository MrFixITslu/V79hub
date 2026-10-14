#!/usr/bin/env python3
"""Deploy the rehearsed G3 Hub and Marketing images with production disabled.

Reuses byte-identical, off-host-backed keys/overlays. Changes two application
containers only. Never retries or rolls back after an uncertain live mutation.
No generation, publication, database restore or original config edit.
"""
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys

RECOVERY = Path('/home/firelion/v79-g3-recovery-20261014T220437Z-bp9zg67v')
ACER_COPY = '/home/firelion/v79-g3-recovery.Uc019pSJ'
WORK = Path('/home/firelion/v79-g3-cutover-c42f671f4ccd-b7934c03f0e3-v1')
runtime = {}
stage = 'preflight'
attempted = []
ROOT = Path('/opt/v79/hub')

CANDIDATE = 'sha256:4a2320ad18549adf42fa60d9a1d06d2c124dba0db2f80b85a1a9cf0fc27dabb1'

SHA = 'c42f671f4ccd4b268f6701989cceba0ba27b5dbd'

MARKETING_CANDIDATE = 'sha256:e34d3c22f325c7fef78bc79bf96aa3386c10a45a7d2fd3e4e5081d39e9d4e0e8'

MARKETING_SHA = 'b7934c03f0e3fd91f826af52e68b62422ef55616'

BUILD_RECEIPT = Path('/home/firelion/v79-g3-build-tqq8d0bg/candidate-build-receipt.json')

OWNER_ORG = '44289786-2583-4bf1-9db2-99eca95dfd96'

OWNER_SCOPED_ID = '102ad8ce-df0b-4767-a3e2-b715ddbfee84'

ACCEPTED_G2_TASK = 'd8719467-1caa-4e24-ae5f-1fd792e0b3de'

BASELINES = {
    'v79-hub': 'sha256:26e959fbc07ace5cf20a1d3ea001229911014346c6eb1c89d629d88993bbca8a',
    'v79marketing-app': 'sha256:0d6f09ef37d73f2826900a8e3232a6f5ef4839614c1f92b42455ef03acf2cbf3',
    'v79-business-agent': 'sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f',
    'v79-hub-postgres': 'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
    'v79-tiquet-manager': 'sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b',
    'tiquet-postgres': 'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685',
}

FILES = {
    '/opt/v79/hub/docker-compose.yml': '186175ec20d10f817a9468b305fed86a6b0b4ae7cd380659e574df95ef688261',
    '/opt/v79/hub/releases/wipay-return-585f701.pinned.yml': '8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74',
    '/home/firelion/.v79-g12-pinned-cutover-49318a690822/candidate-v4.yml': 'fddb7d2a6934dfa65a5ce05358ca71a6769eebdff8c7def760eb070adac2b4c5',
}

HUB_FILES = list(FILES) + [
    '/home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-disabled.yml',
    '/home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-enabled.yml',
]

MARKETING_FILES = ['/home/firelion/V79Marketing/docker-compose.yml']

FILES[MARKETING_FILES[0]] = '306916c23ffdfe2349cee27091cf09672f1ed29dd5045dfcd743ac4276cc58ab'

def mark(value):
    global stage
    stage = value
    print('STAGE='+value, flush=True)

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def run(args, data=None, timeout=60, limit=64*1024*1024):
    # Never print arguments, raw Docker logs, stderr, SQL or environment.
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        errors = result.stderr.lower()
        hints = []
        for phrase, code in (
            (b'one of -d/--dbname and -f/--file must be specified', 'PG_RESTORE_OUTPUT_REQUIRED'),
            (b'already exists', 'OBJECT_ALREADY_EXISTS'),
            (b'permission denied', 'PERMISSION_DENIED'),
            (b'read-only file system', 'READ_ONLY_FILESYSTEM'),
            (b'no space left', 'NO_SPACE'),
            (b'out of memory', 'OUT_OF_MEMORY'),
            (b'no such image', 'IMAGE_UNAVAILABLE'),
            (b'could not connect', 'DATABASE_CONNECTION_FAILED'),
            (b'is not running', 'CONTAINER_NOT_RUNNING'),
            (b'cannot allocate memory', 'MEMORY_ALLOCATION_FAILED')):
            if phrase in errors:
                hints.append(code)
        raise RuntimeError('Command failed at '+stage+'; exit='+str(result.returncode)+
                           '; hints='+(','.join(hints) or 'NONE')+'; sensitive output withheld')
    require(len(result.stdout) <= limit, 'Snapshot exceeds rehearsal memory limit')
    return result.stdout

def inspect(name):
    return json.loads(run(['docker', 'inspect', name]))[0]

def psql(db, sql):
    return run(['docker', 'exec', db, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
                '-U', 'v79hub', '-d', 'v79hub', '-c', sql])

def protected_state(db):
    state = json.loads(psql(db, "SELECT state::text FROM v79_hub_state WHERE store_key='main'"))
    fields = {k: v for k, v in state.items() if k in ('users', 'organizations', 'memberships', 'entitlements')
              or any(word in k.lower() for word in ('billing', 'payment', 'subscription', 'wipay'))}
    require(all(isinstance(state.get(k), list) for k in ('users', 'organizations', 'memberships')),
            'Unexpected restored identity schema')
    workforce = json.loads(psql(db, "SELECT state::text FROM v79_hub_state WHERE store_key='workforce-actions-v1'"))
    require(any(t.get('id') == ACCEPTED_G2_TASK for t in workforce.get('state', {}).get('tasks', [])),
            'Accepted G2 work item missing from captured ledger')
    fields['workforce-actions-v1'] = workforce
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

SQLITE_STATE = r'''const Database=require('better-sqlite3'),crypto=require('node:crypto');
const db=new Database(process.env.DATABASE_PATH||'/app/data/v79_marketing.sqlite',{readonly:true,fileMustExist:true});
const canonical=v=>JSON.stringify(v,(_k,x)=>typeof x==='bigint'?{__sqlite_integer:String(x)}:x&&typeof x==='object'&&!Array.isArray(x)&&!Buffer.isBuffer(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
try{
 db.pragma('query_only = ON');db.defaultSafeIntegers(true);db.exec('BEGIN');
 if(db.pragma('integrity_check',{simple:true})!=='ok')throw Error('Restored SQLite integrity failed');
 const tables=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all().map(x=>x.name);
 const protectedRows={};
 for(const name of tables){
  if(['audit_logs','platform_event_outbox','marketing_production_state'].includes(name))continue;
  if(!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name))throw Error('Unexpected table identifier');
  const rows=db.prepare('SELECT * FROM "'+name+'"').all();if(rows.length>50000)throw Error('Table verification size limit');
  protectedRows[name]=rows.map(canonical).sort();
 }
 const links=db.prepare("SELECT b.id businessId,b.hub_organization_id organizationId,u.hub_user_id scopedHubUserId FROM businesses b JOIN users u ON u.business_id=b.id WHERE u.email='vision79slu@gmail.com' AND u.role='BUSINESS_OWNER'").all();
 const platforms=links.length===1?db.prepare('SELECT platform,COUNT(*) connected,SUM(CASE WHEN access_token_enc IS NOT NULL AND provider_account_id IS NOT NULL THEN 1 ELSE 0 END) tokenRecords FROM social_accounts WHERE business_id=? AND connected=1 GROUP BY platform ORDER BY platform').all(links[0].businessId):[];
 const productionLedgerDigest=tables.includes('marketing_production_state')?crypto.createHash('sha256').update(canonical(db.prepare('SELECT * FROM marketing_production_state ORDER BY business_id').all())).digest('hex'):null;
 db.exec('COMMIT');
 console.log(canonical({digest:crypto.createHash('sha256').update(canonical(protectedRows)).digest('hex'),productionLedgerDigest,founderLinks:links,ownerConnectedPlatforms:platforms.map(r=>({...r,connected:Number(r.connected),tokenRecords:Number(r.tokenRecords)}))}));
}finally{db.close();}
'''

def sqlite_state(name):
    return json.loads(run(['docker', 'exec', '-i', name, 'node', '--input-type=commonjs', '-'],
                          SQLITE_STATE.encode()))

def resolve_stack(name, files, extra=()):
    meta=runtime[name]
    project=meta['Config']['Labels']['com.docker.compose.project']
    root=meta['Config']['Labels']['com.docker.compose.project.working_dir']
    args=['docker','compose','--project-name',project,'--project-directory',root]
    for p in list(files)+list(extra):
        args+=['--file',str(p)]
    return json.loads(run(args+['config','--format','json']))

def normalize_approved_memory(config, service):
    result = copy.deepcopy(config)
    target = result['services'][service]
    value = target.get('mem_limit')
    allowed_strings = {'805306368', '805306368b', '768m', '768mb', '768mib'}
    require((type(value) is int and value == 805306368) or
            (isinstance(value, str) and value.lower() in allowed_strings),
            'Marketing memory limit differs from exact approved 768 MiB')
    target['mem_limit'] = 805306368
    return result

SPECS = {
    'v79-hub': ('v79-hub', 'v79-hub', '/opt/v79/hub', HUB_FILES,
                'g3-hub-disabled.yml', CANDIDATE, SHA),
    'v79marketing-app': ('v79marketing', 'v79-marketing', '/home/firelion/V79Marketing',
                MARKETING_FILES, 'g3-marketing-disabled.yml', MARKETING_CANDIDATE, MARKETING_SHA),
}
BACKUPS = {'hub-pg.dump.gpg', 'hub-data.tar.gpg', 'hub-config.tar.gpg',
    'hub-tokens.tar.gpg', 'marketing-online.sqlite.gpg', 'marketing-files.tar.gpg',
    'g3-protected-config.tar.gpg', 'resolved-original-compose.json.gpg', 'live-runtime-inspect.json.gpg'}
PREPARED = {'g3-hub-disabled.yml', 'g3-marketing-disabled.yml', 'g3-protected-keys.json'}

def file_hash(path, private=False):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), 'Protected file missing or symlinked')
    if private:
        require(p.stat().st_uid == os.getuid(), 'Protected file ownership differs')
        require(p.stat().st_mode & 0o077 == 0, 'Protected file permissions differ')
    require(p.stat().st_size <= 128*1024*1024, 'Protected file exceeds size bound')
    return hashlib.sha256(p.read_bytes()).hexdigest()

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def env_map(items):
    values = dict(x.split('=', 1) for x in items if '=' in x)
    require(len(values) == len(items), 'Duplicate or invalid runtime environment')
    return values

def write_json(path, value):
    with Path(path).open('x') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    # Persist directory entries before marking a live mutation as attempted.
    descriptor = os.open(str(Path(path).parent), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def healthy(meta):
    return meta['State']['Running'] and meta['State'].get('Health', {}).get('Status') == 'healthy'

def original_runtime(build):
    result = {}
    for name, digest in BASELINES.items():
        meta = inspect(name)
        require(meta['Image'] == digest and healthy(meta), 'Live baseline image/health differs: '+name)
        recorded = build['live_containers'][name]
        require(meta['Id'] == recorded['id'] and meta['State']['StartedAt'] == recorded['started_at'],
                'Live container changed after rehearsed candidate build: '+name)
        result[name] = meta
    for name, (project, service, root, files, *_rest) in SPECS.items():
        labels = result[name]['Config']['Labels']
        require(labels.get('com.docker.compose.project') == project and
                labels.get('com.docker.compose.service') == service and
                labels.get('com.docker.compose.project.working_dir') == root and
                labels.get('com.docker.compose.project.config_files') == ','.join(files),
                'Original Compose stack differs: '+name)
    return result

def verify_checkpoint():
    require(RECOVERY.is_dir() and not RECOVERY.is_symlink() and
            RECOVERY.stat().st_uid == os.getuid() and RECOVERY.stat().st_mode & 0o077 == 0,
            'Private rehearsal directory differs')
    file_hash(RECOVERY/'rehearsal-receipt.json', True)
    receipt = json.loads((RECOVERY/'rehearsal-receipt.json').read_text())
    require(receipt.get('candidateImage') == CANDIDATE and receipt.get('candidateCommit') == SHA and
            receipt.get('marketingCandidateImage') == MARKETING_CANDIDATE and
            receipt.get('marketingCandidateCommit') == MARKETING_SHA and
            receipt.get('runtimeImages') == BASELINES and receipt.get('liveDeploymentPerformed') is False,
            'Recovery candidate/baseline differs')
    for field in ('snapshotRestoreVerified', 'isolatedStartupRollbackVerified', 'copiedIdentityBillingPreserved',
            'scratchCleanupVerified', 'liveContainerIdsUnchanged', 'marketingOnlineBackupRestored',
            'marketingOriginalAndCandidateStartupVerified', 'marketingRollbackWithCopiedG3SchemaVerified',
            'pairedG3SignatureReplayAndPublishDisabledVerified', 'copiedG2AcceptedWorkItemPreserved'):
        require(receipt.get(field) is True, 'Incomplete recovery evidence: '+field)
    age = (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(receipt['capturedAt'])).total_seconds()
    require(0 <= age <= 3600, 'Rehearsal checkpoint older than one hour; prepare a fresh checkpoint')
    require((RECOVERY/'STATUS').read_text().strip() == 'ISOLATED_REHEARSAL_PASS_LIVE_DEPLOYMENT_NOT_PERFORMED',
            'Recovery rehearsal status differs')
    require(set(receipt['encryptedBackups']) == BACKUPS and set(receipt['preparedOverlayHashes']) == PREPARED,
            'Recovery backup/prepared file set differs')
    for name, digest in receipt['encryptedBackups'].items():
        require(file_hash(RECOVERY/name, True) == digest, 'Encrypted backup checksum differs')
    for name, digest in receipt['preparedOverlayHashes'].items():
        require(file_hash(RECOVERY/name, True) == digest, 'Backed-up prepared overlay/key differs')
    expected_files = set(HUB_FILES+MARKETING_FILES+['/opt/v79/hub/.env', '/home/firelion/V79Marketing/.env'])
    require(set(receipt['configurationHashes']) == expected_files, 'Original protected configuration set differs')
    require(all(receipt['configurationHashes'].get(k) == v for k, v in FILES.items()),
            'Known baseline configuration hashes differ')
    verify_files(receipt)
    return receipt

def verify_files(receipt):
    for path, digest in receipt['configurationHashes'].items():
        require(file_hash(path) == digest, 'Original Compose/environment file changed')
    for name, digest in receipt['preparedOverlayHashes'].items():
        require(file_hash(RECOVERY/name, True) == digest, 'Protected G3 key/overlay changed')

def approved_overlays():
    keys = json.loads((RECOVERY/'g3-protected-keys.json').read_text())
    require(set(keys) == {'shared', 'audit'} and
            all(isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v) for v in keys.values()) and
            keys['shared'] != keys['audit'], 'Dedicated G3 key structure differs')
    expected = {
        'v79-hub': {'image': CANDIDATE, 'environment': {
            'V79_MARKETING_PRODUCTION_ENABLED': '0', 'V79_MARKETING_PRODUCTION_SHARED_SECRET': keys['shared']}},
        'v79marketing-app': {'image': MARKETING_CANDIDATE, 'environment': {
            'V79_MARKETING_PRODUCTION_ENABLED': '0', 'V79_MARKETING_PRODUCTION_PUBLISH_ENABLED': '0',
            'V79_MARKETING_PRODUCTION_SHARED_SECRET': keys['shared'], 'V79_MARKETING_PRODUCTION_AUDIT_KEY': keys['audit'],
            'V79_MARKETING_PRODUCTION_OWNER_ORG_ID': OWNER_ORG, 'V79_PRODUCTION_ASSET_DIR': '/app/data/production-assets'},
            'mem_limit': 805306368, 'cpus': 1.0},
    }
    for name, (_project, service, _root, _files, filename, *_rest) in SPECS.items():
        value = json.loads((RECOVERY/filename).read_text())
        require(value == {'services': {service: expected[name]}}, 'Prepared G3 overlay exceeds exact approved scope')
    return expected

def configuration_parity(name, old, new, additions):
    service = SPECS[name][1]
    expected = copy.deepcopy(old)
    target = expected['services'][service]
    target['image'] = additions['image']
    target.setdefault('environment', {}).update(additions['environment'])
    if name == 'v79marketing-app':
        target.update(mem_limit=805306368, cpus=1.0)
        expected = normalize_approved_memory(expected, service)
        new = normalize_approved_memory(new, service)
    require(new == expected, 'Resolved G3 configuration exceeds exact approved scope: '+name)

def expected_environment(name, original, additions, image):
    service = SPECS[name][1]
    old = env_map(runtime[name]['Config']['Env'])
    original_env = original['services'][service].get('environment', {})
    require(all(old.get(k) == str(v) for k, v in original_env.items()), 'Original Compose/runtime environment differs')
    prior_image = json.loads(run(['docker', 'image', 'inspect', BASELINES[name]]))[0]
    defaults = env_map(prior_image['Config']['Env'])
    next_defaults = env_map(image['Config']['Env'])
    # Only image-provided Node/PATH/Yarn version metadata may change implicitly.
    changed_defaults = {k for k in set(defaults)|set(next_defaults) if defaults.get(k) != next_defaults.get(k)}
    require(changed_defaults <= {'PATH', 'NODE_VERSION', 'YARN_VERSION'}, 'Unapproved application image environment default changed')
    expected = dict(next_defaults)
    for key, value in old.items():
        if key in original_env or key not in defaults or value != defaults[key]:
            expected[key] = value
    expected.update(additions['environment'])
    if name == 'v79-hub':
        require(old.get('V79_WORKFORCE_ACTIONS_ENABLED') == '1' and len(old.get('V79_WORKFORCE_AUDIT_KEY', '')) >= 32 and
                old.get('V79_WORKFORCE_TOKEN_FILE') == '/run/secrets/v79-workforce-token', 'Current G2 configuration differs')
    return expected

def mounts(meta):
    # Compare stable permissions and source identity; addresses and mount ordering may change.
    return sorted([{k: m.get(k) for k in ('Type', 'Name', 'Source', 'Destination', 'Driver', 'Mode', 'RW', 'Propagation')}
                   for m in meta['Mounts']], key=lambda m: m['Destination'])

def stable_runtime(meta):
    # Health probe timestamps/log entries naturally change between read-only inspections.
    return {k: meta[k] for k in ('Id', 'Image', 'Config', 'HostConfig', 'Mounts')} | {
        'StartedAt': meta['State']['StartedAt'],
        'networks': sorted(meta['NetworkSettings']['Networks'])}

def verify_candidate(name, before, expected_env):
    project, service, root, files, filename, image, _commit = SPECS[name]
    current = inspect(name)
    require(current['Image'] == image and healthy(current) and current['Id'] != before['Id'],
            'Candidate live image/health differs: '+name)
    labels = current['Config']['Labels']
    require(labels.get('com.docker.compose.project') == project and labels.get('com.docker.compose.service') == service and
            labels.get('com.docker.compose.project.working_dir') == root and
            labels.get('com.docker.compose.project.config_files') == ','.join(files+[str(RECOVERY/filename)]),
            'Candidate Compose stack differs: '+name)
    require(env_map(current['Config']['Env']) == expected_env, 'Live candidate environment differs: '+name)
    require(mounts(current) == mounts(before), 'Live mounts/data/credential access changed: '+name)
    for field in ('ReadonlyRootfs', 'Privileged', 'CapAdd', 'CapDrop', 'SecurityOpt', 'NetworkMode', 'PortBindings',
                  'Binds', 'Tmpfs', 'PidsLimit', 'RestartPolicy', 'Devices', 'ExtraHosts'):
        require(current['HostConfig'].get(field) == before['HostConfig'].get(field), 'Runtime isolation/ports changed: '+name)
    require(set(current['NetworkSettings']['Networks']) == set(before['NetworkSettings']['Networks']),
            'Runtime network membership changed: '+name)
    if name == 'v79marketing-app':
        require(current['HostConfig']['Memory'] == 805306368 and current['HostConfig']['NanoCpus'] == 1000000000,
                'Live Marketing resources differ from approved 768 MiB/1 CPU')
    else:
        require(current['HostConfig']['Memory'] == before['HostConfig']['Memory'] and
                current['HostConfig']['NanoCpus'] == before['HostConfig']['NanoCpus'], 'Hub resources changed')
    return current

def verify_untouched():
    for name in set(BASELINES)-set(SPECS):
        current = inspect(name)
        old = runtime[name]
        require(current['Id'] == old['Id'] and current['Image'] == old['Image'] and healthy(current) and
                current['State']['StartedAt'] == old['State']['StartedAt'], 'Unrelated service changed: '+name)

def compose_command(name, extra):
    project, _service, root, files, *_rest = SPECS[name]
    args = ['docker', 'compose', '--project-name', project, '--project-directory', root]
    for path in files+list(extra):
        args += ['--file', str(path)]
    return args

def recreate_command(name, extra):
    return compose_command(name, extra)+['up', '--no-deps', '--no-build', '--pull', 'never',
        '--force-recreate', '--wait', '--wait-timeout', '120', SPECS[name][1]]

def probe_live():
    hub_probe = (r'''import assert from 'node:assert/strict';import fs from 'node:fs';
import {createWorkActionStore} from './server/workforce-action-store.mjs';
import {createApprovedWorkItem} from './server/workforce-actions.mjs';
const id=TASK_ID,base='http://127.0.0.1:3040';
assert.equal(process.env.V79_MARKETING_PRODUCTION_ENABLED,'0');
const worker=fs.readFileSync(process.env.V79_WORKFORCE_TOKEN_FILE,'utf8').trim();
const agent=fs.readFileSync('/run/secrets/v79-agent-token','utf8').trim();
assert.notEqual(worker,agent);
for(const [headers,status] of [[{},403],[{'x-v79-workforce-token':agent},403],
 [{'x-v79-workforce-token':worker,cookie:'session=untrusted'},403]])
 assert.equal((await fetch(base+'/internal/workforce/work-items',{headers,signal:AbortSignal.timeout(5000)})).status,status);
const tasks=await fetch(base+'/internal/workforce/work-items',{headers:{'x-v79-workforce-token':worker},signal:AbortSignal.timeout(5000)});
assert.equal(tasks.status,200);assert.ok((await tasks.json()).tasks.some(t=>t.id===id));
for(const p of ['/api/billing/summary','/api/agent/executive-structure'])
 assert.equal((await fetch(base+p,{signal:AbortSignal.timeout(5000)})).status,401);
assert.equal((await fetch(base+'/internal/marketing-production/authorization',{method:'POST',headers:{'content-type':'application/json'},
 body:'{}',signal:AbortSignal.timeout(5000)})).status,503);
const ledger=createWorkActionStore({file:'/app/data/workforce-actions.json',secret:process.env.V79_WORKFORCE_AUDIT_KEY,
 backend:process.env.V79_HUB_STORE_BACKEND,databaseUrl:process.env.DATABASE_URL});
try{const state=await ledger.read(),matches=state.tasks.filter(t=>t.id===id);assert.equal(matches.length,1);
 const task=matches[0],job=state.jobs.find(j=>j.id===task.jobId);assert.equal(task.assignedTo,'coo');
 assert.equal(job.status,'succeeded');assert.equal(job.result.taskId,id);assert.equal(job.approval.digest,job.digest);
 for(const type of ['proposed','approved','work_item_created'])assert.ok(state.events.some(e=>e.jobId===job.id&&e.type===type));
 assert.throws(()=>createApprovedWorkItem(structuredClone(state),job.id,{organizationId:job.organizationId,
 actor:job.approval.by,expectedRevision:job.revision}));
}finally{await ledger.close();}
''').replace('TASK_ID', json.dumps(ACCEPTED_G2_TASK)).encode()
    run(['docker', 'exec', '-i', 'v79-hub', 'node', '--input-type=module', '-'], hub_probe)
    marketing_probe = b'''import assert from 'node:assert/strict';
const base='http://127.0.0.1:3070';
assert.equal(process.env.V79_MARKETING_PRODUCTION_ENABLED,'0');assert.equal(process.env.V79_MARKETING_PRODUCTION_PUBLISH_ENABLED,'0');
assert.equal((await fetch(base+'/api/health',{signal:AbortSignal.timeout(5000)})).status,200);
for(const p of ['/api/posts','/api/social-accounts'])assert.equal((await fetch(base+p,{signal:AbortSignal.timeout(5000)})).status,401);
assert.equal((await fetch(base+'/api/platform/marketing-production',{method:'POST',headers:{'content-type':'application/json'},
 body:'{}',signal:AbortSignal.timeout(5000)})).status,503);
assert.equal((await fetch(base+'/media/production/00000000-0000-4000-8000-000000000000/'+('0'.repeat(64))+'/poster-square.png',
 {signal:AbortSignal.timeout(5000)})).status,404);
'''
    run(['docker', 'exec', '-i', 'v79marketing-app', 'node', '--input-type=module', '-'], marketing_probe)

def main():
    global runtime
    os.umask(0o077)
    require(socket.gethostname().split('.')[0] == 'v79sl' and pwd.getpwuid(os.getuid()).pw_name == 'firelion' and os.getuid() == 1000,
            'Run only as firelion on v79sl')
    require(shutil.which('docker'), 'Docker missing')
    require(not WORK.exists(), 'Cutover workspace exists; inspect prior status before any retry')
    mark('verify-exact-recovery-and-disabled-overlays')
    receipt = verify_checkpoint()
    file_hash(BUILD_RECEIPT, True)
    build = json.loads(BUILD_RECEIPT.read_text())
    require(build.get('live_identity_unchanged') is True and build.get('deployment_performed') is False,
            'Verified candidate build receipt missing')
    runtime = original_runtime(build)
    additions = approved_overlays()
    original, desired, expected_env = {}, {}, {}
    for name, (_project, service, _root, files, filename, image_id, commit) in SPECS.items():
        repo = 'V79hub' if name == 'v79-hub' else 'V79Marketing'
        require(build['candidates'][repo]['image'] == image_id and build['candidates'][repo]['commit'] == commit,
                'Candidate build record differs')
        image = json.loads(run(['docker', 'image', 'inspect', image_id]))[0]
        require(image['Id'] == image_id and (image['Config'].get('Labels') or {}).get('org.opencontainers.image.revision') == commit,
                'Candidate image/revision differs')
        original[name] = resolve_stack(name, files)
        ref = original[name]['services'][service]['image']
        require(json.loads(run(['docker', 'image', 'inspect', ref]))[0]['Id'] == BASELINES[name],
                'Original Compose image reference differs from live baseline: '+name)
        desired[name] = resolve_stack(name, files, [RECOVERY/filename])
        configuration_parity(name, original[name], desired[name], additions[name])
        expected_env[name] = expected_environment(name, original[name], additions[name], image)
    hub_before = protected_state('v79-hub-postgres')
    marketing_before = sqlite_state('v79marketing-app')
    require(marketing_before['founderLinks'] == [{'businessId': OWNER_ORG, 'organizationId': OWNER_ORG, 'scopedHubUserId': OWNER_SCOPED_ID}],
            'Live founder mapping differs')
    require(marketing_before['ownerConnectedPlatforms'] == receipt['ownerConnectedPlatforms'], 'Founder provider records differ from rehearsal')
    WORK.mkdir(mode=0o700)
    with (WORK/'cutover.lock').open('x') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rollback = {}
        for name, (_project, service, *_rest) in SPECS.items():
            path = WORK/('rollback-'+name+'.yml')
            write_json(path, {'services': {service: {'image': BASELINES[name]}}})
            rollback[name] = {'overlay': str(path), 'sha256': file_hash(path, True),
                             'command': recreate_command(name, [path])}
            tag = 'v79-g3-rollback-'+name+':'+BASELINES[name].split(':')[1][:12]
            prior = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True, timeout=30)
            if prior.returncode == 0:
                require(json.loads(prior.stdout)[0]['Id'] == BASELINES[name], 'Rollback retention tag conflicts')
            else:
                require(b'no such image' in prior.stderr.lower(), 'Rollback retention inspection failed')
                run(['docker', 'image', 'tag', BASELINES[name], tag])
        manifest = {'version': 1, 'recordedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'candidateImages': {name: spec[5] for name, spec in SPECS.items()}, 'baselineImages': BASELINES,
            'originalContainerIds': {name: meta['Id'] for name, meta in runtime.items()},
            'originalConfigurationHashes': receipt['configurationHashes'],
            'originalResolvedConfigurationHashes': {name: fingerprint(value) for name, value in original.items()},
            'desiredResolvedConfigurationHashes': {name: fingerprint(value) for name, value in desired.items()},
            'preparedOverlayHashes': receipt['preparedOverlayHashes'], 'recoveryDirectory': str(RECOVERY),
            'recoveryReceiptSha256': file_hash(RECOVERY/'rehearsal-receipt.json', True),
            'offhostDecryptionEvidence': {'source': 'Owner supplied ALL_NINE_DECRYPT_PASS; no independent machine attestation',
                                        'acerDirectory': ACER_COPY},
            'hubProtectedStateSha256': hub_before, 'marketingProtectedState': marketing_before,
            'generationEnabled': False, 'publicationEnabled': False, 'g2ActionsEnabled': True,
            'rollback': rollback, 'automaticRetryOrRollback': False}
        write_json(WORK/'manifest.json', manifest)
        mark('final-live-drift-check')
        final = original_runtime(build)
        require(all(stable_runtime(final[name]) == stable_runtime(runtime[name]) for name in runtime),
                'Runtime configuration drift immediately before cutover')
        verify_files(receipt)
        for name, (_project, _service, _root, files, filename, *_rest) in SPECS.items():
            require(resolve_stack(name, files) == original[name] and
                    resolve_stack(name, files, [RECOVERY/filename]) == desired[name], 'Resolved configuration changed before cutover')
        require(protected_state('v79-hub-postgres') == hub_before and sqlite_state('v79marketing-app') == marketing_before,
                'Protected data changed before cutover; fresh review required')
        print('EXACT_TWO_SERVICE_DISABLED_CONFIG_AND_OFFHOST_KEY_CUSTODY_PASS', flush=True)
        for name in SPECS:
            verify_files(receipt)
            verify_untouched()
            for service_name in SPECS:
                if service_name in attempted:
                    verify_candidate(service_name, runtime[service_name], expected_env[service_name])
                else:
                    live = inspect(service_name)
                    require(healthy(live) and stable_runtime(live) == stable_runtime(runtime[service_name]),
                            'Not-yet-switched application changed')
            require(protected_state('v79-hub-postgres') == hub_before and
                    sqlite_state('v79marketing-app') == marketing_before, 'Protected data drift before service cutover')
            mark('cutover-'+name+'-generation-disabled')
            write_json(WORK/('switch-attempted-'+name+'.json'), {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'candidateImage': SPECS[name][5]})
            attempted.append(name)
            run(recreate_command(name, [RECOVERY/SPECS[name][4]]), timeout=150)
            verify_candidate(name, runtime[name], expected_env[name])
            write_json(WORK/('switch-verified-'+name+'.json'), {'at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        mark('verify-live-disabled-boundaries-and-data-preservation')
        for name in SPECS:
            verify_candidate(name, runtime[name], expected_env[name])
        verify_untouched()
        verify_files(receipt)
        probe_live()
        require(protected_state('v79-hub-postgres') == hub_before, 'Hub identities/billing/G2 ledger changed during cutover')
        after = sqlite_state('v79marketing-app')
        require(after == marketing_before, 'Marketing identities/provider/customer/production state changed during cutover')
        result = {'version': 1, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'candidateImages': manifest['candidateImages'], 'healthy': True, 'generationEnabled': False, 'publicationEnabled': False,
            'g2SignedAcceptanceReplayDenialAndWorkerVisibilityVerified': True, 'protectedStatePreserved': True,
            'untouchedContainerIdsPreserved': True, 'ownerBrowserAcceptanceVerified': False}
        write_json(WORK/'deployment-disabled.json', result)
        print('G3_HUB_AND_MARKETING_HEALTHY_GENERATION_AND_PUBLICATION_DISABLED')
        print('G2_SIGNED_ACCEPTANCE_REPLAY_DENIAL_AND_WORKER_BOUNDARY_PRESERVED')
        print('WIPAY_ACCOUNTS_BILLING_PROVIDER_RECORDS_AND_DATA_PRESERVED')
        print('AGENT_DATABASES_TIQUET_CONTAINERS_UNCHANGED')
        print('CUTOVER_DIRECTORY='+str(WORK))
        print('OWNER_HUB_AND_MARKETING_BROWSER_ACCEPTANCE_PENDING')

if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('STOP: '+(str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__))
        print('CUTOVER_DIRECTORY='+str(WORK))
        print('LIVE_CUTOVER_UNCERTAIN_INSPECT_BEFORE_ANY_RETRY' if attempted else 'NO_LIVE_RECREATION_ATTEMPTED')
        if WORK.is_dir():
            try:
                write_json(WORK/'failure.json', {'stage': stage, 'attemptedServices': attempted,
                    'automaticRollbackPerformed': False, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
            except Exception:
                pass
        sys.exit(2)

