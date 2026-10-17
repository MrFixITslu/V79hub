#!/usr/bin/env python3
"""Read-test dedicated token, then enable only owner-MFA GitHub workboard."""
import hashlib,json,os,shlex,socket,subprocess,time
from pathlib import Path
ROOT=Path('/home/firelion/v79-workforce-release-plan.dhc2pyxi')
IMAGE='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'
TARGET='/run/secrets/v79-coo-github-token'
READER=r"""
import fs from 'node:fs';
import {readCooGithubRepo} from './server/owner-coo-workboard.mjs';
const path='/run/secrets/v79-coo-github-token';const stat=fs.lstatSync(path);
if(!stat.isFile()||stat.isSymbolicLink()||(stat.mode&0o077)||stat.size<16||stat.size>512)process.exit(1);
const token=fs.readFileSync(path,'utf8').trim();
if(token.length<16||token.length>256||/\s/.test(token))process.exit(1);
const repos=['V79hub','V79Tiquet','V79-Sentinel','V79Marketing','V79acaedmy','V79POS'];
let all=true;
for(const repo of repos){const result=await readCooGithubRepo(repo,token);console.log('REPO='+repo+'|READ_STATUS='+result.state);if(result.state!=='COMPLETE')all=false;}
if(!all)process.exit(2);
console.log('DEDICATED_GITHUB_READ_CHECK=PASS_6_REPOSITORIES');
"""
def run(args,cwd=None,timeout=60):
 p=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError('Command failed; private details withheld')
 return p.stdout

def env(rows):return dict(item.split('=',1) for item in rows or [] if '=' in item)
def private(path,data):
 with path.open('x') as f:os.chmod(path,0o600);json.dump(data,f,indent=2)

def verify_diff(baseline,desired,service,token_file):
 normalized=json.loads(json.dumps(desired));before=baseline['services'][service]
 after=normalized['services'][service]
 if after['environment'].pop('V79_COO_WORKBOARD_ENABLED',None)!='1':raise RuntimeError('Workboard enable flag missing')
 if 'V79_COO_WORKBOARD_ENABLED' in before.get('environment',{}):after['environment']['V79_COO_WORKBOARD_ENABLED']=before['environment']['V79_COO_WORKBOARD_ENABLED']
 additions=[v for v in after.get('volumes',[]) if v['target']==TARGET]
 if len(additions)!=1 or additions[0].get('source')!=token_file or not additions[0].get('read_only') or additions[0].get('bind',{}).get('create_host_path') is not False:raise RuntimeError('Unexpected token mount')
 after['volumes']=[v for v in after['volumes'] if v['target']!=TARGET]
 if normalized!=baseline:raise RuntimeError('Activation changes more than workboard flag and token mount')

def main():
 os.umask(0o077)
 if socket.gethostname()!='v79sl':raise RuntimeError('Run on v79sl only')
 plan=json.loads((ROOT/'release-plan.json').read_text())
 receipt=json.loads((ROOT/'reports-enabled-success.json').read_text())
 if receipt['image']!=IMAGE:raise RuntimeError('Reporting release receipt differs')
 token_file=Path.home()/'.v79-secrets/coo-github-readonly.token';stat=token_file.lstat()
 if token_file.is_symlink() or not token_file.is_file() or stat.st_mode&0o077 or not 16<=stat.st_size<=512:raise RuntimeError('Unsafe dedicated token metadata')
 for file,digest in plan['composeSha256'].items():
  if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=digest:raise RuntimeError('Original Compose input changed')
 live=json.loads(run(['docker','inspect','v79-hub','v79-business-agent','v79-tiquet-manager']))
 hub=next(r for r in live if r['Name']=='/v79-hub')
 for row in live:
  expected=IMAGE if row['Name']=='/v79-hub' else plan['currentImages'][row['Name'].lstrip('/')]
  if row['Image']!=expected or row['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Live baseline changed')
 current_env=env(hub['Config'].get('Env'))
 if current_env.get('V79_COO_GITHUB_TOKEN_FILE',TARGET)!=TARGET:raise RuntimeError('Configured token target differs from planned mount')
 if current_env.get('V79_WORKFORCE_REPORTS_ENABLED')!='1' or current_env.get('V79_COO_WORKBOARD_ENABLED')=='1':raise RuntimeError('Unexpected live workforce flag state')
 files=hub['Config']['Labels']['com.docker.compose.project.config_files'].split(',')
 expected_files=plan['orderedComposeFiles']+[str(ROOT/'reports-disabled.compose.json'),str(ROOT/'reports-enable-flag.compose.json')]
 if files!=expected_files or any(m['Destination']==TARGET for m in hub['Mounts']):raise RuntimeError('Current Compose inputs/token mounts differ')
 # Temporary exact-image reader; only the dedicated token is mounted.
 print('STAGE=TEMPORARY_FIXED_REPOSITORY_READ_TEST',flush=True)
 args=['docker','run','--rm','--network','bridge','--read-only','--user','0:0','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges','--memory','256m','--cpus','1','--pids-limit','64','--mount','type=bind,src='+str(token_file)+',dst='+TARGET+',readonly','--entrypoint','node',IMAGE,'--input-type=module','-e',READER]
 p=subprocess.run(args,text=True,capture_output=True,timeout=90)
 # This reader emits only curated repository identifiers and enums, never token/API content.
 print(p.stdout.strip(),flush=True)
 if p.returncode:raise RuntimeError('Dedicated read check failed; Hub not changed')
 compose=['docker','compose','--project-directory',plan['workingDirectory'],'--project-name',plan['project']]
 for file in files:compose+=['-f',file]
 def config(extra=None):return json.loads(run(compose+(['-f',str(extra)] if extra else [])+['config','--format','json'],cwd=plan['workingDirectory']))
 baseline=config();svc=baseline['services'][plan['service']]
 image=json.loads(run(['docker','image','inspect',IMAGE]))[0]
 expected={**env(image['Config'].get('Env')),**{k:str(v) for k,v in svc.get('environment',{}).items() if v is not None}}
 if current_env!=expected:raise RuntimeError('Current Compose environment differs from runtime')
 overlay=ROOT/'workboard-enabled.compose.json'
 addition={'services':{plan['service']:{'environment':{'V79_COO_WORKBOARD_ENABLED':'1'},'volumes':[{'type':'bind','source':str(token_file),'target':TARGET,'read_only':True,'bind':{'create_host_path':False}}]}}}
 if overlay.exists():
  if json.loads(overlay.read_text())!=addition:raise RuntimeError('Existing workboard overlay differs')
 else:private(overlay,addition)
 verify_diff(baseline,config(overlay),plan['service'],str(token_file))
 rollback=compose+['up','-d','--no-deps','--no-build','--pull','never',plan['service']]
 rollback_file=ROOT/'disable-workboard-command.txt'
 if not rollback_file.exists():
  with rollback_file.open('x') as f:os.chmod(rollback_file,0o600);f.write(shlex.join(rollback)+'\n')
 private(ROOT/'workboard-enable-attempt.json',{'state':'STARTED','at':time.time(),'image':IMAGE})
 print('ACTIVATION_DIFF=WORKBOARD_FLAG_AND_READONLY_TOKEN_MOUNT_ONLY',flush=True)
 print('DISABLE_WORKBOARD_COMMAND_FILE='+str(rollback_file),flush=True)
 run(compose+['-f',str(overlay),'up','-d','--no-deps','--no-build','--pull','never',plan['service']],cwd=plan['workingDirectory'],timeout=180)
 healthy=False
 for attempt in range(60):
  row=json.loads(run(['docker','inspect','v79-hub']))[0]
  if row['Image']==IMAGE and row['State'].get('Health',{}).get('Status')=='healthy':healthy=True;break
  time.sleep(2)
 if not healthy:raise RuntimeError('Activated Hub health not confirmed')
 if env(row['Config'].get('Env'))!={**current_env,'V79_COO_WORKBOARD_ENABLED':'1'}:raise RuntimeError('Postactivation environment changed unexpectedly')
 actual={m['Destination']:m for m in row['Mounts']};mounted=actual.pop(TARGET,None)
 if not mounted or mounted['RW'] or mounted['Source']!=str(token_file):raise RuntimeError('Runtime token mount differs')
 for m in hub['Mounts']:
  item=actual.pop(m['Destination'],None)
  if not item or any(item.get(k)!=m.get(k) for k in ['Type','Source','Destination','RW','Name']):raise RuntimeError('Existing runtime mount changed')
 if actual:raise RuntimeError('Unexpected runtime mount')
 check="const r=await fetch('http://127.0.0.1:3040/api/agent/coo-workboard');if(![401,403].includes(r.status))process.exit(1);console.log('ANONYMOUS_WORKBOARD_ACCESS=DENIED');"
 print(run(['docker','exec','v79-hub','node','--input-type=module','-e',check]).strip(),flush=True)
 for original in live:
  if original['Name']=='/v79-hub':continue
  current=json.loads(run(['docker','inspect',original['Name']]))[0]
  if current['Id']!=original['Id'] or current['Image']!=original['Image'] or current['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Another live service changed')
 private(ROOT/'workboard-enabled-success.json',{'state':'HEALTHY_WORKBOARD_ENABLED','at':time.time(),'image':IMAGE,'browserAcceptance':'OUTSTANDING','executionActivated':False})
 print('HUB_HEALTH=HEALTHY')
 print('WORKBOARD_CONNECTION=ENABLED_READ_ONLY')
 print('REPORTS=REMAIN_ENABLED')
 print('AGENT_AND_TIQUET=UNCHANGED_HEALTHY')
 print('WORKER_OR_AUTONOMY_ACTIVATED=NO')
 print('OWNER_WORKBOARD_BROWSER_CHECK=NEXT')
if __name__=='__main__':
 try:main()
 except Exception as error:
  print('WORKBOARD_ENABLE=STOPPED_OR_UNCERTAIN_NO_AUTOMATIC_RETRY')
  print('REASON='+str(error) if isinstance(error,RuntimeError) else 'REASON='+type(error).__name__)
  raise SystemExit(1)
