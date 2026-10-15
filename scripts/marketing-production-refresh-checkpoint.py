#!/usr/bin/env python3
"""Refresh the encrypted checkpoint for the reviewed G3 partial activation.

No live restart, config edit, key rotation, database write or deployment.
Plaintext snapshots and runtime credentials exist only in RAM and isolated
container tmpfs. Off-host decryption and owner browser acceptance remain open.
"""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path('/opt/v79/hub')
FPR = '484CF39CE37A02884497AD9C41A17102D2842ECE'
PUBLIC = Path('/home/firelion/.v79-g12-recovery-public.asc')
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
ROLLBACK_IMAGES = dict(BASELINES)
BASELINES.update({'v79-hub': CANDIDATE, 'v79marketing-app': MARKETING_CANDIDATE})
SOURCE_RECOVERY = Path('/home/firelion/v79-g3-recovery-20261014T220437Z-bp9zg67v')
SOURCE_CUTOVER = Path('/home/firelion/v79-g3-cutover-c42f671f4ccd-b7934c03f0e3-v2')
SOURCE_ACTIVATION = SOURCE_CUTOVER/'generation-only-v1'
source_document_hashes = {}
source_activation_record = None
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
ORIGINAL_HUB_FILES = list(HUB_FILES)
ORIGINAL_MARKETING_FILES = list(MARKETING_FILES)
HUB_FILES += [str(SOURCE_RECOVERY/'g3-hub-disabled.yml'), str(SOURCE_ACTIVATION/'enable-v79-hub.yml')]
MARKETING_FILES += [str(SOURCE_RECOVERY/'g3-marketing-disabled.yml')]
nonce = secrets.token_hex(8)
label = 'v79.g3.rehearsal'
created = []
work = None
ram = None
runtime = {}
stage = 'preflight'
shared_key = None
audit_key = None

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

def verify_live(first=False):
    for name, digest in BASELINES.items():
        meta = inspect(name)
        require(meta['Image'] == digest and meta['State']['Running'] and
                meta['State'].get('Health', {}).get('Status') == 'healthy',
                'Live baseline or health changed: ' + name)
        if first:
            runtime[name] = meta
        else:
            require(meta['Id'] == runtime[name]['Id'] and
                    meta['State']['StartedAt'] == runtime[name]['State']['StartedAt'] and
                    all(meta.get(key) == runtime[name].get(key) for key in ('Config', 'HostConfig', 'Mounts')),
                    'Live container recreated/restarted: ' + name)
    for filename, digest in FILES.items():
        p = Path(filename)
        require(p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest() == digest,
                'Pinned configuration changed')
    require(runtime['v79-hub']['Config']['Labels']['com.docker.compose.project.config_files'] == ','.join(HUB_FILES),
            'Unexpected live Compose stack')
    require(runtime['v79marketing-app']['Config']['Labels']['com.docker.compose.project.config_files'] == ','.join(MARKETING_FILES),
            'Unexpected Marketing Compose stack')
    if first:
        for filename in HUB_FILES[3:]+MARKETING_FILES[1:]+['/opt/v79/hub/.env','/home/firelion/V79Marketing/.env']:
            p = Path(filename)
            require(p.is_file() and not p.is_symlink(), 'Protected G2 configuration missing')
            FILES[filename] = hashlib.sha256(p.read_bytes()).hexdigest()

def archive_map(blob):
    result = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:') as archive:
        for member in archive:
            name = member.name.rstrip('/')
            require(not member.issym() and not member.islnk() and not member.isdev() and
                    not name.startswith('/') and '..' not in Path(name).parts,
                    'Unsafe archive member; rehearsal stopped')
            if member.isfile():
                result[name] = (member.mode, member.size,
                    hashlib.sha256(archive.extractfile(member).read()).hexdigest())
            elif not member.isdir():
                raise RuntimeError('Unsupported archive member')
    return result

def table_data(sql):
    """Compare COPY blocks and sequence values, excluding random dump headers."""
    blocks = {}
    active = None
    for line in sql.splitlines():
        if active is not None:
            blocks[active].append(line)
            if line == b'\\.':
                active = None
        elif line.startswith(b'COPY ') and line.endswith(b' FROM stdin;'):
            require(line not in blocks, 'Duplicate restored table block')
            active = line
            blocks[active] = []
        elif line.startswith(b'SELECT pg_catalog.setval('):
            blocks[line] = []
        elif line.startswith(b'INSERT INTO '):
            raise RuntimeError('Unexpected INSERT dump format')
    require(active is None and bool(blocks), 'Incomplete database data comparison')
    return blocks

def only_tmpfs(meta):
    return all(m.get('Type') == 'tmpfs' for m in meta.get('Mounts', []))

def encrypt(name, blob):
    destination = work / name
    require(not destination.exists(), 'Backup already exists')
    run(['gpg', '--homedir', str(work/'gnupg'), '--batch', '--yes', '--quiet',
         '--trust-model', 'always', '--recipient', FPR, '--compress-algo', 'none',
         '--output', str(destination), '--encrypt'], blob)
    require(destination.stat().st_size > 0, 'Empty encrypted backup')
    return hashlib.sha256(destination.read_bytes()).hexdigest()

def create(name, args):
    # All resources are created under unique names and an exact ownership label.
    created.append(name)
    run(['docker', 'create', '--name', name, '--label', label+'='+nonce,
         '--pull', 'never'] + args)

def remove(name):
    result=subprocess.run(['docker','inspect',name],capture_output=True,timeout=30)
    if result.returncode:
        require(b'no such object' in result.stderr.lower() or b'no such container' in result.stderr.lower(),
                'Scratch cleanup state unavailable')
        created.remove(name)
        return
    require(json.loads(result.stdout)[0]['Config']['Labels'].get(label) == nonce, 'Scratch ownership mismatch')
    run(['docker', 'rm', '-f', '-v', name])
    created.remove(name)

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

def hub_smoke(db, image, phase, data_tar, token_tar, enabled, keep=False):
    mark('hub-'+phase)
    name = 'v79-g3-rehearsal-hub-'+phase+'-'+nonce
    env = dict(item.split('=', 1) for item in runtime['v79-hub']['Config']['Env'] if '=' in item)
    for key in list(env):
        if 'URL' in key:
            env[key] = 'http://127.0.0.1:19999'
    env.update(APP_URL='https://hub.v79sl.com', PORT='3040', DATA_DIR='/app/data',
               NODE_ENV='production', V79_HUB_STORE_BACKEND='postgres',
               DATABASE_URL='postgresql://v79hub@127.0.0.1:5432/v79hub',
               V79_TRIAL_REMINDERS_ENABLED='0', V79_TRIAL_REMINDERS_WORKER_LEADER='0',
               V79_SENTINEL_HUB_SERVICE_ENABLED='0', V79_SENTINEL_GRANT_ADMIN_ENABLED='0',
               V79_SENTINEL_OWNER_MAPPING_ATTESTED='0', V79_AGENT_SUPERVISED_DRAFTS_ENABLED='0',
               V79_WORKFORCE_ACTIONS_ENABLED='1',
               V79_WORKFORCE_TOKEN_FILE='/run/secrets/v79-workforce-token',
               V79_MARKETING_PRODUCTION_ENABLED=str(int(enabled)),
               V79_MARKETING_PRODUCTION_SHARED_SECRET=shared_key,
               MARKETING_INTERNAL_URL='http://127.0.0.1:3070',
               RESEND_API_KEY='', OPENAI_API_KEY='', WIPAY_ENABLED='0')
    require(len(env.get('V79_WORKFORCE_AUDIT_KEY', '')) >= 32, 'Original G2 audit key missing')
    require(not any('\n' in value or '\r' in value for value in env.values()), 'Unsupported multiline environment')
    envfile = ram/'hub.env'
    envfile.write_text(''.join(key+'='+value+'\n' for key, value in env.items()))
    envfile.chmod(0o600)
    create(name, ['--network', 'container:'+db, '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--pids-limit', '192', '--memory', '768m', '--cpus', '1',
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m,mode=1777',
        '--tmpfs', '/app/data:rw,nosuid,nodev,size=128m,mode=700',
        '--tmpfs', '/run/secrets:rw,nosuid,nodev,size=8m,mode=700',
        '--env-file', str(envfile), '--entrypoint', 'sh', image, '-c',
        'while [ ! -f /tmp/rehearsal-ready ]; do sleep 1; done; exec ./node_modules/.bin/tsx server.ts'])
    envfile.unlink()
    mark('start-hub-'+phase)
    run(['docker', 'start', name])
    meta = inspect(name)
    db_meta = inspect(db)
    allowed_networks = ('container:'+db, 'container:'+db_meta['Id'])
    checks = {
        'exact_image': meta['Image'] == image,
        'tmpfs_only': only_tmpfs(meta),
        'no_published_ports': not meta['HostConfig'].get('PortBindings'),
        'exact_scratch_network': meta['HostConfig']['NetworkMode'] in allowed_networks,
        'scratch_database_disconnected': db_meta['HostConfig']['NetworkMode'] == 'none',
        'scratch_database_owned': db_meta['Config']['Labels'].get(label) == nonce,
        'readonly_root': meta['HostConfig']['ReadonlyRootfs'] is True,
    }
    require(all(checks.values()), 'Scratch isolation mismatch: '+
            ','.join(key for key, passed in checks.items() if not passed))
    mark('restore-files-'+phase)
    run(['docker', 'exec', '-i', name, 'tar', '-C', '/app', '-xof', '-'], data_tar)
    restored = run(['docker', 'exec', name, 'tar', '-C', '/app', '-cf', '-', 'data'])
    require(archive_map(restored) == archive_map(data_tar), 'Restored data file contents/modes differ')
    run(['docker', 'exec', '-i', name, 'tar', '-C', '/run/secrets', '-xof', '-'], token_tar)
    restored = run(['docker', 'exec', name, 'tar', '-C', '/run/secrets', '-cf', '-',
                    'v79-agent-token', 'v79-readonly-platform-token', 'v79-workforce-token'])
    require(archive_map(restored) == archive_map(token_tar), 'Restored token contents/modes differ')
    mark('startup-probe-'+phase)
    run(['docker', 'exec', name, 'touch', '/tmp/rehearsal-ready'])
    probe = b'''const base='http://127.0.0.1:3040';
let ready=false;
for(let i=0;i<150;i++){
 try {if((await fetch(base+'/api/health',{signal:AbortSignal.timeout(500)})).ok){ready=true;break;}}catch{}
 await new Promise(r=>setTimeout(r,200));
}
if(!ready)throw Error('Startup failed');
for(const path of ['/api/agent/executive-structure','/api/billing/summary']){
 const r=await fetch(base+path,{signal:AbortSignal.timeout(2000)});
 if(r.status!==401)throw Error('Anonymous access boundary failed');
}
'''
    run(['docker', 'exec', '-i', name, 'node', '--input-type=module', '-'], probe, timeout=45)
    ledger_probe = ('''import assert from 'node:assert/strict';
import {createWorkActionStore} from './server/workforce-action-store.mjs';
const store=createWorkActionStore({file:'/app/data/workforce-actions.json',secret:process.env.V79_WORKFORCE_AUDIT_KEY,
backend:process.env.V79_HUB_STORE_BACKEND,databaseUrl:process.env.DATABASE_URL});
try{const state=await store.read();assert.equal(state.tasks.filter(t=>t.id==='''+json.dumps(ACCEPTED_G2_TASK)+''').length,1);}
finally{await store.close();}
''').encode()
    run(['docker', 'exec', '-i', name, 'node', '--input-type=module', '-'], ledger_probe)
    if phase.startswith('candidate'):
        probe = b'''const r=await fetch('http://127.0.0.1:3040/internal/marketing-production/authorization',
{method:'POST',headers:{'content-type':'application/json'},body:'{}',signal:AbortSignal.timeout(3000)});
if(r.status!==Number(process.argv[2]))throw Error('Worker boundary failed');
'''
        run(['docker', 'exec', '-i', name, 'node', '--input-type=module', '-',
             '401' if enabled else '503'], probe)
    if not keep:
        remove(name)
    print(phase.upper().replace('-', '_')+'_STARTUP_AND_DENIAL_PASS', flush=True)
    return name

SQLITE_CAPTURE = r'''const fs=require('node:fs'),Database=require('better-sqlite3');
const root='/dev/shm/v79-g3-online-'+process.argv[2],file=root+'/snapshot.sqlite';
if(!/^[a-f0-9]{16}$/.test(process.argv[2]))throw Error('Invalid capture identity');
fs.mkdirSync(root,{mode:0o700});
let source,copy;
try{
 source=new Database(process.env.DATABASE_PATH||'/app/data/v79_marketing.sqlite',{readonly:true,fileMustExist:true});
 source.pragma('query_only = ON');
 const deadline=Date.now()+30000;
 await source.backup(file,{progress(){if(Date.now()>deadline)throw Error('Online capture deadline');return 100;}});
 copy=new Database(file,{readonly:true,fileMustExist:true});
 if(copy.pragma('integrity_check',{simple:true})!=='ok')throw Error('Snapshot integrity failed');
 const bytes=fs.readFileSync(file);if(bytes.length>67108864)throw Error('Snapshot size limit');
 process.stdout.write(bytes);
}finally{copy?.close();source?.close();fs.rmSync(root,{recursive:true,force:true});}
'''
# CommonJS supports neither top-level await nor an ambiguous async exit: await
# capture explicitly and write a fixed error only on failure.
SQLITE_CAPTURE = '(async()=>{'+SQLITE_CAPTURE+'})().catch(()=>{process.stderr.write("SQLite online capture failed");process.exitCode=1;});'

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

def sqlite_capture(name):
    return run(['docker', 'exec', '-i', name, 'node', '--input-type=commonjs', '-', nonce],
               SQLITE_CAPTURE.encode(), timeout=90)

def sqlite_state(name):
    return json.loads(run(['docker', 'exec', '-i', name, 'node', '--input-type=commonjs', '-'],
                          SQLITE_STATE.encode()))

def marketing_smoke(image, phase, database, files_tar, enabled=False, db=None):
    mark('marketing-'+phase)
    name = 'v79-g3-rehearsal-marketing-'+phase+'-'+nonce
    env = dict(x.split('=', 1) for x in runtime['v79marketing-app']['Config']['Env'] if '=' in x)
    for key in list(env):
        if 'URL' in key:
            env[key] = 'http://127.0.0.1:19999'
    env.update(NODE_ENV='production', PORT='3070', DATABASE_PATH='/app/data/v79_marketing.sqlite',
               APP_URL='https://marketing.v79sl.com', V79_MARKETING_SEED_DEMO='0',
               V79_ENABLE_SIMULATED_PUBLISHER='0', V79_ALLOW_LEGACY_LOGIN='0',
               V79_MARKETING_PRODUCTION_ENABLED=str(int(enabled)),
               V79_MARKETING_PRODUCTION_PUBLISH_ENABLED='0',
               V79_MARKETING_PRODUCTION_OWNER_ORG_ID=OWNER_ORG,
               V79_MARKETING_PRODUCTION_SHARED_SECRET=shared_key,
               V79_MARKETING_PRODUCTION_AUDIT_KEY=audit_key,
               V79_HUB_INTERNAL_URL='http://127.0.0.1:3040',
               V79_PRODUCTION_ASSET_DIR='/app/data/production-assets',
               V79_NEWSLETTER_RESEND_API_KEY='', GEMINI_API_KEY='', OPENAI_API_KEY='')
    require(not any('\n' in v or '\r' in v for v in env.values()), 'Unsupported multiline environment')
    envfile=ram/('marketing-'+phase+'.env')
    envfile.write_text(''.join(k+'='+v+'\n' for k,v in env.items()))
    envfile.chmod(0o600)
    network='container:'+db if db else 'none'
    create(name, ['--network',network,'--read-only','--user','1000:1000','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--pids-limit','192','--memory','768m','--cpus','1',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=64m,mode=1777',
        '--tmpfs','/app/data:rw,nosuid,nodev,size=128m,mode=700,uid=1000,gid=1000',
        '--env-file',str(envfile),'--entrypoint','sh',image,'-c',
        'while [ ! -f /tmp/rehearsal-ready ]; do sleep 1; done; exec node dist/server.cjs'])
    envfile.unlink()
    run(['docker','start',name])
    meta=inspect(name)
    networks=(network,'container:'+inspect(db)['Id']) if db else ('none',)
    require(meta['Image']==image and only_tmpfs(meta) and meta['HostConfig']['NetworkMode'] in networks and
            meta['HostConfig']['ReadonlyRootfs'] and not meta['HostConfig'].get('PortBindings') and
            meta['Config']['User']=='1000:1000', 'Marketing scratch isolation mismatch')
    run(['docker','exec','-i',name,'tar','-C','/app','-xof','-'],files_tar)
    restored=run(['docker','exec',name,'tar','-C','/app','--exclude=data/v79_marketing.sqlite',
        '--exclude=data/v79_marketing.sqlite-wal','--exclude=data/v79_marketing.sqlite-shm','-cf','-','data'])
    require(archive_map(restored)==archive_map(files_tar), 'Marketing files differ after restore')
    run(['docker','exec','-i',name,'sh','-c','umask 077; cat > /app/data/v79_marketing.sqlite'],database)
    before=sqlite_state(name)
    run(['docker','exec',name,'touch','/tmp/rehearsal-ready'])
    probe=b'''let ready=false;
for(let i=0;i<150;i++){try{if((await fetch('http://127.0.0.1:3070/api/health',{signal:AbortSignal.timeout(500)})).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,200));}
if(!ready)throw Error('Startup failed');
for(const p of ['/api/posts','/api/social-accounts'])if((await fetch('http://127.0.0.1:3070'+p)).status!==401)throw Error('Anonymous boundary failed');
if(process.argv[2]!=='baseline'&&process.argv[2]!=='rollback-baseline'){
 const body={organizationId:'44289786-2583-4bf1-9db2-99eca95dfd96',actorHubUserId:'102ad8ce-df0b-4767-a3e2-b715ddbfee84',mfaVerifiedAt:null,requestNonce:'00000000-0000-4000-8000-000000000000',request:{action:'list'}};
 const r=await fetch('http://127.0.0.1:3070/api/platform/marketing-production',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
 if(r.status!==Number(process.argv[3]))throw Error('Production signature boundary failed');
 const media=await fetch('http://127.0.0.1:3070/media/production/00000000-0000-4000-8000-000000000000/'+('0'.repeat(64))+'/poster-square.png');
 if(media.status!==404)throw Error('Draft media boundary failed');
}
'''
    run(['docker','exec','-i',name,'node','--input-type=module','-',phase,'401' if enabled else '503'],probe,timeout=45)
    after=sqlite_state(name)
    require(after['digest']==before['digest'], 'Copied Marketing business/customer/provider rows changed')
    if before['productionLedgerDigest'] is not None:
        require(after['productionLedgerDigest']==before['productionLedgerDigest'], 'Copied G3 ledger changed during baseline startup')
    print(phase.upper().replace('-','_')+'_MARKETING_STARTUP_AND_DENIAL_PASS',flush=True)
    return name,before

def paired_boundary(hub, marketing):
    mark('paired-g3-signature-and-replay-boundary')
    probe=('''import assert from 'node:assert/strict';import crypto from 'node:crypto';
const org='''+json.dumps(OWNER_ORG)+''',owner='''+json.dumps(OWNER_SCOPED_ID)+''',key=process.env.V79_MARKETING_PRODUCTION_SHARED_SECRET;
async function signed(base,p,body,service){const raw=JSON.stringify(body),timestamp=String(Date.now());
 const text=['POST',p,timestamp,crypto.createHash('sha256').update(raw).digest('hex')].join('\\n');
 return fetch(base+p,{method:'POST',headers:{'content-type':'application/json','x-v79-service-id':service,'x-v79-timestamp':timestamp,
 'x-v79-signature':crypto.createHmac('sha256',key).update(text).digest('hex')},body:raw,signal:AbortSignal.timeout(5000)});}
const auth='/internal/marketing-production/authorization',prod='/api/platform/marketing-production';
let r=await signed('http://127.0.0.1:3040',auth,{organizationId:org,actorHubUserId:owner},'v79-marketing');
assert.equal(r.status,200);assert.deepEqual(await r.json(),{allowed:true,cacheSeconds:0});
r=await signed('http://127.0.0.1:3040',auth,{organizationId:org,actorHubUserId:crypto.randomUUID()},'v79-marketing');
assert.equal(r.status,200);assert.equal((await r.json()).allowed,false);
const envelope={organizationId:org,actorHubUserId:owner,mfaVerifiedAt:Date.now(),requestNonce:crypto.randomUUID(),request:{action:'list'}};
r=await signed('http://127.0.0.1:3070',prod,envelope,'v79-hub');assert.equal(r.status,200);
const state=await r.json();assert.equal(state.paused,true);assert.equal(state.publishEnabled,false);assert.equal(state.jobs.length,0);
r=await signed('http://127.0.0.1:3070',prod,envelope,'v79-hub');assert.equal(r.status,409);
r=await signed('http://127.0.0.1:3070',prod,{...envelope,requestNonce:crypto.randomUUID(),actorHubUserId:crypto.randomUUID()},'v79-hub');assert.equal(r.status,403);
r=await signed('http://127.0.0.1:3070',prod,{...envelope,requestNonce:crypto.randomUUID(),request:{action:'decision',jobId:crypto.randomUUID(),deliveryId:crypto.randomUUID(),decision:'approve',digest:'0'.repeat(64)}},'v79-hub');assert.equal(r.status,503);
''').encode()
    run(['docker','exec','-i',marketing,'node','--input-type=module','-'],probe,timeout=30)
    print('PAIRED_EXACT_FOUNDER_SIGNATURE_REPLAY_AND_PUBLICATION_DISABLED_PASS',flush=True)

def resolve_stack(name, files, extra=()):
    meta=runtime[name]
    project=meta['Config']['Labels']['com.docker.compose.project']
    root=meta['Config']['Labels']['com.docker.compose.project.working_dir']
    args=['docker','compose','--project-name',project,'--project-directory',root]
    for p in list(files)+list(extra):
        args+=['--file',str(p)]
    return json.loads(run(args+['config','--format','json']))

def normalize_approved_memory(config, service):
    result=json.loads(json.dumps(config))
    target=result['services'][service]
    value=target.get('mem_limit')
    allowed_strings={'805306368','805306368b','768m','768mb','768mib'}
    require((type(value) is int and value==805306368) or
            (isinstance(value,str) and value.lower() in allowed_strings),
            'Marketing memory limit differs from exact approved 768 MiB')
    target['mem_limit']=805306368
    return result

def read_private_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_uid == os.getuid() and
            path.stat().st_mode & 0o077 == 0 and path.stat().st_size <= 2*1024*1024, 'Private source evidence differs')
    source_document_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())

def validate_partial_identity(record, metadata):
    for name, meta in metadata.items():
        require(meta['Image'] == BASELINES[name] and meta['State']['Running'] and
                meta['State'].get('Health', {}).get('Status') == 'healthy', 'Reviewed partial image/health differs')
        if name == 'v79-hub':
            require(meta['Id'] != record['originalContainerIds'][name], 'Expected Hub-only activation recreation missing')
        else:
            require(meta['Id'] == record['originalContainerIds'][name], 'Unexpected service recreation before checkpoint refresh')
    hub_env = dict(x.split('=',1) for x in metadata['v79-hub']['Config']['Env'])
    marketing_env = dict(x.split('=',1) for x in metadata['v79marketing-app']['Config']['Env'])
    require(hub_env.get('V79_MARKETING_PRODUCTION_ENABLED') == '1' and hub_env.get('V79_WORKFORCE_ACTIONS_ENABLED') == '1' and
            marketing_env.get('V79_MARKETING_PRODUCTION_ENABLED') == '0' and
            marketing_env.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED') == '0', 'Reviewed partial activation/publication flags differ')

def verify_reviewed_partial_state():
    global source_activation_record
    for directory in (SOURCE_RECOVERY, SOURCE_CUTOVER, SOURCE_ACTIVATION):
        require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_uid == os.getuid() and
                directory.stat().st_mode & 0o077 == 0, 'Private source recovery directory differs')
    old = read_private_json(SOURCE_RECOVERY/'rehearsal-receipt.json')
    cutover = read_private_json(SOURCE_CUTOVER/'manifest.json')
    deployed = read_private_json(SOURCE_CUTOVER/'deployment-disabled.json')
    record = read_private_json(SOURCE_ACTIVATION/'manifest.json')
    failure = read_private_json(SOURCE_ACTIVATION/'failure.json')
    read_private_json(SOURCE_ACTIVATION/'switch-attempted-v79-hub.json')
    require(not (SOURCE_ACTIVATION/'switch-attempted-v79marketing-app.json').exists() and
            not (SOURCE_ACTIVATION/'generation-enabled.json').exists() and
            not (SOURCE_ACTIVATION/'reconcile-v1'/'switch-attempted-v79marketing-app.json').exists(),
            'Marketing already attempted or activation completed; inspect before refreshing')
    require(failure.get('stage') == 'activate-generation-only-v79-hub' and failure.get('attemptedServices') == ['v79-hub'] and
            failure.get('automaticRollbackPerformed') is False, 'Source failure differs from reviewed partial state')
    candidates = {'v79-hub': CANDIDATE, 'v79marketing-app': MARKETING_CANDIDATE}
    require(record.get('candidateImages') == cutover.get('candidateImages') == deployed.get('candidateImages') == candidates and
            cutover.get('baselineImages') == old.get('runtimeImages') == ROLLBACK_IMAGES and
            old.get('candidateImage') == CANDIDATE and old.get('candidateCommit') == SHA and
            old.get('marketingCandidateImage') == MARKETING_CANDIDATE and old.get('marketingCandidateCommit') == MARKETING_SHA and
            cutover.get('recoveryDirectory') == str(SOURCE_RECOVERY) and record.get('cutoverDirectory') == str(SOURCE_CUTOVER) and
            cutover.get('recoveryReceiptSha256') == source_document_hashes[str(SOURCE_RECOVERY/'rehearsal-receipt.json')] and
            old.get('preparedOverlayHashes') == cutover.get('preparedOverlayHashes') == record.get('preparedOverlayHashes'),
            'Source candidate/configuration/receipt provenance differs')
    require(deployed.get('healthy') is True and deployed.get('generationEnabled') is False and deployed.get('publicationEnabled') is False and
            record.get('generationEnabled') is True and record.get('publicationEnabled') is False,
            'Source accepted generation/publication scope differs')
    for name, digest in old['preparedOverlayHashes'].items():
        require(name in {'g3-hub-disabled.yml','g3-marketing-disabled.yml','g3-protected-keys.json'}, 'Unexpected protected key file')
        read_private_json(SOURCE_RECOVERY/name)
        require(source_document_hashes[str(SOURCE_RECOVERY/name)] == digest, 'Original backed-up G3 overlay/key changed')
    require(set(old['preparedOverlayHashes']) == {'g3-hub-disabled.yml','g3-marketing-disabled.yml','g3-protected-keys.json'}, 'Protected key file set differs')
    require(set(record['activationOverlayHashes']) == {str(SOURCE_ACTIVATION/('enable-'+name+'.yml')) for name in candidates},
            'Source activation overlay set differs')
    for path, digest in record['activationOverlayHashes'].items():
        value = read_private_json(Path(path))
        name = next(name for name in candidates if path == str(SOURCE_ACTIVATION/('enable-'+name+'.yml')))
        service = 'v79-hub' if name == 'v79-hub' else 'v79-marketing'
        require(source_document_hashes[path] == digest and value == {'services':{service:{'environment':{'V79_MARKETING_PRODUCTION_ENABLED':'1'}}}},
                'Source generation-only overlay changed')
    for path, digest in old['configurationHashes'].items():
        require(Path(path).is_file() and not Path(path).is_symlink() and hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest,
                'Original configuration changed before checkpoint refresh')
    validate_partial_identity(record, runtime)
    for name, files in [('v79-hub',HUB_FILES),('v79marketing-app',MARKETING_FILES)]:
        resolved = resolve_stack(name, files)
        expected = record['desiredResolvedConfigHashes'][name] if name == 'v79-hub' else record['originalResolvedConfigHashes'][name]
        require(hashlib.sha256(json.dumps(resolved,sort_keys=True,separators=(',',':')).encode()).hexdigest() == expected,
                'Live partial resolved configuration differs from reviewed record')
        env = dict(x.split('=',1) for x in runtime[name]['Config']['Env'])
        service = runtime[name]['Config']['Labels']['com.docker.compose.service']
        require(all(env.get(k) == str(v) for k,v in resolved['services'][service].get('environment',{}).items()),
                'Live partial environment differs from approved Compose configuration')
    require(protected_state('v79-hub-postgres') == record['hubProtectedStateSha256'] and
            sqlite_state('v79marketing-app') == record['marketingProtectedState'], 'Protected data changed since partial activation; reconcile before refresh')
    source_activation_record = record
    FILES.update(source_document_hashes)

def prepare_overlays():
    # Reuse the exact keys already backed up and accepted off host. This refresh
    # creates no signing/audit key and changes no live Compose file or flag.
    for name in ('g3-hub-disabled.yml','g3-marketing-disabled.yml','g3-protected-keys.json'):
        source = SOURCE_RECOVERY/name
        expected = source_activation_record['preparedOverlayHashes'][name]
        require(hashlib.sha256(source.read_bytes()).hexdigest() == expected, 'Backed-up G3 key/overlay changed before copy')
        with (work/name).open('xb') as output:
            output.write(source.read_bytes()); output.flush(); os.fsync(output.fileno())
        require(hashlib.sha256((work/name).read_bytes()).hexdigest() == expected, 'Copied protected configuration differs')
    return json.dumps({name:resolve_stack(name,files) for name,files in
        [('v79-hub',HUB_FILES),('v79marketing-app',MARKETING_FILES)]},sort_keys=True).encode()


def main():
    global work, ram, shared_key, audit_key
    os.umask(0o077)
    require(socket.gethostname().split('.')[0] == 'v79sl' and pwd.getpwuid(os.getuid()).pw_name == 'firelion',
            'Run only as firelion on v79sl')
    for command in ('docker', 'gpg', 'tar'):
        require(shutil.which(command), 'Missing tool: '+command)
    require(PUBLIC.is_file() and not PUBLIC.is_symlink(), 'Owner public encryption key missing')
    require(b'PRIVATE KEY' not in PUBLIC.read_bytes(), 'Expected public key only')
    require(shutil.disk_usage('/dev/shm').free > 16*1024*1024, 'Insufficient private RAM staging')
    verify_live(first=True)
    mark('verify-reviewed-partial-state-and-existing-key-custody')
    verify_reviewed_partial_state()
    receipt=json.loads(BUILD_RECEIPT.read_text())
    require(receipt.get('live_identity_unchanged') and receipt.get('deployment_performed') is False,
            'Verified build receipt missing')
    for repo,image,commit in [('V79hub',CANDIDATE,SHA),('V79Marketing',MARKETING_CANDIDATE,MARKETING_SHA)]:
        require(receipt['candidates'][repo]['image']==image and receipt['candidates'][repo]['commit']==commit,
                'Build receipt candidate differs')
        candidate=json.loads(run(['docker','image','inspect',image]))[0]
        require(candidate['Id']==image and candidate['Config']['Labels'].get('org.opencontainers.image.revision')==commit,
                'Candidate image/revision differs')
    for name in BASELINES:
        if name not in ('v79-hub','v79marketing-app'):
            require(receipt['live_containers'][name]['id']==runtime[name]['Id'], 'Unrelated live container changed after candidate build')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    work = Path(tempfile.mkdtemp(prefix='v79-g3-refresh-'+stamp+'-', dir='/home/firelion'))
    ram = Path(tempfile.mkdtemp(prefix='v79-g3-ram-', dir='/dev/shm'))
    (work/'gnupg').mkdir(mode=0o700)
    run(['gpg', '--homedir', str(work/'gnupg'), '--batch', '--quiet', '--import', str(PUBLIC)])
    keys = run(['gpg', '--homedir', str(work/'gnupg'), '--batch', '--with-colons', '--fingerprint', '--list-keys'])
    require(('fpr:::::::::'+FPR+':').encode() in keys, 'Public encryption fingerprint mismatch')
    require(b'sec:' not in run(['gpg', '--homedir', str(work/'gnupg'), '--batch', '--with-colons', '--list-secret-keys']),
            'Private key must not be present')
    (work/'STATUS').write_text('IN_PROGRESS\n')
    existing_keys = json.loads((SOURCE_RECOVERY/'g3-protected-keys.json').read_text())
    require(set(existing_keys) == {'shared','audit'} and all(isinstance(v,str) and len(v)==64 for v in existing_keys.values()) and
            existing_keys['shared'] != existing_keys['audit'], 'Existing G3 keys differ')
    shared_key=existing_keys['shared']
    audit_key=existing_keys['audit']
    mark('reuse-exact-backed-up-g3-overlays-and-protected-keys')
    resolved=prepare_overlays()
    prepared=run(['tar','-C',str(work),'-cf','-','g3-hub-disabled.yml','g3-marketing-disabled.yml','g3-protected-keys.json'])
    mark('capture-sqlite-online-and-hub-database')
    sqlite=sqlite_capture('v79marketing-app')
    dump = run(['docker', 'exec', 'v79-hub-postgres', 'pg_dump', '-U', 'v79hub', '-d', 'v79hub',
                '--format=custom', '--no-owner', '--no-acl'])
    data_tar = run(['docker', 'exec', '--user', '0', 'v79-hub', 'tar', '-C', '/app', '-cf', '-', 'data'])
    token_tar = run(['docker', 'exec', '--user', '0', 'v79-hub', 'tar', '-C', '/run/secrets', '-cf', '-',
                     'v79-agent-token', 'v79-readonly-platform-token','v79-workforce-token'])
    marketing_files=run(['docker','exec','v79marketing-app','tar','-C','/app',
        '--exclude=data/v79_marketing.sqlite','--exclude=data/v79_marketing.sqlite-wal',
        '--exclude=data/v79_marketing.sqlite-shm','-cf','-','data'])
    config_tar = run(['tar', '-C', '/', '-cf', '-'] + [x.lstrip('/') for x in FILES])
    for blob in (data_tar, token_tar, config_tar, marketing_files, prepared):
        archive_map(blob)
    backups = {}
    for name, blob in [('hub-pg.dump.gpg', dump), ('hub-data.tar.gpg', data_tar),
                       ('hub-config.tar.gpg', config_tar), ('hub-tokens.tar.gpg', token_tar),
                       ('marketing-online.sqlite.gpg',sqlite),('marketing-files.tar.gpg',marketing_files),
                       ('g3-protected-config.tar.gpg',prepared),('resolved-original-compose.json.gpg',resolved),
                       ('live-runtime-inspect.json.gpg',json.dumps(runtime).encode())]:
        backups[name] = encrypt(name, blob)
    (work/'encrypted-checksums.sha256').write_text(''.join(digest+'  '+name+'\n' for name,digest in backups.items()))
    print('FRESH_NINE_ENCRYPTED_BACKUPS_AND_G3_KEY_BACKUP_CREATED', flush=True)
    original_marketing,marketing_before=marketing_smoke(BASELINES['v79marketing-app'],'baseline',sqlite,marketing_files)
    require(marketing_before['founderLinks']==[{'businessId':OWNER_ORG,'organizationId':OWNER_ORG,'scopedHubUserId':OWNER_SCOPED_ID}],
            'Copied exact founder mapping differs')
    remove(original_marketing)
    candidate_marketing,state=marketing_smoke(MARKETING_CANDIDATE,'candidate-disabled',sqlite,marketing_files)
    require(state['digest']==marketing_before['digest'],'Candidate copied business state differs')
    remove(candidate_marketing)
    print('MARKETING_SQLITE_ONLINE_SNAPSHOT_RESTORE_AND_DISABLED_CANDIDATE_PASS',flush=True)
    db = 'v79-g3-rehearsal-pg-'+nonce
    mark('create-scratch-postgres')
    create(db, ['--network', 'none', '--read-only', '--security-opt', 'no-new-privileges',
        '--pids-limit', '128', '--memory', '384m', '--cpus', '0.5',
        '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev,size=192m',
        '--tmpfs', '/var/run/postgresql:rw,nosuid,nodev,size=8m',
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=16m', '-e', 'POSTGRES_USER=v79hub',
        '-e', 'POSTGRES_DB=v79hub', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', BASELINES['v79-hub-postgres']])
    mark('start-scratch-postgres')
    run(['docker', 'start', db])
    require(only_tmpfs(inspect(db)) and inspect(db)['HostConfig']['NetworkMode'] == 'none', 'Scratch DB isolation differs')
    for attempt in range(45):
        ready = subprocess.run(['docker', 'exec', db, 'pg_isready', '-q', '-U', 'v79hub', '-d', 'v79hub'], capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Scratch database startup timed out')
    mark('restore-captured-database')
    run(['docker', 'exec', '-i', db, 'pg_restore', '-U', 'v79hub', '-d', 'v79hub',
         '--exit-on-error', '--no-owner', '--no-acl'], dump)
    # Verify all restored table data before starting either application image.
    mark('compare-restored-database')
    restored = run(['docker', 'exec', db, 'pg_dump', '-U', 'v79hub', '-d', 'v79hub',
                    '--data-only', '--no-owner', '--no-acl'])
    source = run(['docker', 'exec', '-i', db, 'pg_restore', '--data-only', '--no-owner', '--no-acl', '--file=-'], dump)
    require(table_data(restored) == table_data(source), 'Restored rows/sequences differ from captured dump')
    state_before = protected_state(db)
    require(int(psql(db, "SELECT count(*) FROM v79_hub_state WHERE store_key='main'")) == 1,
            'Expected one restored Hub state')
    print('FRESH_DATABASE_RESTORE_PASS', flush=True)
    for phase, image, enabled in [('baseline', BASELINES['v79-hub'], False),
                                  ('candidate-disabled', CANDIDATE, False)]:
        hub_smoke(db, image, phase, data_tar, token_tar, enabled)
        require(protected_state(db) == state_before, 'Copied identities/billing changed during '+phase)
    hub=hub_smoke(db,CANDIDATE,'candidate-enabled',data_tar,token_tar,True,keep=True)
    marketing,state=marketing_smoke(MARKETING_CANDIDATE,'candidate-enabled',sqlite,marketing_files,True,db)
    paired_boundary(hub,marketing)
    require(sqlite_state(marketing)['digest']==marketing_before['digest'],'Paired test changed protected Marketing rows')
    upgraded_sqlite=sqlite_capture(marketing)
    remove(marketing)
    remove(hub)
    require(protected_state(db)==state_before,'Paired test changed copied Hub identities/billing/workforce ledger')
    rollback,state=marketing_smoke(ROLLBACK_IMAGES['v79marketing-app'],'rollback-baseline',upgraded_sqlite,marketing_files)
    require(state['digest']==marketing_before['digest'],'Rollback changed Marketing business state')
    remove(rollback)
    hub_smoke(db,ROLLBACK_IMAGES['v79-hub'],'rollback-baseline',data_tar,token_tar,False)
    require(protected_state(db)==state_before,'Rollback changed copied Hub protected state')
    mark('cleanup-and-live-drift-check')
    remove(db)
    verify_live()
    require(protected_state('v79-hub-postgres') == source_activation_record['hubProtectedStateSha256'] and
            sqlite_state('v79marketing-app') == source_activation_record['marketingProtectedState'],
            'Live protected state drifted during fresh rehearsal')
    receipt = {'version':1, 'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'candidateCommit':SHA, 'candidateImage':CANDIDATE,
        'marketingCandidateCommit':MARKETING_SHA,'marketingCandidateImage':MARKETING_CANDIDATE,
        'runtimeImages':BASELINES,
        'configurationHashes':FILES, 'encryptedBackups':backups,
        'snapshotRestoreVerified':True, 'isolatedStartupRollbackVerified':True,
        'encryptedBackupDecryptionVerified':False, 'liveDeploymentPerformed':False,
        'liveOwnerAcceptanceVerified':False, 'copiedIdentityBillingPreserved':True,
        'scratchCleanupVerified':True, 'liveContainerIdsUnchanged':True,
        'scope':'Hub DB/files/tokens restore and startup-only rollback; no real release-worker deployment rehearsal'}
    receipt.update(marketingOnlineSnapshotSha256=hashlib.sha256(sqlite).hexdigest(),
        crossServiceSnapshotAtomic=False,
        marketingOnlineBackupRestored=True,marketingOriginalAndCandidateStartupVerified=True,
        marketingRollbackWithCopiedG3SchemaVerified=True,pairedG3SignatureReplayAndPublishDisabledVerified=True,
        copiedG2AcceptedWorkItemPreserved=True,ownerConnectedPlatforms=marketing_before['ownerConnectedPlatforms'],
        preparedOverlayHashes={name:hashlib.sha256((work/name).read_bytes()).hexdigest() for name in
            ['g3-hub-disabled.yml','g3-marketing-disabled.yml','g3-protected-keys.json']},
        scope='Copied Hub PostgreSQL and Marketing online SQLite/data/config restore; paired signature/replay boundaries and original-image startup against upgraded copied state. No live cutover or external provider test.')
    receipt.update(mode='fresh-checkpoint-for-reviewed-partial-activation',
        sourceRecoveryDirectory=str(SOURCE_RECOVERY),sourceCutoverDirectory=str(SOURCE_CUTOVER),
        sourceActivationDirectory=str(SOURCE_ACTIVATION),sourceDocumentHashes=source_document_hashes,
        existingG3KeysReused=True,liveGenerationFlags={'v79-hub':'1','v79marketing-app':'0'},
        livePublicationEnabled=False,liveRuntimeIds={name:meta['Id'] for name,meta in runtime.items()},
        rollbackImages=ROLLBACK_IMAGES,hubProtectedStateSha256=source_activation_record['hubProtectedStateSha256'],
        marketingProtectedState=source_activation_record['marketingProtectedState'],
        scope='Fresh encrypted current partial-state checkpoint with copied database/files restore, original-image startup rollback and paired G3 signature/replay tests. Existing G3 keys reused; no live recreation, config edit or provider send.')
    (work/'rehearsal-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    (work/'STATUS').write_text('ISOLATED_REHEARSAL_PASS_LIVE_DEPLOYMENT_NOT_PERFORMED\n')
    reference = {'version':1,'directory':str(work),
        'receiptSha256':hashlib.sha256((work/'rehearsal-receipt.json').read_bytes()).hexdigest(),
        'createdAt':receipt['capturedAt'],'offhostDecryptionVerified':False}
    pointer = SOURCE_ACTIVATION/'fresh-checkpoint-reference.json'
    require(not pointer.is_symlink(), 'Fresh checkpoint reference must not be a symlink')
    if pointer.exists():
        require(pointer.is_file() and pointer.stat().st_uid==os.getuid() and pointer.stat().st_mode & 0o077==0,
                'Existing checkpoint reference permissions differ')
    temporary = SOURCE_ACTIVATION/('.fresh-checkpoint-'+nonce+'.tmp')
    with temporary.open('x') as output:
        json.dump(reference,output,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
    os.replace(temporary,pointer)
    descriptor=os.open(str(SOURCE_ACTIVATION),os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print('COPIED_IDENTITIES_BILLING_PROVIDER_RECORDS_AND_G2_ACCEPTED_TASK_PRESERVED')
    print('OWNER_CONNECTED_PLATFORM_COUNTS='+json.dumps(marketing_before['ownerConnectedPlatforms']))
    print('SCRATCH_CLEANUP_AND_LIVE_CONTAINERS_UNCHANGED_PASS')
    print('RECOVERY_DIRECTORY='+str(work))
    print('EXISTING_G3_KEYS_REUSED_CURRENT_PARTIAL_STATE_CHECKPOINT_PASS')
    print('OFFHOST_NINE_FRESH_BACKUP_DECRYPTIONS_REQUIRED_BEFORE_MARKETING_RECONCILIATION')

if __name__ == '__main__':
    failed = False
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        failed = True
        # Only our own bounded messages may be displayed; suppress raw errors.
        print('STOP: '+(str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__))
        if work:
            print('RECOVERY_DIRECTORY='+str(work))
            (work/'STATUS').write_text('INCOMPLETE_NOT_DEPLOYABLE\n')
    finally:
        for name in list(reversed(created)):
            try:
                remove(name)
            except Exception:
                failed = True
                print('SCRATCH_CLEANUP_INCOMPLETE='+name)
        if ram:
            shutil.rmtree(ram)
        if not created:
            print('OWNED_SCRATCH_CONTAINERS_REMOVED')
    sys.exit(2 if failed else 0)
