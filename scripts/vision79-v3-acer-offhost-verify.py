#!/usr/bin/env python3
"""Copy and verify the v3 encrypted checkpoint on the Acer without plaintext files.

No server writes, Docker actions, deployment, or restore. This is not a restore
rehearsal. GPG decrypts into local process pipes only.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REMOTE='/home/firelion/.v79-v3-encrypted-checkpoints/v3-20261026T194538Z-gnm710en'
FINGERPRINT='484CF39CE37A02884497AD9C41A17102D2842ECE'
PRIOR='sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4'
NAMES=['hub-postgres.dump.gpg','tiquet-postgres.dump.gpg','prior-hub-image.tar.gpg',
 'live-runtime.json.gpg','hub-compose.tar.gpg',
 *[f'v79-hub-mount-{i:02d}.tar.gpg' for i in range(1,8)],
 *[f'v79-tiquet-manager-mount-{i:02d}.tar.gpg' for i in range(1,3)]]
class Stop(Exception): pass
def need(value,code):
 if not value: raise Stop(code)
def check_receipt(directory):
 names=set(NAMES)
 need(set(p.name for p in directory.iterdir())==names|{'STATUS','receipt.json'},'CHECKPOINT_FILE_SET_DRIFT')
 for p in directory.iterdir():need(p.is_file() and not p.is_symlink(),'NONREGULAR_CHECKPOINT_FILE')
 need((directory/'STATUS').read_text()=='CAPTURED_NOT_OFFHOST_VERIFIED\n','CAPTURE_STATUS_DRIFT')
 try:receipt=json.loads((directory/'receipt.json').read_text())
 except (ValueError,UnicodeError):raise Stop('RECEIPT_INVALID') from None
 need(receipt.get('schema')=='vision79-v3-encrypted-capture' and receipt.get('hub_image')==PRIOR
  and receipt.get('recipient_fingerprint')==FINGERPRINT and receipt.get('release_gate')=='HOLD'
  and receipt.get('offhost_copy_verified') is False and receipt.get('decryption_verified') is False
  and receipt.get('isolated_restore_verified') is False,'RECEIPT_BASELINE_DRIFT')
 hashes=receipt.get('encrypted_sha256')
 need(isinstance(hashes,dict) and set(hashes)==names and all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in hashes.values()),'RECEIPT_HASH_SET_DRIFT')
 for name in NAMES:
  h=hashlib.sha256()
  with (directory/name).open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  need(h.hexdigest()==hashes[name],'CIPHERTEXT_HASH_MISMATCH')
 return receipt
def gpg_args(path):return ['gpg','--batch','--no-tty','--quiet','--decrypt',str(path)]
def verify_dump(path):
 with subprocess.Popen(gpg_args(path),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as p:
  if p.stdout.read(5)!=b'PGDMP':
   p.kill();p.wait();raise Stop('DATABASE_DUMP_HEADER_INVALID')
  while p.stdout.read(1024*1024):pass
  need(p.wait(timeout=1200)==0,'DECRYPT_FAILED')
def verify_json(path):
 with subprocess.Popen(gpg_args(path),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as p:
  chunks=[];length=0
  while True:
   block=p.stdout.read(1024*1024)
   if not block:break
   length+=len(block)
   if length>16*1024*1024:
    p.kill();p.wait();raise Stop('RUNTIME_JSON_TOO_LARGE')
   chunks.append(block)
  need(p.wait(timeout=1200)==0,'DECRYPT_FAILED')
 try:rows=json.loads(b''.join(chunks))
 except (ValueError,UnicodeDecodeError):raise Stop('RUNTIME_JSON_INVALID') from None
 need(isinstance(rows,list) and len(rows)==5,'RUNTIME_JSON_SHAPE_INVALID')
 names={row.get('Name','').lstrip('/') for row in rows}
 need(names=={'v79-hub','v79-hub-postgres','v79-tiquet-manager','tiquet-postgres','v79-business-agent'},'RUNTIME_CONTAINER_SET_DRIFT')
def verify_tar(path):
 with subprocess.Popen(gpg_args(path),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as decrypt:
  with subprocess.Popen(['tar','-tf','-'],stdin=decrypt.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as listing:
   decrypt.stdout.close()
   tar_ok=listing.wait(timeout=1200)==0
   gpg_ok=decrypt.wait(timeout=1200)==0
   need(tar_ok and gpg_ok,'TAR_OR_DECRYPT_INVALID')
def private_key_ready():
 p=subprocess.run(['gpg','--batch','--with-colons','--fingerprint','--list-secret-keys'],
                  stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
 need(p.returncode==0 and FINGERPRINT in [line.split(':')[9] for line in p.stdout.decode().splitlines() if line.startswith('fpr:')],'ACER_PRIVATE_KEY_UNAVAILABLE')
def verify():
 need(socket.gethostname().split('.')[0]=='firelion-Aspire-A315-51','ACER_HOST_REQUIRED')
 need(not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'),'DOCKER_OVERRIDE_REFUSED')
 private_key_ready()
 os.umask(0o077)
 local=Path(tempfile.mkdtemp(prefix='v79-v3-offhost-',dir=Path.home()))
 print('ACER_OFFHOST_DIRECTORY='+str(local),flush=True)
 command=['scp','-r','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
          'firelion@192.168.100.163:'+REMOTE,str(local)]
 p=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1800)
 need(p.returncode==0,'OFFHOST_COPY_FAILED')
 directory=local/Path(REMOTE).name
 need(directory.is_dir() and not directory.is_symlink(),'OFFHOST_DIRECTORY_MISSING')
 check_receipt(directory)
 for name in NAMES:
  path=directory/name
  if name.endswith('.dump.gpg'):verify_dump(path)
  elif name=='live-runtime.json.gpg':verify_json(path)
  else:verify_tar(path)
  print('DECRYPT_AND_STRUCTURE=PASS_'+name,flush=True)
 # Recheck ciphertext after the decryption pass; never write the decryption key or plaintext.
 check_receipt(directory)
 proof={'schema':'vision79-v3-acer-offhost-verification',
  'verified_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
  'server_receipt_sha256':hashlib.sha256((directory/'receipt.json').read_bytes()).hexdigest(),
  'offhost_ciphertext_hashes':'PASS_14',
  'decryption_and_structure':'PASS_14','acer_copy':str(directory),'isolated_restore_verified':False,
  'production_changes':'NONE','release_gate':'HOLD'}
 with (local/'offhost-verification.json').open('x') as f:
  os.chmod(local/'offhost-verification.json',0o600)
  json.dump(proof,f,sort_keys=True,indent=2);f.write('\n')
 print(json.dumps(proof,sort_keys=True))
class Tests(unittest.TestCase):
 def test_name_set(self):self.assertEqual(len(NAMES),14);self.assertEqual(len(set(NAMES)),14)
 def test_host_gate_no_copy(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.private_key_ready') as key:
   with self.assertRaises(Stop):verify()
   key.assert_not_called()
 def test_bad_receipt_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'STATUS').write_text('IN_PROGRESS\n')
   with self.assertRaises(Stop):check_receipt(p)
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ('--self-test','--verify'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if result.wasSuccessful() else 1
 verify();return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print(json.dumps({'status':'STOP','reason':str(e),'release_gate':'HOLD'}));sys.exit(3)
 except Exception:print(json.dumps({'status':'STOP','reason':'REDACTED_ERROR','release_gate':'HOLD'}));sys.exit(3)
