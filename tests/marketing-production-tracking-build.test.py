"""Paired tracking builder never deploys and requires tests and live parity."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

SOURCE=Path(__file__).resolve().parents[1]/'scripts/marketing-production-tracking-build.py'
def load():
 s=importlib.util.spec_from_file_location('tracking_build',SOURCE);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class TrackingBuilderTests(unittest.TestCase):
 def test_every_test_container_is_nonroot_bounded_network_none_with_no_host_mounts(self):
  m=load();args=m.isolated('sha256:synthetic',['tests/run'],['NODE_ENV=test'])
  for key,value in [('--network','none'),('--user','node'),('--cap-drop','ALL'),('--security-opt','no-new-privileges'),('--memory','768m'),('--cpus','2')]:self.assertEqual(args[args.index(key)+1],value)
  self.assertIn('--read-only',args);self.assertIn('--rm',args);self.assertNotIn('--mount',args);self.assertNotIn('-v',args);self.assertEqual(args[-2:],['sha256:synthetic','tests/run'])

 def test_failed_image_tests_or_live_drift_never_write_a_passed_build_receipt(self):
  for failure in (None,'image-tests','live-drift'):
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
    m=load();calls=[];checks=0
    def snapshot():
     nonlocal checks
     checks+=1;return {'runtime':'changed' if failure=='live-drift' and checks>1 else 'accepted'}
    def build(root,spec):
     calls.append(spec[0])
     if failure=='image-tests':raise RuntimeError('Synthetic isolated tests failed')
     return {'image':'sha256:'+spec[0],'commit':spec[1],'isolatedTestsPassed':True}
    with patch.object(m.socket,'gethostname',return_value='v79sl'),patch.object(m.os,'getuid',return_value=1000),patch.object(m.pwd,'getpwuid',return_value=SimpleNamespace(pw_name='firelion')),patch.object(m,'snapshot',side_effect=snapshot),patch.object(m,'build',side_effect=build),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=20*1024**3)),patch.object(m.tempfile,'mkdtemp',return_value=directory),redirect_stdout(io.StringIO()):
     if failure:
      with self.assertRaises(RuntimeError):m.main()
     else:m.main()
    receipt=Path(directory)/'tracking-build-receipt.json';self.assertEqual(receipt.exists(),failure is None)
    if failure is None:
     data=json.loads(receipt.read_text());self.assertFalse(data['deploymentPerformed']);self.assertTrue(data['publicationEnabled']);self.assertFalse(data['cleanupPerformed']);self.assertEqual(set(data['candidates']),{'V79hub','V79Marketing'})

 def test_compiled_source_mismatch_stops_marketing_build_after_tests_without_deploying(self):
  for mismatch in (False,True):
   with self.subTest(mismatch=mismatch),tempfile.TemporaryDirectory() as directory:
    m=load();root=Path(directory);checkout=root/'source';checkout.mkdir();calls=[]
    files=('server.ts','src/lib/productionTracking.ts','src/lib/publicationLinks.ts','src/lib/productionWorkflow.ts','src/lib/productionStore.ts','src/lib/publisher.ts','src/lib/db.ts')
    for filename in files:
     p=checkout/filename;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic public source')
    hashes={'../'+f:m.hashlib.sha256((checkout/f).read_bytes()).hexdigest() for f in files}
    if mismatch:hashes['../src/lib/productionTracking.ts']='changed'
    def run(args,**kwargs):
     calls.append(args)
     self.assertNotIn('compose',args);self.assertNotIn('restart',args)
     if args[:3]==['docker','image','inspect']:
      return json.dumps([{'Id':'sha256:test-image','Config':{'Labels':{'org.opencontainers.image.revision':m.MARKETING[1]},'Env':['NODE_ENV=production']}}]).encode()
     if args[:2]==['docker','run'] and '-e' in args:return json.dumps(hashes).encode()
     return b''
    with patch.object(m,'checkout',return_value=checkout),patch.object(m,'run',side_effect=run),redirect_stdout(io.StringIO()):
     if mismatch:
      with self.assertRaises(RuntimeError):m.build(root,m.MARKETING)
     else:self.assertTrue(m.build(root,m.MARKETING)['isolatedTestsPassed'])
    containers=[c for c in calls if c[:2]==['docker','run']];self.assertEqual(len(containers),3)
    for c in containers:self.assertEqual(c[c.index('--network')+1],'none');self.assertNotIn('--mount',c)
    verification=(root/'marketing-verification.Dockerfile').read_text();self.assertIn('npm ci --include=dev',verification);self.assertTrue(verification.endswith('USER node\n'))

if __name__=='__main__':unittest.main()
