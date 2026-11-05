#!/usr/bin/env python3
"""Scoped paired rollout; prepare never starts apps; retains original containers."""
import copy,fcntl,hashlib,importlib.util,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path('/home/firelion/.v79-workforce-delivery-release-20261105')
SOURCE=Path('/home/firelion/v79-workforce-completion-20261105')
APP_SHA='01691b7e72c75192801a94291477cf493594ee7b'
CHECKPOINT='c9c6dd9c3f546720681358aee864135a391b56b26fc6ec702d3552e5c98e4524'
TIMERS=['v79-g2-approved-task-worker.timer','v79-workforce-morning.timer','v79-workforce-evening.timer']
SPECS={
 'v79-business-agent':{'old':'sha256:8c12d67b45486c30adca3e19dde88e1654995b15a26c6cb7a52e51fd7b62691f','tag':'localhost/v79-workforce-agent:01691b7','stage':'v79-workforce-agent-stage-20261105','previous':'v79-workforce-agent-rollback-20261105','mounts':1,'url':'https://hub.v79sl.com/','flags':{'OLLAMA_AGENT_MODEL':'qwen2.5:3b','V79_SPECIALIST_REVIEW_MODEL':'qwen2.5:3b'}},
 'v79-hub':{'old':'sha256:96a0b3cc2455d1a02c508c8db30f9856660bc26d8892b50f65829f942bdb6de3','tag':'localhost/v79-workforce-hub:01691b7','stage':'v79-workforce-hub-stage-20261105','previous':'v79-workforce-hub-rollback-20261105','mounts':7,'url':'https://hub.v79sl.com/','flags':{'V79_WORKFORCE_SPECIALIST_REVIEWS_ENABLED':'1'}},
}

def expected_runtime(original,spec):
 result=copy.deepcopy(original);conf=result['Config'];flags=spec['flags']
 allowed={'V79_WORKFORCE_SPECIALIST_REVIEWS_ENABLED','V79_SPECIALIST_REVIEW_MODEL','OLLAMA_AGENT_MODEL'}
 if not set(flags)<=allowed:raise RuntimeError('Unapproved environment delta')
 env=[v for v in conf['Env'] if v.split('=',1)[0] not in flags]
 conf['Env']=env+[k+'='+v for k,v in flags.items()]
 labels={k:v for k,v in (conf.get('Labels') or {}).items() if not k.startswith('com.docker.compose.')}
 labels.update({'org.opencontainers.image.revision':APP_SHA,'com.v79.guarded-release':'20261102-stage-before-stop'})
 conf['Labels']=labels;conf['Image']=spec['tag'];return result

def mount_signature(container):
 return sorted((m['Type'],m.get('Name') if m['Type']=='volume' else m['Source'],m['Destination'],m['RW']) for m in container['Mounts'])

def assert_parity(original,staged,spec):
 expected=expected_runtime(original,spec)
 if original['Image']!=spec['old'] or original['State']['Status']!='running' or original['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Baseline image/health drift')
 if staged['Image']!=spec['image'] or staged['State']['Status']!='created':raise RuntimeError('Candidate image/state drift')
 if staged['Config']!=expected['Config']:raise RuntimeError('Candidate process/environment/labels drift')
 if staged['HostConfig']!=original['HostConfig']:raise RuntimeError('Candidate host security/ports/restart drift')
 if mount_signature(staged)!=mount_signature(original) or len(staged['Mounts'])!=spec['mounts']:raise RuntimeError('Candidate persistent mounts drift')
 if set(staged['NetworkSettings']['Networks'])!=set(original['NetworkSettings']['Networks']):raise RuntimeError('Candidate networks drift')
 if not all(spec['name'] in n.get('Aliases',[]) for n in staged['NetworkSettings']['Networks'].values()):raise RuntimeError('Canonical service network alias missing')

def load_module(path,name):
 definition=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(definition);definition.loader.exec_module(module);return module

def controllers():
 prepare=load_module(Path('/home/firelion/.v79-admin-workday-20261102/safe-release/prepare-f73024d7.py'),'v79_prepare')
 promote=load_module(Path('/home/firelion/.v79-admin-workday-20261102/safe-release/promote-f73024d7.py'),'v79_promote')
 promote.ROOT=ROOT;promote.parity=assert_parity
 return prepare,promote

def systemctl(*args,check=True):
 env={**os.environ,'XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
 return subprocess.run(['systemctl','--user',*args],env=env,capture_output=True,text=True,timeout=12,check=check)

def save(doc):
 temporary=ROOT/'manifest.tmp';temporary.write_text(json.dumps(doc,sort_keys=True));os.chmod(temporary,0o600)
 with temporary.open('rb') as handle:os.fsync(handle.fileno())
 temporary.replace(ROOT/'paired-release-manifest.json')
 fd=os.open(ROOT,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)

def note(event):
 with (ROOT/'paired-release-events.jsonl').open('a') as handle:handle.write(json.dumps({'at':time.time(),'event':event})+'\n');handle.flush();os.fsync(handle.fileno())
 print(event,flush=True)

def preflight(prepare,promote):
 if os.uname().nodename!='v79sl':raise RuntimeError('Wrong host')
 pressure=Path('/proc/pressure/io').read_text()
 for kind,limit in [('some',15),('full',10)]:
  if float(re.search(kind+r' avg10=([0-9.]+)',pressure).group(1))>limit:raise RuntimeError('Host I/O pressure: defer release')
 receipt=json.loads((ROOT/'offhost-restore-receipt.json').read_text())
 if receipt.get('encryptedSha256')!=CHECKPOINT or receipt.get('isolatedPostgres17Restore')!='PASS' or receipt.get('offhostArchiveIntegrity')!='PASS':raise RuntimeError('Offhost restoration receipt missing')
 archive=ROOT/'V79_Workforce_PreRelease_Encrypted_20261105.tar.gz.gpg'
 if hashlib.sha256(archive.read_bytes()).hexdigest()!=CHECKPOINT:raise RuntimeError('Checkpoint ciphertext changed')
 subprocess.run(['git','-C',str(SOURCE),'diff','--exit-code',APP_SHA,'--','server.ts','server','src','agent-service/src','scripts/workforce-specialist-review-worker.mjs'],check=True,capture_output=True,timeout=10)
 status,containers=prepare.api('GET','/containers/json')
 if status!=200:raise RuntimeError('Container inventory unavailable')
 protected={}
 for row in containers:
  name=row['Names'][0].lstrip('/')
  if name in SPECS:continue
  current=prepare.inspect(name)
  if current['State']['Status']!='running' or current['State'].get('Health',{}).get('Status','healthy')!='healthy':raise RuntimeError('Protected service unhealthy')
  protected[name]={'id':current['Id'],'image':current['Image']}
 for name,spec in SPECS.items():
  live=prepare.inspect(name)
  if live['Image']!=spec['old'] or live['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Protected baseline drift')
  if promote.exists(spec['previous']):raise RuntimeError('Rollback name already exists')
  status,image=prepare.api('GET','/images/'+spec['tag'].replace('/','%2F')+'/json')
  if status!=200 or image['Config'].get('Labels',{}).get('org.opencontainers.image.revision')!=APP_SHA:raise RuntimeError('Candidate provenance missing')
  spec.update({'image':image['Id'],'name':name})
 if promote.curlcode('https://hub.v79sl.com/')!=200:raise RuntimeError('Public Hub unavailable')
 return protected

def protected_check(prepare,protected):
 for name,expected in protected.items():
  current=prepare.inspect(name)
  if current['Id']!=expected['id'] or current['Image']!=expected['image'] or current['State']['Status']!='running' or current['State'].get('Health',{}).get('Status','healthy')!='healthy':raise RuntimeError('Protected service changed')

def pause_timers(doc):
 doc['activeTimers']=[t for t in TIMERS if systemctl('is-active',t,check=False).returncode==0];save(doc)
 for timer in doc['activeTimers']:systemctl('stop',timer)
 for service in ['v79-g2-approved-task-worker.service','v79-workforce-briefing@morning.service','v79-workforce-briefing@evening.service']:
  for _ in range(45):
   state=systemctl('show',service,'-p','ActiveState','--value').stdout.strip()
   if state not in ('active','activating','deactivating'):break
   time.sleep(1)
  else:raise RuntimeError('Existing worker did not drain; no cutover')
 note('EXISTING_WORKFORCE_TIMERS_PAUSED_AND_DRAINED')

def resume_timers(doc):
 for timer in doc.get('activeTimers',[]):systemctl('start',timer)
 note('EXISTING_WORKFORCE_TIMERS_RESTORED')

def rollback(prepare,promote,doc):
 systemctl('stop','v79-specialist-review.timer',check=False)
 for name in reversed(list(SPECS)):
  spec=doc['specs'][name];current=promote.exists(name)
  if current and current['Image']==spec['old'] and current['State'].get('Health',{}).get('Status')=='healthy':continue
  if promote.exists(spec['previous']):promote.restore(name,spec)
 protected_check(prepare,doc['protected']);resume_timers(doc);doc['phase']='rolled-back';save(doc);note('PAIRED_ROLLBACK_VERIFIED')

def main():
 if len(sys.argv)!=2 or sys.argv[1] not in ('prepare','deploy','rollback','verify'):raise RuntimeError('Usage: prepare|deploy|rollback|verify')
 ROOT.mkdir(mode=0o700,exist_ok=True)
 lock=os.open(ROOT/'paired-release.lock',os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 prepare,promote=controllers();mode=sys.argv[1]
 if mode=='prepare':
  protected=preflight(prepare,promote)
  if (ROOT/'paired-release-manifest.json').exists():raise RuntimeError('Existing manifest: inspect before preparing again')
  for name,spec in SPECS.items():
   live=prepare.inspect(name)
   if promote.exists(spec['stage']):raise RuntimeError('Stage name already exists')
   prepare.create(name,{'new':spec['tag'],'prepared':spec['stage']},expected_runtime(live,spec))
   assert_parity(live,prepare.inspect(spec['stage']),spec)
  save({'phase':'prepared','appSha':APP_SHA,'specs':SPECS,'protected':protected,'activeTimers':[]})
  note('PAIRED_STOPPED_CANDIDATES_VERIFIED_LIVE_UNCHANGED');return
 doc=json.loads((ROOT/'paired-release-manifest.json').read_text())
 if doc.get('appSha')!=APP_SHA:raise RuntimeError('Manifest source drift')
 if mode=='rollback':rollback(prepare,promote,doc);return
 if mode=='verify':
  for name,spec in doc['specs'].items():promote.wait_health(name,spec['image'],15)
  protected_check(prepare,doc['protected']);note('PAIRED_RELEASE_HEALTH_AND_PROTECTED_SERVICES_VERIFIED');return
 if doc['phase']!='prepared':raise RuntimeError('Release is not in prepared state')
 current_protected=preflight(prepare,promote)
 if current_protected!=doc['protected']:raise RuntimeError('Protected inventory changed since prepare')
 if doc['specs']!=SPECS:raise RuntimeError('Manifest specifications changed since prepare')
 for name,spec in doc['specs'].items():assert_parity(prepare.inspect(name),prepare.inspect(spec['stage']),spec)
 try:
  pause_timers(doc);doc['phase']='cutover-intent';save(doc)
  for name,spec in doc['specs'].items():
   note('PROMOTING_'+name);promote.promote(name,spec);protected_check(prepare,doc['protected'])
  if promote.curlcode('https://hub.v79sl.com/api/agent/work-actions') not in (401,403):raise RuntimeError('Anonymous work actions must be denied')
  if promote.curlcode('https://hub.v79sl.com/api/agent/skills') not in (401,403):raise RuntimeError('Anonymous skills must be denied')
  resume_timers(doc);doc['phase']='deployed';save(doc);note('PAIRED_RELEASE_PASS_ORIGINAL_CONTAINERS_RETAINED')
 except BaseException:
  note('RELEASE_FAILED_ROLLBACK_BEGIN');rollback(prepare,promote,doc);raise

if __name__=='__main__':
 try:main()
 except Exception as error:print('GUARDED_RELEASE_STOP='+type(error).__name__,flush=True);sys.exit(1)
