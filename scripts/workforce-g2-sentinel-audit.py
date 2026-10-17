#!/usr/bin/env python3
"""Read-only signed queue, scheduler and Sentinel runtime metadata audit."""
import hashlib,json,os,re,shutil,socket,subprocess
from pathlib import Path

def cmd(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=40)
 return p.returncode,p.stdout

def schedules():
 for scope in ['user','system']:
  prefix=['systemctl']+(['--user'] if scope=='user' else [])
  code,out=cmd(prefix+['list-timers','--all','--no-pager','--full'])
  rows=[line for line in out.splitlines() if re.search(r'v79|workforce|sentinel',line,re.I)]
  print('TIMER_SCOPE='+scope+'|QUERY='+('AVAILABLE' if code==0 else 'UNAVAILABLE')+'|MATCHES='+str(len(rows)))
  for row in rows:print('TIMER_METADATA='+row.strip())
  code,out=cmd(prefix+['list-unit-files','--no-pager','--no-legend'])
  for row in out.splitlines():
   name=row.split()[0] if row.split() else ''
   if re.search(r'(v79|workforce|sentinel)',name,re.I) and name.endswith('.service'):
    rc,state=cmd(prefix+['show',name,'--property=ActiveState','--property=SubState','--property=Result','--property=ExecMainStatus'])
    print('SERVICE='+scope+':'+name+'|'+state.strip().replace('\n','|'))
 if shutil.which('crontab'):
  code,out=cmd(['crontab','-l'])
  print('USER_CRON_WORKER_REFERENCE='+('PRESENT' if 'workforce-release-worker' in out else 'NOT_FOUND' if code in [0,1] else 'UNAVAILABLE'))

NODE=r'''
import fs from 'node:fs';
import crypto from 'node:crypto';
import {createWorkActionStore} from './server/workforce-action-store.mjs';
const flag=process.env.V79_WORKFORCE_ACTIONS_ENABLED==='1';
console.log('G2_ACTIONS_FLAG='+String(flag));
const key=process.env.V79_WORKFORCE_AUDIT_KEY||'';
console.log('G2_AUDIT_KEY_CONFIGURED='+String(key.length>=32));
const token=process.env.V79_WORKFORCE_TOKEN_FILE||'/run/secrets/v79-workforce-token';
try{const s=fs.lstatSync(token);console.log('WORKER_TOKEN_METADATA='+String(s.isFile()&&!s.isSymbolicLink()&&!(s.mode&0o077)&&s.size>=32));}catch{console.log('WORKER_TOKEN_METADATA=UNAVAILABLE');}
if(key.length>=32){
 const ledger=createWorkActionStore({file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',secret:key,backend:process.env.V79_HUB_STORE_BACKEND||'json',databaseUrl:process.env.DATABASE_URL||''});
 try{
  const state=await ledger.read();
  console.log('QUEUE_READ=PASS_STORE_READER_VALIDATES_EXISTING_ENVELOPES');
  console.log('QUEUE_PAUSED='+String(state.paused));
  const allowed=new Set(['proposed','pending','approved','rejected','cancelled','running','succeeded','failed','uncertain','expired']);const counts={};
  for(const j of state.jobs){const k=allowed.has(j.status)?j.status:'other';counts[k]=(counts[k]||0)+1;}
  console.log('QUEUE_STATUS_COUNTS='+JSON.stringify(counts));
  console.log('COO_TASK_COUNT='+state.tasks.length);
  console.log('AUDIT_EVENT_COUNT='+state.events.length);
  console.log('APPROVED_BUT_EXPIRED='+state.jobs.filter(j=>j.status==='approved'&&Date.parse(j.approval?.expiresAt)<=Date.now()).length);
 }catch{console.log('SIGNED_QUEUE_READ=UNAVAILABLE_OR_INTEGRITY_FAILURE');}
 finally{await ledger.close();}
}
for(const file of ['scripts/workforce-release-worker.mjs','server/workforce-actions.mjs','server/workforce-action-routes.mjs']){
 try{console.log('SOURCE_SHA256='+file+'|'+crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'));}catch{console.log('SOURCE_UNAVAILABLE='+file);}
}
'''
print('HOST='+socket.gethostname())
print('MODE=READ_ONLY_NO_CLAIM_NO_APPROVAL_NO_EXECUTION')
schedules()
if socket.gethostname()=='v79sl' and shutil.which('docker'):
 code,out=cmd(['docker','inspect','v79-hub'])
 if code:raise SystemExit('STOP=HUB_UNAVAILABLE')
 hub=json.loads(out)[0]
 print('HUB_IMAGE='+hub['Image'])
 print('HUB_HEALTH='+hub['State'].get('Health',{}).get('Status','UNAVAILABLE'))
 files=hub['Config']['Labels'].get('com.docker.compose.project.config_files','').split(',')
 print('HUB_COMPOSE_INPUT_COUNT='+str(len(files)))
 code,out=cmd(['docker','image','inspect',hub['Image']])
 if code==0:
  label=json.loads(out)[0]['Config'].get('Labels',{}).get('org.opencontainers.image.revision','')
  print('HUB_REVISION_LABEL='+ (label if re.fullmatch('[0-9a-f]{40}',label) else 'ABSENT_OR_UNVERIFIED'))
 code,out=cmd(['docker','exec','v79-hub','node','--input-type=module','-e',NODE])
 print(out.strip() if code==0 else 'QUEUE_AUDIT=UNAVAILABLE_NO_MUTATIONS')
 code,out=cmd(['docker','ps','-a','--format','{{.Names}}|{{.Image}}|{{.Status}}'])
 rows=[row for row in out.splitlines() if 'sentinel' in row.lower()]
 print('SENTINEL_CONTAINER_MATCHES='+str(len(rows)))
 for row in rows:print('SENTINEL_CONTAINER='+row)
else:
 for directory in [Path.home()/'V79-Sentinel/g221-mobilefix-isolated-review',Path.home()/'V79-Sentinel']:
  if (directory/'.git').exists():
   code,out=cmd(['git','-C',str(directory),'rev-parse','HEAD']);print('ACER_SENTINEL_HEAD='+out.strip())
print('PRODUCTION_CHANGES=NONE')
