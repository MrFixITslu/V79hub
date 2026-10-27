#!/usr/bin/env python3
"""Hub-only SUPERVISOR for the PRE-EXISTING tested paired-compose-transaction engine.

Does NOT implement Docker recreate or rollback: calls engine.deploy/engine.rollback.
Keeps a persistent one-shot expiry timer for loss of operator connection.
"""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

ROOT=Path('/home/firelion/v79-v3-hardened-hub-manifest-20261026')
NAME='v79_v3_hardened_hub_release_v2.py'
COMPAT_SHA='11fb9d90d24939ff85ca71a2ce97d099899cd92a7514e0e213d3adaf1a6bb4f1'
FILE=ROOT/NAME
MANIFEST='4424b8ad83d66fe5b551bc9efc845545f0127fce66737f66cc2c5f8fe1076857'
PRIOR='sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4'
CANDIDATE='sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6'
REVISION='114841271d4f8b9c4b63df6aedfd55bde2e82f40'
REQUIRED={'--mfa-ok','--sso-ok','--visual-ok','--tenant-ok'}
TIMER='vision79-v3-hardened-hub-expiry.timer'
SERVICE='vision79-v3-hardened-hub-expiry.service'
UNITS=Path('/home/firelion/.config/systemd/user')
STATE=ROOT/'v3-hardened-state.json'
LOCK=ROOT/'v3-hardened.lock'
WINDOW=20*60
MODULES={
 'paired-compose-transaction.py':'a0d42890a4ad3f39203893dc166e2717545ebe4b',
 'paired-mount-contract.py':'00f46b9284a982748b697b253a4e34317d77f074',
 'paired-release-context.py':'fb32367a8f316884646980bc38f13dc0b43e50f0',
}
class Stop(Exception):pass

def check(ok,code):
 if not ok:raise Stop(code)

def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\x00'+data).hexdigest()

def sha(data):return hashlib.sha256(data).hexdigest()

def canon(data):return json.dumps(data,sort_keys=True,separators=(',',':')).encode()

def run(args,env=None,timeout=45,permissive=False):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop('COMMAND_UNAVAILABLE') from None
 if not permissive:check(p.returncode==0,'COMMAND_FAILED')
 return p

def sysenv():
 uid=pwd.getpwnam('firelion').pw_uid
 result=dict(os.environ)
 result['XDG_RUNTIME_DIR']=f'/run/user/{uid}'
 result['DBUS_SESSION_BUS_ADDRESS']=f'unix:path=/run/user/{uid}/bus'
 return result

def ctl(*args,permissive=False):
 return run(['systemctl','--user',*args],sysenv(),permissive=permissive).stdout.decode().strip()

def prop(unit,key):return ctl('show',unit,'--property',key,'--value')

def private(path):
 st=path.lstat()
 check(path.is_file() and not path.is_symlink() and st.st_uid==os.geteuid() and not st.st_mode&0o077,
       'PRIVATE_FILE_PERMISSION_DRIFT')
 return path.read_bytes()

@contextlib.contextmanager
def locked():
 check(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.stat().st_mode&0o077==0,
       'SEALED_DIRECTORY_UNSAFE')
 fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX)
  yield
 finally:
  fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

def state():
 if not STATE.exists():return None
 return json.loads(private(STATE))

def put(d):
 new=ROOT/('.state-tmp-'+str(os.getpid()))
 fd=os.open(new,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(canon(d));f.flush();os.fsync(f.fileno())
 os.replace(new,STATE)
 dirfd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(dirfd)
 finally:os.close(dirfd)

def engine_plan():
 check(os.uname().nodename=='v79sl' and os.geteuid()==pwd.getpwnam('firelion').pw_uid,
       'AUTHORIZED_DELL_USER_ONLY')
 for n,pin in MODULES.items():
  check(blob(private(ROOT/n))==pin,'HARDENED_ENGINE_MODULE_DRIFT')
 spec=importlib.util.spec_from_file_location('paired_compose_transaction',ROOT/'paired-compose-transaction.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 plan=module.load_plan(ROOT,MANIFEST)
 check(plan.get('schema')=='v79-hardened-hub-only-manifest-v1'
       and set(plan.get('apps',{}))=={'v79-hub'}
       and plan.get('requires_supervision') is True
       and len(plan.get('protected',{}))==43,'HUB_ONLY_MANIFEST_SCOPE_DRIFT')
 entry=plan['apps']['v79-hub']
 check(entry.get('rollback_image',{}).get('Id')==PRIOR
       and entry.get('candidate_image',{}).get('Id')==CANDIDATE
       and entry['candidate_image'].get('Config',{}).get('Labels',{}).get('org.opencontainers.image.revision')==REVISION,
       'HUB_IMAGE_SOURCE_PIN_DRIFT')
 check(entry.get('service')=='v79-hub','UNEXPECTED_SERVICE_SCOPE')
 backend=module.ComposeBackend(ROOT,plan)
 backend.check_files()
 compat_path=ROOT/'vision79-v3-image-label-compat.py'
 check(sha(private(compat_path))==COMPAT_SHA,'COMPAT_MODULE_DRIFT')
 spec=importlib.util.spec_from_file_location('v79_pinned_compat',compat_path)
 compat=importlib.util.module_from_spec(spec);spec.loader.exec_module(compat)
 check(run(['docker','compose','version','--short']).stdout.decode().strip()==entry['compose_version']
       and entry['compose_version'].lstrip('v')=='5.6.0','COMPOSE_VERSION_CHANGED')
 for pin in (CANDIDATE,PRIOR):compat.validate_image(compat.inspect_image(pin),pin)
 compat.install(module)
 module._v79_compat=compat
 bind_durable_context(backend,plan)
 return module,plan,backend

def bind_durable_context(backend,plan):
 original_switch=backend.switch
 original_verify=backend.verify
 def switch(name,which):
  s=state()
  check(isinstance(s,dict) and s.get('manifest_sha256')==MANIFEST,
        'DURABLE_RELEASE_CONTEXT_MISSING')
  previous=backend.inspect(name,allow_missing=which=='rollback')
  value=previous['Id'] if previous is not None else None
  check(value is None or re.fullmatch('[0-9a-f]{64}',value),'REPLACEMENT_CONTEXT_INVALID')
  s.setdefault('replacement_ids',{})[which]=value
  put(s) # fsync state before original engine's destructive Compose operation.
  return original_switch(name,which)
 def verify(name,which,row=None):
  s=state()
  check(isinstance(s,dict) and s.get('manifest_sha256')==MANIFEST
        and which in s.get('replacement_ids',{}),'DURABLE_REPLACEMENT_ID_MISSING')
  plan['apps'][name]['_replaced_id']=s['replacement_ids'][which]
  return original_verify(name,which,row)
 backend.switch=switch
 backend.verify=verify

def supervision_preflight():
 check(run(['loginctl','show-user','firelion','--property=Linger','--value']).stdout.decode().strip()=='yes',
       'USER_MANAGER_NOT_DURABLE_ACROSS_LOGOUT')
 check(prop(SERVICE,'ActiveState') in ('inactive','failed'), 'EXPIRY_SERVICE_ALREADY_RUNNING')
 check(not (UNITS/TIMER).exists() and not (UNITS/SERVICE).exists(),'EXPIRY_UNITS_ALREADY_EXIST')
 check(sha(private(FILE))==sha(Path(__file__).read_bytes()),'INSTALLED_SUPERVISOR_CHANGED')

def preflight():
 with locked():
  m,plan,backend=engine_plan()
  check(state() is None,'RELEASE_ALREADY_STARTED')
  assert_prior_snapshot(m,plan,backend)
  supervision_preflight()
  return {'result':'PASS_V2_INSTALLED_PREFLIGHT','protected_count':43,
          'production_changes':'NONE','release_gate':'HOLD'}

def prior_healthy(backend):
 row=backend.inspect('v79-hub',allow_missing=True)
 return bool(row is not None and row.get('Image')==PRIOR
             and (row.get('State') or {}).get('Status')=='running'
             and ((row.get('State') or {}).get('Health') or {}).get('Status')=='healthy')

def candidate_healthy(backend):
 row=backend.inspect('v79-hub',allow_missing=True)
 return bool(row is not None and row.get('Image')==CANDIDATE
             and (row.get('State') or {}).get('Status')=='running'
             and ((row.get('State') or {}).get('Health') or {}).get('Status')=='healthy')

def assert_prior_snapshot(m,plan,backend):
 backend.protected()
 row=backend.inspect('v79-hub')
 check(prior_healthy(backend),'BASELINE_HUB_NOT_HEALTHY')
 check(m.protected_fingerprint(row)==m.protected_fingerprint(plan['apps']['v79-hub']['baseline']),
       'SEALED_CURRENT_BASELINE_CHANGED')
 check(run(['docker','image','inspect',CANDIDATE]).returncode==0,'APPROVED_IMAGE_UNAVAILABLE')
 check(prop('vision79-v3-automatic-rollback.service','ActiveState')=='inactive'
       and prop('vision79-v3-automatic-rollback.timer','ActiveState')=='inactive',
       'PREVIOUS_WATCHDOG_NOT_CONTAINED')

def heart(stop):
 while not stop.is_set():
  tmp=ROOT/('.lease-'+str(os.getpid()))
  fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as f:
   f.write(canon({'monotonic':time.monotonic()}));f.flush();os.fsync(f.fileno())
  os.replace(tmp,ROOT/'supervision.json')
  stop.wait(4)

@contextlib.contextmanager
def heartbeat():
 # Ensure the first lease exists before the hardened engine's first supervised() check.
 seed=ROOT/('.lease-seed-'+str(os.getpid()))
 fd=os.open(seed,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:
  f.write(canon({'monotonic':time.monotonic()}));f.flush();os.fsync(f.fileno())
 os.replace(seed,ROOT/'supervision.json')
 halt=threading.Event()
 worker=threading.Thread(target=heart,args=(halt,),daemon=True)
 worker.start()
 try:yield
 finally:
  halt.set();worker.join(timeout=10)

def unit_text(deadline):
 utc=datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
 service=(f'[Unit]\nDescription=Vision79 v3 hardened-engine expiry rollback\n'
          f'[Service]\nType=oneshot\nTimeoutStartSec=900\n'
          f'ExecStart=/usr/bin/sg docker -c "/usr/bin/python3 -B {FILE} --expire"\n')
 timer=(f'[Unit]\nDescription=Vision79 v3 candidate expiry\n'
        f'[Timer]\nOnCalendar={utc}\nPersistent=true\nAccuracySec=1s\nUnit={SERVICE}\n'
        f'[Install]\nWantedBy=timers.target\n')
 return service,timer

def arm(deadline):
 check(UNITS.is_dir() and not UNITS.is_symlink() and UNITS.stat().st_uid==os.geteuid(),
       'SYSTEMD_USER_UNIT_DIRECTORY_MISSING')
 check(all(not p.exists() and not p.is_symlink() for p in (UNITS/TIMER,UNITS/SERVICE)),
       'EXPIRY_UNIT_ALREADY_EXISTS')
 a,b=unit_text(deadline)
 for path,contents in [(UNITS/SERVICE,a),(UNITS/TIMER,b)]:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'w') as f:f.write(contents);f.flush();os.fsync(f.fileno())
 ctl('daemon-reload');ctl('enable','--now',TIMER)
 check(prop(TIMER,'ActiveState')=='active','EXPIRY_TIMER_NOT_ACTIVE')
 next_time=prop(TIMER,'NextElapseUSecRealtime')
 check(next_time not in ('','n/a','N/A','infinity'),'EXPIRY_TIMER_NOT_SCHEDULED')

def disarm():
 result=run(['systemctl','--user','disable','--now',TIMER],sysenv(),permissive=True)
 return result.returncode==0 and prop(TIMER,'ActiveState')=='inactive'

def roll(m,backend,s):
 backend.protected()
 if prior_healthy(backend):
  row=backend.inspect('v79-hub')
  entry=backend.plan['apps']['v79-hub']
  if row['Id']==entry['baseline']['Id']:
   check(m.protected_fingerprint(row)==m.protected_fingerprint(entry['baseline']),
         'PRIOR_RUNTIME_CHANGED_NO_RECREATION')
  else:
   backend.verify('v79-hub','rollback',row)
  s=state() or s
  # Never recreate a verified healthy prior Hub.
  s['phase']='PRIOR_HEALTHY_NO_RECREATION'
  put(s)
  return 'PRIOR_IMAGE_HEALTHY_NO_RECREATION'
 try:
  outcome=m.rollback(backend,['v79-hub'])
  check(outcome.get('status')=='PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED',
        'ORIGINAL_ENGINE_ROLLBACK_INCOMPLETE')
  backend.protected()
  check(prior_healthy(backend),'PRIOR_IMAGE_NOT_HEALTHY_AFTER_ROLLBACK')
  s=state() or s
  s['phase']='ROLLED_BACK';put(s)
  return 'PASS_HARDENED_ENGINE_PRIOR_RESTORED'
 except Exception:
  s=state() or s
  s['phase']='ROLLBACK_MANUAL_REVIEW';put(s)
  raise

def deployment():
 check(os.getenv('V79_V3_OWNER_PRESENT')=='I_AM_PRESENT_FOR_MFA_SSO_AND_VISUAL_CHECKS',
       'OWNER_SUPERVISION_REQUIRED')
 with locked():
  m,plan,backend=engine_plan()
  check(state() is None,'RELEASE_ALREADY_STARTED')
  assert_prior_snapshot(m,plan,backend)
  supervision_preflight()
  print('IMAGE_LABEL_PROOF=REUSED_CHECKING_NEW_REPLACEMENT_CODEC',flush=True)
  with heartbeat():
   proof=m._v79_compat.replacement_profiles(m,backend)
   check(proof.get('profiles_verified')==2,'TWO_STOPPED_REPLACEMENT_PROFILES_REQUIRED')
  assert_prior_snapshot(m,plan,backend)
  print('STOPPED_REPLACEMENT_CODEC_PROOF=PASS_BOTH',flush=True)
  due=time.time()+WINDOW
  s={'schema':'v79-hardened-hub-v3','phase':'ARMING','deadline_epoch':due,
     'owner_accepted':False,'prior':PRIOR,'candidate':CANDIDATE,'manifest_sha256':MANIFEST}
  put(s)
  print('RELEASE_PHASE=ARM_PERSISTENT_HARDENED_ROLLBACK_TIMER',flush=True)
  arm(due)
  s['phase']='WATCHDOG_ARMED';put(s)
  print('RELEASE_PHASE=WATCHDOG_ARMED_NOW_SWITCH_HUB_ONLY',flush=True)
  try:
   with heartbeat():outcome=m.deploy(backend)
   s=state()
   if outcome.get('status')=='PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING':
    check(candidate_healthy(backend),'CANDIDATE_HEALTH_CHANGED_AFTER_ENGINE')
    backend.protected()
    s['phase']='OWNER_REVIEW_PENDING';put(s)
    return {'result':'V3_HARDENED_HUB_LIVE_REVIEW_PENDING','deadline_epoch':int(due),
            'candidate_healthy':True,'protected_count':len(plan['protected']),
            'owner_acceptance_required':True,
            'deadline_saint_lucia':datetime.datetime.fromtimestamp(due,datetime.timezone(
              datetime.timedelta(hours=-4))).isoformat(),
            'release_gate':'HOLD'}
   check(outcome.get('status')=='PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED'
         and outcome.get('candidate_deployment_failed') is True,
         'ENGINE_DEPLOY_OUTCOME_UNEXPECTED')
   s=state() or s
   s['phase']='ROLLED_BACK';put(s)
   closed=disarm()
   return {'result':'V3_CANDIDATE_FAILED_PRIOR_RESTORED','reason':outcome.get('candidate_failure_reason'),
           'timer_disabled':closed,'release_gate':'HOLD'}
  except Exception:
   s=state() or s
   s['phase']='RECOVERY_PENDING';put(s)
   try:
    result=roll(m,backend,s)
    closed=disarm()
    return {'result':'V3_RELEASE_FAILED_RECOVERY_'+result,'timer_disabled':closed,
            'release_gate':'HOLD'}
   except Exception:
    return {'result':'V3_RELEASE_FAILED_SINGLE_WATCHDOG_ATTEMPT_AT_DEADLINE',
            'release_gate':'HOLD'}

def expire(manual=False):
 with locked():
  m,plan,backend=engine_plan()
  s=state()
  check(isinstance(s,dict) and s.get('manifest_sha256')==MANIFEST,'PENDING_RELEASE_STATE_MISSING')
  check(s.get('phase') not in ('ACCEPTED',),'ACCEPTED_RELEASE_NO_ROLLBACK')
  if s.get('phase') in ('ROLLED_BACK','PRIOR_HEALTHY_NO_RECREATION'):
   return {'result':'NOOP_ALREADY_RECOVERED','release_gate':'HOLD'}
  if not manual:check(time.time()>=s.get('deadline_epoch',0)-3,'EXPIRY_BEFORE_DEADLINE')
  result=roll(m,backend,s)
  closed=disarm() if manual else True
  return {'result':result,'timer_disabled':closed if manual else None,'release_gate':'HOLD'}

def accept(attestations):
 check(set(attestations)==REQUIRED and len(attestations)==4,'FOUR_GENUINE_OWNER_CHECKS_REQUIRED')
 with locked():
  m,plan,backend=engine_plan()
  s=state()
  check(isinstance(s,dict) and s.get('phase')=='OWNER_REVIEW_PENDING',
        'OWNER_REVIEW_NOT_PENDING')
  check(time.time()<s['deadline_epoch']-30,'OWNER_ACCEPTANCE_DEADLINE_EXPIRED')
  check(prop(TIMER,'ActiveState')=='active','AUTO_ROLLBACK_NOT_ARMED')
  with heartbeat():
   backend.healthy('v79-hub','candidate')
  backend.protected()
  check(candidate_healthy(backend),'CANDIDATE_NOT_HEALTHY')
  s['phase']='ACCEPTED';s['owner_accepted']=True
  s['owner_acceptance_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  s['owner_checks']=sorted(attestations)
  put(s)
  closed=disarm()
  return {'result':'PASS_V3_HARDENED_HUB_OWNER_ACCEPTED',
          'candidate_live_healthy':True,'timer_disabled':closed,
          'release_gate':'GO' if closed else 'ACCEPTED_TIMER_DISARM_REVIEW'}

def status():
 with locked():
  m,plan,backend=engine_plan()
  s=state()
  h=backend.inspect('v79-hub',allow_missing=True)
  return {'result':'HUB_RELEASE_STATUS','phase':s.get('phase') if isinstance(s,dict) else 'NOT_STARTED',
          'hub_image':h.get('Image') if h else None,
          'hub_health':((h.get('State') or {}).get('Health') or {}).get('Status') if h else None,
          'timer_state':prop(TIMER,'ActiveState') if (UNITS/TIMER).exists() else 'NOT_CREATED',
          'release_gate':'GO' if isinstance(s,dict) and s.get('phase')=='ACCEPTED' else 'HOLD'}

class Tests(unittest.TestCase):
 def test_only_four_attestations(self):
  self.assertEqual(len(REQUIRED),4)
  self.assertEqual(len(set(REQUIRED)),4)
 def test_valid_systemd_deadline(self):
  a,b=unit_text(1793059961)
  self.assertIn('--expire',a)
  self.assertIn('Persistent=true',b)
  self.assertIn('AccuracySec=1s',b)
 def test_original_engine_is_source_of_rollback(self):
  import inspect as ip
  self.assertIn('m.rollback(backend',ip.getsource(roll))
  self.assertNotIn('docker compose up',ip.getsource(roll))
 def test_prior_healthy_idempotent(self):
  mock=MagicMock();m=MagicMock()
  original=globals()['prior_healthy']
  globals()['prior_healthy']=lambda b:True
  old=globals()['put'];globals()['put']=lambda s:None
  try:
   s={'phase':'RECOVERY_PENDING'}
   self.assertEqual(roll(m,mock,s),'PRIOR_IMAGE_HEALTHY_NO_RECREATION')
   m.rollback.assert_not_called()
  finally:
   globals()['prior_healthy']=original;globals()['put']=old

if __name__=='__main__':
 arg=argparse.ArgumentParser()
 mode=arg.add_mutually_exclusive_group(required=True)
 for a in ('deploy','accept','expire','rollback','status','preflight','self-test'):
  mode.add_argument('--'+a,action='store_true')
 for a in sorted(REQUIRED):arg.add_argument(a,action='store_true')
 x=arg.parse_args()
 try:
  if x.self_test:
   t=unittest.main(argv=[sys.argv[0]],exit=False)
   sys.exit(0 if t.result.wasSuccessful() else 2)
  if x.preflight:result=preflight()
  elif x.deploy:result=deployment()
  elif x.accept:result=accept([a for a in REQUIRED if getattr(x,a[2:].replace('-','_'))])
  elif x.expire:result=expire()
  elif x.rollback:result=expire(manual=True)
  else:result=status()
  print(json.dumps(result,sort_keys=True))
  if x.deploy and result.get('result')!='V3_HARDENED_HUB_LIVE_REVIEW_PENDING':sys.exit(2)
  if x.accept and result.get('release_gate')!='GO':sys.exit(2)
 except Exception as e:
  value=str(e)
  reason=value if re.fullmatch('[A-Z][A-Z0-9_]+',value) else type(e).__name__
  print(json.dumps({'result':'STOP_HARDENED_RELEASE','reason':reason,'release_gate':'HOLD'}))
  sys.exit(2)
