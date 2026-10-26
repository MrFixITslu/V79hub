#!/usr/bin/env python3
"""Restore both v3 database dumps in disposable, disconnected Acer Podman.

Uses only exact local DB image IDs and encrypted verified inputs. Never
contacts production, publishes ports, writes decrypted files or runs migrations.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT=Path('/home/firelion/v79-v3-offhost-we7b0lir')
COPY=ROOT/'v3-20261026T194538Z-gnm710en'
RECEIPT_HASH='35a9b4d41b5c42a8c6653e1c1985ebdae49ce77432d57c94ff68c82172173df5'
IMAGES={'hub':('sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24','hub-postgres.dump.gpg'),
        'tiquet':('sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685','tiquet-postgres.dump.gpg')}
PODMAN=['podman','--remote=false']
SQL="SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON c.relnamespace=n.oid WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%';"
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def cmd(args,timeout=45):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop('LOCAL_COMMAND_UNAVAILABLE') from None
 need(p.returncode==0 and len(p.stdout)<8*1024*1024,'LOCAL_COMMAND_FAILED')
 return p.stdout.strip()
def hashfile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def preflight():
 need(socket.gethostname().split('.')[0]=='firelion-Aspire-A315-51','ACER_HOST_REQUIRED')
 need(os.geteuid()!=0 and not os.getenv('CONTAINER_HOST') and not os.getenv('DOCKER_HOST'),'ROOTLESS_LOCAL_ONLY')
 need(ROOT.is_dir() and COPY.is_dir() and not ROOT.is_symlink() and not COPY.is_symlink(),'OFFHOST_COPY_MISSING')
 need(ROOT.stat().st_mode & 0o077==0 and COPY.stat().st_mode & 0o077==0,'COPY_PERMISSIONS')
 proof=ROOT/'offhost-verification.json';receipt=COPY/'receipt.json'
 need(proof.is_file() and receipt.is_file() and not proof.is_symlink() and not receipt.is_symlink(),'PROOF_MISSING')
 need(hashfile(receipt)==RECEIPT_HASH,'SERVER_RECEIPT_HASH_DRIFT')
 try:a=json.loads(proof.read_text());b=json.loads(receipt.read_text())
 except (ValueError,UnicodeError):raise Stop('PROOF_JSON_INVALID') from None
 need(a.get('server_receipt_sha256')==RECEIPT_HASH and a.get('offhost_ciphertext_hashes')=='PASS_14'
  and a.get('decryption_and_structure')=='PASS_14' and a.get('isolated_restore_verified') is False,'OFFHOST_PROOF_DRIFT')
 for _,filename in IMAGES.values():
  p=COPY/filename
  need(p.is_file() and not p.is_symlink() and hashfile(p)==b['encrypted_sha256'].get(filename),'DUMP_CIPHERTEXT_DRIFT')
 need(shutil.disk_usage(Path.home()).free>=8*1024**3,'ACER_DISK_LOW')
 need(cmd([*PODMAN,'info','--format','{{.Host.Security.Rootless}}'])==b'true','ROOTLESS_PODMAN_REQUIRED')
 for image,_ in IMAGES.values():
  p=subprocess.run([*PODMAN,'image','exists',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
  need(p.returncode==0,'EXACT_DB_IMAGE_NOT_CACHED')
 return True
def run_args(name,image):
 return [*PODMAN,'run','--rm','--detach','--pull=never','--name',name,'--network=none',
  '--security-opt=no-new-privileges','--pids-limit=160',
  '--tmpfs=/var/lib/postgresql/data:rw,size=1073741824,mode=0700',
  '--tmpfs=/var/run/postgresql:rw,size=16777216','--tmpfs=/tmp:rw,size=67108864',
  '--env','POSTGRES_PASSWORD='+secrets.token_hex(24),'--env','POSTGRES_USER=postgres',
  '--env','POSTGRES_DB=postgres',image]
def wait_sql(name):
 for _ in range(90):
  p=subprocess.run([*PODMAN,'exec',name,'psql','-X','-U','postgres','-d','postgres','-t','-A','-c','SELECT 1'],
     stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15)
  if p.returncode==0 and p.stdout.strip()==b'1':return
  time.sleep(.5)
 raise Stop('ISOLATED_DATABASE_NOT_READY')
def isolation(name):
 rows=json.loads(cmd([*PODMAN,'inspect','--type=container',name]))
 need(len(rows)==1,'ISOLATED_INSPECT_SHAPE')
 host=rows[0]['HostConfig'];mounts=rows[0].get('Mounts') or []
 need(host.get('NetworkMode')=='none' and not host.get('PortBindings')
  and all(m.get('Type')=='tmpfs' for m in mounts)
  and '/var/lib/postgresql/data' in (host.get('Tmpfs') or {}),'ISOLATION_DRIFT')
def restore(name,filename):
 dec=subprocess.Popen(['gpg','--batch','--quiet','--decrypt',str(COPY/filename)],
                      stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 receiver=None
 try:
  receiver=subprocess.Popen([*PODMAN,'exec','-i',name,'pg_restore','-U','postgres','--no-owner',
    '--no-acl','--single-transaction','--exit-on-error','--dbname=postgres'],
    stdin=dec.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  dec.stdout.close()
  receiver_ok=receiver.wait(timeout=900)==0;decrypt_ok=dec.wait(timeout=60)==0
  need(receiver_ok and decrypt_ok,'DECRYPT_OR_RESTORE_FAILED')
 finally:
  if receiver is not None and receiver.poll() is None:receiver.kill()
  if dec.poll() is None:dec.kill()
  if receiver is not None:receiver.wait()
  dec.wait()
def restore_one(label,image,filename):
 name='v79-v3-'+label+'-'+secrets.token_hex(4)
 exists=subprocess.run([*PODMAN,'container','exists',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
 need(exists.returncode!=0,'DISPOSABLE_NAME_COLLISION')
 try:
  cmd(run_args(name,image),timeout=90)
  isolation(name);wait_sql(name);restore(name,filename)
  count=cmd([*PODMAN,'exec',name,'psql','-X','-U','postgres','-d','postgres','-t','-A','-c',SQL])
  need(count.isdecimal() and int(count)>0,'NO_RESTORED_USER_TABLES')
  print(label.upper()+'_ISOLATED_DB_RESTORE=PASS',flush=True)
  print(label.upper()+'_USER_TABLE_COUNT='+count.decode(),flush=True)
 finally:
  subprocess.run([*PODMAN,'rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45)
  p=subprocess.run([*PODMAN,'container','exists',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
  need(p.returncode!=0,'DISPOSABLE_CONTAINER_NOT_REMOVED')
class Tests(unittest.TestCase):
 def test_run_args_disconnected(self):
  a=run_args('test',IMAGES['hub'][0]);self.assertIn('--network=none',a);self.assertFalse(any('--publish' in v for v in a))
 def test_host_before_commands(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.cmd') as command:
   with self.assertRaises(Stop):preflight()
   command.assert_not_called()
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ('--self-test','--restore'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if result.wasSuccessful() else 1
 preflight()
 for label,(image,filename) in IMAGES.items():restore_one(label,image,filename)
 proof={'schema':'vision79-v3-disconnected-db-restore','verified_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
  'server_receipt_sha256':RECEIPT_HASH,'database_restore':'PASS_BOTH',
  'disposable_containers':'REMOVED','app_boot_verified':False,'full_recovery_verified':False,
  'production_changes':'NONE','release_gate':'HOLD'}
 with (ROOT/'isolated-db-restore.json').open('x') as f:
  os.chmod(ROOT/'isolated-db-restore.json',0o600);json.dump(proof,f,sort_keys=True,indent=2);f.write('\n')
 print(json.dumps(proof,sort_keys=True))
 return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print(json.dumps({'status':'STOP','reason':str(e),'release_gate':'HOLD'}));sys.exit(3)
 except Exception:print(json.dumps({'status':'STOP','reason':'REDACTED_ERROR','release_gate':'HOLD'}));sys.exit(3)
