#!/usr/bin/env python3
"""Deploy the verified Hub UI image only; preserve keys, data and publication flags."""
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import urllib.request

BUILD = Path('/home/firelion/v79-g3-ui-build-36jqnxjq')
PREVIOUS_WORK = Path('/home/firelion/v79-g3-ui-cutover-8d82b21a4def-v1')
WORK = Path('/home/firelion/v79-g3-ui-cutover-8d82b21a4def-v2')
IMAGE = 'sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e'
OLD_IMAGE = 'sha256:4a2320ad18549adf42fa60d9a1d06d2c124dba0db2f80b85a1a9cf0fc27dabb1'
COMMIT = '8d82b21a4defe47a3d377a57dcd648b3c9818fea'
TREE = '7a6f5e5835f1e141bb4197060da634cd6c2cefcc'
RECIPIENT = '484CF39CE37A02884497AD9C41A17102D2842ECE'
FILES = [
    '/opt/v79/hub/docker-compose.yml',
    '/opt/v79/hub/releases/wipay-return-585f701.pinned.yml',
    '/home/firelion/.v79-g12-pinned-cutover-49318a690822/candidate-v4.yml',
    '/home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-disabled.yml',
    '/home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-enabled.yml',
    '/home/firelion/v79-g3-recovery-20261014T220437Z-bp9zg67v/g3-hub-disabled.yml',
    '/home/firelion/v79-g3-cutover-c42f671f4ccd-b7934c03f0e3-v2/generation-only-v1/enable-v79-hub.yml',
]
HELPERS = [
    ('6a14a75bae67b18d1219f4d401d4573776db146c', 'marketing-production-panel-build.py',
     '4ca319f177cc3c10575c619936661a110eb8e1f9fa978bc91aee1b4040cbe8a5'),
    ('638fb3cb5b52d6f627014a4c2cb6d3ad6f29bbe7', 'marketing-production-reconcile-fresh-generation.py',
     '5fedd5e0f7a36bd2e10111bb373d745fc813620664e9eda949ddbc603d769e39'),
]
helper = None
stage = 'preflight'
attempted = False

MARKETING_STATE = r'''
const Database=require('better-sqlite3'),crypto=require('node:crypto');
const canonical=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const id='44289786-2583-4bf1-9db2-99eca95dfd96';
const db=new Database(process.env.DATABASE_PATH||'/app/data/v79_marketing.sqlite',{readonly:true,fileMustExist:true});
try{
 db.pragma('query_only=ON');
 const {state,hmac}=JSON.parse(db.prepare('SELECT envelope FROM marketing_production_state WHERE business_id=?').get(id).envelope);
 const mac=crypto.createHmac('sha256',process.env.V79_MARKETING_PRODUCTION_AUDIT_KEY).update('v79-marketing-production-v1\n'+id+'\n'+canonical(state)).digest('hex');
 if(!/^[a-f0-9]{64}$/.test(hmac)||!crypto.timingSafeEqual(Buffer.from(mac),Buffer.from(hmac)))throw Error('Ledger integrity');
 if(state.jobs.some(j=>['queued','generating'].includes(j.status)||j.deliveries.some(d=>d.status==='running')))throw Error('Worker is active; wait for production before a UI cutover');
 if(!state.paused&&state.plan?.automaticDrafts){
  const cadence=state.plan.cadenceDays,last=Date.parse(state.lastAutomaticAt||''),now=Date.now();
  if(!Number.isInteger(cadence)||cadence<3||cadence>30||!Number.isFinite(last)||last>now||last+cadence*86400000-now<=600000)
   throw Error('Automatic production is due within the ten-minute cutover buffer; wait for it to finish');
 }
 // Replay nonces and SQL row revision/timestamps may change during read polling.
 // All brand, plan, package, approval, digest and audit content remains bound.
 delete state.seenRequests;
 console.log(crypto.createHash('sha256').update(canonical(state)).digest('hex'));
}finally{db.close();}
'''


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def mark(value):
    global stage
    stage = value
    if helper is not None:
        helper['stage'] = value
    print('STAGE=' + value, flush=True)


def load_helper(spec):
    commit, filename, expected = spec
    url = 'https://raw.githubusercontent.com/MrFixITslu/V79hub/' + commit + '/scripts/' + filename
    with urllib.request.urlopen(url, timeout=30) as response:
        code = response.read(1048577)
    require(hashlib.sha256(code).hexdigest() == expected, 'Pinned helper integrity mismatch')
    namespace = {'__name__': 'ui_cutover_support'}
    exec(compile(code, '<verified-ui-cutover-support>', 'exec'), namespace)
    return namespace


def parity(before, after):
    expected = copy.deepcopy(before)
    expected['services']['v79-hub']['image'] = IMAGE
    require(expected == after, 'UI overlay changes exceed exact Hub image scope')


def command(files):
    args = ['docker', 'compose', '--project-name', 'v79-hub', '--project-directory', '/opt/v79/hub']
    for filename in files:
        args += ['--file', str(filename)]
    return args


def resolve(files):
    return json.loads(helper['run'](command(files) + ['config', '--format', 'json']))


def runtime_parity(before, after, configured_hostname):
    require(after['Image'] == IMAGE and after['Id'] != before['Id'] and helper['healthy'](after), 'New Hub image or health differs')
    a, b = copy.deepcopy(before['Config']), copy.deepcopy(after['Config'])
    old_labels, new_labels = a.pop('Labels'), b.pop('Labels')
    require(b.pop('Image') == IMAGE, 'Container image reference differs')
    a.pop('Image')
    if configured_hostname is None:
        require(a.get('Hostname') == before['Id'][:12] and b.get('Hostname') == after['Id'][:12], 'Unexpected Docker-generated hostname')
        a.pop('Hostname'); b.pop('Hostname')
    require(a == b, 'Hub environment, command, user or runtime configuration changed')
    require(before['HostConfig'] == after['HostConfig'] and helper['mounts'](before) == helper['mounts'](after) and
            set(before['NetworkSettings']['Networks']) == set(after['NetworkSettings']['Networks']), 'Hub resources, mounts or networks changed')
    require(old_labels.get('com.docker.compose.project.config_files') == ','.join(FILES) and
            new_labels.get('com.docker.compose.project.config_files') == ','.join(FILES + [str(WORK/'ui-image.yml')]), 'Hub Compose provenance changed')
    require(old_labels.get('org.opencontainers.image.revision') == 'c42f671f4ccd4b268f6701989cceba0ba27b5dbd' and
            new_labels.get('org.opencontainers.image.revision') == COMMIT, 'Hub source revision differs')
    # Compose's image bookkeeping label changes with the image. The actual
    # container Image and Config.Image above bind the exact tested digest.
    for labels in (old_labels, new_labels):
        for key in ('com.docker.compose.project.config_files', 'com.docker.compose.config-hash', 'com.docker.compose.image', 'org.opencontainers.image.revision'):
            labels.pop(key, None)
    require(old_labels == new_labels, 'Unapproved service labels changed')


def semantic_marketing():
    return helper['run'](['docker', 'exec', '-i', 'v79marketing-app', 'node', '--input-type=commonjs', '-'], data=MARKETING_STATE.encode()).decode().strip()


def verify_previous_backup_failure():
    require(PREVIOUS_WORK.is_dir() and not PREVIOUS_WORK.is_symlink() and PREVIOUS_WORK.stat().st_mode & 0o077 == 0,
            'Previous private pre-switch failure directory differs')
    require(not (PREVIOUS_WORK/'switch-attempted.json').exists() and not (PREVIOUS_WORK/'deployed.json').exists(),
            'Previous live switch may have been attempted; inspect before proceeding')
    hashes = {str(PREVIOUS_WORK/name): helper['file_hash'](PREVIOUS_WORK/name, True)
              for name in ('failure.json', 'ui-image.yml', 'rollback-image.yml')}
    failure = json.loads((PREVIOUS_WORK/'failure.json').read_text())
    require(failure.get('stage') == 'capture-encrypted-hub-recovery-and-exact-rollback-stack' and
            failure.get('liveSwitchAttempted') is False and failure.get('automaticRetryOrRollback') is False,
            'Previous failure is not the reviewed pre-switch backup failure')
    for filename, image in [('ui-image.yml', IMAGE), ('rollback-image.yml', OLD_IMAGE)]:
        require(json.loads((PREVIOUS_WORK/filename).read_text()) == {'services': {'v79-hub': {'image': image}}},
                'Previous image-only overlay differs')
    return hashes


def main():
    global helper, attempted
    os.umask(0o077)
    require(socket.gethostname().split('.')[0] == 'v79sl' and os.getuid() == 1000 and pwd.getpwuid(os.getuid()).pw_name == 'firelion', 'Run as firelion on v79sl')
    require(not WORK.exists(), 'Cutover directory exists; inspect its receipt/attempt marker before any retry')
    builder, helper = [load_helper(spec) for spec in HELPERS]
    mark('verify-recorded-backup-failure-before-new-attempt')
    previous_failure_hashes = verify_previous_backup_failure()
    mark('verify-tested-image-receipt-and-current-runtime')
    receipt_path = BUILD/'ui-build-receipt.json'
    receipt_sha = helper['file_hash'](receipt_path, True)
    receipt = json.loads(receipt_path.read_text())
    require(receipt.get('candidate') == {'commit': COMMIT, 'tree': TREE, 'image': IMAGE, 'tag': 'v79-hub-g3-ui:8d82b21a4def'} and
            receipt.get('deploymentPerformed') is False and receipt.get('isolatedTestsPassed') is True and
            receipt.get('sourceScopeVerified') is True and receipt.get('testEnvironment') == 'test', 'Build receipt differs from passed owner-run image tests')
    age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(receipt['at'])).total_seconds()
    # Test evidence remains bound to the immutable image. Current runtime
    # equality and fresh protected-state/backup checks establish live safety.
    require(age >= 0, 'UI build receipt timestamp is in the future')
    require(builder['snapshot']() == receipt['liveRuntime'], 'Live containers differ from tested build receipt')
    builder['verify_checkout_scope'](BUILD/'V79hub')
    runtime = {name: helper['inspect'](name) for name in builder['NAMES']}
    before = runtime['v79-hub']
    labels = before['Config']['Labels']
    require(labels['com.docker.compose.project.config_files'].split(',') == FILES and labels['com.docker.compose.project'] == 'v79-hub' and
            labels['com.docker.compose.service'] == 'v79-hub' and labels['com.docker.compose.project.working_dir'] == '/opt/v79/hub', 'Accepted Hub Compose stack differs')
    mark('verify-immutable-candidate-image')
    image = json.loads(helper['run'](['docker', 'image', 'inspect', IMAGE]))[0]
    require(image['Id'] == IMAGE and image['Config']['Labels'].get('org.opencontainers.image.revision') == COMMIT, 'Tested image revision differs')
    file_hashes = {p: helper['file_hash'](p) for p in FILES}
    secret_files = {mount['Source']: helper['file_hash'](mount['Source']) for mount in before['Mounts']
                    if mount.get('Type') == 'bind' and Path(mount['Source']).is_file()}
    mark('resolve-accepted-hub-compose-stack')
    original = resolve(FILES)
    require(original['services']['v79-hub']['image'] == OLD_IMAGE, 'Current Hub image is not pinned')
    mark('read-hub-protected-state')
    hub_state = helper['protected_state']('v79-hub-postgres')
    mark('read-marketing-protected-state')
    marketing = helper['sqlite_state']('v79marketing-app')
    mark('verify-signed-marketing-worker-idle-window')
    packages = semantic_marketing()
    WORK.mkdir(mode=0o700)
    with (WORK/'deployment.lock').open('x') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper['write_json'](WORK/'ui-image.yml', {'services': {'v79-hub': {'image': IMAGE}}})
        helper['write_json'](WORK/'rollback-image.yml', {'services': {'v79-hub': {'image': OLD_IMAGE}}})
        candidate = resolve(FILES + [WORK/'ui-image.yml'])
        parity(original, candidate)
        mark('capture-hub-database-backup')
        database_backup = helper['run'](['docker', 'exec', 'v79-hub-postgres', 'pg_dump', '-U', 'v79hub', '-d', 'v79hub', '-Fc'], timeout=120)
        mark('capture-hub-files-through-running-container')
        # Use the same read-only archive command as the successful restore rehearsal.
        # Host-owned/root-owned modes remain intact; no chmod/chown is performed.
        data_backup = helper['run'](['docker', 'exec', '--user', '0', 'v79-hub', 'tar', '-C', '/app', '-cf', '-', 'data'], timeout=120)
        blobs = {
            'hub-pg.dump.gpg': database_backup,
            'hub-data.tar.gpg': data_backup,
            'hub-runtime-and-config.json.gpg': json.dumps({'runtime': runtime, 'resolved': original,
                'composeFiles': {p: Path(p).read_text() for p in FILES}, 'originalStack': FILES,
                'mountedSecretFiles': {p: Path(p).read_text() for p in secret_files}}, sort_keys=True).encode(),
        }
        mark('encrypt-captured-hub-recovery')
        for name, data in blobs.items():
            helper['run'](['gpg', '--batch', '--yes', '--trust-model', 'always', '--encrypt', '--recipient', RECIPIENT,
                           '--output', str(WORK/name)], data=data, timeout=120)
        backup_hashes = {name: helper['file_hash'](WORK/name, True) for name in blobs}
        with (WORK/'encrypted-checksums.sha256').open('x') as output:
            output.write(''.join(digest+'  '+name+'\n' for name, digest in backup_hashes.items()))
        helper['write_json'](WORK/'manifest.json', {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'candidateImage': IMAGE, 'originalImage': OLD_IMAGE, 'previousPreSwitchFailureHashes': previous_failure_hashes, 'buildReceiptSha256': receipt_sha, 'originalStack': FILES,
            'sourceFileHashes': file_hashes, 'mountedSecretFileHashes': secret_files, 'encryptedBackups': backup_hashes, 'hubProtectedStateSha256': hub_state,
            'marketingProtectedStateSha256': marketing['digest'], 'signedMarketingPackagesSha256': packages,
            'onlyServiceToRecreate': 'v79-hub', 'publicationEnabled': False, 'automaticRetryOrRollback': False})
        mark('final-image-only-config-and-live-drift-check')
        require(builder['snapshot']() == receipt['liveRuntime'] and helper['file_hash'](receipt_path, True) == receipt_sha,
                'Live runtime or tested receipt changed before cutover')
        require(all(helper['file_hash'](p) == digest for p, digest in {**file_hashes, **secret_files}.items()), 'Original Compose or mounted secret file changed')
        require(resolve(FILES) == original and resolve(FILES + [WORK/'ui-image.yml']) == candidate, 'Resolved configuration changed')
        parity(original, candidate)
        require(helper['protected_state']('v79-hub-postgres') == hub_state and helper['sqlite_state']('v79marketing-app')['digest'] == marketing['digest'] and
                semantic_marketing() == packages, 'Protected data or campaign packages changed before cutover')
        mark('deploy-only-verified-hub-ui-image')
        helper['write_json'](WORK/'switch-attempted.json', {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'image': IMAGE})
        attempted = True
        helper['run'](command(FILES + [WORK/'ui-image.yml']) + ['up', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', '--wait', '--wait-timeout', '120', 'v79-hub'], timeout=180)
        mark('verify-live-ui-runtime-and-protected-state')
        after = helper['inspect']('v79-hub')
        runtime_parity(before, after, original['services']['v79-hub'].get('hostname'))
        for name in set(runtime)-{'v79-hub'}:
            current = helper['inspect'](name)
            require(helper['healthy'](current) and helper['stable_runtime'](current) == helper['stable_runtime'](runtime[name]), 'Unrelated live service changed: '+name)
        require(resolve(FILES + [WORK/'ui-image.yml']) == candidate and all(helper['file_hash'](p) == digest for p, digest in {**file_hashes, **secret_files}.items()), 'Cutover Compose configuration or mounted secret differs')
        helper['probe_live']()
        require(helper['protected_state']('v79-hub-postgres') == hub_state and helper['sqlite_state']('v79marketing-app')['digest'] == marketing['digest'] and
                semantic_marketing() == packages, 'Protected accounts, billing or campaign packages changed')
        served = helper['run'](['docker', 'exec', 'v79-hub', 'node', '--input-type=module', '-'], data=b"const r=await fetch('http://127.0.0.1:3040/');if(!r.ok||!(await r.text()).includes('index-CHQuh9Xa.js'))throw Error('UI asset identity differs');console.log('PINNED_UI_ASSET_SERVED_PASS');")
        require(b'PINNED_UI_ASSET_SERVED_PASS' in served, 'New UI assets were not served')
        helper['write_json'](WORK/'deployed.json', {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'image': IMAGE,
            'hubContainerId': after['Id'], 'healthy': True, 'publicationEnabled': False, 'protectedStatePreserved': True,
            'campaignPackagesPreserved': True, 'onlyHubRecreated': True, 'automaticRetryOrRollback': False})
        print('HUB_UI_LOGO_AND_AUTOMATIC_STATUS_FIX_DEPLOYED_HEALTHY')
        print('ACCOUNTS_BILLING_G2_AND_MARKETING_CAMPAIGNS_PRESERVED')
        print('MARKETING_AGENT_DATABASES_TIQUET_CONTAINERS_UNCHANGED_PUBLICATION_DISABLED')
        print('CUTOVER_DIRECTORY=' + str(WORK))
        print('OWNER_LOGO_SAVE_AND_AUTOMATIC_DRAFT_COMPLETION_CHECK_PENDING')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('STOP: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__))
        print('CUTOVER_DIRECTORY=' + str(WORK))
        print('LIVE_HUB_CUTOVER_UNCERTAIN_INSPECT_BEFORE_ANY_RETRY' if attempted else 'NO_LIVE_RECREATION_ATTEMPTED')
        if helper and WORK.is_dir():
            try:
                helper['write_json'](WORK/'failure.json', {'stage': stage, 'liveSwitchAttempted': attempted,
                    'automaticRetryOrRollback': False, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
            except Exception:
                pass
        raise SystemExit(1)
