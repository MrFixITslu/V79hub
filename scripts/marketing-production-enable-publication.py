#!/usr/bin/env python3
"""Run on Acer: back up Marketing, verify off-host decryption, enable exact approvals."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import tempfile

ENCRYPTED = ('marketing-online.sqlite.gpg', 'marketing-files.tar.gpg', 'marketing-runtime-config.json.gpg')

REMOTE_PROGRAM = r'''
import copy,datetime,fcntl,hashlib,json,os,pathlib,pwd,secrets,socket,sys,tempfile,urllib.request
Path=pathlib.Path
ROOT=Path('/home/firelion/v79-g3-publication-v1')
UI=Path('/home/firelion/v79-g3-ui-cutover-8d82b21a4def-v3')
MARKETING='v79marketing-app'
SERVICE='v79-marketing'
PROJECT='v79marketing'
DIRECTORY='/home/firelion/V79Marketing'
FLAG='V79_MARKETING_PRODUCTION_PUBLISH_ENABLED'
IMAGE='sha256:e34d3c22f325c7fef78bc79bf96aa3386c10a45a7d2fd3e4e5081d39e9d4e0e8'
HUB_IMAGE='sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e'
NAMES=('v79-hub',MARKETING,'v79-business-agent','v79-hub-postgres','v79-tiquet-manager','tiquet-postgres')
GEN='/home/firelion/v79-g3-cutover-c42f671f4ccd-b7934c03f0e3-v2/generation-only-v1'
FILES=[DIRECTORY+'/docker-compose.yml','/home/firelion/v79-g3-recovery-20261014T220437Z-bp9zg67v/g3-marketing-disabled.yml',GEN+'/enable-v79marketing-app.yml']
BACKUPS=('marketing-online.sqlite.gpg','marketing-files.tar.gpg','marketing-runtime-config.json.gpg')
h=None;support=None;attempted=False;stage='preflight'
def require(ok,message):
 if not ok:raise RuntimeError(message)
def mark(value):
 global stage
 stage=value
 if h:h['stage']=value
 print('STAGE='+value,file=sys.stderr,flush=True)
def load(commit,name,digest):
 url='https://raw.githubusercontent.com/MrFixITslu/V79hub/'+commit+'/scripts/'+name
 with urllib.request.urlopen(url,timeout=30) as r:code=r.read(1048577)
 require(hashlib.sha256(code).hexdigest()==digest,'Pinned support integrity differs')
 ns={'__name__':'publication_support_only'};exec(compile(code,'<verified-publication-support>','exec'),ns);return ns
def sha(blob):return hashlib.sha256(blob).hexdigest()
def command(files):
 args=['docker','compose','--project-name',PROJECT,'--project-directory',DIRECTORY]
 for path in files:args+=['--file',str(path)]
 return args
def resolve(files):return json.loads(h['run'](command(files)+['config','--format','json']))
def parity(before,after):
 expected=copy.deepcopy(before);expected['services'][SERVICE]['environment'][FLAG]='1'
 require(after==expected,'Publication overlay changes more than the single flag')
def host(meta):
 result=copy.deepcopy(meta['HostConfig'])
 if isinstance(result.get('Binds'),list):result['Binds']=sorted(result['Binds'])
 return result
def runtime_parity(before,after,configured_hostname):
 require(h['healthy'](after) and before['Image']==after['Image']==IMAGE and after['Id']!=before['Id'],'Marketing image, health or recreation differs')
 a,b=copy.deepcopy(before['Config']),copy.deepcopy(after['Config'])
 old_labels,new_labels=a.pop('Labels'),b.pop('Labels')
 env=h['env_map'](a.pop('Env'));env[FLAG]='1'
 require(h['env_map'](b.pop('Env'))==env,'Environment changed beyond publication flag')
 if configured_hostname is None:
  require(a.pop('Hostname')==before['Id'][:12] and b.pop('Hostname')==after['Id'][:12],'Docker-generated hostname differs')
 else:require(a.get('Hostname')==b.get('Hostname')==configured_hostname,'Explicit hostname changed')
 require(a==b and host(before)==host(after) and h['mounts'](before)==h['mounts'](after) and sorted(before['NetworkSettings']['Networks'])==sorted(after['NetworkSettings']['Networks']),'Marketing runtime, resources, mounts or networks changed')
 require(old_labels['com.docker.compose.project.config_files']==','.join(FILES) and new_labels['com.docker.compose.project.config_files']==','.join(FILES+[str(ROOT/'publication.yml')]),'Publication Compose provenance differs')
 for labels in (old_labels,new_labels):
  for key in ('com.docker.compose.project.config_files','com.docker.compose.config-hash'):labels.pop(key,None)
 require(old_labels==new_labels,'Marketing labels changed beyond Compose configuration')
def snapshot():
 values={name:h['inspect'](name) for name in NAMES}
 require(all(h['healthy'](v) for v in values.values()),'An application is not healthy')
 require(values['v79-hub']['Image']==HUB_IMAGE and values[MARKETING]['Image']==IMAGE,'Accepted image differs')
 for name in ('v79-hub',MARKETING):require(h['env_map'](values[name]['Config']['Env']).get('V79_MARKETING_PRODUCTION_ENABLED')=='1','Generation must remain enabled')
 return values
def runtime_hashes(values):return {name:h['fingerprint'](h['stable_runtime'](v)) for name,v in values.items()}
def signed_state():
 # Reuse the verified read-only HMAC/scheduler guard, additionally refusing
 # approved or uncertain effects so this switch itself cannot release a post.
 source=support['MARKETING_STATE'].replace("d.status==='running'","['approved','running','uncertain'].includes(d.status)")
 require(source!=support['MARKETING_STATE'],'Publication idle guard not installed')
 return h['run'](['docker','exec','-i',MARKETING,'node','--input-type=commonjs','-'],data=source.encode()).decode().strip()
def protected():return {'hub':h['protected_state']('v79-hub-postgres'),'marketing':h['sqlite_state'](MARKETING)['digest'],'campaigns':signed_state()}
def source_hashes(runtime):
 paths=set(FILES+[DIRECTORY+'/.env','/opt/v79/hub/.env',str(UI/'deployed.json')])
 for meta in runtime.values():
  for path in (meta['Config'].get('Labels') or {}).get('com.docker.compose.project.config_files','').split(','):
   if path:paths.add(path)
  for mount in meta.get('Mounts',[]):
   if mount.get('Type')=='bind' and Path(mount['Source']).is_file():paths.add(mount['Source'])
 return {path:h['file_hash'](path) for path in sorted(paths)}
def check_disabled(runtime):
 meta=runtime[MARKETING];labels=meta['Config']['Labels'];env=h['env_map'](meta['Config']['Env'])
 require(env.get(FLAG)=='0','Publication already active or partial; inspect instead of retrying')
 require(labels.get('com.docker.compose.project')==PROJECT and labels.get('com.docker.compose.service')==SERVICE and labels.get('com.docker.compose.project.working_dir')==DIRECTORY and labels.get('com.docker.compose.project.config_files')==','.join(FILES),'Accepted Marketing stack differs')
 require(env.get('V79_MARKETING_PRODUCTION_OWNER_ORG_ID')==h['OWNER_ORG'],'Founder organization differs')
 require(env.get('NODE_ENV')=='production' and env.get('V79_ENABLE_SIMULATED_PUBLISHER')!='1' and env.get('V79_ALLOW_LEGACY_LOGIN')!='1','Production authentication or real-provider mode differs')
 config=resolve(FILES)
 require(config['services'][SERVICE]['image']==IMAGE and config['services'][SERVICE]['environment'][FLAG]=='0','Original Marketing image/flag not pinned')
 return config

def prepare():
 global support
 require(not ROOT.exists(),'Publication directory exists; inspect its record before retrying')
 mark('verify-accepted-ui-and-generation')
 receipt=json.loads((UI/'deployed.json').read_text())
 require(receipt.get('image')==HUB_IMAGE and receipt.get('healthy') is True and receipt.get('finalizedWithoutRestart') is True,'Finalized UI deployment evidence differs')
 runtime=snapshot();before=check_disabled(runtime);baseline=protected();files=source_hashes(runtime)
 h['probe_live']()
 ROOT.mkdir(mode=0o700)
 support['helper']=h;support['WORK']=ROOT
 mark('verify-public-only-owner-encryption-key')
 public_sha=support['prepare_public_keyring']()
 h['write_json'](ROOT/'publication.yml',{'services':{SERVICE:{'environment':{FLAG:'1'}}}})
 h['write_json'](ROOT/'disable-publication.yml',{'services':{SERVICE:{'environment':{FLAG:'0'}}}})
 candidate=resolve(FILES+[ROOT/'publication.yml']);parity(before,candidate)
 mark('capture-fresh-marketing-online-sqlite-and-assets')
 nonce=secrets.token_hex(8)
 capture=r"""(async()=>{const fs=require('node:fs'),Database=require('better-sqlite3');
const root='/dev/shm/v79-publish-'+process.argv[2],file=root+'/snapshot.sqlite';
if(!/^[a-f0-9]{16}$/.test(process.argv[2]))throw Error('Capture identity');fs.mkdirSync(root,{mode:0o700});
let source,copy;try{source=new Database(process.env.DATABASE_PATH||'/app/data/v79_marketing.sqlite',{readonly:true,fileMustExist:true});source.pragma('query_only=ON');
const deadline=Date.now()+30000;await source.backup(file,{progress(){if(Date.now()>deadline)throw Error('Deadline');return 100;}});
copy=new Database(file,{readonly:true,fileMustExist:true});if(copy.pragma('integrity_check',{simple:true})!=='ok')throw Error('Snapshot integrity');
const bytes=fs.readFileSync(file);if(bytes.length>67108864)throw Error('Snapshot size');process.stdout.write(bytes);
}finally{copy?.close();source?.close();fs.rmSync(root,{recursive:true,force:true});}})().catch(()=>{process.stderr.write('Online backup failed');process.exitCode=1;});"""
 sqlite=h['run'](['docker','exec','-i',MARKETING,'node','--input-type=commonjs','-',nonce],data=capture.encode(),timeout=90)
 assets=h['run'](['docker','exec',MARKETING,'tar','-C','/app','--exclude=data/v79_marketing.sqlite','--exclude=data/v79_marketing.sqlite-wal','--exclude=data/v79_marketing.sqlite-shm','-cf','-','data'],timeout=120)
 config=json.dumps({'runtime':runtime,'resolved':before,'desired':candidate,'originalStack':FILES,'sourceFiles':{p:Path(p).read_text() for p in files},'rollbackCommand':command(FILES)+['up','--no-deps','--no-build','--pull','never','--force-recreate','--wait',SERVICE]},sort_keys=True).encode()
 blobs=dict(zip(BACKUPS,(sqlite,assets,config)));encrypted={};clear={}
 mark('encrypt-fresh-recovery-checkpoint')
 for name,blob in blobs.items():
  clear[name]=sha(blob)
  h['run'](support['encryption_command']()+['--output',str(ROOT/name),'--encrypt'],data=blob,timeout=120)
  encrypted[name]=h['file_hash'](ROOT/name,True)
 require(protected()==baseline and runtime_hashes(snapshot())==runtime_hashes(runtime) and source_hashes(runtime)==files,'Live state changed during recovery capture; no activation')
 manifest={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'directory':str(ROOT),'runtimeHashes':runtime_hashes(runtime),'sourceHashes':files,'protected':baseline,'originalResolvedHash':h['fingerprint'](before),'desiredResolvedHash':h['fingerprint'](candidate),'encryptedBackups':encrypted,'plaintextHashes':clear,'overlayHash':h['file_hash'](ROOT/'publication.yml',True),'publicKeyHash':public_sha,'automaticRetryOrRollback':False,'scope':'Marketing publication flag only; no approvals or provider calls'}
 h['write_json'](ROOT/'manifest.json',manifest)
 print(json.dumps({'directory':str(ROOT),'manifestSha256':h['file_hash'](ROOT/'manifest.json',True),'encryptedBackups':encrypted,'plaintextHashes':clear}),flush=True)

def probe_enabled():
 # List and deliberately unauthorized requests only; never forge fresh MFA.
 script=r"""import assert from 'node:assert/strict';import crypto from 'node:crypto';
const base=process.env.MARKETING_INTERNAL_URL||'http://v79marketing-app:3070',path='/api/platform/marketing-production',key=process.env.V79_MARKETING_PRODUCTION_SHARED_SECRET;
const envelope={organizationId:'44289786-2583-4bf1-9db2-99eca95dfd96',actorHubUserId:'102ad8ce-df0b-4767-a3e2-b715ddbfee84',mfaVerifiedAt:null,requestNonce:crypto.randomUUID(),request:{action:'list'}};
async function send(v,extra={}){const body=JSON.stringify(v),ts=String(Date.now()),input=['POST',path,ts,crypto.createHash('sha256').update(body).digest('hex')].join('\n');return fetch(new URL(path,base),{method:'POST',redirect:'error',signal:AbortSignal.timeout(5000),headers:{'content-type':'application/json','x-v79-service-id':'v79-hub','x-v79-timestamp':ts,'x-v79-signature':crypto.createHmac('sha256',key).update(input).digest('hex'),...extra},body});}
let r=await send(envelope);assert.equal(r.status,200);const state=await r.json();assert.equal(state.publishEnabled,true);
r=await send(envelope);assert.equal(r.status,409);
r=await send({...envelope,requestNonce:crypto.randomUUID(),actorHubUserId:crypto.randomUUID()});assert.equal(r.status,403);
r=await send({...envelope,requestNonce:crypto.randomUUID()},{cookie:'session=untrusted'});assert.equal(r.status,401);
r=await send({...envelope,requestNonce:crypto.randomUUID(),request:{action:'decision',jobId:crypto.randomUUID(),deliveryId:crypto.randomUUID(),decision:'approve',digest:'0'.repeat(64)}});assert.equal(r.status,403);
console.log('LIVE_PUBLICATION_FLAG_SIGNATURE_REPLAY_AND_FRESH_MFA_PASS');"""
 output=h['run'](['docker','exec','-i','v79-hub','node','--input-type=module','-'],data=script.encode())
 require(b'LIVE_PUBLICATION_FLAG_SIGNATURE_REPLAY_AND_FRESH_MFA_PASS' in output,'Live approval boundary probe missing')
 script=b"import assert from 'node:assert/strict';const b='http://127.0.0.1:3070';assert.equal(process.env.V79_MARKETING_PRODUCTION_PUBLISH_ENABLED,'1');assert.equal((await fetch(b+'/api/health')).status,200);for(const p of ['/api/posts','/api/social-accounts'])assert.equal((await fetch(b+p)).status,401);assert.equal((await fetch(b+'/media/production/00000000-0000-4000-8000-000000000000/'+('0'.repeat(64))+'/short.mp4')).status,404);console.log('MARKETING_AUTH_AND_PRIVATE_DRAFT_PASS');"
 output=h['run'](['docker','exec','-i',MARKETING,'node','--input-type=module','-'],data=script)
 require(b'MARKETING_AUTH_AND_PRIVATE_DRAFT_PASS' in output,'Private draft probe missing')

def activate(payload):
 global attempted
 require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.stat().st_uid==os.getuid() and ROOT.stat().st_mode&0o077==0,'Private publication directory differs')
 with (ROOT/'activation.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  require(not (ROOT/'switch-attempted.json').exists() and not (ROOT/'deployed.json').exists(),'Prior activation recorded; inspect instead of retrying')
  require(h['file_hash'](ROOT/'manifest.json',True)==payload['manifestSha256'],'Owner-verified manifest differs')
  manifest=json.loads((ROOT/'manifest.json').read_text())
  require(payload['encryptedBackups']==manifest['encryptedBackups'] and payload['plaintextHashes']==manifest['plaintextHashes'],'Off-host recovery evidence differs')
  age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(manifest['at'])).total_seconds()
  require(0<=age<=3600,'Checkpoint older than one hour; refresh required')
  require(all(h['file_hash'](ROOT/name,True)==digest for name,digest in manifest['encryptedBackups'].items()),'Encrypted recovery changed')
  mark('verify-offhost-recovery-and-final-publication-only-scope')
  runtime=snapshot();before=check_disabled(runtime);candidate=resolve(FILES+[ROOT/'publication.yml']);parity(before,candidate)
  require(runtime_hashes(runtime)==manifest['runtimeHashes'] and source_hashes(runtime)==manifest['sourceHashes'] and protected()==manifest['protected'],'Runtime, configuration or signed campaigns changed; no activation')
  require(h['file_hash'](ROOT/'publication.yml',True)==manifest['overlayHash'] and h['fingerprint'](before)==manifest['originalResolvedHash'] and h['fingerprint'](candidate)==manifest['desiredResolvedHash'],'Resolved flag-only configuration differs')
  mark('enable-only-marketing-exact-approved-publication')
  h['write_json'](ROOT/'switch-attempted.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Marketing publication flag 0 to 1','offhostCopy':payload['acerCopy'],'automaticRetryOrRollback':False})
  attempted=True
  h['run'](command(FILES+[ROOT/'publication.yml'])+['up','--no-deps','--no-build','--pull','never','--force-recreate','--wait','--wait-timeout','120',SERVICE],timeout=180)
  mark('verify-live-approval-boundaries-and-preservation')
  after=snapshot();runtime_parity(runtime[MARKETING],after[MARKETING],before['services'][SERVICE].get('hostname'))
  require(all(h['stable_runtime'](after[name])==h['stable_runtime'](runtime[name]) for name in NAMES if name!=MARKETING),'An unrelated service changed')
  require(resolve(FILES+[ROOT/'publication.yml'])==candidate and source_hashes(runtime)==manifest['sourceHashes'],'Compose or protected key files changed')
  probe_enabled()
  require(protected()==manifest['protected'],'Accounts, billing, G2, provider records or campaign state changed')
  h['write_json'](ROOT/'deployed.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'image':IMAGE,'marketingContainerId':after[MARKETING]['Id'],'publicationEnabled':True,'exactOwnerApprovalRequired':True,'noApprovalsCreated':True,'noProviderCallsMadeByActivation':True,'protectedStatePreserved':True,'onlyMarketingRecreated':True,'offhostCopy':payload['acerCopy'],'automaticRetryOrRollback':False})
  print('EXACT_OWNER_APPROVED_PUBLICATION_ENABLED')
  print('LIVE_SIGNATURE_REPLAY_FRESH_MFA_AND_PRIVATE_DRAFT_BOUNDARIES_PASS')
  print('NO_PUBLICATION_APPROVALS_CREATED_OR_POSTS_SENT_BY_ACTIVATION')
  print('HUB_G2_ACCOUNTS_BILLING_PROVIDER_RECORDS_AND_CAMPAIGNS_PRESERVED')
  print('HUB_AGENT_DATABASES_TIQUET_CONTAINERS_UNCHANGED')
  print('PUBLICATION_DIRECTORY='+str(ROOT))

def main():
 global h,support
 os.umask(0o077)
 require(socket.gethostname().split('.')[0]=='v79sl' and os.getuid()==1000 and pwd.getpwuid(os.getuid()).pw_name=='firelion','Run remote phase as firelion on v79sl')
 h=load('638fb3cb5b52d6f627014a4c2cb6d3ad6f29bbe7','marketing-production-reconcile-fresh-generation.py','5fedd5e0f7a36bd2e10111bb373d745fc813620664e9eda949ddbc603d769e39')
 support=load('c659116623d42303b07660c37883ebe5f6eaa194','marketing-production-panel-cutover.py','c13f87a5cf22c14780315c501d62668d8e4f7a1c256c7e557f7ccf0723614c21')
 payload=json.load(sys.stdin)
 if payload['phase']=='prepare':prepare()
 elif payload['phase']=='activate':activate(payload)
 else:raise RuntimeError('Unknown phase')

if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as exc:
  print('STOP: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
  print('PUBLICATION_DIRECTORY='+str(ROOT),file=sys.stderr)
  print('LIVE_ACTIVATION_UNCERTAIN_INSPECT_BEFORE_ANY_RETRY' if attempted else 'NO_LIVE_RECREATION_ATTEMPTED',file=sys.stderr)
  if h and ROOT.is_dir() and not (ROOT/'failure.json').exists():
   try:h['write_json'](ROOT/'failure.json',{'stage':stage,'liveSwitchAttempted':attempted,'automaticRetryOrRollback':False})
   except Exception:pass
  sys.exit(1)
'''


def remote(payload, capture=False):
    result = subprocess.run(['ssh', 'firelion@v79sl', 'python3 -B -c '+shlex.quote(REMOTE_PROGRAM)],
                            input=json.dumps(payload).encode(), stdout=subprocess.PIPE if capture else None, check=True)
    return json.loads(result.stdout) if capture else None


def decrypt_hash(path):
    digest = hashlib.sha256()
    with subprocess.Popen(['gpg', '--quiet', '--decrypt', str(path)], stdout=subprocess.PIPE) as proc:
        for chunk in iter(lambda: proc.stdout.read(1048576), b''):
            digest.update(chunk)
        if proc.wait() != 0:
            raise RuntimeError('Off-host decryption failed; activation was not requested')
    return digest.hexdigest()


def main():
    os.umask(0o077)
    if socket.gethostname().split('.')[0] != 'firelion-Aspire-A315-51':
        raise RuntimeError('Run directly on your Acer laptop')
    print('Keep the Marketing approval panel idle until this command finishes.', flush=True)
    prepared = remote({'phase': 'prepare'}, capture=True)
    local = Path(tempfile.mkdtemp(prefix='v79-g3-publication-recovery-', dir=Path.home()))
    print('ACER_PUBLICATION_RECOVERY_COPY='+str(local), flush=True)
    directory = prepared['directory']
    if directory != '/home/firelion/v79-g3-publication-v1':
        raise RuntimeError('Unexpected recovery directory')
    subprocess.run(['scp']+['firelion@v79sl:'+directory+'/'+name for name in (*ENCRYPTED, 'manifest.json')]+[str(local)+'/'], check=True)
    manifest_bytes = (local/'manifest.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != prepared['manifestSha256']:
        raise RuntimeError('Copied manifest integrity mismatch')
    manifest = json.loads(manifest_bytes)
    if manifest['encryptedBackups'] != prepared['encryptedBackups'] or manifest['plaintextHashes'] != prepared['plaintextHashes']:
        raise RuntimeError('Recovery manifest differs')
    for name in ENCRYPTED:
        if hashlib.sha256((local/name).read_bytes()).hexdigest() != prepared['encryptedBackups'][name]:
            raise RuntimeError('Encrypted backup checksum mismatch')
        if decrypt_hash(local/name) != prepared['plaintextHashes'][name]:
            raise RuntimeError('Decrypted backup integrity mismatch')
        print('OFFHOST_CHECKSUM_AND_DECRYPT_PASS='+name, flush=True)
    remote({'phase': 'activate', **prepared, 'acerCopy': str(local)})


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('STOP: '+(str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__))
        raise SystemExit(1)
