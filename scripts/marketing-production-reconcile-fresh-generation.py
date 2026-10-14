#!/usr/bin/env python3
"""Reconcile the verified Hub-active/Marketing-disabled G3 activation state.

Uses the same images, keys, mounts and customer state as the accepted disabled
cutover. Initializes an empty paused G3 ledger, verifies current owner service
boundaries, and creates no brand plan, package, approval or provider send.
No retry or rollback after an uncertain live restart.
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
WORK = Path('/home/firelion/v79-g3-cutover-c42f671f4ccd-b7934c03f0e3-v2')
ACTIVATION = WORK/'generation-only-v1'
RECONCILE = ACTIVATION/'reconcile-fresh-v2'
FRESH = Path('/home/firelion/v79-g3-refresh-20261014T232003Z-iyexdyhg')
ACER_FRESH_COPY = '/home/firelion/v79-g3-refresh.Dm7MTN3b'
fresh_receipt = None
fresh_reference_hash = None
fresh_receipt_hash = None
runtime = {}
stage = 'preflight'
attempted = []
ROOT = Path('/opt/v79/hub')

CANDIDATE = 'sha256:4a2320ad18549adf42fa60d9a1d06d2c124dba0db2f80b85a1a9cf0fc27dabb1'

SHA = 'c42f671f4ccd4b268f6701989cceba0ba27b5dbd'

MARKETING_CANDIDATE = 'sha256:e34d3c22f325c7fef78bc79bf96aa3386c10a45a7d2fd3e4e5081d39e9d4e0e8'

MARKETING_SHA = 'b7934c03f0e3fd91f826af52e68b62422ef55616'

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

def verify_original_history():
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

def verify_checkpoint():
    global fresh_receipt, fresh_reference_hash, fresh_receipt_hash
    history = verify_original_history()
    require(FRESH.is_dir() and not FRESH.is_symlink() and FRESH.stat().st_uid == os.getuid() and
            FRESH.stat().st_mode & 0o077 == 0, 'Expected fresh private checkpoint directory differs')
    pointer = ACTIVATION/'fresh-checkpoint-reference.json'
    reference_hash = file_hash(pointer, True)
    reference = json.loads(pointer.read_text())
    require(reference.get('directory') == str(FRESH) and reference.get('receiptSha256') == file_hash(FRESH/'rehearsal-receipt.json', True),
            'Fresh checkpoint reference differs from owner-decrypted checkpoint')
    receipt = json.loads((FRESH/'rehearsal-receipt.json').read_text())
    verify_fresh_receipt(receipt, history)
    require(reference.get('createdAt') == receipt['capturedAt'] and
            (FRESH/'STATUS').read_text().strip() == 'ISOLATED_REHEARSAL_PASS_LIVE_DEPLOYMENT_NOT_PERFORMED',
            'Fresh checkpoint completion/reference differs')
    for name, digest in receipt['encryptedBackups'].items():
        require(file_hash(FRESH/name, True) == digest, 'Owner-decrypted fresh encrypted backup changed')
    for name, digest in receipt['preparedOverlayHashes'].items():
        require(file_hash(FRESH/name, True) == digest == history['preparedOverlayHashes'][name], 'Fresh copied original G3 key/overlay differs')
    for path, digest in receipt['sourceDocumentHashes'].items():
        require(file_hash(path, True) == digest, 'Fresh source provenance document changed')
    for path, digest in receipt['configurationHashes'].items():
        require(file_hash(path) == digest, 'Configuration changed after fresh checkpoint')
    fresh_receipt = receipt
    fresh_reference_hash = reference_hash
    fresh_receipt_hash = file_hash(FRESH/'rehearsal-receipt.json', True)
    return history

def verify_fresh_receipt(receipt, history):
    expected_runtime = dict(BASELINES)
    expected_runtime.update({'v79-hub': CANDIDATE, 'v79marketing-app': MARKETING_CANDIDATE})
    require(receipt.get('mode') == 'fresh-checkpoint-for-reviewed-partial-activation' and
            receipt.get('candidateImage') == CANDIDATE and receipt.get('candidateCommit') == SHA and
            receipt.get('marketingCandidateImage') == MARKETING_CANDIDATE and receipt.get('marketingCandidateCommit') == MARKETING_SHA and
            receipt.get('runtimeImages') == expected_runtime and receipt.get('rollbackImages') == BASELINES and
            receipt.get('existingG3KeysReused') is True and receipt.get('liveDeploymentPerformed') is False and
            receipt.get('liveGenerationFlags') == {'v79-hub':'1','v79marketing-app':'0'} and receipt.get('livePublicationEnabled') is False and
            receipt.get('sourceRecoveryDirectory') == str(RECOVERY) and receipt.get('sourceCutoverDirectory') == str(WORK) and
            receipt.get('sourceActivationDirectory') == str(ACTIVATION), 'Fresh checkpoint scope/provenance differs')
    for field in ('snapshotRestoreVerified', 'isolatedStartupRollbackVerified', 'copiedIdentityBillingPreserved',
            'scratchCleanupVerified', 'liveContainerIdsUnchanged', 'marketingOnlineBackupRestored',
            'marketingOriginalAndCandidateStartupVerified', 'marketingRollbackWithCopiedG3SchemaVerified',
            'pairedG3SignatureReplayAndPublishDisabledVerified', 'copiedG2AcceptedWorkItemPreserved'):
        require(receipt.get(field) is True, 'Incomplete fresh recovery evidence: '+field)
    age = (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(receipt['capturedAt'])).total_seconds()
    require(0 <= age <= 3600, 'Fresh checkpoint older than one hour; refresh required')
    require(set(receipt['encryptedBackups']) == BACKUPS and set(receipt['preparedOverlayHashes']) == PREPARED and
            receipt['preparedOverlayHashes'] == history['preparedOverlayHashes'] and
            set(receipt['liveRuntimeIds']) == set(BASELINES), 'Fresh backup/key/runtime identity set differs')
    source_paths = {str(RECOVERY/'rehearsal-receipt.json'), str(WORK/'manifest.json'), str(WORK/'deployment-disabled.json'),
        str(ACTIVATION/'manifest.json'), str(ACTIVATION/'failure.json'), str(ACTIVATION/'switch-attempted-v79-hub.json')}
    source_paths.update(str(RECOVERY/name) for name in PREPARED)
    source_paths.update(str(ACTIVATION/('enable-'+name+'.yml')) for name in SPECS)
    require(set(receipt['sourceDocumentHashes']) == source_paths and
            set(receipt['configurationHashes']) == set(history['configurationHashes']) | source_paths and
            all(receipt['configurationHashes'].get(path) == digest for path, digest in history['configurationHashes'].items()) and
            all(receipt['configurationHashes'].get(path) == digest for path, digest in receipt['sourceDocumentHashes'].items()),
            'Fresh exact configuration/source document set differs')

def verify_files(receipt):
    for path, digest in receipt['configurationHashes'].items():
        require(file_hash(path) == digest, 'Original Compose/environment file changed')
    for name, digest in receipt['preparedOverlayHashes'].items():
        require(file_hash(RECOVERY/name, True) == digest, 'Protected G3 key/overlay changed')
    if fresh_receipt is not None:
        for path, digest in fresh_receipt['configurationHashes'].items():
            require(file_hash(path) == digest, 'Fresh checkpoint configuration/source evidence changed')
        require(file_hash(FRESH/'rehearsal-receipt.json', True) == fresh_receipt_hash and
                file_hash(ACTIVATION/'fresh-checkpoint-reference.json', True) == fresh_reference_hash,
                'Fresh checkpoint receipt/reference changed')
        for name, digest in fresh_receipt['encryptedBackups'].items():
            require(file_hash(FRESH/name, True) == digest, 'Fresh encrypted custody backup changed')

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

def mounts(meta):
    # Compare stable permissions and source identity; addresses and mount ordering may change.
    return sorted([{k: m.get(k) for k in ('Type', 'Name', 'Source', 'Destination', 'Driver', 'Mode', 'RW', 'Propagation')}
                   for m in meta['Mounts']], key=lambda m: m['Destination'])

def stable_runtime(meta):
    # Health probe timestamps/log entries naturally change between read-only inspections.
    return {k: meta[k] for k in ('Id', 'Image', 'Config', 'HostConfig', 'Mounts')} | {
        'StartedAt': meta['State']['StartedAt'],
        'networks': sorted(meta['NetworkSettings']['Networks'])}

def verify_untouched():
    for name in set(BASELINES)-set(SPECS):
        current = inspect(name)
        old = runtime[name]
        require(current['Id'] == old['Id'] and current['Image'] == old['Image'] and healthy(current) and
                current['State']['StartedAt'] == old['State']['StartedAt'], 'Unrelated service changed: '+name)

def safe_error(exc):
    if isinstance(exc, RuntimeError):
        return str(exc)
    # Show only our own function name and line, never a missing key value,
    # traceback source line, argument, Docker stderr or credential-bearing locals.
    location = ''
    tb = exc.__traceback__
    while tb:
        if tb.tb_frame.f_globals is globals():
            location = ' at '+tb.tb_frame.f_code.co_name+':'+str(tb.tb_lineno)
        tb = tb.tb_next
    return type(exc).__name__+location

def activation_config_parity(name, old, new):
    expected = copy.deepcopy(old)
    service = SPECS[name][1]
    require(expected['services'][service]['image'] == SPECS[name][5], 'Accepted G3 image changed')
    environment = expected['services'][service].get('environment', {})
    require(environment.get('V79_MARKETING_PRODUCTION_ENABLED') == '0', 'Production already enabled before activation')
    environment['V79_MARKETING_PRODUCTION_ENABLED'] = '1'
    if name == 'v79marketing-app':
        require(environment.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED') == '0', 'Publication must remain disabled')
        expected = normalize_approved_memory(expected, service)
        new = normalize_approved_memory(new, service)
    require(new == expected, 'Activation exceeds exact generation-flag scope: '+name)

def activation_command(name):
    project, service, root, files, filename, *_rest = SPECS[name]
    args = ['docker', 'compose', '--project-name', project, '--project-directory', root]
    for path in files+[str(RECOVERY/filename), str(ACTIVATION/('enable-'+name+'.yml'))]:
        args += ['--file', str(path)]
    return args+['up', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', '--wait', '--wait-timeout', '120', service]

def compare_runtime_config(before, current, configured_hostname=None):
    old_config, new_config = copy.deepcopy(before['Config']), copy.deepcopy(current['Config'])
    old_labels, new_labels = old_config.pop('Labels'), new_config.pop('Labels')
    old_config.pop('Env'); new_config.pop('Env')
    if configured_hostname is None:
        require(old_config.get('Hostname') == before['Id'][:12] and new_config.get('Hostname') == current['Id'][:12],
                'Unexpected hostname outside exact Docker-generated container identity')
        old_config['Hostname'] = new_config['Hostname'] = '<docker-generated-container-id>'
    else:
        require(old_config.get('Hostname') == configured_hostname and new_config.get('Hostname') == configured_hostname,
                'Explicit configured hostname changed')
    require(old_config == new_config, 'Activation changed application runtime configuration')
    return old_labels, new_labels

def verify_active(name, configured_hostname=None):
    current = inspect(name)
    before = runtime[name]
    require(current['Image'] == before['Image'] and healthy(current) and current['Id'] != before['Id'],
            'Activated image/health differs: '+name)
    expected_env = env_map(before['Config']['Env'])
    expected_env['V79_MARKETING_PRODUCTION_ENABLED'] = '1'
    require(env_map(current['Config']['Env']) == expected_env, 'Activation changed environment beyond generation flag')
    require(mounts(current) == mounts(before) and current['HostConfig'] == before['HostConfig'],
            'Activation changed mounts, resources, network or runtime permissions')
    require(set(current['NetworkSettings']['Networks']) == set(before['NetworkSettings']['Networks']),
            'Activation changed network membership')
    old_labels, new_labels = compare_runtime_config(before, current, configured_hostname)
    expected_files = old_labels['com.docker.compose.project.config_files']+','+str(ACTIVATION/('enable-'+name+'.yml'))
    require(new_labels.get('com.docker.compose.project.config_files') == expected_files, 'Activated Compose stack differs')
    for labels in (old_labels, new_labels):
        labels.pop('com.docker.compose.config-hash', None)
        labels.pop('com.docker.compose.project.config_files', None)
    require(new_labels == old_labels, 'Activation changed service/project/image labels')
    return current

def paired_live_boundaries():
    # Use configured service URLs in each direction; do not forge an owner MFA
    # timestamp. Only list requests write replay nonces to the fresh G3 ledger.
    marketing_probe = (r'''import assert from 'node:assert/strict';import crypto from 'node:crypto';
const org=ORG,owner=OWNER,key=process.env.V79_MARKETING_PRODUCTION_SHARED_SECRET;
const path='/internal/marketing-production/authorization',base=process.env.V79_HUB_INTERNAL_URL;
async function signed(actor){const body=JSON.stringify({organizationId:org,actorHubUserId:actor}),ts=String(Date.now());
const input=['POST',path,ts,crypto.createHash('sha256').update(body).digest('hex')].join('\n');
return fetch(new URL(path,base),{method:'POST',redirect:'error',signal:AbortSignal.timeout(5000),
headers:{'content-type':'application/json','x-v79-service-id':'v79-marketing','x-v79-timestamp':ts,
'x-v79-signature':crypto.createHmac('sha256',key).update(input).digest('hex')},body});}
let r=await signed(owner);assert.equal(r.status,200);assert.deepEqual(await r.json(),{allowed:true,cacheSeconds:0});
r=await signed(crypto.randomUUID());assert.equal(r.status,200);assert.deepEqual(await r.json(),{allowed:false,cacheSeconds:0});
''').replace('ORG', json.dumps(OWNER_ORG)).replace('OWNER', json.dumps(OWNER_SCOPED_ID)).encode()
    run(['docker', 'exec', '-i', 'v79marketing-app', 'node', '--input-type=module', '-'], marketing_probe)

    hub_probe = (r'''import assert from 'node:assert/strict';import crypto from 'node:crypto';
const org=ORG,owner=OWNER,key=process.env.V79_MARKETING_PRODUCTION_SHARED_SECRET;
const path='/api/platform/marketing-production',base=process.env.MARKETING_INTERNAL_URL||'http://v79marketing-app:3070';
async function signed(envelope,extra={}){const body=JSON.stringify(envelope),ts=String(Date.now());
const input=['POST',path,ts,crypto.createHash('sha256').update(body).digest('hex')].join('\n');
return fetch(new URL(path,base),{method:'POST',redirect:'error',signal:AbortSignal.timeout(5000),
headers:{'content-type':'application/json','x-v79-service-id':'v79-hub','x-v79-timestamp':ts,
'x-v79-signature':crypto.createHmac('sha256',key).update(input).digest('hex'),...extra},body});}
const envelope={organizationId:org,actorHubUserId:owner,mfaVerifiedAt:null,requestNonce:crypto.randomUUID(),request:{action:'list'}};
let r=await signed(envelope);assert.equal(r.status,200);const s=await r.json();
assert.equal(s.mode,'owner-approved-marketing-production');assert.equal(s.publishEnabled,false);
assert.equal(s.paused,true);assert.equal(s.configRevision,0);assert.equal(s.brand,null);assert.equal(s.plan,null);
assert.equal(s.ownerHubUserId,'');assert.equal(s.jobs.length,0);assert.equal(s.events.length,0);
r=await signed(envelope);assert.equal(r.status,409);
r=await signed({...envelope,requestNonce:crypto.randomUUID(),actorHubUserId:crypto.randomUUID()});assert.equal(r.status,403);
r=await signed({...envelope,requestNonce:crypto.randomUUID()},{cookie:'session=untrusted'});assert.equal(r.status,401);
r=await signed({...envelope,requestNonce:crypto.randomUUID(),request:{action:'pause',paused:false}});assert.equal(r.status,403);
r=await signed({...envelope,requestNonce:crypto.randomUUID(),request:{action:'decision',jobId:crypto.randomUUID(),
deliveryId:crypto.randomUUID(),decision:'approve',digest:'0'.repeat(64)}});assert.equal(r.status,403);
''').replace('ORG', json.dumps(OWNER_ORG)).replace('OWNER', json.dumps(OWNER_SCOPED_ID)).encode()
    run(['docker', 'exec', '-i', 'v79-hub', 'node', '--input-type=module', '-'], hub_probe)
    ledger_probe = (r'''const Database=require('better-sqlite3'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const db=new Database(process.env.DATABASE_PATH||'/app/data/v79_marketing.sqlite',{readonly:true,fileMustExist:true});
const canonical=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
try{db.pragma('query_only = ON');db.exec('BEGIN');
const rows=db.prepare('SELECT business_id,envelope FROM marketing_production_state').all();assert.equal(rows.length,1);
assert.equal(rows[0].business_id,ORG);const {state,hmac}=JSON.parse(rows[0].envelope);
const mac=crypto.createHmac('sha256',process.env.V79_MARKETING_PRODUCTION_AUDIT_KEY).update('v79-marketing-production-v1\n'+ORG+'\n'+canonical(state)).digest('hex');
assert.equal(hmac,mac);assert.equal(state.version,1);assert.equal(state.paused,true);assert.equal(state.configRevision,0);
assert.equal(state.brand,null);assert.equal(state.plan,null);assert.equal(state.ownerHubUserId,'');assert.equal(state.lastAutomaticAt,null);
assert.deepEqual(state.jobs,[]);assert.deepEqual(state.events,[]);db.exec('COMMIT');
}finally{db.close();}
''').replace('ORG', json.dumps(OWNER_ORG)).encode()
    run(['docker', 'exec', '-i', 'v79marketing-app', 'node', '--input-type=commonjs', '-'], ledger_probe)

def probe_live():
    hub_probe = (r'''import assert from 'node:assert/strict';import fs from 'node:fs';
import {createWorkActionStore} from './server/workforce-action-store.mjs';
import {createApprovedWorkItem} from './server/workforce-actions.mjs';
const id=TASK_ID,base='http://127.0.0.1:3040';
assert.equal(process.env.V79_MARKETING_PRODUCTION_ENABLED,'1');
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
 body:'{"organizationId":"44289786-2583-4bf1-9db2-99eca95dfd96","actorHubUserId":"102ad8ce-df0b-4767-a3e2-b715ddbfee84","mfaVerifiedAt":null,"requestNonce":"00000000-0000-4000-8000-000000000000","request":{"action":"list"}}',signal:AbortSignal.timeout(5000)})).status,401);
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
assert.equal(process.env.V79_MARKETING_PRODUCTION_ENABLED,'1');assert.equal(process.env.V79_MARKETING_PRODUCTION_PUBLISH_ENABLED,'0');
assert.equal((await fetch(base+'/api/health',{signal:AbortSignal.timeout(5000)})).status,200);
for(const p of ['/api/posts','/api/social-accounts'])assert.equal((await fetch(base+p,{signal:AbortSignal.timeout(5000)})).status,401);
assert.equal((await fetch(base+'/api/platform/marketing-production',{method:'POST',headers:{'content-type':'application/json'},
 body:'{"organizationId":"44289786-2583-4bf1-9db2-99eca95dfd96","actorHubUserId":"102ad8ce-df0b-4767-a3e2-b715ddbfee84","mfaVerifiedAt":null,"requestNonce":"00000000-0000-4000-8000-000000000000","request":{"action":"list"}}',signal:AbortSignal.timeout(5000)})).status,401);
assert.equal((await fetch(base+'/media/production/00000000-0000-4000-8000-000000000000/'+('0'.repeat(64))+'/poster-square.png',
 {signal:AbortSignal.timeout(5000)})).status,404);
'''
    run(['docker', 'exec', '-i', 'v79marketing-app', 'node', '--input-type=module', '-'], marketing_probe)

def assert_pristine_production(metadata):
    require(metadata['productionLedgerDigest'] is None, 'Existing G3 production state requires review before first activation')
    require(metadata['founderLinks'] == [{'businessId': OWNER_ORG, 'organizationId': OWNER_ORG, 'scopedHubUserId': OWNER_SCOPED_ID}],
            'Live founder mapping differs')

def protected_marketing_equal(before, after):
    require(all(after[field] == before[field] for field in ('digest', 'founderLinks', 'ownerConnectedPlatforms')),
            'Marketing customer/identity/provider rows changed during activation')

def verify_application_profile(profile, image_config, runtime_config):
    for docker_key, compose_key in [('User', 'user'), ('Cmd', 'command'), ('Entrypoint', 'entrypoint'), ('WorkingDir', 'working_dir')]:
        value = profile.get(compose_key)
        if value is None:
            value = image_config.get(docker_key)
        actual = runtime_config.get(docker_key)
        if docker_key == 'User' and profile.get('user') is None and image_config.get('User') is None:
            # Observed Docker inspect representations of an unset image user:
            # the image omits it/null, while the container exposes an empty string.
            require(actual is None or actual == '', 'Partial-state default user changed to an explicit user')
        else:
            require(actual == value, 'Partial-state application '+docker_key+' configuration differs')

def verify_partial_runtime(record, cutover, disabled, enabled):
    result = {}
    for name, image in BASELINES.items():
        meta = inspect(name)
        require(healthy(meta) and meta['Image'] == (SPECS[name][5] if name in SPECS else image), 'Partial-state image/health differs: '+name)
        if name not in SPECS:
            require(meta['Id'] == record['originalContainerIds'][name] == cutover['originalContainerIds'][name],
                    'Unrelated container changed during partial activation')
            result[name] = meta
            continue
        project, service, root, files, filename, candidate, commit = SPECS[name]
        active = name == 'v79-hub'
        require((meta['Id'] != record['originalContainerIds'][name]) if active else
                (meta['Id'] == record['originalContainerIds'][name]), 'Unexpected application recreation in partial state')
        expected_files = files+[str(RECOVERY/filename)]+([str(ACTIVATION/('enable-'+name+'.yml'))] if active else [])
        labels = meta['Config']['Labels']
        require(labels.get('com.docker.compose.project') == project and labels.get('com.docker.compose.service') == service and
                labels.get('com.docker.compose.project.working_dir') == root and
                labels.get('com.docker.compose.project.config_files') == ','.join(expected_files), 'Partial-state Compose stack differs')
        config = enabled[name] if active else disabled[name]
        profile = config['services'][service]
        require('hostname' not in profile and meta['Config'].get('Hostname') == meta['Id'][:12],
                'Partial-state hostname is not the exact Docker-generated identity')
        image_meta = json.loads(run(['docker', 'image', 'inspect', candidate]))[0]
        require(image_meta['Id'] == candidate and (image_meta['Config'].get('Labels') or {}).get('org.opencontainers.image.revision') == commit,
                'Partial-state image revision differs')
        expected_env = env_map(image_meta['Config']['Env'])
        expected_env.update({key: str(value) for key, value in profile.get('environment', {}).items()})
        env = env_map(meta['Config']['Env'])
        require(env == expected_env and env.get('V79_MARKETING_PRODUCTION_ENABLED') == ('1' if active else '0'),
                'Partial-state runtime environment differs from exact approved configuration')
        verify_application_profile(profile, image_meta['Config'], meta['Config'])
        require(meta['HostConfig'].get('Privileged', False) == profile.get('privileged', False) and
                meta['HostConfig'].get('ReadonlyRootfs', False) == profile.get('read_only', False), 'Partial-state runtime permissions differ')
        for docker_key, compose_key in [('CapAdd', 'cap_add'), ('CapDrop', 'cap_drop'), ('SecurityOpt', 'security_opt')]:
            require(sorted(meta['HostConfig'].get(docker_key) or []) == sorted(profile.get(compose_key) or []), 'Partial-state capabilities/security options differ')
        volumes = profile.get('volumes', [])
        require(len(volumes) == len(meta['Mounts']), 'Partial-state mount count differs')
        for volume in volumes:
            match = [mount for mount in meta['Mounts'] if mount['Destination'] == volume['target']]
            require(len(match) == 1 and match[0]['Type'] == volume['type'] and match[0]['RW'] == (not volume.get('read_only', False)),
                    'Partial-state mount identity/access differs')
            if volume['type'] == 'bind':
                require(match[0]['Source'] == volume['source'], 'Partial-state bind mount source differs')
            elif volume['type'] == 'volume':
                require(match[0]['Name'] == config['volumes'][volume['source']]['name'], 'Partial-state named data volume differs')
            else:
                raise RuntimeError('Unexpected partial-state mount type')
        if active:
            require(env.get('V79_WORKFORCE_ACTIONS_ENABLED') == '1' and len(env.get('V79_WORKFORCE_AUDIT_KEY', '')) >= 32,
                    'G2 settings differ in already-active Hub')
        else:
            require(env.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED') == '0' and
                    meta['HostConfig']['Memory'] == 805306368 and meta['HostConfig']['NanoCpus'] == 1000000000,
                    'Marketing publication/resource boundary differs')
        result[name] = meta
    return result

def main():
    global runtime
    os.umask(0o077)
    require(socket.gethostname().split('.')[0] == 'v79sl' and pwd.getpwuid(os.getuid()).pw_name == 'firelion' and os.getuid() == 1000,
            'Run only as firelion on v79sl')
    require(shutil.which('docker'), 'Docker missing')
    require(not RECONCILE.exists(), 'Reconciliation workspace exists; inspect status before any further action')
    for directory in (WORK, ACTIVATION):
        require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_uid == os.getuid() and
                directory.stat().st_mode & 0o077 == 0, 'Private partial-activation directory differs')
    mark('verify-recorded-hub-only-attempt-and-unchanged-keys')
    recovery = verify_checkpoint()
    documents = {}
    hashes = {}
    for path in (WORK/'manifest.json', WORK/'deployment-disabled.json', ACTIVATION/'manifest.json', ACTIVATION/'failure.json',
                 ACTIVATION/'switch-attempted-v79-hub.json'):
        hashes[str(path)] = file_hash(path, True)
        documents[str(path)] = json.loads(path.read_text())
    cutover = documents[str(WORK/'manifest.json')]
    deployed = documents[str(WORK/'deployment-disabled.json')]
    record = documents[str(ACTIVATION/'manifest.json')]
    failure = documents[str(ACTIVATION/'failure.json')]
    candidates = {name: spec[5] for name, spec in SPECS.items()}
    require(failure.get('stage') == 'activate-generation-only-v79-hub' and failure.get('attemptedServices') == ['v79-hub'] and
            failure.get('automaticRollbackPerformed') is False, 'Recorded activation failure does not match reviewed state')
    require(not (ACTIVATION/'switch-attempted-v79marketing-app.json').exists() and
            not (ACTIVATION/'generation-enabled.json').exists() and
            not (ACTIVATION/'reconcile-v1'/'switch-attempted-v79marketing-app.json').exists(),
            'Marketing already attempted or activation completed; inspect before proceeding')
    require(record.get('candidateImages') == cutover.get('candidateImages') == deployed.get('candidateImages') == candidates and
            cutover.get('baselineImages') == BASELINES and record.get('cutoverDirectory') == str(WORK) and
            cutover.get('recoveryDirectory') == str(RECOVERY) and
            cutover.get('recoveryReceiptSha256') == file_hash(RECOVERY/'rehearsal-receipt.json', True) and
            record.get('preparedOverlayHashes') == cutover.get('preparedOverlayHashes') == recovery['preparedOverlayHashes'] and
            cutover.get('originalConfigurationHashes') == recovery['configurationHashes'], 'Partial activation provenance differs')
    require(record.get('generationEnabled') is True and record.get('publicationEnabled') is False and
            record.get('automaticRetryOrRollback') is False and deployed.get('healthy') is True and
            deployed.get('generationEnabled') is False and deployed.get('publicationEnabled') is False,
            'Recorded generation/publication scope differs')
    # The activation attempt is historical. Freshness is established by the new
    # restore rehearsal and its exact source hash, not by rewriting an old date.
    require(fresh_receipt['sourceDocumentHashes'][str(ACTIVATION/'manifest.json')] == file_hash(ACTIVATION/'manifest.json', True),
            'Fresh checkpoint does not bind the recorded activation attempt')
    overlay_paths = {str(ACTIVATION/('enable-'+name+'.yml')) for name in SPECS}
    require(set(record['activationOverlayHashes']) == overlay_paths, 'Recorded activation overlay set differs')
    for path, digest in record['activationOverlayHashes'].items():
        require(file_hash(path, True) == digest, 'Reviewed activation overlay changed')
        name = next(name for name in SPECS if str(ACTIVATION/('enable-'+name+'.yml')) == path)
        require(json.loads(Path(path).read_text()) == {'services': {SPECS[name][1]: {'environment': {'V79_MARKETING_PRODUCTION_ENABLED': '1'}}}},
                'Reviewed activation overlay exceeds generation-only scope')
    # Resolve using exact original stacks, then verify live metadata against the
    # operator-observed split state. Never recreate the already-active Hub.
    runtime = {name: inspect(name) for name in BASELINES}
    additions = approved_overlays()
    disabled, enabled = {}, {}
    for name, (_project, _service, _root, files, filename, *_rest) in SPECS.items():
        disabled[name] = resolve_stack(name, files, [RECOVERY/filename])
        enabled[name] = resolve_stack(name, files, [RECOVERY/filename, ACTIVATION/('enable-'+name+'.yml')])
        require(fingerprint(disabled[name]) == record['originalResolvedConfigHashes'][name] == cutover['desiredResolvedConfigurationHashes'][name] and
                fingerprint(enabled[name]) == record['desiredResolvedConfigHashes'][name], 'Reviewed partial-state resolved configuration changed')
        configuration_parity(name, resolve_stack(name, files), disabled[name], additions[name])
        activation_config_parity(name, disabled[name], enabled[name])
    mark('verify-live-hub-active-marketing-disabled-and-protected-state')
    runtime = verify_partial_runtime(record, cutover, disabled, enabled)
    require(all(meta['Id'] == fresh_receipt['liveRuntimeIds'][name] for name, meta in runtime.items()),
            'Live container changed since owner-decrypted fresh checkpoint')
    hub_before = protected_state('v79-hub-postgres')
    marketing_before = sqlite_state('v79marketing-app')
    require(hub_before == record['hubProtectedStateSha256'] == fresh_receipt['hubProtectedStateSha256'] and
            marketing_before == record['marketingProtectedState'] == fresh_receipt['marketingProtectedState'],
            'Protected state changed since recorded activation attempt')
    assert_pristine_production(marketing_before)
    RECONCILE.mkdir(mode=0o700)
    with (RECONCILE/'reconciliation.lock').open('x') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write_json(RECONCILE/'manifest.json', {'version': 1, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'candidateImages': candidates, 'reviewedPartialState': {'hubGeneration': True, 'marketingGeneration': False, 'publication': False},
            'sourceDocumentHashes': hashes, 'activationOverlayHashes': record['activationOverlayHashes'],
            'originalContainerIds': {name: meta['Id'] for name, meta in runtime.items()},
            'runtimeFingerprints': {name: fingerprint(stable_runtime(meta)) for name, meta in runtime.items()},
            'hubProtectedStateSha256': hub_before, 'marketingProtectedState': marketing_before,
            'operatorEvidence': 'Owner supplied read-only diagnostic confirming generated hostnames and exact partial-state config hashes',
            'onlyServiceToRecreate': 'v79marketing-app', 'automaticRetryOrRollback': False})
        write_json(RECONCILE/'fresh-checkpoint-custody.json', {'freshCheckpointDirectory': str(FRESH),
            'freshReceiptSha256': file_hash(FRESH/'rehearsal-receipt.json', True),
            'encryptedBackupHashes': fresh_receipt['encryptedBackups'],
            'offhostDecryptionEvidence': {'source':'Owner supplied ALL_NINE_FRESH_DECRYPT_PASS; no independent machine attestation',
                'acerDirectory': ACER_FRESH_COPY}, 'oldReceiptDatesModified': False, 'existingG3KeysReused': True})
        def unchanged_files():
            verify_files(recovery)
            for path, digest in hashes.items():
                require(file_hash(path, True) == digest, 'Recorded partial-state evidence changed')
            for path, digest in record['activationOverlayHashes'].items():
                require(file_hash(path, True) == digest, 'Generation-only activation overlay changed')
        mark('final-marketing-only-reconciliation-drift-check')
        unchanged_files()
        final = verify_partial_runtime(record, cutover, disabled, enabled)
        require(all(stable_runtime(final[name]) == stable_runtime(runtime[name]) for name in runtime), 'Partial runtime drift before Marketing activation')
        for name, (_project, _service, _root, files, filename, *_rest) in SPECS.items():
            require(resolve_stack(name, files, [RECOVERY/filename]) == disabled[name] and
                    resolve_stack(name, files, [RECOVERY/filename, ACTIVATION/('enable-'+name+'.yml')]) == enabled[name],
                    'Partial resolved configuration drift before activation')
        require(protected_state('v79-hub-postgres') == hub_before and sqlite_state('v79marketing-app') == marketing_before,
                'Protected data drift before Marketing activation')
        mark('activate-only-marketing-generation-publication-disabled')
        write_json(RECONCILE/'switch-attempted-v79marketing-app.json', {'at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        attempted.append('v79marketing-app')
        run(activation_command('v79marketing-app'), timeout=150)
        verify_active('v79marketing-app', disabled['v79marketing-app']['services']['v79-marketing'].get('hostname'))
        write_json(RECONCILE/'switch-verified-v79marketing-app.json', {'at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        mark('complete-live-founder-signature-replay-mfa-and-g2-checks')
        paired_live_boundaries()
        probe_live()
        verify_active('v79marketing-app', disabled['v79marketing-app']['services']['v79-marketing'].get('hostname'))
        hub = inspect('v79-hub')
        require(healthy(hub) and stable_runtime(hub) == stable_runtime(runtime['v79-hub']), 'Already-active Hub changed during reconciliation')
        verify_untouched()
        unchanged_files()
        require(protected_state('v79-hub-postgres') == hub_before, 'Hub protected state changed during reconciliation')
        protected_marketing_equal(marketing_before, sqlite_state('v79marketing-app'))
        result = {'version': 1, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'candidateImages': candidates,
            'healthy': True, 'generationEnabled': True, 'publicationEnabled': False,
            'currentOwnerSignatureReplayAndMfaBoundaryVerified': True, 'emptyPausedSignedProductionLedgerVerified': True,
            'g2SignedAcceptanceAndWorkerBoundaryVerified': True, 'protectedStatePreserved': True,
            'unrelatedContainerIdsUnchanged': True, 'hubContainerUnchangedDuringReconciliation': True,
            'ownerBrandPlanAccepted': False, 'firstDraftAccepted': False, 'reconciliationDirectory': str(RECONCILE),
            'freshCheckpointDirectory': str(FRESH), 'freshReceiptSha256': file_hash(FRESH/'rehearsal-receipt.json', True)}
        write_json(RECONCILE/'generation-enabled.json', result)
        write_json(ACTIVATION/'generation-enabled.json', result)
        print('G3_GENERATION_ENABLED_PUBLICATION_DISABLED')
        print('LIVE_FOUNDER_SIGNATURE_REPLAY_MFA_AND_EMPTY_PAUSED_LEDGER_PASS')
        print('G2_SIGNED_ACCEPTANCE_WORKER_BOUNDARY_AND_PROTECTED_DATA_PRESERVED')
        print('ALREADY_ACTIVE_HUB_AGENT_DATABASES_TIQUET_CONTAINERS_UNCHANGED')
        print('RECONCILIATION_DIRECTORY='+str(RECONCILE))
        print('OWNER_BRAND_PLAN_AND_FIRST_DRAFT_ACCEPTANCE_PENDING')

if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('STOP: '+safe_error(exc))
        print('RECONCILIATION_DIRECTORY='+str(RECONCILE))
        print('LIVE_MARKETING_ACTIVATION_UNCERTAIN_INSPECT_BEFORE_ANY_RETRY' if attempted else 'NO_LIVE_RECREATION_ATTEMPTED')
        if RECONCILE.is_dir():
            try:
                write_json(RECONCILE/'failure.json', {'stage': stage, 'attemptedServices': attempted,
                    'automaticRollbackPerformed': False, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
            except Exception:
                pass
        sys.exit(2)
