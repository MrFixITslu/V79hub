#!/usr/bin/env python3
"""Fresh encrypted backups + copied-state startup/rollback checks. Never deploy."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

BUILD=Path('/home/firelion/v79-g3-tracking-build-1qcu4yh_')
EXPECTED={
 'V79hub':{'commit':'045d68a61257c758f2f6ca229d050e4e7a7df618','tree':'d1157d636ede68b5981a4c69306f1d29cf58041c','image':'sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06','tag':'v79-hub-tracking:045d68a61257'},
 'V79Marketing':{'commit':'de806c5c8db2d798ecb94621e3e1b04e9d7c8592','tree':'15595d37621996d866100e6a57297e5406006b2c','image':'sha256:32641b8f302b4ec38a56167ee6df9d5e0a185bf017431fa86f5bb9f462f7eaf3','tag':'v79-marketing-tracking:de806c5c8db2'}}
NONCE=secrets.token_hex(8)
LABEL='v79.tracking-recovery'
created=[]
removal_requested=set()
cleanup_uncertain=set()
h=None
root=None
ram=None

BASIS=r"""const Database=require('better-sqlite3'),crypto=require('node:crypto');
const canonical=v=>JSON.stringify(v,(_k,x)=>typeof x==='bigint'?{__sqlite_integer:String(x)}:x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const hash=v=>crypto.createHash('sha256').update(canonical(v)).digest('hex');
const db=new Database(process.env.DATABASE_PATH||'/app/data/v79_marketing.sqlite',{readonly:true,fileMustExist:true});
try{db.pragma('query_only=ON');db.defaultSafeIntegers(true);db.exec('BEGIN');
if(db.pragma('integrity_check',{simple:true})!=='ok')throw Error('SQLite integrity');
const tables=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all().map(x=>x.name),protectedTables={};
for(const name of tables){if(['audit_logs','platform_event_outbox','marketing_production_state','production_post_links'].includes(name))continue;
 if(!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name))throw Error('Table name');const rows=db.prepare('SELECT * FROM "'+name+'"').all();if(rows.length>50000)throw Error('Row bound');protectedTables[name]=hash(rows.map(canonical).sort());}
const ledgers=db.prepare('SELECT business_id,envelope FROM marketing_production_state ORDER BY business_id').all(),states=[],counts={packages:{},deliveries:{}},confirmed=[];let founder=false;
for(const row of ledgers){const {state,hmac}=JSON.parse(row.envelope),mac=crypto.createHmac('sha256',process.env.V79_MARKETING_PRODUCTION_AUDIT_KEY).update('v79-marketing-production-v1\n'+row.business_id+'\n'+canonical(state)).digest('hex');
 if(!/^[a-f0-9]{64}$/.test(hmac||'')||!crypto.timingSafeEqual(Buffer.from(mac),Buffer.from(hmac)))throw Error('Signed ledger integrity');
 if(row.business_id==='44289786-2583-4bf1-9db2-99eca95dfd96'){
  founder=true;
  if(state.ownerHubUserId!=='102ad8ce-df0b-4767-a3e2-b715ddbfee84')throw Error('Founder mapping');
  for(const j of state.jobs){counts.packages[j.status]=(counts.packages[j.status]||0)+1;
   if(['queued','generating'].includes(j.status))throw Error('Production active');
   for(const d of j.deliveries){counts.deliveries[d.status]=(counts.deliveries[d.status]||0)+1;
    if(['running','uncertain'].includes(d.status))throw Error('Provider effect requires reconciliation');
    if(d.status==='approved'&&(!Number.isFinite(Date.parse(d.scheduledAt))||Date.parse(d.scheduledAt)-Date.now()<=1800000))throw Error('Approved publication due within the thirty-minute release buffer');
    if(d.status==='succeeded')confirmed.push({jobId:j.id,deliveryId:d.id,channel:d.channel,providerPostId:d.result?.providerPostId||null,recorded:!!d.result?.marketingPostId});}}
  if(!state.paused&&state.plan?.automaticDrafts){const last=Date.parse(state.lastAutomaticAt||''),cadence=state.plan.cadenceDays;
   if(!Number.isInteger(cadence)||cadence<3||cadence>30||!Number.isFinite(last)||last>Date.now()||last+cadence*86400000-Date.now()<=1800000)throw Error('Automatic production due within release buffer');}}
 delete state.seenRequests;states.push({businessId:row.business_id,state});}
if(!founder)throw Error('Founder ledger missing');
const links=tables.includes('production_post_links')?db.prepare('SELECT * FROM production_post_links ORDER BY post_id').all():[];
db.exec('COMMIT');console.log(canonical({protectedTables,signedLedgerSha256:hash(states),trackingLinksSha256:hash(links),trackingLinksCount:links.length,hasTrackingSchema:tables.includes('production_post_links'),counts,confirmed}));
}finally{db.close();}"""


def require(ok,message):
 if not ok:raise RuntimeError(message)


def load(commit,name,expected):
 with urllib.request.urlopen('https://raw.githubusercontent.com/MrFixITslu/V79hub/'+commit+'/scripts/'+name,timeout=30) as response:code=response.read(1048577)
 require(hashlib.sha256(code).hexdigest()==expected,'Pinned recovery support integrity differs')
 ns={'__name__':'tracking_recovery_support'};exec(compile(code,'<verified-tracking-recovery-support>','exec'),ns);return ns


def mark(value):
 if h:h['stage']=value
 print('STAGE='+value,flush=True)


def basis(name):
 allowed=('SQLite integrity','Table name','Row bound','Signed ledger integrity','Founder mapping','Founder ledger missing','Production active',
  'Provider effect requires reconciliation','Approved publication due within the thirty-minute release buffer','Automatic production due within release buffer')
 program='try{'+BASIS+'}catch(e){const allowed='+json.dumps(allowed)+";console.log(JSON.stringify({error:allowed.includes(e.message)?e.message:'Protected snapshot unavailable'}));}"
 result=json.loads(h['run'](['docker','exec','-i',name,'node','--input-type=commonjs','-'],data=program.encode()))
 require('error' not in result,'Read-only Marketing check: '+result.get('error','unknown'))
 return result


def protected_equal(before,after,require_schema=False):
 for key in ('protectedTables','signedLedgerSha256','trackingLinksSha256','trackingLinksCount'):
  require(before[key]==after[key],'Copied Marketing data or approved campaign state changed: '+key)
 if require_schema:require(after['hasTrackingSchema'] is True,'Candidate tracking schema missing')


def cleanup_one(name):
 def inspect_owned():
  result=subprocess.run(['docker','inspect',name],capture_output=True,timeout=15)
  if result.returncode:
   require(any(v in result.stderr.lower() for v in (b'no such object',b'no such container')),'Scratch cleanup could not be verified')
   return None
  meta=json.loads(result.stdout)[0]
  require(meta['Config']['Labels'].get(LABEL)==NONCE,'Scratch ownership label differs; not removed')
  return meta
 meta=inspect_owned()
 if meta is None:return
 require(name not in cleanup_uncertain,'Previous scratch removal remains uncertain; inspect before another rehearsal')
 mark('confirm-owned-scratch-removal-'+name)
 process=None
 try:
  # A timed-out Docker client does not prove the daemon stopped removing.
  # Send at most one request, then wait for inspect to confirm absence.
  if meta['State']['Status']!='removing':
   require(name not in removal_requested,'Scratch removal was already requested; inspect before retry')
   removal_requested.add(name)
   process=subprocess.Popen(['docker','rm','--force',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  deadline=time.monotonic()+300;next_report=time.monotonic()+15
  while True:
   meta=inspect_owned()
   if meta is None:
    print('OWNED_SCRATCH_REMOVAL_CONFIRMED='+name,flush=True)
    return
   require(not process or process.poll() in (None,0) or meta['State']['Status']=='removing','Scratch removal request failed; inspect before retry')
   now=time.monotonic()
   require(now<deadline,'Scratch removal still pending after five minutes; inspect before retry')
   if now>=next_report:
    print('WAITING_FOR_DOCKER_SCRATCH_REMOVAL='+name,flush=True);next_report=now+15
   time.sleep(2)
 except BaseException:
  cleanup_uncertain.add(name)
  raise
 finally:
  if process:
   # Reap only this CLI child; never signal Docker or containerd.
   try:process.wait(timeout=2)
   except subprocess.TimeoutExpired:
    process.kill();process.wait(timeout=5)


def scratch(image,phase,database,assets,baseline,runtime):
 mark('copied-marketing-'+phase)
 name='v79-tracking-'+phase+'-'+NONCE
 environment=h['env_map'](runtime['v79marketing-app']['Config']['Env'])
 for key in list(environment):
  if 'URL' in key:environment[key]='http://127.0.0.1:1'
 environment.update(NODE_ENV='production',PORT='3070',DATABASE_PATH='/app/data/v79_marketing.sqlite',APP_URL='https://marketing.v79sl.com',
  V79_MARKETING_PRODUCTION_ENABLED='1',V79_MARKETING_PRODUCTION_PUBLISH_ENABLED='1',V79_ENTITLEMENT_RECHECK_ENABLED='1',
  V79_MARKETING_SEED_DEMO='0',V79_ENABLE_SIMULATED_PUBLISHER='0',V79_ALLOW_LEGACY_LOGIN='0',
  V79_HUB_INTERNAL_URL='http://127.0.0.1:1',OLLAMA_BASE_URL='',V79_PRODUCTION_ASSET_DIR='/app/data/production-assets')
 require(not any('\n' in v or '\r' in v for v in environment.values()),'Multiline environment unsupported')
 env_path=ram/(phase+'.env');env_path.write_text(''.join(k+'='+v+'\n' for k,v in environment.items()));env_path.chmod(0o600)
 args=['docker','create','--name',name,'--label',LABEL+'='+NONCE,'--pull','never','--network','none','--read-only','--user','node',
  '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','768m','--cpus','1',
  '--tmpfs','/app/data:rw,nosuid,nodev,uid=1000,gid=1000,mode=0700,size=128m','--tmpfs','/tmp:rw,nosuid,nodev,mode=1777,size=64m',
  '--env-file',str(env_path),'--entrypoint','/bin/sh',image,'-c','while [ ! -f /tmp/recovery-ready ]; do sleep 0.1; done; exec node dist/server.cjs']
 created.append(name);h['run'](args);h['run'](['docker','start',name])
 meta=h['inspect'](name)
 require(meta['HostConfig']['NetworkMode']=='none' and meta['HostConfig']['ReadonlyRootfs'] is True and meta['Config']['User']=='node' and
  not meta['HostConfig'].get('PortBindings') and all(m.get('Type')=='tmpfs' for m in meta['Mounts']),'Scratch isolation differs')
 h['run'](['docker','exec','-i',name,'sh','-c','cat > /app/data/v79_marketing.sqlite'],data=database)
 h['run'](['docker','exec','-i',name,'tar','-C','/app','-xf','-'],data=assets)
 h['run'](['docker','exec',name,'touch','/tmp/recovery-ready'])
 ready=False
 probe=b"fetch('http://127.0.0.1:3070/api/health',{signal:AbortSignal.timeout(1000)}).then(r=>console.log(r.ok?'READY':'WAIT')).catch(()=>console.log('WAIT'));"
 for _ in range(45):
  if b'READY' in h['run'](['docker','exec','-i',name,'node','--input-type=module','-'],data=probe):ready=True;break
  time.sleep(0.5)
 require(ready,'Copied Marketing startup did not become healthy')
 after=basis(name);protected_equal(baseline,after,require_schema=phase=='candidate')
 denial=b"import assert from 'node:assert/strict';const b='http://127.0.0.1:3070';for(const p of ['/api/posts','/api/post-deliveries','/api/social-accounts'])assert.equal((await fetch(b+p,{signal:AbortSignal.timeout(2000)})).status,401);assert.equal((await fetch(b+'/media/production/00000000-0000-4000-8000-000000000000/'+('0'.repeat(64))+'/short.mp4')).status,404);console.log('COPIED_AUTH_AND_PRIVATE_DRAFT_PASS');"
 require(b'COPIED_AUTH_AND_PRIVATE_DRAFT_PASS' in h['run'](['docker','exec','-i',name,'node','--input-type=module','-'],data=denial),'Copied authentication checks missing')
 print(phase.upper()+'_COPIED_SQLITE_SIGNED_APPROVALS_STARTUP_AND_DENIAL_PASS',flush=True)
 return name,after


def main():
 global h,root,ram
 os.umask(0o077)
 require(socket.gethostname().split('.')[0]=='v79sl' and os.getuid()==1000 and pwd.getpwuid(os.getuid()).pw_name=='firelion','Run as firelion on v79sl')
 h=load('638fb3cb5b52d6f627014a4c2cb6d3ad6f29bbe7','marketing-production-reconcile-fresh-generation.py','5fedd5e0f7a36bd2e10111bb373d745fc813620664e9eda949ddbc603d769e39')
 builder=load('4dd78c25c23cc42f7069145210edabcd83fee9f1','marketing-production-tracking-build.py','b726c9cc780e7394ddd45337e66d83ddfd5905b6a2e03c920420068541770f85')
 capture=load('c8cd7c1a0022d50b7a786e18c8765f140c80a09f','marketing-production-recovery-rehearsal.py','e0006b73a8ae47c447de8e12d49214247c9288ac38893758a6408fd2e1bfa65c')
 mark('verify-passed-immutable-build-and-current-runtime')
 receipt_path=BUILD/'tracking-build-receipt.json';receipt_hash=h['file_hash'](receipt_path,True);receipt=json.loads(receipt_path.read_text())
 require(receipt.get('deploymentPerformed') is False and receipt.get('runtimeSourceVerified') is True and receipt.get('publicationEnabled') is True,'Passed build receipt scope differs')
 for repo,expected in EXPECTED.items():
  item=receipt['candidates'][repo]
  require(all(item.get(k)==v for k,v in expected.items()) and item.get('isolatedTestsPassed') is True and item.get('sourceScopeVerified') is True,'Tested immutable image evidence differs')
  meta=json.loads(h['run'](['docker','image','inspect',expected['image']]))[0]
  require(meta['Id']==expected['image'] and meta['Config']['Labels'].get('org.opencontainers.image.revision')==expected['commit'],'Candidate image provenance differs')
 before=builder['snapshot']();require(before==receipt['liveRuntime'],'Live services changed since passed build; inspect before checkpoint')
 require(not h['run'](['docker','ps','--all','--filter','label='+LABEL,'--format','{{.ID}}']).strip(),'An earlier tracking scratch container still exists; inspect before retry')
 runtime={name:h['inspect'](name) for name in before}
 mark('verify-signed-idle-window-and-preserved-approved-schedules')
 baseline=basis('v79marketing-app');hub_state=h['protected_state']('v79-hub-postgres')
 require(shutil.disk_usage('/home/firelion').free>2*1024**3,'Insufficient backup space')
 root=Path(tempfile.mkdtemp(prefix='v79-g3-tracking-recovery-',dir='/home/firelion'))
 ram=Path(tempfile.mkdtemp(prefix='v79-tracking-'+NONCE+'-',dir='/dev/shm'))
 print('RECOVERY_DIRECTORY='+str(root),flush=True)
 support=load('c659116623d42303b07660c37883ebe5f6eaa194','marketing-production-panel-cutover.py','c13f87a5cf22c14780315c501d62668d8e4f7a1c256c7e557f7ccf0723614c21')
 support.update(helper=h,WORK=root)
 mark('verify-public-only-encryption-key')
 public_hash=support['prepare_public_keyring']()
 mark('capture-fresh-hub-and-marketing-recovery')
 files=set(['/opt/v79/hub/.env','/home/firelion/V79Marketing/.env']);resolved={};stacks={}
 for name in ('v79-hub','v79marketing-app'):
  labels=runtime[name]['Config']['Labels'];stack=labels['com.docker.compose.project.config_files'].split(',');stacks[name]=stack;files.update(stack)
  args=['docker','compose','--project-name',labels['com.docker.compose.project'],'--project-directory',labels['com.docker.compose.project.working_dir']]
  for filename in stack:args+=['--file',filename]
  resolved[name]=json.loads(h['run'](args+['config','--format','json']))
  require(resolved[name]['services'][labels['com.docker.compose.service']]['image']==runtime[name]['Image'],'Original app image is not pinned to runtime')
  for mount in runtime[name]['Mounts']:
   if mount.get('Type')=='bind' and Path(mount['Source']).is_file():files.add(mount['Source'])
 source_hashes={p:h['file_hash'](p) for p in sorted(files)}
 sqlite=capture['sqlite_capture']('v79marketing-app')
 assets=h['run'](['docker','exec','v79marketing-app','tar','-C','/app','--exclude=data/v79_marketing.sqlite','--exclude=data/v79_marketing.sqlite-wal','--exclude=data/v79_marketing.sqlite-shm','-cf','-','data'],timeout=120)
 dump=h['run'](['docker','exec','v79-hub-postgres','pg_dump','-U','v79hub','-d','v79hub','-Fc'],timeout=120)
 hub_data=h['run'](['docker','exec','--user','0','v79-hub','tar','-C','/app','-cf','-','data'],timeout=120)
 blobs={'hub-pg.dump.gpg':dump,'hub-data.tar.gpg':hub_data,'marketing-online.sqlite.gpg':sqlite,'marketing-files.tar.gpg':assets,
  'runtime-config.json.gpg':json.dumps({'runtime':runtime,'resolved':resolved,'originalStacks':stacks,'sourceFiles':{p:Path(p).read_text() for p in files}},sort_keys=True).encode()}
 encrypted={};clear={}
 for name,blob in blobs.items():
  h['run'](support['encryption_command']()+['--output',str(root/name),'--encrypt'],data=blob,timeout=120)
  encrypted[name]=h['file_hash'](root/name,True);clear[name]=hashlib.sha256(blob).hexdigest()
 print('FIVE_FRESH_ENCRYPTED_RECOVERY_BACKUPS_CREATED',flush=True)
 original_image=runtime['v79marketing-app']['Image']
 name,_=scratch(original_image,'baseline',sqlite,assets,baseline,runtime);cleanup_one(name)
 name,candidate_basis=scratch(EXPECTED['V79Marketing']['image'],'candidate',sqlite,assets,baseline,runtime)
 upgraded=capture['sqlite_capture'](name);cleanup_one(name)
 name,_=scratch(original_image,'rollback',upgraded,assets,candidate_basis,runtime);cleanup_one(name)
 mark('verify-scratch-cleanup-and-live-preservation')
 protected_equal(baseline,basis('v79marketing-app'))
 require(builder['snapshot']()==before and h['protected_state']('v79-hub-postgres')==hub_state,'Live runtime, billing, identities or G2 state changed')
 require(all(h['file_hash'](p)==digest for p,digest in source_hashes.items()) and h['file_hash'](receipt_path,True)==receipt_hash,'Compose, key files or tested build receipt changed')
 manifest={'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'buildReceipt':str(receipt_path),'buildReceiptSha256':receipt_hash,'candidates':EXPECTED,
  'liveRuntime':before,'originalStacks':stacks,'originalResolvedHashes':{k:h['fingerprint'](v) for k,v in resolved.items()},'sourceHashes':source_hashes,
  'marketingBasis':baseline,'hubProtectedStateSha256':hub_state,'publicKeySha256':public_hash,'encryptedBackups':encrypted,'plaintextHashes':clear,
  'copiedOnlineRestoreVerified':True,'copiedCandidateMigrationAndRollbackVerified':True,'signedCampaignsAndSchedulesPreserved':True,'scratchCleanupVerified':True,
  'liveDeploymentPerformed':False,'publicationEnabled':True}
 h['write_json'](root/'recovery-receipt.json',manifest)
 with (root/'encrypted-checksums.sha256').open('x') as output:output.write(''.join(digest+'  '+name+'\n' for name,digest in encrypted.items()))
 print('TRACKING_SCHEMA_COPIED_RESTORE_AND_ROLLBACK_PASS')
 print('LIVE_ACCOUNTS_BILLING_G2_APPROVALS_PROVIDER_RECORDS_AND_SERVICES_UNCHANGED')
 print('CAMPAIGN_STATUS_COUNTS='+json.dumps(baseline['counts'],sort_keys=True))
 print('CONFIRMED_PROVIDER_RECEIPTS='+json.dumps(baseline['confirmed'],sort_keys=True))
 print('RECOVERY_DIRECTORY='+str(root))
 print('OFFHOST_FIVE_BACKUP_DECRYPTIONS_AND_IMAGE_ONLY_DEPLOYMENT_PENDING')


if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as exc:
  print('STOP: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__))
  if root:print('RECOVERY_DIRECTORY='+str(root))
  print('NO_LIVE_RECREATION_UPLOAD_OR_CAMPAIGN_CLEANUP_ATTEMPTED')
  raise SystemExit(1)
 finally:
  for name in reversed(created):
   try:cleanup_one(name)
   except Exception:print('STOP: owned scratch cleanup requires inspection: '+name)
  if ram:shutil.rmtree(ram,ignore_errors=True)
