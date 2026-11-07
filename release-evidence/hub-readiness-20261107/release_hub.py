import os,json,subprocess,hashlib,secrets,tarfile,io,fcntl,socket,http.client,time,sys
from pathlib import Path
ROOT=Path('/home/firelion/.v79-production-readiness-20261107');BASE='sha256:e605371a5ee8125fbaf73670fd6722811d9ac20eb3f870bbb339c4c5f0a83ecb';TAG='localhost/v79-readiness-hub:20261107';BACKUP='v79-hub-rollback-readiness-20261107'
os.umask(0o077)
def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
def inspect(name):return json.loads(docker('inspect',name))[0]
def sha(data):return hashlib.sha256(data).hexdigest()
class UnixHTTP(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect('/var/run/docker.sock')
def api(method,path,payload=None):
 c=UnixHTTP('localhost');body=None if payload is None else json.dumps(payload).encode();c.request(method,'/v1.47'+path,body,{'Content-Type':'application/json'});r=c.getresponse();b=r.read();c.close()
 if r.status>=300:raise RuntimeError('Docker request failed '+str(r.status)+' '+path)
 return json.loads(b) if b else None
def guard():
 d=inspect('v79-hub');assert d['Image']==BASE,'Live Hub changed; reconcile before release';assert d['State']['Health']['Status']=='healthy';return d
mode=sys.argv[1]
if mode=='backup':
 d=guard();(ROOT/'hub-runtime.private.json').write_text(json.dumps(d));sessions=subprocess.check_output(['docker','exec','v79-hub','cat','/app/data/hub-sessions.json']);(ROOT/'hub-sessions.before.json').write_bytes(sessions)
 with (ROOT/'hub-before.pgdump').open('wb') as out:subprocess.run(['docker','exec','v79-hub-postgres','sh','-c','exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner'],stdout=out,check=True)
 chk=subprocess.run(['docker','exec','-i','v79-hub-postgres','pg_restore','--list'],input=(ROOT/'hub-before.pgdump').read_bytes(),capture_output=True);assert chk.returncode==0,'Checkpoint dump unreadable'
 key=ROOT/'hub-recovery.pass';assert not key.exists(),'Recovery files already exist; do not overwrite';key.write_text(secrets.token_urlsafe(48));os.chmod(key,0o600)
 buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w:gz') as tar:
  for name in ['hub-runtime.private.json','hub-sessions.before.json','hub-before.pgdump','hub-release-manifest.json']:tar.add(ROOT/name,arcname=name)
 subprocess.run(['gpg','--batch','--yes','--pinentry-mode','loopback','--passphrase-file',str(key),'--symmetric','--cipher-algo','AES256','--output',str(ROOT/'hub-recovery.tar.gz.gpg')],input=buf.getvalue(),check=True,capture_output=True)
 record={'archive_sha256':sha((ROOT/'hub-recovery.tar.gz.gpg').read_bytes()),'plaintext_sha256':sha(buf.getvalue()),'dump_list_readable':True,'base_image':BASE};(ROOT/'hub-backup-record.json').write_text(json.dumps(record));print(json.dumps({'backup_created':True,'encrypted':True,'pg_dump_list_readable':True,'archive_bytes':(ROOT/'hub-recovery.tar.gz.gpg').stat().st_size}));sys.exit()
assert mode=='deploy';assert (ROOT/'offhost-hub-backup-pass.json').exists(),'Off-host verification required'
lock=open('/home/firelion/.v79-deploy.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
old=guard();candidate=docker('image','inspect',TAG,'--format','{{.Id}}');assert candidate!=BASE
try:inspect(BACKUP);raise RuntimeError('Rollback name already exists')
except subprocess.CalledProcessError:pass
manifest=json.loads((ROOT/'hub-release-manifest.json').read_text())
for name,digest in manifest['changed_files'].items():
 if name=='Dockerfile':continue
 actual=subprocess.check_output(['docker','run','--rm','--network','none','--entrypoint','sha256sum',TAG,'/app/'+name],text=True).split()[0];assert actual==digest,'Candidate file mismatch '+name
config=dict(old['Config']);config['Image']=candidate
networks={name:{'Aliases':[a for a in (data.get('Aliases') or []) if a!=old['Id'][:12]]} for name,data in old['NetworkSettings']['Networks'].items()}
config['HostConfig']=old['HostConfig'];config['NetworkingConfig']={'EndpointsConfig':networks}
changed=False;created=None
try:
 api('POST','/containers/v79-hub/stop?t=25');api('POST','/containers/v79-hub/rename?name='+BACKUP);changed=True
 api('POST','/containers/'+BACKUP+'/update',{'RestartPolicy':{'Name':'no','MaximumRetryCount':0}})
 created=api('POST','/containers/create?name=v79-hub',config)['Id'];api('POST','/containers/'+created+'/start');print('HUB_CANDIDATE_STARTED',flush=True)
 for _ in range(55):
  d=inspect('v79-hub');health=d['State'].get('Health',{}).get('Status');assert d['State']['Running'],'Candidate exited'
  if health=='healthy':break
  if health=='unhealthy':raise RuntimeError('Candidate unhealthy')
  time.sleep(2)
 else:raise RuntimeError('Candidate readiness timed out')
 d=inspect('v79-hub');assert d['Image']==candidate;assert d['Config']['Env']==old['Config']['Env'];assert set(d['NetworkSettings']['Networks'])==set(old['NetworkSettings']['Networks'])
 for key in ['Binds','Mounts','ReadonlyRootfs','SecurityOpt','CapDrop','CapAdd','PortBindings','NetworkMode','Memory','NanoCpus']:
  assert d['HostConfig'].get(key)==old['HostConfig'].get(key),'Runtime setting changed '+key
 checks={}
 for path,expected in [('/',200),('/api/health',200),('/api/auth/google/config',200),('/api/agent/work-actions',401),('/api/agent/skills',401),('/api/help/catalog',401),('/owner-step-up-client.js',200),('/assets/index-V79Readiness20261107.js',200)]:
  code=subprocess.check_output(['curl','-sS','--max-time','15','-o','/dev/null','-w','%{http_code}','https://hub.v79sl.com'+path],text=True);assert code==str(expected),'Public check failed '+path;checks[path]=int(code)
 code=subprocess.check_output(['curl','-sS','--max-time','15','-X','POST','-H','Origin: https://hub.v79sl.com','-H','Content-Type: application/json','--data','{}','-o','/dev/null','-w','%{http_code}','https://hub.v79sl.com/api/security/mfa/step-up/challenge'],text=True);assert code=='401';checks['anonymous_step_up_POST']=401
 public=subprocess.check_output(['curl','-fsS','--max-time','15','https://hub.v79sl.com/owner-step-up-client.js']);assert sha(public)==manifest['changed_files']['dist/owner-step-up-client.js']
 record={'status':'DEPLOYED_VERIFIED','base_image':BASE,'live_image':candidate,'rollback_container':BACKUP,'public_checks':checks,'runtime_settings_preserved':True,'database_migrations':0,'new_production_tasks':0,'owner_live_MFA_journey':'OWNER_ACCEPTANCE_PENDING'};(ROOT/'hub-deployment-record.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
except BaseException:
 if created:api('DELETE','/containers/'+created+'?force=true')
 if changed:
  api('POST','/containers/'+BACKUP+'/rename?name=v79-hub');api('POST','/containers/v79-hub/update',{'RestartPolicy':old['HostConfig']['RestartPolicy']});api('POST','/containers/v79-hub/start');print('PREVIOUS_HUB_RESTORED',flush=True)
 else:
  try:api('POST','/containers/v79-hub/start')
  except:pass
 raise
