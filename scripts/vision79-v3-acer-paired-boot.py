#!/usr/bin/env python3
"""Disconnected Acer smoke of candidate Hub, Tiquet, restored DBs and app data.

Uses synthetic credentials, RAM-backed scratch, no published ports, and no
production access. Also cold-boots the prior Hub image as rollback rehearsal.
This is not real owner MFA/SSO acceptance or exact Compose runtime parity.
"""
import hashlib,json,os,re,secrets,shutil,socket,subprocess,sys,tarfile,tempfile,time,unittest
from pathlib import Path,PurePosixPath
from unittest.mock import patch

ROOT=Path('/home/firelion/v79-v3-offhost-we7b0lir')
COPY=ROOT/'v3-20261026T194538Z-gnm710en'
RECEIPT_HASH='35a9b4d41b5c42a8c6653e1c1985ebdae49ce77432d57c94ff68c82172173df5'
IMAGES={
 'candidate':'sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6',
 'prior':'sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4',
 'tiquet':'sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0',
 'hub_db':'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
 'tiquet_db':'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685'}
SELECTED={'v79-hub-mount-01.tar.gpg':('data','hub_data'),
 'v79-tiquet-manager-mount-01.tar.gpg':('data','tiquet_data'),
 'v79-tiquet-manager-mount-02.tar.gpg':('uploads','tiquet_uploads')}
SQL="SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON c.relnamespace=n.oid WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%';"
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def call(args,timeout=90):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop('LOCAL_COMMAND_FAILED') from None
 need(p.returncode==0 and len(p.stdout)<8*1024*1024,'LOCAL_COMMAND_FAILED')
 return p.stdout.strip()
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def preflight():
 need(socket.gethostname().split('.')[0]=='firelion-Aspire-A315-51','ACER_HOST_REQUIRED')
 need(os.geteuid()!=0 and not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'),'LOCAL_DOCKER_ONLY')
 need(call(['docker','context','show'])==b'default' and
  call(['docker','info','--format','{{.Name}}'])==b'firelion-Aspire-A315-51','LOCAL_DOCKER_DAEMON_REQUIRED')
 need(Path('/dev/shm').is_dir() and call(['stat','-f','-c','%T','/dev/shm'])==b'tmpfs'
  and shutil.disk_usage('/dev/shm').free>=1024**3,'RAM_SCRATCH_UNAVAILABLE')
 swap=subprocess.run(['swapon','--noheadings','--show'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
 need(swap.returncode==0 and not swap.stdout.strip(),'ACTIVE_SWAP_REFUSED_FOR_PRIVATE_RECOVERY')
 proof=ROOT/'offhost-verification.json';db=ROOT/'isolated-db-restore.json';receipt=COPY/'receipt.json'
 need(all(p.is_file() and not p.is_symlink() for p in (proof,db,receipt)) and
  digest(receipt)==RECEIPT_HASH,'RECOVERY_PROOF_MISSING')
 a=json.loads(proof.read_text());b=json.loads(db.read_text());r=json.loads(receipt.read_text())
 need(a.get('decryption_and_structure')=='PASS_14' and
  b.get('database_restore')=='PASS_BOTH' and
  a.get('server_receipt_sha256')==b.get('server_receipt_sha256')==RECEIPT_HASH,'RECOVERY_PROOF_DRIFT')
 for name in [*SELECTED,'hub-postgres.dump.gpg','tiquet-postgres.dump.gpg']:
  p=COPY/name
  need(p.is_file() and not p.is_symlink() and digest(p)==r['encrypted_sha256'].get(name),'ARCHIVE_DRIFT')
 for image in IMAGES.values():
  rows=json.loads(call(['docker','image','inspect',image]))
  need(len(rows)==1 and rows[0].get('Id')==image,'PINNED_IMAGE_UNAVAILABLE')
def extract(archive,prefix,dest,total):
 dest.mkdir(mode=0o700)
 p=subprocess.Popen(['gpg','--batch','--quiet','--decrypt',str(archive)],
  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 count=0
 try:
  with tarfile.open(fileobj=p.stdout,mode='r|') as tar:
   for member in tar:
    count+=1;need(count<=20000,'TAR_MEMBER_COUNT_LIMIT')
    n=member.name.removeprefix('./').rstrip('/')
    parts=PurePosixPath(n).parts
    need(n and not n.startswith('/') and '..' not in parts and '\\' not in n and '\x00' not in n,'TAR_PATH_UNSAFE')
    allowed=(prefix,prefix+'/'+prefix,'app/'+prefix)
    root=next((x for x in allowed if n==x or n.startswith(x+'/')),None)
    need(root is not None and (member.isfile() or member.isdir()),'TAR_MEMBER_UNSAFE')
    suffix=n[len(root):].lstrip('/')
    if not suffix:
     need(member.isdir(),'TAR_ROOT_NOT_DIRECTORY')
     continue
    need(len(PurePosixPath(suffix).parts)<=14,'TAR_NESTING_LIMIT')
    target=dest/suffix
    need(not target.is_symlink(),'TAR_SYMLINK_TARGET')
    if member.isdir():target.mkdir(mode=0o700,parents=True);continue
    need(0<=member.size<=64*1024*1024,'TAR_FILE_LIMIT')
    total[0]+=member.size;need(total[0]<=512*1024*1024,'RAM_DATA_LIMIT')
    target.parent.mkdir(mode=0o700,parents=True)
    need(not target.exists(),'DUPLICATE_TAR_MEMBER')
    source=tar.extractfile(member);need(source is not None,'TAR_SOURCE_INVALID')
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:
     remaining=member.size
     while remaining:
      block=source.read(min(131072,remaining));need(block,'TAR_TRUNCATED')
      output.write(block);remaining-=len(block)
  p.stdout.close();need(p.wait(timeout=60)==0,'TAR_DECRYPT_FAILED')
 finally:
  if p.stdout and not p.stdout.closed:p.stdout.close()
  if p.poll() is None:p.kill()
  p.wait()
 need(count>0,'EMPTY_APP_MOUNT')
def restore_dump(container,name,port):
 producer=subprocess.Popen(['gpg','--batch','--quiet','--decrypt',str(COPY/name)],
  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 receiver=None
 try:
  receiver=subprocess.Popen(['docker','exec','-i',container,'pg_restore','-U','postgres','-p',str(port),'--no-owner','--no-acl',
   '--single-transaction','--exit-on-error','--dbname=postgres'],
   stdin=producer.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  producer.stdout.close()
  good=receiver.wait(timeout=900)==0;auth=producer.wait(timeout=60)==0
  need(good and auth,'RESTORE_STREAM_FAILED')
 finally:
  if receiver is not None and receiver.poll() is None:receiver.kill()
  if producer.poll() is None:producer.kill()
  if receiver is not None:receiver.wait()
  producer.wait()
 count=call(['docker','exec',container,'psql','-X','-U','postgres','-p',str(port),'-d','postgres','-t','-A','-c',SQL])
 need(count.isdigit() and int(count)>0,'RESTORED_TABLES_MISSING')
def wait_sql(name,port):
 for _ in range(90):
  p=subprocess.run(['docker','exec',name,'psql','-X','-U','postgres','-p',str(port),'-d','postgres','-t','-A','-c','SELECT 1'],
   stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15)
  if p.returncode==0 and p.stdout.strip()==b'1':return
  time.sleep(.5)
 raise Stop('DB_NOT_READY')
def health(name,url):
 js="const h=require('http');let q=h.get(process.argv[1],r=>{r.resume();r.on('end',()=>process.exit(r.statusCode>=200&&r.statusCode<300?0:2))});q.on('error',()=>process.exit(3));q.setTimeout(3000,()=>{q.destroy();process.exit(4)})"
 for _ in range(45):
  p=subprocess.run(['docker','exec',name,'node','-e',js,url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
  if p.returncode==0:return True
  time.sleep(.5)
 return False
def inspect_isolation(name,holder=None,database=False,scratch=None):
 row=json.loads(call(['docker','inspect','--type=container',name]))[0]
 host=row.get('HostConfig') or {}
 need(not host.get('PortBindings') and (host.get('NetworkMode')=='none' if holder is None else
  host.get('NetworkMode','').startswith('container:')),'ISOLATION_DRIFT')
 need(host.get('ReadonlyRootfs') is True and (host.get('LogConfig') or {}).get('Type')=='none','FILESYSTEM_OR_LOG_DRIFT')
 mounts=row.get('Mounts') or []
 for m in mounts:
  if m.get('Type')=='tmpfs':continue
  need(not database and scratch is not None and m.get('Type')=='bind' and
   str(m.get('Source','')).startswith(str(scratch)+'/') and
   m.get('Destination') in ('/app/data','/app/uploads','/app/logs'),'PERSISTENT_OR_UNREVIEWED_MOUNT')
 if database:
  need('/var/lib/postgresql/data' in (host.get('Tmpfs') or {}) and
   all(m.get('Type')=='tmpfs' for m in mounts),'DATABASE_NOT_RAM_BACKED')
def envs(ph,pt):
 shared=secrets.token_hex(32)
 hub={'NODE_ENV':'production','PORT':'3040','DATA_DIR':'/app/data','V79_HUB_STORE_BACKEND':'json',
  'DATABASE_URL':f'postgresql://postgres:{ph}@127.0.0.1:5432/postgres',
  'V79_HUB_ADMIN_USERNAME':'v3-isolated','V79_HUB_ADMIN_EMAIL':'vision79slu@gmail.com',
  'V79_HUB_ADMIN_PASSWORD':secrets.token_hex(24),'V79_REQUIRE_ADMIN_MFA':'1',
  'V79_HUB_SECURITY_KEY':secrets.token_hex(32),'V79_PLATFORM_SHARED_SECRET':shared,
  'V79_TIQUET_LAUNCH_SECRET':shared,'WIPAY_ENABLED':'0','RESEND_API_KEY':'',
  'V79_WORKFORCE_ACTIONS_ENABLED':'0','V79_MARKETING_PRODUCTION_ENABLED':'0',
  'V79_AGENT_INTERNAL_URL':'http://127.0.0.1:9','APP_URL':'http://127.0.0.1:3040',
  'TIQUET_PUBLIC_URL':'http://127.0.0.1:3050'}
 tiquet={'NODE_ENV':'production','PORT':'3050','DB_HOST':'127.0.0.1','DB_PORT':'5433','DB_NAME':'postgres',
  'DB_USER':'postgres','DB_PASSWORD':pt,'DATABASE_PATH':'/app/data/tiquet.db',
  'APP_BASE_URL':'http://127.0.0.1:3050','V79_HUB_INTERNAL_URL':'http://127.0.0.1:3040',
  'V79_HUB_BILLING_URL':'http://127.0.0.1:3040','V79_HUB_PUBLIC_URL':'http://127.0.0.1:3040',
  'V79_PLATFORM_SHARED_SECRET':shared,'V79_TIQUET_LAUNCH_SECRET':shared,'V79_HUB_MANAGED_BILLING':'1',
  'V79_ALLOW_LEGACY_AUTH':'0','V79_ALLOW_EMAIL_ACCOUNT_LINK':'0',
  'JWT_SECRET':secrets.token_hex(48),'SUPER_ADMIN_JWT_SECRET':secrets.token_hex(48),
  'V79_ENTITLEMENT_RECHECK_ENABLED':'1','GOOGLE_CLIENT_ID':''}
 return hub,tiquet
def app_args(name,image,holder,settings,mounts):
 args=['docker','run','--detach','--pull=never','--name',name,'--network','container:'+holder,
  '--read-only','--log-driver','none','--security-opt','no-new-privileges',
  '--tmpfs','/tmp:rw,size=67108864,mode=0700']
 for k,v in settings.items():args.extend(['--env',k+'='+v])
 for source,target in mounts:args.extend(['--mount','type=bind,src='+str(source)+',dst='+target])
 return args+[image]
def run():
 preflight();os.umask(0o077)
 scratch=Path(tempfile.mkdtemp(prefix='v79-v3-',dir='/dev/shm'))
 names=[];uid=secrets.token_hex(5)
 holder='v79-v3-holder-'+uid;hdb='v79-v3-hpg-'+uid;tdb='v79-v3-tpg-'+uid
 hub='v79-v3-hub-'+uid;tiquet='v79-v3-tiquet-'+uid;rollback='v79-v3-prior-'+uid
 planned=[rollback,tiquet,hub,tdb,hdb,holder]
 need(all(subprocess.run(['docker','container','inspect',name],stdout=subprocess.DEVNULL,
  stderr=subprocess.DEVNULL,timeout=20).returncode!=0 for name in planned),'DISPOSABLE_NAME_COLLISION')
 try:
  total=[0]
  for archive,(prefix,folder) in SELECTED.items():extract(COPY/archive,prefix,scratch/folder,total)
  (scratch/'tiquet_logs').mkdir(mode=0o700)
  print('MOUNTED_APP_DATA_RAM_RESTORE=PASS_3',flush=True)
  call(['docker','run','--detach','--pull=never','--name',holder,'--network','none',
   '--read-only','--log-driver','none','--tmpfs','/tmp:rw,size=67108864',
   '--entrypoint','/bin/sh',IMAGES['candidate'],'-c','sleep 1200'])
  names.append(holder);inspect_isolation(holder)
  ph=secrets.token_hex(24);pt=secrets.token_hex(24)
  for name,image,pw,port in ((hdb,IMAGES['hub_db'],ph,5432),(tdb,IMAGES['tiquet_db'],pt,5433)):
   args=['docker','run','--detach','--pull=never','--name',name,'--network','container:'+holder,
    '--read-only','--log-driver','none','--security-opt','no-new-privileges',
    '--tmpfs','/var/lib/postgresql/data:rw,size=1073741824,mode=0700',
    '--tmpfs','/var/run/postgresql:rw,size=16777216',
    '--tmpfs','/tmp:rw,size=67108864',
    '--env','POSTGRES_PASSWORD='+pw,'--env','POSTGRES_USER=postgres','--env','POSTGRES_DB=postgres',image]
   if port==5433:args+=['postgres','-c','port=5433']
   call(args,timeout=120);names.append(name);inspect_isolation(name,holder,database=True)
   wait_sql(name,port)
  restore_dump(hdb,'hub-postgres.dump.gpg',5432);restore_dump(tdb,'tiquet-postgres.dump.gpg',5433)
  print('PAIRED_DATABASE_RESTORE=PASS_BOTH',flush=True)
  eh,et=envs(ph,pt)
  hm=[(scratch/'hub_data','/app/data')]
  tm=[(scratch/'tiquet_data','/app/data'),(scratch/'tiquet_uploads','/app/uploads'),
      (scratch/'tiquet_logs','/app/logs')]
  call(app_args(hub,IMAGES['candidate'],holder,eh,hm),timeout=120);names.append(hub);inspect_isolation(hub,holder,scratch=scratch)
  call(app_args(tiquet,IMAGES['tiquet'],holder,et,tm),timeout=120);names.append(tiquet);inspect_isolation(tiquet,holder,scratch=scratch)
  need(health(hub,'http://127.0.0.1:3040/api/health') and
       health(tiquet,'http://127.0.0.1:3050/health'),'CANDIDATE_OR_TIQUET_HEALTH_FAILED')
  print('CANDIDATE_HUB_AND_TIQUET_HEALTH=PASS',flush=True)
  call(['docker','rm','-f',hub]);names.remove(hub)
  call(app_args(rollback,IMAGES['prior'],holder,eh,hm),timeout=120);names.append(rollback)
  inspect_isolation(rollback,holder,scratch=scratch)
  need(health(rollback,'http://127.0.0.1:3040/api/health') and
       health(tiquet,'http://127.0.0.1:3050/health'),'PRIOR_HUB_ROLLBACK_BOOT_FAILED')
  print('PRIOR_HUB_ROLLBACK_COLD_BOOT=PASS',flush=True)
 finally:
  for name in planned:
   subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
  # Clear container-owned files within the unique RAM-backed subtree before
  # removing it as the nonroot Acer user. No host disk receives plaintext.
  subprocess.run(['docker','run','--rm','--pull=never','--network','none','--read-only',
   '--log-driver','none','--entrypoint','/bin/sh',
   '--mount','type=bind,src='+str(scratch)+',dst=/scratch',IMAGES['candidate'],
   '-c','rm -rf /scratch/hub_data /scratch/tiquet_data /scratch/tiquet_uploads /scratch/tiquet_logs'],
   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
  shutil.rmtree(scratch)
  need(all(subprocess.run(['docker','container','inspect',name],stdout=subprocess.DEVNULL,
   stderr=subprocess.DEVNULL,timeout=20).returncode!=0 for name in planned),'DISPOSABLE_CLEANUP_FAILED')
 print(json.dumps({'schema':'vision79-v3-disconnected-paired-boot','app_data_ram_restore':'PASS_3',
  'database_restore':'PASS_BOTH','candidate_hub_tiquet_health':'PASS','prior_hub_rollback_cold_boot':'PASS',
  'disposable_cleanup':'PASS','real_owner_mfa_sso_verified':False,'exact_runtime_parity_verified':False,
  'production_changes':'NONE','release_gate':'HOLD'},sort_keys=True))
class Tests(unittest.TestCase):
 def test_wrong_host_no_docker(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.call') as command:
   with self.assertRaises(Stop):preflight()
   command.assert_not_called()
 def test_image_pins(self):self.assertEqual(len(set(IMAGES.values())),5)
 def test_app_no_ports(self):
  args=app_args('n',IMAGES['candidate'],'h',{},[])
  self.assertNotIn('--publish',args);self.assertIn('container:h',args)
 def test_database_volume_rejected(self):
  row={'HostConfig':{'NetworkMode':'container:holder','PortBindings':None,
     'ReadonlyRootfs':True,'LogConfig':{'Type':'none'},'Tmpfs':{'/var/lib/postgresql/data':'rw'}},
     'Mounts':[{'Type':'volume','Destination':'/var/lib/postgresql/data'}]}
  with patch(__name__+'.call',return_value=json.dumps([row]).encode()):
   with self.assertRaises(Stop):inspect_isolation('db','holder',database=True)
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ('--self-test','--run'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 run();return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print(json.dumps({'status':'STOP','reason':str(e),'release_gate':'HOLD'}));sys.exit(3)
 except Exception as e:print(json.dumps({'status':'STOP','reason':'REDACTED_ERROR','error_type':type(e).__name__,'release_gate':'HOLD'}));sys.exit(3)
