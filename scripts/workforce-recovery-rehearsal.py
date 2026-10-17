#!/usr/bin/env python3
"""Acer-only encrypted-backup rehearsal; disposable offline containers only."""
import hashlib,json,os,re,shlex,socket,subprocess,sys,time,uuid
from pathlib import Path

HOST='firelion@v79sl'
HUB='sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06'
EXPECTED={'v79-hub':HUB,'v79-business-agent':'sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f','v79-tiquet-manager':'sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42'}

def remote(args):
 p=subprocess.run(['ssh',HOST,shlex.join(args)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=90)
 if p.returncode:raise RuntimeError('Remote rehearsal command failed; private details withheld')
 return p.stdout.decode()

def stream(file,args):
 decrypt=subprocess.Popen(['gpg','--quiet','--decrypt',str(file)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 try:
  runner=subprocess.Popen(['ssh',HOST,shlex.join(args)],stdin=decrypt.stdout,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  decrypt.stdout.close()
  try:out,_=runner.communicate(timeout=180)
  except subprocess.TimeoutExpired:
   runner.kill();runner.communicate();raise RuntimeError('Restore stream timed out')
  if decrypt.wait(timeout=30) or runner.returncode:raise RuntimeError('Encrypted restore stream failed')
  return out.decode()
 finally:
  if decrypt.poll() is None:decrypt.kill();decrypt.wait()

def baseline():
 rows=json.loads(remote(['docker','inspect',*EXPECTED]))
 if len(rows)!=3 or any(row['Image']!=EXPECTED[row['Name'].lstrip('/')] or row['State'].get('Health',{}).get('Status')!='healthy' for row in rows):raise RuntimeError('Live baseline changed')

EXTRACT=r'''
import os,sys,tarfile
from pathlib import Path
root=Path('/restore'); count=0
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
 for member in archive:
  name=Path(member.name)
  if name.is_absolute() or '..' in name.parts or not (member.isdir() or member.isfile()):raise SystemExit('UNSAFE_ARCHIVE_MEMBER')
  target=root/name
  if member.isdir():target.mkdir(parents=True,exist_ok=True,mode=0o700)
  else:
   target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
   with archive.extractfile(member) as source,open(target,'wb') as output:
    while chunk:=source.read(1024*1024):output.write(chunk)
   os.chmod(target,0o600);count+=1
if not count:raise SystemExit('EMPTY_ARCHIVE')
print('RESTORED_FILE_COUNT='+str(count))
'''
IMAGE_CHECK='#!/usr/bin/env python3\n"""Stream-verify Docker/OCI archive digests and reachable graph; never load images."""\nimport hashlib,json,re,subprocess,sys,tarfile\n\nEXPECTED=\'sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06\'\n\ndef verify(source, expected=EXPECTED):\n if not re.fullmatch(\'sha256:[0-9a-f]{64}\',expected):raise ValueError(\'Invalid expected image identity\')\n blobs={};nodes={};index=None;docker_manifest=None\n with tarfile.open(fileobj=source,mode=\'r|\') as archive:\n  for member in archive:\n   name=member.name.removeprefix(\'./\')\n   if not member.isfile():continue\n   digest_name=None\n   if re.fullmatch(r\'blobs/sha256/[0-9a-f]{64}\',name):digest_name=\'sha256:\'+name.rsplit(\'/\',1)[1]\n   if digest_name:\n    if digest_name in blobs:raise ValueError(\'Duplicate blob\')\n    h=hashlib.sha256();count=0;small=bytearray() if member.size<=2_000_000 else None\n    data=archive.extractfile(member)\n    while chunk:=data.read(1024*1024):\n     h.update(chunk);count+=len(chunk)\n     if small is not None:small.extend(chunk)\n    if count!=member.size or \'sha256:\'+h.hexdigest()!=digest_name:raise ValueError(\'Blob digest/size mismatch\')\n    blobs[digest_name]=count\n    if small is not None:\n     try:obj=json.loads(small)\n     except (ValueError,UnicodeDecodeError):continue\n     # Keep only graph structure, never image environment, labels or history.\n     if isinstance(obj,dict):\n      if isinstance(obj.get(\'manifests\'),list):nodes[digest_name]=(\'index\',obj[\'manifests\'])\n      elif isinstance(obj.get(\'config\'),dict) and isinstance(obj.get(\'layers\'),list):nodes[digest_name]=(\'manifest\',[obj[\'config\'],*obj[\'layers\']])\n      elif isinstance(obj.get(\'rootfs\'),dict):nodes[digest_name]=(\'config\',[])\n   elif name in [\'index.json\',\'manifest.json\']:\n    if member.size>2_000_000:raise ValueError(\'Oversized archive index\')\n    obj=json.load(archive.extractfile(member))\n    if name==\'index.json\':\n     if index is not None:raise ValueError(\'Duplicate index\')\n     index=obj\n    else:\n     if docker_manifest is not None:raise ValueError(\'Duplicate Docker manifest\')\n     docker_manifest=obj\n if not blobs or not isinstance(index,dict) or not isinstance(index.get(\'manifests\'),list):raise ValueError(\'OCI archive index unavailable\')\n roots=[d for d in index[\'manifests\'] if isinstance(d,dict) and d.get(\'digest\')==expected]\n if len(roots)!=1:raise ValueError(\'Expected live image absent from archive index\')\n seen=set();configs=set();manifests=0\n def walk(descriptor,ancestors):\n  nonlocal manifests\n  if not isinstance(descriptor,dict):raise ValueError(\'Invalid graph descriptor\')\n  digest=descriptor.get(\'digest\');size=descriptor.get(\'size\')\n  if digest not in blobs or not isinstance(size,int) or isinstance(size,bool) or size!=blobs[digest]:raise ValueError(\'Missing or incorrectly sized graph blob\')\n  if digest in ancestors:raise ValueError(\'Cyclic graph\')\n  if digest in seen:return\n  seen.add(digest)\n  kind,children=nodes.get(digest,(\'layer\',[]))\n  if kind==\'config\':configs.add(digest)\n  elif kind==\'manifest\':manifests+=1\n  for child in children:walk(child,ancestors|{digest})\n walk(roots[0],set())\n if not manifests or not configs:raise ValueError(\'No reachable image manifest/config\')\n if not isinstance(docker_manifest,list) or not any(isinstance(row,dict) and \'sha256:\'+str(row.get(\'Config\',\'\')).removeprefix(\'./\').removeprefix(\'blobs/sha256/\') in configs for row in docker_manifest):raise ValueError(\'Docker manifest does not reference a reachable config\')\n return {\'hashedBlobs\':len(blobs),\'reachableBlobs\':len(seen),\'reachableImageManifests\':manifests,\'reachableConfigs\':len(configs),\'rootImage\':expected}\n\nresult=verify(sys.stdin.buffer,sys.argv[1])\nprint(\'ORIGINAL_IMAGE_OCI_GRAPH=PASS\')\n'

def main():
 if socket.gethostname()=='v79sl':raise RuntimeError('Run on Acer, not the server')
 if len(sys.argv)!=2:raise RuntimeError('Provide the existing Acer encrypted backup directory')
 root=Path(sys.argv[1]).expanduser().resolve()
 names=['hub-pg.dump.gpg','hub-data.tar.gpg','hub-config.tar.gpg','runtime-config.json.gpg','hub-original-image.tar.gpg']
 for name in names:
  f=root/name
  if not f.is_file() or f.is_symlink() or f.stat().st_mode&0o077:raise RuntimeError('Missing or unsafe encrypted backup')
 # Match the existing checksum manifest before consuming archives.
 sums={}
 for line in (root/'SHA256SUMS').read_text().splitlines():
  digest,name=line.split(None,1);sums[Path(name.strip().lstrip('*')).name]=digest
 for name in names:
  h=hashlib.sha256()
  with (root/name).open('rb') as f:
   while chunk:=f.read(1024*1024):h.update(chunk)
  if sums.get(name)!=h.hexdigest():raise RuntimeError('Encrypted checksum mismatch')
 config=subprocess.run(['gpg','--quiet','--decrypt',str(root/'runtime-config.json.gpg')],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
 if config.returncode:raise RuntimeError('Runtime checkpoint decryption failed')
 saved=json.loads(config.stdout)
 if len(saved)!=3 or any(item['Image']!=EXPECTED[item['Name'].lstrip('/')] for item in saved):raise RuntimeError('Checkpoint runtime identity mismatch')
 baseline();print('PRE_REHEARSAL_LIVE_BASELINE=PASS',flush=True)
 pg=remote(['docker','inspect','--format={{.Image}}','v79-hub-postgres']).strip()
 if not re.fullmatch(r'sha256:[0-9a-f]{64}',pg):raise RuntimeError('Postgres image unavailable')
 run_id='v79-workforce-restore-'+uuid.uuid4().hex[:16]
 resources=[]
 def create(name,image,extra):
  cid=remote(['docker','create','--name',name,'--label','v79.workforce.restore='+run_id,'--network','none','--memory','512m','--cpus','1','--pids-limit','128','--security-opt','no-new-privileges',*extra,image]).strip()
  if not re.fullmatch('[0-9a-f]{64}',cid):raise RuntimeError('Unexpected disposable container ID')
  resources.append(cid)
  row=json.loads(remote(['docker','inspect',cid]))[0]
  if row['HostConfig']['NetworkMode']!='none' or row['HostConfig'].get('Binds') or row['HostConfig'].get('PortBindings') or any(m['Type']!='tmpfs' for m in row.get('Mounts',[])):raise RuntimeError('Disposable isolation unavailable')
  return cid
 try:
  db=create(run_id+'-db',pg,['--tmpfs','/var/lib/postgresql/data:rw,nosuid,nodev,size=768m','-e','PGDATA=/var/lib/postgresql/data/rehearsal','-e','POSTGRES_USER=rehearsal','-e','POSTGRES_DB=rehearsal','-e','POSTGRES_HOST_AUTH_METHOD=trust'])
  remote(['docker','start',db])
  for attempt in range(45):
   try:remote(['docker','exec',db,'pg_isready','-U','rehearsal','-d','rehearsal']);break
   except RuntimeError:
    if attempt==44:raise
    time.sleep(1)
  stream(root/'hub-pg.dump.gpg',['docker','exec','-i',db,'pg_restore','--exit-on-error','--no-owner','--no-privileges','-U','rehearsal','-d','rehearsal'])
  count=remote(['docker','exec',db,'psql','-X','-A','-t','-U','rehearsal','-d','rehearsal','-c',"SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema');"]).strip()
  if not count.isdigit() or int(count)<1:raise RuntimeError('Restored database has no user tables')
  print('ISOLATED_DATABASE_RESTORE=PASS',flush=True)
  print('RESTORED_USER_TABLES='+count,flush=True)
  # Each archive extracts only inside a fresh tmpfs. No host mount or real DB.
  for index,name in enumerate(['hub-data.tar.gpg','hub-config.tar.gpg']):
   result=stream(root/name,['docker','run','--rm','-i','--name',run_id+'-reader-'+str(index),'--label','v79.workforce.restore='+run_id,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','512m','--cpus','1','--pids-limit','64','--tmpfs','/restore:rw,nosuid,nodev,size=384m','--entrypoint','python3',HUB,'-c',EXTRACT])
   print(name+': '+result.strip(),flush=True)
  result=stream(root/'hub-original-image.tar.gpg',['docker','run','--rm','-i','--name',run_id+'-image-reader','--label','v79.workforce.restore='+run_id,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','256m','--cpus','1','--pids-limit','64','--entrypoint','python3',HUB,'-c',IMAGE_CHECK,HUB])
  print(result.strip(),flush=True)
 finally:
  cleanup=True
  # Only this run's explicitly identified containers may be removed.
  ids=remote(['docker','ps','-aq','--filter','label=v79.workforce.restore='+run_id]).split()
  for cid in ids:
   row=json.loads(remote(['docker','inspect',cid]))[0]
   if row['Config']['Labels'].get('v79.workforce.restore')!=run_id:cleanup=False;continue
   remote(['docker','rm','-f',cid])
  if remote(['docker','ps','-aq','--filter','label=v79.workforce.restore='+run_id]).strip():cleanup=False
  baseline()
  print('DISPOSABLE_RESOURCE_CLEANUP='+('PASS' if cleanup else 'FAILED'),flush=True)
  print('LIVE_IMAGE_AND_HEALTH_RECHECK=PASS',flush=True)
  if not cleanup:raise RuntimeError('Disposable cleanup incomplete')
 receipt={'schema':1,'state':'PASS_ISOLATED_RESTORE','originalImage':HUB,'candidateImage':'sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698','verifiedAt':time.time(),'databaseRestore':True,'fileArchiveExtraction':True,'imageConfigIdentity':True,'imageGraphVerified':True,'fullDockerImageReload':False,'productionDeployed':False}
 target=root/('restore-receipt-'+run_id+'.json')
 with target.open('x') as f:os.chmod(target,0o600);json.dump(receipt,f)
 print('RECOVERY_REHEARSAL=PASS_DATABASE_FILES_IMAGE_CONFIG_IDENTITY')
 print('FULL_DOCKER_IMAGE_RELOAD=NOT_PERFORMED')
 print('PRODUCTION_DEPLOYED=NO')

if __name__=='__main__':
 try:main()
 except Exception:
  print('RECOVERY_REHEARSAL=FAILED_DETAILS_WITHHELD');raise SystemExit(1)
