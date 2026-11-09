#!/usr/bin/env python3
"""Encrypted, read-only production capture. Server-only; no restart or deploy.

Capture is incomplete until an Acer offhost copy, full decryption and isolated
restore are independently verified. Secret-bearing streams never go to stdout.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

EXPECTED = {
 'v79-hub':'sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4',
 'v79-hub-postgres':'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
 'v79-tiquet-manager':'sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0',
 'tiquet-postgres':'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685',
 'v79-business-agent':'sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b',
}
COMPOSE_SHA='2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083'
KEY=Path('/home/firelion/.v79-g12-recovery-public.asc')
FINGERPRINT='484CF39CE37A02884497AD9C41A17102D2842ECE'
BASE=Path('/home/firelion/.v79-v3-encrypted-checkpoints')

class Stop(Exception): pass
def need(value,code):
 if not value: raise Stop(code)
def run(args,timeout=30):
 try: p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired): raise Stop('COMMAND_UNAVAILABLE_OR_TIMEOUT') from None
 need(p.returncode==0 and len(p.stdout)<=16*1024*1024,'READ_ONLY_COMMAND_FAILED')
 return p.stdout
def inspect(name):
 try: rows=json.loads(run(['docker','inspect','--type','container',name]))
 except (ValueError,UnicodeDecodeError): raise Stop('INSPECT_INVALID') from None
 need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),'INSPECT_SHAPE')
 return rows[0]
def baseline():
 need(socket.gethostname().split('.')[0]=='v79sl','WRONG_HOST')
 need(not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'),'DOCKER_OVERRIDE_REFUSED')
 records={name:inspect(name) for name in EXPECTED}
 for name,row in records.items():
  need(row.get('Image')==EXPECTED[name] and row.get('State',{}).get('Status')=='running'
       and row.get('State',{}).get('Health',{}).get('Status')=='healthy','LIVE_BASELINE_DRIFT')
 hub=records['v79-hub']; labels=(hub.get('Config') or {}).get('Labels') or {}
 files=labels.get('com.docker.compose.project.config_files','').split(',')
 need(len(files)==1 and Path(files[0]).is_absolute() and Path(files[0]).name=='hub-candidate.json','HUB_COMPOSE_CHAIN_DRIFT')
 p=Path(files[0]);need(p.is_file() and not p.is_symlink() and p.stat().st_size<2_000_000,'HUB_COMPOSE_INVALID')
 need(hashlib.sha256(p.read_bytes()).hexdigest()==COMPOSE_SHA,'HUB_COMPOSE_DRIFT')
 for name in ('v79-hub','v79-tiquet-manager'):
  for m in records[name].get('Mounts') or []:
   need(m.get('Destination','').startswith('/') and m.get('Type') in ('bind','volume'),'MOUNT_SHAPE_DRIFT')
 return records,p
def sources(records,compose):
 # All Hub and Tiquet mounted files/data, two DB logical dumps, current Hub
 # image, live runtime metadata, and the exact running Hub Compose input.
 streams={
  'hub-postgres.dump':['docker','exec','v79-hub-postgres','sh','-ec','exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" --format=custom --no-owner --no-acl'],
  'tiquet-postgres.dump':['docker','exec','tiquet-postgres','sh','-ec','exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" --format=custom --no-owner --no-acl'],
  'prior-hub-image.tar':['docker','image','save',EXPECTED['v79-hub']],
  'live-runtime.json':['docker','inspect',*EXPECTED],
  'hub-compose.tar':['tar','-C','/','-cf','-',str(compose).lstrip('/')],
 }
 for name in ('v79-hub','v79-tiquet-manager'):
  mounts=records[name].get('Mounts') or []
  for index,m in enumerate(sorted(mounts,key=lambda x:x['Destination']),1):
   streams[f'{name}-mount-{index:02d}.tar']=['docker','cp',name+':'+m['Destination'],'-']
 return streams
def encrypted_stream(args,dest,gnupg):
 partial=dest.with_name(dest.name+'.partial')
 try:
  with partial.open('xb') as output:
   producer=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
   try:
    consumer=subprocess.Popen(['gpg','--homedir',str(gnupg),'--batch','--no-tty','--quiet',
      '--trust-model','always','--recipient',FINGERPRINT,'--compress-algo','none','--encrypt','--output','-'],
      stdin=producer.stdout,stdout=output,stderr=subprocess.DEVNULL)
    producer.stdout.close()
    consumer_ok=consumer.wait(timeout=1200)==0
    producer_ok=producer.wait(timeout=1200)==0
    ok=consumer_ok and producer_ok
   except (OSError,subprocess.TimeoutExpired):
    producer.kill();producer.wait();raise Stop('ENCRYPTED_STREAM_TIMEOUT') from None
   need(ok and partial.stat().st_size>0,'ENCRYPTED_STREAM_FAILED')
  partial.rename(dest)
 except OSError: raise Stop('ENCRYPTED_STREAM_IO_FAILED') from None
 h=hashlib.sha256()
 with dest.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def capture():
 os.umask(0o077)
 records,compose=baseline()
 need(KEY.is_file() and not KEY.is_symlink() and KEY.stat().st_size<100_000,'PUBLIC_KEY_MISSING')
 need(shutil.disk_usage('/home/firelion').free>=20*1024**3,'INSUFFICIENT_DISK')
 BASE.mkdir(mode=0o700,exist_ok=True)
 need(not BASE.is_symlink() and BASE.stat().st_mode & 0o077==0,'CHECKPOINT_DIRECTORY_PERMISSIONS')
 keyring=Path(tempfile.mkdtemp(prefix='.v79-v3-keyring-',dir=BASE))
 try:
  run(['gpg','--homedir',str(keyring),'--batch','--quiet','--import',str(KEY)])
  listed=run(['gpg','--homedir',str(keyring),'--batch','--with-colons','--fingerprint','--list-keys']).decode()
  need(FINGERPRINT in [line.split(':')[9] for line in listed.splitlines() if line.startswith('fpr:')],'RECIPIENT_FINGERPRINT_DRIFT')
  secret_listing=subprocess.run(['gpg','--homedir',str(keyring),'--batch','--with-colons','--list-secret-keys'],
    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
  need(secret_listing.returncode in (0,2) and not secret_listing.stdout.strip(),'PRIVATE_KEY_ON_SERVER')
  stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
  directory=Path(tempfile.mkdtemp(prefix='v3-'+stamp+'-',dir=BASE))
  (directory/'STATUS').write_text('IN_PROGRESS\n')
  hashes={}
  for label,args in sources(records,compose).items():
   hashes[label+'.gpg']=encrypted_stream(args,directory/(label+'.gpg'),keyring)
   print('ENCRYPTED_ITEM='+label,flush=True)
  again,_=baseline()
  need(all(all(again[name].get(field)==records[name].get(field)
       for field in ('Id','Image','Config','HostConfig','Mounts'))
       for name in EXPECTED),'LIVE_CHANGED_DURING_CAPTURE')
  receipt={'schema':'vision79-v3-encrypted-capture','captured_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
   'hub_image':EXPECTED['v79-hub'],'hub_container_id':records['v79-hub']['Id'],
   'candidate_image_on_server':False,'recipient_fingerprint':FINGERPRINT,'encrypted_sha256':hashes,
   'cross_database_atomic':False,'offhost_copy_verified':False,'decryption_verified':False,
   'isolated_restore_verified':False,'production_runtime_changes':'NONE','release_gate':'HOLD'}
  with (directory/'receipt.json').open('x') as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n')
  (directory/'STATUS').write_text('CAPTURED_NOT_OFFHOST_VERIFIED\n')
  print(json.dumps({'checkpoint_directory':str(directory),'encrypted_items':len(hashes),
    'status':'CAPTURED_NOT_OFFHOST_VERIFIED','production_runtime_changes':'NONE','release_gate':'HOLD'},sort_keys=True))
 finally:
  shutil.rmtree(keyring)
class Tests(unittest.TestCase):
 def test_wrong_host_before_docker(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.run') as command:
   with self.assertRaises(Stop):baseline()
   command.assert_not_called()
 def test_stream_inventory(self):
  rec={n:{'Mounts':[]} for n in EXPECTED}
  rec['v79-hub']['Mounts']=[{'Destination':'/app/data'}]
  result=sources(rec,Path('/tmp/hub-candidate.json'))
  self.assertEqual(len(result),6)
  self.assertEqual(result['prior-hub-image.tar'][-1],EXPECTED['v79-hub'])
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ('--self-test','--capture'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if result.wasSuccessful() else 1
 capture();return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print(json.dumps({'status':'STOP','reason':str(e),'release_gate':'HOLD'}));sys.exit(3)
 except Exception:print(json.dumps({'status':'STOP','reason':'REDACTED_ERROR','release_gate':'HOLD'}));sys.exit(3)
