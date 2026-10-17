#!/usr/bin/env python3
"""Deploy only two tested image IDs after copied recovery and Acer decryption."""
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import time
import urllib.request

RECOVERY=Path('/home/firelion/v79-g3-tracking-recovery-u85okvlh')
WORK=Path('/home/firelion/v79-g3-tracking-cutover-v1')
SPECS={
 'v79-hub':('V79hub','v79-hub','v79-hub','/opt/v79/hub'),
 'v79marketing-app':('V79Marketing','v79marketing','v79-marketing','/home/firelion/V79Marketing')}
h=None
recovery=None
attempted=[]
work_owned=False
stage='preflight'


def require(ok,message):
 if not ok:raise RuntimeError(message)


def mark(value):
 global stage
 stage=value
 if h:h['stage']=value
 print('STAGE='+value,flush=True)


def load(commit,name,digest):
 with urllib.request.urlopen('https://raw.githubusercontent.com/MrFixITslu/V79hub/'+commit+'/scripts/'+name,timeout=30) as response:code=response.read(1048577)
 require(hashlib.sha256(code).hexdigest()==digest,'Pinned deployment support integrity differs')
 ns={'__name__':'tracking_cutover_support'};exec(compile(code,'<verified-tracking-cutover-support>','exec'),ns);return ns


def freshness(value):
 date=datetime.datetime.fromisoformat(value)
 require(date.tzinfo is not None,'Recovery timestamp lacks timezone')
 age=(datetime.datetime.now(datetime.timezone.utc)-date).total_seconds()
 require(0<=age<=3600,'Recovery checkpoint older than one hour; refresh before deployment')


def verify_evidence(receipt,proof,receipt_hash):
 freshness(receipt['capturedAt']);freshness(proof['verifiedAt'])
 for flag in ('copiedOnlineRestoreVerified','copiedCandidateMigrationAndRollbackVerified','signedCampaignsAndSchedulesPreserved','scratchCleanupVerified'):
  require(receipt.get(flag) is True,'Copied recovery evidence incomplete: '+flag)
 require(receipt.get('liveDeploymentPerformed') is False and receipt.get('publicationEnabled') is True,'Recovery deployment/publication scope differs')
 require(receipt['candidates']==recovery['EXPECTED'],'Recovered candidate images differ from tested images')
 require(proof.get('allFiveFullDecryptionsVerified') is True and proof.get('recoveryDirectory')==str(RECOVERY) and proof.get('recoveryReceiptSha256')==receipt_hash,'Off-host receipt binding differs')
 names={'hub-pg.dump.gpg','hub-data.tar.gpg','marketing-online.sqlite.gpg','marketing-files.tar.gpg','runtime-config.json.gpg'}
 require(set(receipt['encryptedBackups'])==set(receipt['plaintextHashes'])==names,'Recovery backup set differs')
 require(all(proof.get(k)==receipt[k] for k in ('encryptedBackups','plaintextHashes')),'Off-host backup/decrypted hashes differ')
 require(isinstance(proof.get('acerRecoveryCopy'),str) and proof['acerRecoveryCopy'].startswith('/home/firelion/v79-g3-tracking-recovery.'),'Acer recovery copy differs')
 require(not receipt['marketingBasis']['confirmed'],'A confirmed provider receipt now requires a tracking-aware reconciliation')


def command(name,files):
 _repo,project,_service,directory=SPECS[name]
 args=['docker','compose','--project-name',project,'--project-directory',directory]
 for path in files:args+=['--file',str(path)]
 return args


def resolve(name,files):return json.loads(h['run'](command(name,files)+['config','--format','json']))


def parity(name,before,after,image):
 expected=copy.deepcopy(before);expected['services'][SPECS[name][2]]['image']=image
 require(after==expected,'Configuration changes exceed exact application image: '+name)


def profile(meta,configured_hostname):
 config=copy.deepcopy(meta['Config']);labels=config.pop('Labels')
 config.pop('Image');config['Env']=sorted(config['Env'])
 if configured_hostname is None:
  require(config.pop('Hostname')==meta['Id'][:12],'Unexpected Docker-generated hostname')
 else:require(config.get('Hostname')==configured_hostname,'Explicit application hostname changed')
 for key in ('com.docker.compose.project.config_files','com.docker.compose.config-hash','com.docker.compose.image','org.opencontainers.image.revision'):labels.pop(key,None)
 host=copy.deepcopy(meta['HostConfig'])
 if isinstance(host.get('Binds'),list):host['Binds']=sorted(host['Binds'])
 return {'applicationSha256':h['fingerprint'](config),'preservedLabelsSha256':h['fingerprint'](labels),'hostConfigSha256':h['fingerprint'](host),
  'mountsSha256':h['fingerprint'](h['mounts'](meta)),'networks':sorted(meta['NetworkSettings']['Networks'])}


def runtime_parity(name,before,after,configured_hostname,files,overlay):
 repo,project,service,directory=SPECS[name];image=recovery['EXPECTED'][repo]
 require(h['healthy'](after) and after['Id']!=before['Id'] and after['Image']==image['image'],'New image, recreation or health differs: '+name)
 require(after['Config']['Image']==image['image'],'New container image is not pinned: '+name)
 labels=after['Config']['Labels']
 require(labels.get('org.opencontainers.image.revision')==image['commit'],'New source revision differs: '+name)
 require(labels.get('com.docker.compose.project')==project and labels.get('com.docker.compose.service')==service and labels.get('com.docker.compose.project.working_dir')==directory,'Compose project identity changed: '+name)
 require(labels.get('com.docker.compose.project.config_files')==','.join(files+[str(overlay)]),'New Compose stack order differs: '+name)
 require(profile(before,configured_hostname)==profile(after,configured_hostname),'Application environment, command, resources, mounts, labels or networks changed: '+name)


def compose_switch(args):
 # One request only. Killing this CLI on timeout never authorizes a retry.
 process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 deadline=time.monotonic()+300;next_report=time.monotonic()+15
 try:
  while process.poll() is None:
   now=time.monotonic()
   require(now<deadline,'Compose switch timed out; live state uncertain, inspect before retry')
   if now>=next_report:
    print('WAITING_FOR_EXACT_IMAGE_SWITCH='+attempted[-1],flush=True);next_report=now+15
   time.sleep(1)
  require(process.returncode==0,'Compose switch failed; sensitive output withheld; inspect before retry')
 finally:
  if process.poll() is None:process.kill();process.wait(timeout=5)


def switch_services(runtime,stacks,resolved,desired,overlays):
 for name in SPECS:
  mark('deploy-only-tested-image-'+name)
  repo,_project,service,_directory=SPECS[name]
  # Refuse data/config/runtime drift immediately before each service switch.
  recovery['protected_equal'](manifest['marketingBasis'],recovery['basis']('v79marketing-app'))
  freshness(manifest['capturedAt'])
  require(h['protected_state']('v79-hub-postgres')==manifest['hubProtectedStateSha256'],'Hub protected state changed before switch')
  require(all(h['file_hash'](p)==digest for p,digest in manifest['sourceHashes'].items()),'Original configuration/key file changed before switch')
  for other,old in runtime.items():
   current=h['inspect'](other)
   if other in attempted:
    runtime_parity(other,old,current,resolved[other]['services'][SPECS[other][2]].get('hostname'),stacks[other],overlays[other])
   else:require(h['healthy'](current) and h['stable_runtime'](current)==h['stable_runtime'](old),'A service changed before switch: '+other)
  require(resolve(name,stacks[name]+[str(overlays[name])])==desired[name],'Desired image-only configuration changed')
  h['write_json'](WORK/('switch-attempted-'+name+'.json'),{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'image':recovery['EXPECTED'][repo]['image'],'automaticRetryOrRollback':False})
  attempted.append(name)
  compose_switch(command(name,stacks[name]+[str(overlays[name])])+['up','--no-deps','--no-build','--pull','never','--force-recreate','--wait','--wait-timeout','180',service])
  runtime_parity(name,runtime[name],h['inspect'](name),resolved[name]['services'][service].get('hostname'),stacks[name],overlays[name])


G2_PROBE=r"""import assert from 'node:assert/strict';import fs from 'node:fs';
import {createWorkActionStore} from './server/workforce-action-store.mjs';import {createApprovedWorkItem} from './server/workforce-actions.mjs';
const id='d8719467-1caa-4e24-ae5f-1fd792e0b3de',base='http://127.0.0.1:3040',worker=fs.readFileSync(process.env.V79_WORKFORCE_TOKEN_FILE,'utf8').trim(),agent=fs.readFileSync('/run/secrets/v79-agent-token','utf8').trim();assert.notEqual(worker,agent);
assert.equal(process.env.V79_MARKETING_PRODUCTION_ENABLED,'1');
for(const [headers,status] of [[{},403],[{'x-v79-workforce-token':agent},403],[{'x-v79-workforce-token':worker,cookie:'session=untrusted'},403]])assert.equal((await fetch(base+'/internal/workforce/work-items',{headers,signal:AbortSignal.timeout(5000)})).status,status);
const r=await fetch(base+'/internal/workforce/work-items',{headers:{'x-v79-workforce-token':worker},signal:AbortSignal.timeout(5000)});assert.equal(r.status,200);assert.ok((await r.json()).tasks.some(t=>t.id===id));
for(const p of ['/api/billing/summary','/api/agent/executive-structure'])assert.equal((await fetch(base+p,{signal:AbortSignal.timeout(5000)})).status,401);
const ledger=createWorkActionStore({file:'/app/data/workforce-actions.json',secret:process.env.V79_WORKFORCE_AUDIT_KEY,backend:process.env.V79_HUB_STORE_BACKEND,databaseUrl:process.env.DATABASE_URL});
try{const state=await ledger.read(),tasks=state.tasks.filter(t=>t.id===id);assert.equal(tasks.length,1);const task=tasks[0],job=state.jobs.find(j=>j.id===task.jobId);assert.equal(task.assignedTo,'coo');assert.equal(job.status,'succeeded');assert.equal(job.result.taskId,id);assert.equal(job.approval.digest,job.digest);for(const type of ['proposed','approved','work_item_created'])assert.ok(state.events.some(e=>e.jobId===job.id&&e.type===type));assert.throws(()=>createApprovedWorkItem(structuredClone(state),job.id,{organizationId:job.organizationId,actor:job.approval.by,expectedRevision:job.revision}));}finally{await ledger.close();}
console.log('G2_SIGNED_TASK_REPLAY_DENIAL_AND_WORKER_VISIBILITY_PASS');"""

UI_PROBE=r"""import assert from 'node:assert/strict';import fs from 'node:fs';import crypto from 'node:crypto';
const base='http://127.0.0.1:'+process.env.PORT,html=fs.readFileSync('dist/index.html','utf8'),page=await fetch(base+'/',{signal:AbortSignal.timeout(5000)});assert.equal(page.status,200);const served=await page.text();
const main=[...html.matchAll(/src="(\/assets\/[^"\s]+\.js)"/g)].map(m=>m[1]);assert.ok(main.length);for(const asset of main){assert.ok(served.includes(asset));const r=await fetch(base+asset,{signal:AbortSignal.timeout(5000)});assert.equal(r.status,200);assert.deepEqual(Buffer.from(await r.arrayBuffer()),fs.readFileSync('dist'+asset));}
const markers=process.env.PORT==='3040'?['Clear failed attempts','Publication complete','https://www.youtube.com/watch?v=']:['Owner-approved production'];
const files=fs.readdirSync('dist/assets').filter(p=>p.endsWith('.js'));for(const marker of markers){const file=files.find(p=>fs.readFileSync('dist/assets/'+p,'utf8').includes(marker));assert.ok(file);const r=await fetch(base+'/assets/'+file,{signal:AbortSignal.timeout(5000)});assert.equal(r.status,200);assert.deepEqual(Buffer.from(await r.arrayBuffer()),fs.readFileSync('dist/assets/'+file));}
console.log('EXACT_TRACKING_UI_ASSETS_SERVED_PASS');"""


def main():
 global h,recovery,manifest,work_owned
 os.umask(0o077)
 require(socket.gethostname().split('.')[0]=='v79sl' and os.getuid()==1000 and pwd.getpwuid(os.getuid()).pw_name=='firelion','Run as firelion on v79sl')
 require(not WORK.exists(),'Cutover directory exists; inspect its record before any retry')
 recovery=load('4f2c624351e0e8fcf8b15ae99b8fdc50ccc41870','marketing-production-tracking-recovery.py','7a52b86c7e4975251da8886cfddd00d987079b780fab7f0ad105c0967b18d53f')
 h=load('638fb3cb5b52d6f627014a4c2cb6d3ad6f29bbe7','marketing-production-reconcile-fresh-generation.py','5fedd5e0f7a36bd2e10111bb373d745fc813620664e9eda949ddbc603d769e39');recovery['h']=h
 builder=load('4dd78c25c23cc42f7069145210edabcd83fee9f1','marketing-production-tracking-build.py','b726c9cc780e7394ddd45337e66d83ddfd5905b6a2e03c920420068541770f85')
 mark('verify-complete-recovery-and-five-offhost-decryptions')
 require(RECOVERY.is_dir() and not RECOVERY.is_symlink() and RECOVERY.stat().st_uid==os.getuid() and RECOVERY.stat().st_mode&0o077==0,'Private recovery directory differs')
 receipt_hash=h['file_hash'](RECOVERY/'recovery-receipt.json',True);manifest=json.loads((RECOVERY/'recovery-receipt.json').read_text())
 proof_hash=h['file_hash'](RECOVERY/'offhost-verification.json',True);proof=json.loads((RECOVERY/'offhost-verification.json').read_text());verify_evidence(manifest,proof,receipt_hash)
 for name,digest in manifest['encryptedBackups'].items():require(h['file_hash'](RECOVERY/name,True)==digest,'Encrypted recovery file changed')
 require(h['file_hash'](manifest['buildReceipt'],True)==manifest['buildReceiptSha256'],'Passed build receipt changed')
 build=json.loads(Path(manifest['buildReceipt']).read_text())
 require(build.get('deploymentPerformed') is False and build.get('runtimeSourceVerified') is True and build.get('liveRuntime')==manifest['liveRuntime'],'Tested build/runtime evidence differs')
 mark('verify-exact-images-runtime-and-idle-approved-schedule')
 require(builder['snapshot']()==manifest['liveRuntime'],'Live services changed since recovery; inspect before deploying')
 require(not h['run'](['docker','ps','--all','--filter','label='+recovery['LABEL'],'--format','{{.ID}}']).strip(),'A tracking scratch container remains')
 recovery['protected_equal'](manifest['marketingBasis'],recovery['basis']('v79marketing-app'))
 require(h['protected_state']('v79-hub-postgres')==manifest['hubProtectedStateSha256'],'Hub accounts/billing/G2 changed since backup')
 images={}
 for repo,expected in recovery['EXPECTED'].items():
  item=build['candidates'][repo];require(all(item.get(k)==v for k,v in expected.items()) and item.get('isolatedTestsPassed') is True and item.get('sourceScopeVerified') is True,'Candidate build evidence differs')
  image=json.loads(h['run'](['docker','image','inspect',expected['image']]))[0]
  require(image['Id']==expected['image'] and image['Config']['Labels'].get('org.opencontainers.image.revision')==expected['commit'],'Candidate image provenance differs')
  images[repo]=image
 runtime={name:h['inspect'](name) for name in manifest['liveRuntime']};stacks=manifest['originalStacks'];resolved={};desired={};overlays={}
 require(all(h['file_hash'](p)==digest for p,digest in manifest['sourceHashes'].items()),'Original Compose, environment or key files changed')
 require(not WORK.exists(),'Another cutover attempt appeared')
 WORK.mkdir(mode=0o700)
 work_owned=True
 with (WORK/'deployment.lock').open('x') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  mark('prepare-two-exact-image-overlays-and-original-rollback-stacks')
  for name,(repo,project,service,directory) in SPECS.items():
   labels=runtime[name]['Config']['Labels']
   require(labels['com.docker.compose.project']==project and labels['com.docker.compose.service']==service and labels['com.docker.compose.project.working_dir']==directory and labels['com.docker.compose.project.config_files']==','.join(stacks[name]),'Original Compose provenance differs')
   resolved[name]=resolve(name,stacks[name]);require(h['fingerprint'](resolved[name])==manifest['originalResolvedHashes'][name] and resolved[name]['services'][service]['image']==runtime[name]['Image'],'Original pinned Compose configuration differs')
   application=resolved[name]['services'][service]
   h['verify_application_profile'](application,images[repo]['Config'],runtime[name]['Config'])
   expected_env=h['env_map'](images[repo]['Config'].get('Env',[]));expected_env.update(application.get('environment',{}))
   require(expected_env==h['env_map'](runtime[name]['Config']['Env']),'Candidate image would change runtime environment defaults: '+name)
   expected_labels=dict(images[repo]['Config'].get('Labels') or {});expected_labels.update(application.get('labels',{}))
   require(expected_labels.pop('org.opencontainers.image.revision',None)==recovery['EXPECTED'][repo]['commit'],'Compose would override the candidate source revision')
   old_labels={k:v for k,v in labels.items() if not k.startswith('com.docker.compose.') and k!='org.opencontainers.image.revision'}
   require(expected_labels==old_labels,'Candidate image would change preserved application labels: '+name)
   overlays[name]=WORK/(name+'-image.yml');h['write_json'](overlays[name],{'services':{service:{'image':recovery['EXPECTED'][repo]['image']}}})
   desired[name]=resolve(name,stacks[name]+[str(overlays[name])]);parity(name,resolved[name],desired[name],recovery['EXPECTED'][repo]['image'])
  record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'recoveryDirectory':str(RECOVERY),'recoveryReceiptSha256':receipt_hash,'offhostProofSha256':proof_hash,
   'candidates':recovery['EXPECTED'],'originalRuntime':manifest['liveRuntime'],'originalStacks':stacks,'beforeRuntimeProfiles':{n:profile(runtime[n],resolved[n]['services'][SPECS[n][2]].get('hostname')) for n in SPECS},
   'desiredResolvedHashes':{n:h['fingerprint'](v) for n,v in desired.items()},'overlayHashes':{str(p):h['file_hash'](p,True) for p in overlays.values()},
   'rollbackCommands':{n:command(n,stacks[n])+['up','--no-deps','--no-build','--pull','never','--force-recreate','--wait',SPECS[n][2]] for n in SPECS},'automaticRetryOrRollback':False}
  h['write_json'](WORK/'manifest.json',record)
  switch_services(runtime,stacks,resolved,desired,overlays)
  mark('verify-live-ui-approval-worker-boundaries-and-preserved-data')
  publication=load('4f2c624351e0e8fcf8b15ae99b8fdc50ccc41870','marketing-production-enable-publication.py','aee7e5fc07aa59ae0a75689a85c05ae0edc3e726a43c7c497859200b5fb8a9a5')
  probes={'__name__':'tracking_read_only_probes'};exec(compile(publication['REMOTE_PROGRAM'],'<verified-live-publication-probes>','exec'),probes);probes['h']=h;probes['probe_enabled']()
  require(b'G2_SIGNED_TASK_REPLAY_DENIAL_AND_WORKER_VISIBILITY_PASS' in h['run'](['docker','exec','-i','v79-hub','node','--input-type=module','-'],data=G2_PROBE.encode()),'G2/worker boundary verification missing')
  for name in SPECS:require(b'EXACT_TRACKING_UI_ASSETS_SERVED_PASS' in h['run'](['docker','exec','-i',name,'node','--input-type=module','-'],data=UI_PROBE.encode()),'Pinned UI assets not served: '+name)
  after={name:h['inspect'](name) for name in runtime}
  for name in SPECS:
   runtime_parity(name,runtime[name],after[name],resolved[name]['services'][SPECS[name][2]].get('hostname'),stacks[name],overlays[name])
   require(resolve(name,stacks[name]+[str(overlays[name])])==desired[name],'Resolved image-only configuration changed')
  for name in set(runtime)-set(SPECS):require(h['healthy'](after[name]) and h['stable_runtime'](after[name])==h['stable_runtime'](runtime[name]),'Unrelated service changed: '+name)
  recovery['protected_equal'](manifest['marketingBasis'],recovery['basis']('v79marketing-app'),True)
  require(h['protected_state']('v79-hub-postgres')==manifest['hubProtectedStateSha256'],'Hub accounts, billing or G2 changed')
  require(all(h['file_hash'](p)==digest for p,digest in manifest['sourceHashes'].items()) and all(h['file_hash'](p,True)==digest for p,digest in record['overlayHashes'].items()),'Original configuration, keys or image overlays changed')
  require(h['file_hash'](RECOVERY/'recovery-receipt.json',True)==receipt_hash and h['file_hash'](RECOVERY/'offhost-verification.json',True)==proof_hash,'Recovery evidence changed during switch')
  h['write_json'](WORK/'deployed.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidates':recovery['EXPECTED'],'liveRuntimeSha256':{n:h['fingerprint'](h['stable_runtime'](v)) for n,v in after.items()},
   'bothImagesHealthy':True,'publicationStillEnabled':True,'approvedSchedulesAndSignedCampaignsPreserved':True,'protectedDataPreserved':True,'otherFourServicesUnchanged':True,'noApprovalsOrProviderCallsByDeployment':True,
   'offhostCopy':proof['acerRecoveryCopy'],'recoveryReceiptSha256':receipt_hash,'automaticRetryOrRollback':False})
  print('HUB_STATUS_LINKS_FAILED_ATTEMPT_CONTROLS_AND_MARKETING_TRACKING_DEPLOYED_HEALTHY')
  print('SIGNED_CAMPAIGNS_APPROVED_SCHEDULES_PUBLICATION_FLAGS_AND_KEYS_PRESERVED')
  print('ACCOUNTS_BILLING_G2_PROVIDER_RECORDS_AND_OTHER_FOUR_SERVICES_PRESERVED')
  print('NO_APPROVALS_CREATED_NO_UPLOADS_SENT_NO_CAMPAIGNS_CANCELLED_BY_DEPLOYMENT')
  print('CUTOVER_DIRECTORY='+str(WORK))
  print('OWNER_BROWSER_ACCEPTANCE_AND_SCHEDULED_UPLOAD_CONFIRMATION_PENDING')


if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as exc:
  print('STOP: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__)+'; stage='+stage)
  print('CUTOVER_DIRECTORY='+str(WORK))
  print('LIVE_SWITCH_UNCERTAIN_INSPECT_BEFORE_ANY_RETRY' if attempted else 'NO_LIVE_RECREATION_ATTEMPTED')
  if h and work_owned and WORK.is_dir() and not (WORK/'failure.json').exists():
   h['write_json'](WORK/'failure.json',{'stage':stage,'errorType':type(exc).__name__,'attemptedServices':attempted,'automaticRetryOrRollback':False})
  raise SystemExit(1)
