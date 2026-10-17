#!/usr/bin/env python3
"""Prepare a private, nonexecuting Hub release plan. Never starts/stops containers."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

EXPECTED = {
 'v79-hub':'sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06',
 'v79-business-agent':'sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f',
 'v79-tiquet-manager':'sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42',
}
CANDIDATE='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'

def command(args, cwd=None):
 p=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=60)
 if p.returncode: raise RuntimeError('Command unavailable; no release prepared')
 return p.stdout

def env_map(rows):
 return dict(row.split('=',1) for row in rows or [] if '=' in row)

def write_private(path, value):
 with path.open('x',encoding='utf-8') as f:
  os.chmod(path,0o600)
  json.dump(value,f,indent=2); f.write('\n')

def main():
 os.umask(0o077)
 if socket.gethostname()!='v79sl': raise RuntimeError('Run on v79sl only')
 live=json.loads(command(['docker','inspect',*EXPECTED]))
 for item in live:
  name=item['Name'].lstrip('/')
  if item['Image']!=EXPECTED[name] or item['State'].get('Health',{}).get('Status')!='healthy':
   raise RuntimeError('Live baseline image/health changed')
 hub=next(item for item in live if item['Name']=='/v79-hub')
 labels=hub['Config']['Labels']
 files=labels['com.docker.compose.project.config_files'].split(',')
 working=labels['com.docker.compose.project.working_dir']
 project=labels['com.docker.compose.project']
 service=labels['com.docker.compose.service']
 if len(files)!=9 or service!='v79-hub': raise RuntimeError('Unexpected ordered Compose baseline')
 hashes={}
 for name in files:
  p=Path(name)
  if not p.is_absolute() or not p.is_file(): raise RuntimeError('Compose input missing')
  hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
 args=['docker','compose','--project-directory',working,'--project-name',project]
 for name in files: args+=['-f',name]
 baseline=json.loads(command(args+['config','--format','json'],cwd=working))
 svc=baseline['services'][service]
 image_env=env_map(json.loads(command(['docker','image','inspect',EXPECTED['v79-hub']]))[0]['Config'].get('Env'))
 actual=env_map(hub['Config'].get('Env'))
 expected_env={**image_env,**{k:str(v) for k,v in svc.get('environment',{}).items() if v is not None}}
 drift=sorted(k for k in set(actual)|set(expected_env) if actual.get(k)!=expected_env.get(k))
 if drift:
  print('ENVIRONMENT_PARITY=MISMATCH')
  for key in drift: print('DRIFT_VARIABLE_NAME='+key)
  raise RuntimeError('Compose environment does not reproduce running Hub; values withheld')
 resolved_base=json.loads(command(['docker','image','inspect',svc['image']]))[0]['Id']
 if resolved_base!=EXPECTED['v79-hub']: raise RuntimeError('Compose image does not resolve to live image')
 candidate=json.loads(command(['docker','image','inspect',CANDIDATE]))[0]
 if candidate['Id']!=CANDIDATE: raise RuntimeError('Candidate image unavailable')
 # Config must preserve container launch behavior; image-only change cannot silently change command.
 for key,config_key in [('entrypoint','Entrypoint'),('command','Cmd')]:
  configured=svc.get(key)
  effective=configured if configured is not None else candidate['Config'].get(config_key)
  if effective!=hub['Config'].get(config_key): raise RuntimeError('Candidate launch command differs')
 report_dir=Path.home()/'.local/share/v79-workforce-operations/reports'
 stat=report_dir.lstat()
 if report_dir.is_symlink() or not report_dir.is_dir() or stat.st_mode&0o077: raise RuntimeError('Unsafe report directory')
 target='/run/v79-workforce-reports'
 if any(m['Destination']==target for m in hub['Mounts']): raise RuntimeError('Report target already mounted')
 # Check existing bind/volume sources before preparing any override.
 current_mounts={m['Destination']:m for m in hub['Mounts']}
 configured_targets=set()
 for v in svc.get('volumes',[]):
  configured_targets.add(v['target'])
  actual_mount=current_mounts.get(v['target'])
  if not actual_mount: raise RuntimeError('Compose mount absent from runtime')
  source=v.get('source')
  if v['type']=='volume': source=baseline.get('volumes',{}).get(source,{}).get('name',source)
  actual_source=actual_mount.get('Name') if v['type']=='volume' else actual_mount.get('Source')
  if source!=actual_source or bool(v.get('read_only',False))==bool(actual_mount['RW']):
   raise RuntimeError('Compose mount differs from runtime')
 if configured_targets!=set(current_mounts): raise RuntimeError('Runtime has additional unaccounted mounts')
 stage=Path(tempfile.mkdtemp(prefix='v79-workforce-release-plan.',dir=Path.home()))
 overlay={'services':{service:{'image':CANDIDATE,'environment':{'V79_WORKFORCE_REPORTS_ENABLED':'1'},'volumes':[{'type':'bind','source':str(report_dir),'target':target,'read_only':True,'bind':{'create_host_path':False}}]}}}
 rollback={'services':{service:{'image':EXPECTED['v79-hub']}}}
 write_private(stage/'candidate.compose.json',overlay)
 write_private(stage/'rollback.compose.json',rollback)
 candidate_config=json.loads(command(args+['-f',str(stage/'candidate.compose.json'),'config','--format','json'],cwd=working))
 # Only three service fields may differ; every other service must be identical.
 for name,other in baseline['services'].items():
  if name!=service and candidate_config['services'].get(name)!=other: raise RuntimeError('Candidate changes another service')
 original=dict(svc);changed=dict(candidate_config['services'][service])
 for key in ['image','environment','volumes']:
  original.pop(key,None);changed.pop(key,None)
 if original!=changed: raise RuntimeError('Candidate changes additional Hub fields')
 next_svc=candidate_config['services'][service]
 next_env=dict(next_svc.get('environment',{}));next_env.pop('V79_WORKFORCE_REPORTS_ENABLED',None)
 old_env=dict(svc.get('environment',{}));old_env.pop('V79_WORKFORCE_REPORTS_ENABLED',None)
 if next_env!=old_env: raise RuntimeError('Candidate changes other environment values')
 if next_svc['environment'].get('V79_WORKFORCE_REPORTS_ENABLED')!='1': raise RuntimeError('Report flag not enabled in plan')
 before_volumes={v['target']:v for v in svc.get('volumes',[])}
 after_volumes={v['target']:v for v in next_svc.get('volumes',[])}
 if {k:v for k,v in after_volumes.items() if k!=target}!=before_volumes: raise RuntimeError('Existing mounts not preserved')
 if after_volumes[target].get('read_only') is not True: raise RuntimeError('Report mount is not read-only')
 rollback_config=json.loads(command(args+['-f',str(stage/'rollback.compose.json'),'config','--format','json'],cwd=working))
 if rollback_config['services'][service]!=svc: raise RuntimeError('Rollback overlay does not reproduce original service')
 # Detect source or runtime changes while this plan was calculated.
 if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in hashes.items()): raise RuntimeError('Compose inputs changed during preparation')
 after=json.loads(command(['docker','inspect',*EXPECTED]))
 if any(c['Image']!=EXPECTED[c['Name'].lstrip('/')] or c['State'].get('Health',{}).get('Status')!='healthy' for c in after): raise RuntimeError('Live image/health changed during preparation')
 manifest={'schema':1,'mode':'PREPARED_ONLY_NOT_DEPLOYED','workingDirectory':working,'project':project,'service':service,'orderedComposeFiles':files,'composeSha256':hashes,'currentImages':EXPECTED,'candidateImage':CANDIDATE,'candidateOverlay':str(stage/'candidate.compose.json'),'rollbackOverlay':str(stage/'rollback.compose.json'),'remainingGates':['fresh encrypted recovery verification','authenticated isolated browser acceptance','precutover parity recheck']}
 write_private(stage/'release-plan.json',manifest)
 print('ENVIRONMENT_PARITY=PASS')
 print('EXISTING_MOUNTS_PARITY=PASS')
 print('ORDERED_COMPOSE_INPUTS=9_PRESERVED')
 print('CANDIDATE_DIFF=IMAGE_REPORT_FLAG_READONLY_REPORT_MOUNT_ONLY')
 print('ROLLBACK_CONFIG_PARITY=PASS')
 print('LIVE_IMAGE_AND_HEALTH_RECHECK=PASS')
 print('RELEASE_PLAN_DIRECTORY='+str(stage))
 print('PRODUCTION_DEPLOYED=NO')

if __name__=='__main__':
 try: main()
 except Exception as exc:
  # Only local fixed diagnostic messages; never echo Docker stderr or config values.
  print('PREPARE=STOP')
  print('REASON='+str(exc) if isinstance(exc,RuntimeError) else 'REASON=Local prerequisite unavailable; details withheld')
  raise SystemExit(1)
