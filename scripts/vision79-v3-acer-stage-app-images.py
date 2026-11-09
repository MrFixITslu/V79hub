#!/usr/bin/env python3
"""Stage exact rollback Hub and current Tiquet images on Acer local Docker.

Rollback Hub comes from the independently decrypted offhost checkpoint; Tiquet
is read through SSH from the healthy server. No production writes or starts.
"""
import hashlib,json,os,socket,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch

PRIOR='sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4'
TIQUET='sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0'
CANDIDATE='sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6'
ROOT=Path('/home/firelion/v79-v3-offhost-we7b0lir')
ARCHIVE=ROOT/'v3-20261026T194538Z-gnm710en/prior-hub-image.tar.gpg'
RECEIPT_HASH='35a9b4d41b5c42a8c6653e1c1985ebdae49ce77432d57c94ff68c82172173df5'
SSH=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','firelion@192.168.100.163']
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def call(args,limit=16*1024*1024):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
 need(p.returncode==0 and len(p.stdout)<=limit,'COMMAND_FAILED')
 return p.stdout
def image_ok(image):
 try:rows=json.loads(call(['docker','image','inspect',image]))
 except (Stop,ValueError,UnicodeDecodeError):return False
 return len(rows)==1 and rows[0].get('Id')==image
def transfer(producer_args):
 producer=subprocess.Popen(producer_args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 consumer=None
 try:
  consumer=subprocess.Popen(['docker','image','load'],stdin=producer.stdout,
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  producer.stdout.close()
  loaded=consumer.wait(timeout=1800)==0;saved=producer.wait(timeout=1800)==0
  need(loaded and saved,'IMAGE_STREAM_FAILED')
 finally:
  if consumer is not None and consumer.poll() is None:consumer.kill()
  if producer.poll() is None:producer.kill()
  if consumer is not None:consumer.wait()
  producer.wait()
def preflight():
 need(socket.gethostname().split('.')[0]=='firelion-Aspire-A315-51','ACER_HOST_REQUIRED')
 need(not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'),'DOCKER_OVERRIDE_REFUSED')
 need(call(['docker','context','show']).strip()==b'default'
      and call(['docker','info','--format','{{.Name}}']).strip()==b'firelion-Aspire-A315-51','LOCAL_DOCKER_REQUIRED')
 need(image_ok(CANDIDATE),'APPROVED_CANDIDATE_MISSING')
 need(ARCHIVE.is_file() and not ARCHIVE.is_symlink(),'OFFHOST_PRIOR_IMAGE_MISSING')
 receipt=ARCHIVE.parent/'receipt.json'
 need(receipt.is_file() and hashlib.sha256(receipt.read_bytes()).hexdigest()==RECEIPT_HASH,'RECEIPT_DRIFT')
 data=json.loads(receipt.read_text());h=hashlib.sha256()
 with ARCHIVE.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 need(h.hexdigest()==data['encrypted_sha256'].get(ARCHIVE.name),'PRIOR_IMAGE_CIPHERTEXT_DRIFT')
def remote_tiquet():
 raw=call([*SSH,"sg docker -c 'docker inspect --type container v79-tiquet-manager'"])
 rows=json.loads(raw)
 need(len(rows)==1 and rows[0].get('Image')==TIQUET and
      rows[0].get('State',{}).get('Health',{}).get('Status')=='healthy','LIVE_TIQUET_DRIFT')
 return rows[0]['Id']
def stage():
 preflight()
 if not image_ok(PRIOR):transfer(['gpg','--batch','--quiet','--decrypt',str(ARCHIVE)])
 need(image_ok(PRIOR),'ROLLBACK_IMAGE_ID_NOT_RETAINED')
 before=remote_tiquet()
 if not image_ok(TIQUET):transfer([*SSH,"sg docker -c 'docker image save "+TIQUET+"'"])
 need(image_ok(TIQUET) and remote_tiquet()==before,'TIQUET_IMAGE_OR_LIVE_ID_DRIFT')
 print(json.dumps({'schema':'vision79-v3-acer-app-images','candidate':'PASS_EXACT_ID',
  'prior_hub_from_offhost_checkpoint':'PASS_EXACT_ID','current_tiquet':'PASS_EXACT_ID',
  'production_changes':'NONE','release_gate':'HOLD'},sort_keys=True))
class Tests(unittest.TestCase):
 def test_wrong_host_before_docker(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.call') as command:
   with self.assertRaises(Stop):preflight()
   command.assert_not_called()
 def test_distinct_pins(self):self.assertEqual(len({PRIOR,TIQUET,CANDIDATE}),3)
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ('--self-test','--stage'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 stage();return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print(json.dumps({'status':'STOP','reason':str(e),'release_gate':'HOLD'}));sys.exit(3)
 except Exception:print(json.dumps({'status':'STOP','reason':'REDACTED_ERROR','release_gate':'HOLD'}));sys.exit(3)
