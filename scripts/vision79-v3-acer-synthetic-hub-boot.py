#!/usr/bin/env python3
"""Acer-only disconnected Hub candidate and prior-image health smoke.

Uses synthetic credentials and empty tmpfs data, no production data or server
access. Active swap is permitted because all generated state is synthetic.
"""
import json,os,secrets,socket,subprocess,sys,time,unittest
from unittest.mock import patch

CANDIDATE='sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6'
PRIOR='sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4'
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def call(args,timeout=90):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 need(p.returncode==0 and len(p.stdout)<8*1024*1024,'LOCAL_DOCKER_COMMAND_FAILED')
 return p.stdout.strip()
def preflight():
 need(socket.gethostname().split('.')[0]=='firelion-Aspire-A315-51','ACER_HOST_REQUIRED')
 need(not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'),'DOCKER_OVERRIDE_REFUSED')
 need(call(['docker','context','show'])==b'default' and
  call(['docker','info','--format','{{.Name}}'])==b'firelion-Aspire-A315-51','LOCAL_DOCKER_ONLY')
 for image in (CANDIDATE,PRIOR):
  rows=json.loads(call(['docker','image','inspect',image]))
  need(len(rows)==1 and rows[0].get('Id')==image,'IMAGE_IDENTITY_DRIFT')
def args(name,image):
 settings={'NODE_ENV':'production','PORT':'3040','DATA_DIR':'/app/data',
  'V79_HUB_STORE_BACKEND':'json','V79_HUB_ADMIN_USERNAME':'v3-synthetic',
  'V79_HUB_ADMIN_EMAIL':'vision79slu@gmail.com',
  'V79_HUB_ADMIN_PASSWORD':secrets.token_hex(24),'V79_REQUIRE_ADMIN_MFA':'1',
  'V79_HUB_SECURITY_KEY':secrets.token_hex(32),'V79_PLATFORM_SHARED_SECRET':secrets.token_hex(32),
  'V79_TIQUET_LAUNCH_SECRET':secrets.token_hex(32),'WIPAY_ENABLED':'0',
  'V79_WORKFORCE_ACTIONS_ENABLED':'0','V79_MARKETING_PRODUCTION_ENABLED':'0',
  'V79_AGENT_INTERNAL_URL':'http://127.0.0.1:9','APP_URL':'http://127.0.0.1:3040',
  'TIQUET_PUBLIC_URL':'http://127.0.0.1:3050'}
 result=['docker','run','--detach','--pull=never','--name',name,'--network','none',
  '--read-only','--log-driver','none','--security-opt','no-new-privileges',
  '--tmpfs','/app/data:rw,size=67108864,mode=0700,uid=1000,gid=1000',
  '--tmpfs','/tmp:rw,size=67108864,mode=0700']
 for k,v in settings.items():result.extend(['--env',k+'='+v])
 return result+[image]
def health(name):
 js="const h=require('http');let q=h.get('http://127.0.0.1:3040/api/health',r=>{r.resume();r.on('end',()=>process.exit(r.statusCode===200?0:2))});q.on('error',()=>process.exit(3));q.setTimeout(3000,()=>{q.destroy();process.exit(4)})"
 for _ in range(50):
  p=subprocess.run(['docker','exec',name,'node','-e',js],stdout=subprocess.DEVNULL,
   stderr=subprocess.DEVNULL,timeout=10)
  if p.returncode==0:return
  time.sleep(.5)
 raise Stop('ISOLATED_HUB_HEALTH_FAILED')
def one(label,image):
 name='v79-v3-synthetic-'+label+'-'+secrets.token_hex(5)
 need(subprocess.run(['docker','container','inspect',name],stdout=subprocess.DEVNULL,
  stderr=subprocess.DEVNULL,timeout=20).returncode!=0,'NAME_COLLISION')
 try:
  call(args(name,image),timeout=120)
  row=json.loads(call(['docker','inspect','--type=container',name]))[0]
  host=row.get('HostConfig') or {};mounts=row.get('Mounts') or []
  need(host.get('NetworkMode')=='none' and not host.get('PortBindings')
   and host.get('ReadonlyRootfs') is True
   and (host.get('LogConfig') or {}).get('Type')=='none'
   and all(m.get('Type')=='tmpfs' for m in mounts)
   and '/app/data' in (host.get('Tmpfs') or {}),'ISOLATION_DRIFT')
  health(name)
  print(label.upper()+'_SYNTHETIC_HEALTH=PASS',flush=True)
 finally:
  subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,
   stderr=subprocess.DEVNULL,timeout=60)
  need(subprocess.run(['docker','container','inspect',name],stdout=subprocess.DEVNULL,
   stderr=subprocess.DEVNULL,timeout=20).returncode!=0,'DISPOSABLE_CLEANUP_FAILED')
class Tests(unittest.TestCase):
 def test_wrong_host_no_docker(self):
  with patch('socket.gethostname',return_value='wrong'),patch(__name__+'.call') as command:
   with self.assertRaises(Stop):preflight()
   command.assert_not_called()
 def test_no_public_ports_or_mounts(self):
  a=args('test',CANDIDATE)
  self.assertIn('none',a);self.assertNotIn('--publish',a);self.assertNotIn('--volume',a)
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ('--self-test','--run'),'MODE_REQUIRED')
 if sys.argv[1]=='--self-test':
  r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 preflight();one('candidate',CANDIDATE);one('prior',PRIOR)
 print(json.dumps({'schema':'vision79-v3-synthetic-hub-image-boot','candidate':'PASS_HEALTH',
  'prior':'PASS_HEALTH','customer_data_used':False,'paired_tiquet_verified':False,
  'production_changes':'NONE','release_gate':'HOLD'},sort_keys=True))
 return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Stop as e:print(json.dumps({'status':'STOP','reason':str(e),'release_gate':'HOLD'}));sys.exit(3)
 except Exception as e:print(json.dumps({'status':'STOP','reason':'REDACTED_ERROR',
  'error_type':type(e).__name__,'release_gate':'HOLD'}));sys.exit(3)
