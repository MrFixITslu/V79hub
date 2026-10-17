#!/usr/bin/env python3
"""Owner-authorized activation of read-only briefing history only."""
import hashlib,json,os,shlex,socket,subprocess,time
from pathlib import Path
ROOT=Path('/home/firelion/v79-workforce-release-plan.dhc2pyxi')
IMAGE='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'

def run(args,cwd=None,timeout=60):
 p=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError('Command failed; private details withheld')
 return p.stdout

def env(rows):return dict(item.split('=',1) for item in rows or [] if '=' in item)
def private(path,obj):
 with path.open('x') as f:os.chmod(path,0o600);json.dump(obj,f,indent=2)

def verify_flag_only(baseline,desired,service):
 normalized=json.loads(json.dumps(desired))
 if normalized['services'][service]['environment'].get('V79_WORKFORCE_REPORTS_ENABLED')!='1':raise RuntimeError('Enable flag not effective')
 normalized['services'][service]['environment']['V79_WORKFORCE_REPORTS_ENABLED']='0'
 if normalized!=baseline:raise RuntimeError('Activation changes more than one environment flag')

def main():
 os.umask(0o077)
 if socket.gethostname()!='v79sl':raise RuntimeError('Run on v79sl only')
 plan=json.loads((ROOT/'release-plan.json').read_text())
 receipt=json.loads((ROOT/'disabled-cutover-success.json').read_text())
 if receipt['image']!=IMAGE or receipt['reportsEnabled'] is not False:raise RuntimeError('Disabled cutover receipt unavailable')
 for name,digest in plan['composeSha256'].items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Original Compose input changed')
 live=json.loads(run(['docker','inspect','v79-hub','v79-business-agent','v79-tiquet-manager']))
 hub=next(row for row in live if row['Name']=='/v79-hub')
 for row in live:
  expected=IMAGE if row['Name']=='/v79-hub' else plan['currentImages'][row['Name'].lstrip('/')]
  if row['Image']!=expected or row['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Live image/health changed')
 if env(hub['Config'].get('Env')).get('V79_WORKFORCE_REPORTS_ENABLED')!='0':raise RuntimeError('Expected disabled report state')
 files=hub['Config']['Labels']['com.docker.compose.project.config_files'].split(',')
 if files!=plan['orderedComposeFiles']+[str(ROOT/'reports-disabled.compose.json')]:raise RuntimeError('Running Compose stack differs from disabled cutover')
 args=['docker','compose','--project-directory',plan['workingDirectory'],'--project-name',plan['project']]
 for file in files:args+=['-f',file]
 def config(extra=None):return json.loads(run(args+(['-f',str(extra)] if extra else [])+['config','--format','json'],cwd=plan['workingDirectory']))
 baseline=config();svc=baseline['services'][plan['service']]
 image=json.loads(run(['docker','image','inspect',IMAGE]))[0]
 expected={**env(image['Config'].get('Env')),**{k:str(v) for k,v in svc.get('environment',{}).items() if v is not None}}
 if env(hub['Config'].get('Env'))!=expected:raise RuntimeError('Compose environment drift')
 overlay=ROOT/'reports-enable-flag.compose.json'
 flag={'services':{plan['service']:{'environment':{'V79_WORKFORCE_REPORTS_ENABLED':'1'}}}}
 if overlay.exists():
  if json.loads(overlay.read_text())!=flag:raise RuntimeError('Enable overlay differs')
 else:private(overlay,flag)
 desired=config(overlay)
 verify_flag_only(baseline,desired,plan['service'])
 rollback=args+['up','-d','--no-deps','--no-build','--pull','never',plan['service']]
 rollback_file=ROOT/'disable-reports-command.txt'
 if not rollback_file.exists():
  with rollback_file.open('x') as f:os.chmod(rollback_file,0o600);f.write(shlex.join(rollback)+'\n')
 print('ACTIVATION_DIFF=ONE_REPORT_ACCESS_FLAG_ONLY',flush=True)
 print('IMAGE_AND_MOUNTS=UNCHANGED',flush=True)
 print('DISABLE_REPORTS_COMMAND_FILE='+str(rollback_file),flush=True)
 private(ROOT/'enable-reports-attempt.json',{'state':'STARTED','at':time.time(),'image':IMAGE})
 run(args+['-f',str(overlay),'up','-d','--no-deps','--no-build','--pull','never',plan['service']],cwd=plan['workingDirectory'],timeout=180)
 healthy=False
 for attempt in range(60):
  row=json.loads(run(['docker','inspect','v79-hub']))[0]
  if row['Image']==IMAGE and row['State'].get('Health',{}).get('Status')=='healthy':healthy=True;break
  time.sleep(2)
 if not healthy:raise RuntimeError('Enabled Hub health not confirmed')
 if env(row['Config'].get('Env'))!={**env(hub['Config'].get('Env')),'V79_WORKFORCE_REPORTS_ENABLED':'1'}:raise RuntimeError('Postactivation environment differs')
 def mounts(item):return sorted([{k:m.get(k) for k in ['Type','Source','Destination','RW','Name']} for m in item['Mounts']],key=lambda m:m['Destination'])
 if mounts(row)!=mounts(hub):raise RuntimeError('Postactivation mounts differ')
 # Confirm the validated reader can see reports in the exact active runtime.
 reader="import {createPythonBriefingStatus} from './server/workforce-python-report-reader.mjs';const r=await createPythonBriefingStatus({directory:'/run/v79-workforce-reports'})();if(r.status!=='report_available'||!r.reports.length)process.exit(1);console.log('ACTIVE_RUNTIME_REPORT_READER=PASS');console.log('REPORT_COUNT='+r.reports.length);const response=await fetch('http://127.0.0.1:3040/api/agent/workforce-briefings');if(![401,403].includes(response.status))process.exit(1);console.log('ANONYMOUS_REPORT_ACCESS=DENIED');"
 print(run(['docker','exec','v79-hub','node','--input-type=module','-e',reader]).strip(),flush=True)
 for original in live:
  if original['Name']=='/v79-hub':continue
  current=json.loads(run(['docker','inspect',original['Name']]))[0]
  if current['Id']!=original['Id'] or current['Image']!=original['Image'] or current['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Another live service changed')
 private(ROOT/'reports-enabled-success.json',{'state':'HEALTHY_REPORTS_ENABLED','at':time.time(),'image':IMAGE,'browserReportAcceptance':'OUTSTANDING','executionEnabledByThisRelease':False})
 print('HUB_HEALTH=HEALTHY')
 print('REPORT_ACCESS=ENABLED_READ_ONLY')
 print('AGENT_AND_TIQUET=UNCHANGED_HEALTHY')
 print('NEW_SCHEDULER_STARTED=NO')
 print('WORKER_OR_AUTONOMY_ACTIVATED=NO')
 print('OWNER_REPORT_BROWSER_CHECK=NEXT')
if __name__=='__main__':
 try:main()
 except Exception as error:
  print('ENABLE_REPORTS=STOPPED_OR_UNCERTAIN_NO_AUTOMATIC_RETRY')
  print('REASON='+str(error) if isinstance(error,RuntimeError) else 'REASON='+type(error).__name__)
  print('DISABLE_REPORTS_COMMAND_FILE='+str(ROOT/'disable-reports-command.txt'))
  raise SystemExit(1)
