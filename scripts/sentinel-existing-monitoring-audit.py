#!/usr/bin/env python3
"""Read existing collector metadata/evidence only. No probes, keys or writes."""
import hashlib,json,os,re,shutil,socket,sqlite3,subprocess,time,urllib.request
from pathlib import Path

def cmd(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=30)
 return p.returncode,p.stdout

def readonly_db(path):
 conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
 conn.execute('PRAGMA query_only=ON')
 return conn

def database_summary(path):
 try:
  with readonly_db(path) as db:
   tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
   for table,column in [('sentinel_real_measurements','seen'),('sentinel_real_checks','updated')]:
    if table in tables:
     count,last=db.execute(f'SELECT count(*),max({column}) FROM {table}').fetchone()
     age=int(time.time())-int(last) if last is not None else None
     print('DB_TABLE='+table+'|COUNT='+str(count)+'|LAST_RECORD_AGE_SECONDS='+str(age))
   if 'sentinel_real_incidents' in tables:
    rows=db.execute('SELECT state,count(*) FROM sentinel_real_incidents GROUP BY state').fetchall()
    print('SIGNED_INCIDENT_STATE_COUNTS='+json.dumps({state:count for state,count in rows if state in ['open','resolved']}))
 except Exception:print('READ_ONLY_DATABASE_SUMMARY=UNAVAILABLE')

def acer():
 units=['v79-sentinel-noc.service','v79-sentinel-dell-signed.service','v79-sentinel-pilot-collect.service','v79-sentinel-app-readiness.service','v79-sentinel-app-public-check.service','v79-sentinel-app-incident-mock.service']
 for unit in units:
  code,out=cmd(['systemctl','--user','show',unit,'--property=ExecStart','--property=WorkingDirectory','--property=MainPID'])
  scripts=set(re.findall(r'(?<!\S)(/[^\s;{}]+\.(?:py|sh))(?=\s|;|$)',out))
  print('UNIT='+unit)
  for name in sorted(scripts):
   path=Path(name)
   if path.is_file():print('UNIT_SCRIPT='+name+'|SHA256='+hashlib.sha256(path.read_bytes()).hexdigest())
  cwd=next((line.split('=',1)[1] for line in out.splitlines() if line.startswith('WorkingDirectory=')),None)
  if cwd:print('WORKING_DIRECTORY='+cwd)
 root=Path.home()/'V79-Sentinel/secure-edge-transport-staging/data/v79-owned-pilot'
 for name in ['last-observation.json','app-checks-latest.json','service-readiness-latest.json','certificate-health.json','app-incidents-mock-latest.json']:
  path=root/name
  if not path.is_file() or path.is_symlink():print('EVIDENCE_FILE='+name+'|STATE=ABSENT_OR_UNSAFE');continue
  stat=path.stat()
  if stat.st_mode&0o077 or stat.st_size>65536:print('EVIDENCE_FILE='+name+'|STATE=UNSAFE');continue
  print('EVIDENCE_FILE='+name+'|MODIFIED_AGE_SECONDS='+str(max(0,int(time.time()-stat.st_mtime))))
  try:
   data=json.loads(path.read_text())
   for key in ['schema_version','collected_at','captured_at','checked_at','cycle']:
    value=data.get(key)
    if type(value) in [int,float] or isinstance(value,str) and re.fullmatch(r'[0-9T:Z+.-]{10,40}',value):print('EVIDENCE_METADATA='+key+'|'+str(value))
  except Exception:print('EVIDENCE_PARSE=UNAVAILABLE')
 dbpath=Path.home()/'V79-Sentinel/sentinel/data/noc-staging.sqlite3'
 database_summary(dbpath)
 # Independently re-check the most recent stored signed claim using PUBLIC material only.
 home=Path.home()/'.config/v79-sentinel/dell-signed-pilot'
 try:
  pub=home/'observer-ed25519.pub';config=home/'pilot-config.json'
  for path in [pub,config]:
   s=path.lstat()
   if path.is_symlink() or not path.is_file() or s.st_mode&0o077 or s.st_size>65536:raise ValueError()
  policy=json.loads(config.read_text());public=pub.read_bytes()
  if hashlib.sha256(public).hexdigest()!=policy.get('public_fingerprint'):raise ValueError()
  with readonly_db(dbpath) as db:
   row=db.execute('SELECT envelope FROM sentinel_real_measurements WHERE agent_id=? ORDER BY sequence DESC LIMIT 1',(policy['agent_id'],)).fetchone()
  if not row:raise ValueError()
  envelope=json.loads(row[0]);claims=envelope['claims']
  if policy.get('target_ip')!='192.168.100.163' or policy.get('target_port')!=443:raise ValueError()
  for a,b in [('agent_id','agent_id'),('check_id','check_id'),('customer_id','customer_id'),('site_id','site_id'),('target_ip','target_ip'),('target_port','target_port')]:
   if claims.get(a)!=policy.get(b):raise ValueError()
  from cryptography.hazmat.primitives import serialization
  from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
  key=serialization.load_pem_public_key(public)
  if not isinstance(key,Ed25519PublicKey):raise ValueError()
  key.verify(bytes.fromhex(envelope['signature']),json.dumps(claims,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
  age=int(time.time())-claims['observed_at']
  print('STORED_DELL_SIGNED_CLAIM=VALID_SIGNATURE_AND_LOCAL_PIN')
  print('SIGNED_CLAIM_AGE_SECONDS='+str(age))
  print('SIGNED_CLAIM_FRESH='+str(0<=age<=900))
  print('CLAIMED_PROBE_KIND='+('TCP' if claims.get('probe_kind')=='tcp' else 'UNEXPECTED'))
  print('CLAIMED_TCP_RESULT='+('OPEN' if claims.get('ok') is True else 'FAILED_OR_INVALID'))
  print('TRUST_LIMIT=LOCAL_KEY_CONSISTENCY_NOT_INDEPENDENT_SENSOR_ATTESTATION_OR_HTTPS_HEALTH')
 except Exception:print('STORED_DELL_SIGNED_CLAIM=UNAVAILABLE_OR_INVALID_NO_NEW_PROBE')

SERVER_READER=r'''
import hashlib,json,sqlite3,sys,time,urllib.request
from pathlib import Path
try:
 with urllib.request.urlopen('http://127.0.0.1:8788/readyz',timeout=3) as response: data=json.load(response)
 allowed={'simulated-only','disabled','live','unknown'}
 print('NOC_READINESS_COLLECTOR='+str(data.get('collector') if data.get('collector') in allowed else 'UNCLASSIFIED'))
 print('NOC_READINESS_INTEGRATIONS='+str(data.get('integrations') if data.get('integrations') in allowed else 'UNCLASSIFIED'))
except Exception:print('NOC_READINESS=UNAVAILABLE')
path=Path(sys.argv[1])
try:
 with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
  db.execute('PRAGMA query_only=ON')
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  for table,column in [('sentinel_real_measurements','seen'),('sentinel_real_checks','updated')]:
   if table in tables:
    count,last=db.execute('SELECT count(*),max('+column+') FROM '+table).fetchone()
    print('STAGE_SIGNED_TABLE='+table+'|COUNT='+str(count)+'|LAST_RECORD_AGE_SECONDS='+str(int(time.time())-int(last) if last else None))
except Exception:print('STAGE_DATABASE_SUMMARY=UNAVAILABLE')
'''
def server():
 code,out=cmd(['docker','ps','-a','--format','{{.Names}}'])
 for name in out.splitlines():
  if not re.fullmatch(r'[A-Za-z0-9_.-]*sentinel[A-Za-z0-9_.-]*',name):continue
  code,out=cmd(['docker','inspect',name])
  if code:continue
  row=json.loads(out)[0]
  print('STAGE_CONTAINER='+name+'|IMAGE='+row['Image']+'|HEALTH='+row['State'].get('Health',{}).get('Status','NONE'))
  print('CONTAINER_USER='+row['Config'].get('User','default'))
  print('HOST_NETWORK='+str(row['HostConfig'].get('NetworkMode')=='host'))
  print('DOCKER_SOCKET_MOUNTED='+str(any(m['Destination']=='/var/run/docker.sock' for m in row['Mounts'])))
  print('HOST_PORT_BINDINGS='+json.dumps(row['HostConfig'].get('PortBindings',{})))
  if 'noc' in name:
   args=row['Config'].get('Cmd',[])
   if isinstance(args,list) and '--db' in args:
    path=args[args.index('--db')+1]
    if path.startswith(('/app/data/','/data/')) and '..' not in Path(path).parts:
     code,out=cmd(['docker','exec',name,'python3','-c',SERVER_READER,path]);print(out.strip() if code==0 else 'STAGE_READER=UNAVAILABLE')
print('HOST='+socket.gethostname())
print('MODE=EXISTING_EVIDENCE_ONLY_NO_PROBES_NO_SECRET_KEYS_NO_MUTATIONS')
if socket.gethostname()=='v79sl':server()
else:acer()
print('PRODUCTION_CHANGES=NONE')
