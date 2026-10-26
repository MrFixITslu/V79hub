#!/usr/bin/env python3
"""Read exact live DB images through SSH into Acer's local Docker image store.

No server writes, no container starts, and no plaintext archive on disk.
"""
import json
import os
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

IMAGES={
 'v79-hub-postgres':'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
 'tiquet-postgres':'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685'}
SERVER='firelion@192.168.100.163'
SSH=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',SERVER]
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def call(args,limit=16*1024*1024,timeout=60):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop('COMMAND_UNAVAILABLE') from None
 need(p.returncode==0 and len(p.stdout)<=limit,'COMMAND_FAILED')
 return p.stdout
def acer():
 need(socket.gethostname().split('.')[0]=='firelion-Aspire-A315-51','ACER_HOST_REQUIRED')
 need(not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'),'DOCKER_OVERRIDE_REFUSED')
 need(call(['docker','context','show'],limit=100).strip()==b'default','LOCAL_DOCKER_CONTEXT_REQUIRED')
 need(call(['docker','info','--format','{{.Name}}'],limit=200).strip()==b'firelion-Aspire-A315-51','LOCAL_DOCKER_DAEMON_REQUIRED')
def remote_baseline():
 raw=call([*SSH,"sg docker -c 'docker inspect --type container v79-hub-postgres tiquet-postgres'"])
 try:rows=json.loads(raw)
 except (ValueError,UnicodeDecodeError):raise Stop('REMOTE_INSPECT_INVALID') from None
 need(len(rows)==2 and {r.get('Name','').lstrip('/') for r in rows}==set(IMAGES),'REMOTE_DB_SET_DRIFT')
 for row in rows:
  name=row['Name'].lstrip('/')
  need(row.get('Image')==IMAGES[name] and row.get('State',{}).get('Status')=='running'
       and row.get('State',{}).get('Health',{}).get('Status')=='healthy','REMOTE_DB_IMAGE_OR_HEALTH_DRIFT')
 return {r['Name'].lstrip('/'):r['Id'] for r in rows}
def local_image(image):
 try:rows=json.loads(call(['docker','image','inspect',image]))
 except Stop:return False
 except (ValueError,UnicodeDecodeError):return False
 return len(rows)==1 and rows[0].get('Id')==image
def stage():
 acer();before=remote_baseline()
 if not all(local_image(image) for image in IMAGES.values()):
  remote="sg docker -c 'docker image save "+' '.join(IMAGES.values())+"'"
  producer=subprocess.Popen([*SSH,remote],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  receiver=None
  try:
   receiver=subprocess.Popen(['docker','image','load'],stdin=producer.stdout,
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   producer.stdout.close()
   loaded=receiver.wait(timeout=1800)==0
   saved=producer.wait(timeout=1800)==0
   need(loaded and saved,'IMAGE_TRANSFER_FAILED')
  finally:
   if receiver is not None and receiver.poll() is None:receiver.kill()
   if producer.poll() is None:producer.kill()
   if receiver is not None:receiver.wait()
   producer.wait()
 need(all(local_image(image) for image in IMAGES.values()),'EXACT_LOCAL_IMAGE_ID_NOT_RETAINED')
 need(remote_baseline()==before,'REMOTE_DB_CHANGED_DURING_STAGE')
 print(json.dumps({'schema':'vision79-v3-acer-db-image-stage','exact_images':'PASS_2',
   'local_daemon':'ACER','server_access':'READ_ONLY_IMAGE_SAVE',
   'production_changes':'NONE','release_gate':'HOLD'},sort_keys=True))
class Tests(unittest.TestCase):
 def test_wrong_host_no_docker(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.call') as command:
   with self.assertRaises(Stop):acer()
   command.assert_not_called()
 def test_expected_images_distinct(self):
  self.assertEqual(len(set(IMAGES.values())),2)
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ('--self-test','--stage'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if result.wasSuccessful() else 1
 stage();return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print(json.dumps({'status':'STOP','reason':str(e),'release_gate':'HOLD'}));sys.exit(3)
 except Exception:print(json.dumps({'status':'STOP','reason':'REDACTED_ERROR','release_gate':'HOLD'}));sys.exit(3)
