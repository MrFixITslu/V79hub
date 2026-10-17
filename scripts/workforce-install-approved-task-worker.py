#!/usr/bin/env python3
"""Install a task-only G2 timer. No release claims or Hub recreation."""
import hashlib,json,os,shlex,socket,subprocess,sys
from pathlib import Path
WORKER_SOURCE='#!/usr/bin/env python3\n"""Only executes the fixed G2 approved-work-item endpoint. No release claims."""\nimport json,os,re,sys,urllib.request\nfrom pathlib import Path\nURL=\'https://hub.v79sl.com/internal/workforce/execute-work-item\'\nclass NoRedirect(urllib.request.HTTPRedirectHandler):\n def redirect_request(self,*args,**kwargs):raise RuntimeError(\'Redirect refused\')\ndef run_once(config,opener=None):\n if set(config)!={\'schema\',\'tokenFile\'} or config[\'schema\']!=1:raise ValueError(\'Invalid worker configuration\')\n file=Path(config[\'tokenFile\']);s=file.lstat()\n if not file.is_absolute() or file.is_symlink() or not file.is_file() or s.st_mode&0o077 or not 32<=s.st_size<=512:raise ValueError(\'Unsafe worker token\')\n token=file.read_text().strip()\n if not 32<=len(token)<=256 or re.search(r\'\\s\',token):raise ValueError(\'Invalid worker credential\')\n request=urllib.request.Request(URL,data=b\'{}\',method=\'POST\',headers={\'Content-Type\':\'application/json\',\'X-V79-Workforce-Token\':token,\'Accept\':\'application/json\',\'User-Agent\':\'V79-approved-task-worker\'})\n transport=opener or urllib.request.build_opener(NoRedirect())\n with transport.open(request,timeout=20) as response:\n  if response.status!=200:raise RuntimeError(\'Unexpected worker status\')\n  raw=response.read(65537)\n  if len(raw)>65536:raise RuntimeError(\'Oversized worker response\')\n  body=json.loads(raw)\n if not isinstance(body,dict) or set(body)!={\'job\'}:raise RuntimeError(\'Unexpected worker envelope\')\n job=body[\'job\']\n if job is None:return {\'state\':\'idle\',\'operation\':\'create_work_item\'}\n if not isinstance(job,dict) or job.get(\'operation\')!=\'create_work_item\' or job.get(\'status\')!=\'succeeded\':raise RuntimeError(\'Unexpected operation result\')\n if not isinstance(job.get(\'digest\'),str) or not re.fullmatch(\'[0-9a-f]{64}\',job[\'digest\']):raise RuntimeError(\'Missing approved job digest\')\n return {\'state\':\'succeeded\',\'operation\':\'create_work_item\',\'approvedDigest\':job[\'digest\']}\ndef main():\n os.umask(0o077)\n if len(sys.argv)!=2:raise ValueError(\'Provide private configuration path\')\n config_file=Path(sys.argv[1]);root=config_file.parent;blocked=root/\'uncertain.json\'\n if blocked.exists():print(\'TASK_WORKER=BLOCKED_PENDING_OPERATOR_RECONCILIATION\');return\n try:\n  s=config_file.lstat()\n  if config_file.is_symlink() or s.st_mode&0o077:raise ValueError(\'Unsafe configuration\')\n  result=run_once(json.loads(config_file.read_text()))\n  temporary=root/\'status.tmp\'\n  with temporary.open(\'w\') as f:os.chmod(temporary,0o600);json.dump(result,f);f.flush();os.fsync(f.fileno())\n  os.replace(temporary,root/\'status.json\')\n  print(\'TASK_WORKER=\'+result[\'state\'].upper())\n except Exception:\n  # No automatic retry after an unknown POST outcome or missing receipt.\n  with blocked.open(\'x\') as f:os.chmod(blocked,0o600);json.dump({\'state\':\'uncertain\',\'action\':\'inspect_signed_queue_before_reset\'},f)\n  print(\'TASK_WORKER=UNCERTAIN_RECONCILIATION_REQUIRED\');raise SystemExit(1)\nif __name__==\'__main__\':main()\n'
IMAGE='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'
def run(args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=45)
 if p.returncode:raise RuntimeError('Operator prerequisite or service failed; no automatic retry')
 return p.stdout.strip()
def private(path,text):
 with path.open('x') as f:os.chmod(path,0o600);f.write(text)
def main():
 os.umask(0o077)
 if socket.gethostname()!='v79sl':raise RuntimeError('Run on v79sl only')
 if run(['loginctl','show-user',str(os.getuid()),'--property=Linger','--value'])!='yes':raise RuntimeError('Persistent user scheduling unavailable')
 hub=json.loads(run(['docker','inspect','v79-hub']))[0]
 if hub['Image']!=IMAGE or hub['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Hub baseline changed')
 env=dict(item.split('=',1) for item in hub['Config']['Env'] if '=' in item)
 if env.get('V79_WORKFORCE_ACTIONS_ENABLED')!='1':raise RuntimeError('G2 owner-approved actions are disabled')
 target=env.get('V79_WORKFORCE_TOKEN_FILE','/run/secrets/v79-workforce-token')
 mount=next((m for m in hub['Mounts'] if m['Destination']==target),None)
 if not mount or mount['RW']:raise RuntimeError('Separate read-only worker credential mount unavailable')
 token=Path(mount['Source']);stat=token.lstat()
 if token.is_symlink() or not token.is_file() or stat.st_mode&0o077 or not 32<=stat.st_size<=512 or not os.access(token,os.R_OK):raise RuntimeError('Separate worker credential is not privately readable')
 audit="import {createWorkActionStore} from './server/workforce-action-store.mjs';const l=createWorkActionStore({file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',secret:process.env.V79_WORKFORCE_AUDIT_KEY,backend:process.env.V79_HUB_STORE_BACKEND||'json',databaseUrl:process.env.DATABASE_URL||''});try{const s=await l.read();console.log(JSON.stringify({paused:s.paused,approved:s.jobs.filter(j=>j.status==='approved').length,running:s.jobs.filter(j=>j.status==='running').length}));}finally{await l.close()}"
 queue=json.loads(run(['docker','exec','v79-hub','node','--input-type=module','-e',audit]))
 if queue['approved'] or queue['running']:raise RuntimeError('Existing approved/running work requires reconciliation before installing a new schedule')
 home=Path.home();root=home/'.local/share/v79-approved-task-worker';units=home/'.config/systemd/user'
 names=['v79-g2-approved-task-worker.service','v79-g2-approved-task-worker.timer']
 if any((units/n).exists() or (units/n).is_symlink() for n in names):raise RuntimeError('Existing worker units must be reconciled; nothing overwritten')
 root.mkdir(parents=True,exist_ok=True,mode=0o700);units.mkdir(parents=True,exist_ok=True,mode=0o700)
 script=root/'worker.py';config=root/'config.json'
 private(script,WORKER_SOURCE);private(config,json.dumps({'schema':1,'tokenFile':str(token)}))
 service='[Unit]\nDescription=V79 G2 owner-approved task creation only\n[Service]\nType=oneshot\nUMask=0077\nNoNewPrivileges=true\nMemoryMax=96M\nCPUQuota=20%\nTimeoutStartSec=35\nExecStart=/usr/bin/python3 -I '+str(script)+' '+str(config)+'\n'
 timer='[Unit]\nDescription=V79 G2 approved task poll (no release worker)\n[Timer]\nOnBootSec=90s\nOnUnitActiveSec=60s\nAccuracySec=5s\nUnit='+names[0]+'\n[Install]\nWantedBy=timers.target\n'
 private(units/names[0],service);private(units/names[1],timer)
 run(['systemctl','--user','daemon-reload'])
 try:run(['systemctl','--user','start',names[0]])
 except RuntimeError:
  print('WORKER_FIRST_POLL=FAILED_TIMER_NOT_ENABLED')
  raise
 state=json.loads((root/'status.json').read_text())
 if state.get('state')!='idle':raise RuntimeError('Initial task worker poll was not idle; inspect before enabling timer')
 run(['systemctl','--user','enable','--now',names[1]])
 if run(['systemctl','--user','is-active',names[1]])!='active':raise RuntimeError('Worker timer not active')
 current=json.loads(run(['docker','inspect','v79-hub']))[0]
 if current['Id']!=hub['Id'] or current['State'].get('Health',{}).get('Status')!='healthy':raise RuntimeError('Live Hub identity/health changed')
 private(root/'installation.json',json.dumps({'schema':1,'operation':'create_work_item','sourceSha256':hashlib.sha256(WORKER_SOURCE.encode()).hexdigest(),'releaseClaimsEnabled':False}))
 print('G2_TASK_WORKER_FIRST_POLL=IDLE')
 print('G2_TASK_WORKER_TIMER=ACTIVE_60_SECONDS')
 print('SCOPE=EXACT_OWNER_APPROVED_CREATE_WORK_ITEM_ONLY')
 print('RELEASE_WORKER_SCHEDULED=NO')
 print('AUTONOMOUS_APPROVAL_OR_DEPLOYMENT=NO')
 print('HUB_CONTAINER=UNCHANGED_HEALTHY')
 print('WORKER_DIRECTORY='+str(root))
if __name__=='__main__':
 try:main()
 except Exception as error:
  print('G2_WORKER_INSTALL=STOPPED_NO_AUTOMATIC_RETRY')
  print('REASON='+str(error) if isinstance(error,RuntimeError) else 'REASON='+type(error).__name__)
  raise SystemExit(1)
