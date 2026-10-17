#!/usr/bin/env python3
"""Owner-authorized Hub-only cutover with workforce report access disabled."""
import hashlib,json,os,shlex,socket,subprocess,sys,time
from pathlib import Path
OLD='sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06'
NEW='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'
PLAN=Path('/home/firelion/v79-workforce-release-plan.dhc2pyxi/release-plan.json')

def run(args,cwd=None,timeout=60):
 p=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError('Release command failed; private Docker output withheld')
 return p.stdout

def env(rows):return dict(row.split('=',1) for row in rows or [] if '=' in row)
def private(path,data):
 with path.open('x') as f:os.chmod(path,0o600);json.dump(data,f,indent=2)
def main():
 os.umask(0o077)
 if socket.gethostname()!='v79sl':raise RuntimeError('Run on v79sl only')
 plan=json.loads(PLAN.read_text());root=PLAN.parent
 if plan['candidateImage']!=NEW or plan['currentImages']['v79-hub']!=OLD:raise RuntimeError('Release plan identity mismatch')
 files=plan['orderedComposeFiles']
 if len(files)!=9:raise RuntimeError('Expected nine original Compose inputs')
 for file in files:
  if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=plan['composeSha256'][file]:raise RuntimeError('Original Compose input changed')
 names=list(plan['currentImages']);live=json.loads(run(['docker','inspect',*names]))
 for row in live:
  if row['Image']!=plan['currentImages'][row['Name'].lstrip('/')] or row['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Live baseline changed')
 hub=next(row for row in live if row['Name']=='/v79-hub')
 if hub['Config']['Labels']['com.docker.compose.project.config_files'].split(',')!=files:raise RuntimeError('Running Compose stack changed')
 args=['docker','compose','--project-directory',plan['workingDirectory'],'--project-name',plan['project']]
 for file in files:args+=['-f',file]
 def config(extra=None):return json.loads(run(args+(['-f',str(extra)] if extra else [])+['config','--format','json'],cwd=plan['workingDirectory']))
 baseline=config();svc=baseline['services'][plan['service']]
 image=json.loads(run(['docker','image','inspect',OLD]))[0]
 expected={**env(image['Config'].get('Env')),**{k:str(v) for k,v in svc.get('environment',{}).items() if v is not None}}
 if expected!=env(hub['Config'].get('Env')):raise RuntimeError('Effective environment no longer matches runtime')
 if json.loads(run(['docker','image','inspect',svc['image']]))[0]['Id']!=OLD:raise RuntimeError('Original Compose image changed')
 candidate_image=json.loads(run(['docker','image','inspect',NEW]))[0]
 for key in ['Cmd','Entrypoint','User','WorkingDir']:
  if candidate_image['Config'].get(key)!=image['Config'].get(key):raise RuntimeError('Candidate image launch defaults differ')
 enabled=json.loads(Path(plan['candidateOverlay']).read_text())
 enabled['services'][plan['service']]['environment']['V79_WORKFORCE_REPORTS_ENABLED']='0'
 overlay=root/'reports-disabled.compose.json'
 if overlay.exists():
  if json.loads(overlay.read_text())!=enabled:raise RuntimeError('Existing disabled overlay differs')
 else:private(overlay,enabled)
 desired=config(overlay)
 for name,original in baseline['services'].items():
  if name!=plan['service'] and desired['services'].get(name)!=original:raise RuntimeError('Another service would change')
 target=desired['services'][plan['service']]
 if target.get('image')!=NEW:raise RuntimeError('Candidate overlay image changed')
 a=dict(svc);b=dict(target)
 for key in ['image','environment','volumes']:a.pop(key,None);b.pop(key,None)
 if a!=b:raise RuntimeError('Unexpected Hub configuration change')
 before=dict(svc.get('environment',{}));after=dict(target.get('environment',{}))
 before.pop('V79_WORKFORCE_REPORTS_ENABLED',None)
 if after.pop('V79_WORKFORCE_REPORTS_ENABLED',None)!='0' or before!=after:raise RuntimeError('Reports not disabled or other environment changed')
 old_mounts={m['target']:m for m in svc.get('volumes',[])};new_mounts={m['target']:m for m in target.get('volumes',[])}
 report=new_mounts.pop('/run/v79-workforce-reports',None)
 if not report or not report.get('read_only') or report.get('source')!=str(Path.home()/'.local/share/v79-workforce-operations/reports') or new_mounts!=old_mounts:raise RuntimeError('Mount configuration drift')
 if config(Path(plan['rollbackOverlay']))['services'][plan['service']]!=svc:raise RuntimeError('Rollback configuration drift')
 rollback=args+['-f',plan['rollbackOverlay'],'up','-d','--no-deps','--no-build','--pull','never',plan['service']]
 command_path=root/'rollback-command.txt'
 if not command_path.exists():
  with command_path.open('x') as f:os.chmod(command_path,0o600);f.write(shlex.join(rollback)+'\n')
 print('PRECUTOVER_CONFIG_PARITY=PASS',flush=True)
 print('REPORT_ACCESS=DISABLED',flush=True)
 print('ROLLBACK_COMMAND_FILE='+str(command_path),flush=True)
 # One explicit mutation, one service; no retry or automatic rollback.
 marker=root/'cutover-attempt.json'
 private(marker,{'state':'STARTED','at':time.time(),'oldImage':OLD,'newImage':NEW,'reportsEnabled':False})
 print('STAGE=REPLACE_ONLY_V79_HUB',flush=True)
 run(args+['-f',str(overlay),'up','-d','--no-deps','--no-build','--pull','never',plan['service']],cwd=plan['workingDirectory'],timeout=180)
 healthy=False
 for attempt in range(60):
  row=json.loads(run(['docker','inspect','v79-hub']))[0]
  if row['Image']==NEW and row['State'].get('Health',{}).get('Status')=='healthy':healthy=True;break
  time.sleep(2)
 if not healthy:raise RuntimeError('Candidate health not confirmed; inspect before rollback')
 if env(row['Config'].get('Env')).get('V79_WORKFORCE_REPORTS_ENABLED')!='0':raise RuntimeError('Runtime report flag is not disabled')
 if env(row['Config'].get('Env'))!={**env(hub['Config'].get('Env')),'V79_WORKFORCE_REPORTS_ENABLED':'0'}:raise RuntimeError('Postcutover environment drift')
 actual_mounts={m['Destination']:m for m in row['Mounts']}
 mounted=actual_mounts.pop('/run/v79-workforce-reports',None)
 if not mounted or mounted['RW'] or mounted['Source']!=report['source']:raise RuntimeError('Runtime report mount mismatch')
 for prior_mount in hub['Mounts']:
  current_mount=actual_mounts.pop(prior_mount['Destination'],None)
  if not current_mount or any(current_mount.get(k)!=prior_mount.get(k) for k in ['Type','Source','Destination','RW','Name']):raise RuntimeError('Runtime original mount changed')
 if actual_mounts:raise RuntimeError('Unexpected runtime mount')
 for original in live:
  if original['Name']=='/v79-hub':continue
  current=json.loads(run(['docker','inspect',original['Name']]))[0]
  if current['Id']!=original['Id'] or current['Image']!=original['Image'] or current['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Other live service changed')
 private(root/'disabled-cutover-success.json',{'state':'HEALTHY_REPORTS_DISABLED','at':time.time(),'image':NEW,'browserAcceptance':'OUTSTANDING','reportsEnabled':False})
 print('HUB_IMAGE_SWITCH=PASS_EXACT_CANDIDATE')
 print('HUB_HEALTH=HEALTHY')
 print('REPORT_ACCESS=DISABLED')
 print('AGENT_AND_TIQUET=UNCHANGED_HEALTHY')
 print('OWNER_LOGIN_MFA_BROWSER_CHECK=NEXT')

if __name__=='__main__':
 try:main()
 except Exception as error:
  print('CUTOVER=STOPPED_OR_UNCERTAIN_NO_AUTOMATIC_RETRY')
  print('REASON='+str(error) if isinstance(error,RuntimeError) else 'REASON='+type(error).__name__)
  print('ROLLBACK_COMMAND_FILE='+str(PLAN.parent/'rollback-command.txt'))
  raise SystemExit(1)
