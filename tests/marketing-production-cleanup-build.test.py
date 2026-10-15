"""Cleanup builder emits evidence only after isolated image tests and live parity."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

ROOT=Path(__file__).resolve().parents[1]
def load():
    spec=importlib.util.spec_from_file_location('cleanup_build',ROOT/'scripts/marketing-production-cleanup-build.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class CleanupBuildTests(unittest.TestCase):
    def test_snapshot_binds_healthy_current_images_and_active_publication(self):
        m=load();meta={'Id':'same','Image':m.HUB_IMAGE,'State':{'Running':True,'StartedAt':'old','Health':{'Status':'healthy'}},
            'Config':{'Env':['V79_MARKETING_PRODUCTION_ENABLED=1','V79_MARKETING_PRODUCTION_PUBLISH_ENABLED=1']},'HostConfig':{},'Mounts':[]}
        def inspect(args):
            result=copy.deepcopy(meta)
            if args[-1]=='v79marketing-app':result['Image']=m.MARKETING_IMAGE
            return json.dumps([result]).encode()
        self.assertEqual(set(m.snapshot(inspect)),set(m.NAMES))
        for failure in ('health','image','publication'):
            def bad(args):
                result=json.loads(inspect(args))[0]
                if failure=='health':result['State']['Health']['Status']='unhealthy'
                if failure=='image':result['Image']='other'
                if failure=='publication':result['Config']['Env']=['V79_MARKETING_PRODUCTION_ENABLED=1','V79_MARKETING_PRODUCTION_PUBLISH_ENABLED=0']
                return json.dumps([result]).encode()
            with self.assertRaises(RuntimeError):m.snapshot(bad)

    def test_no_receipt_on_build_test_or_runtime_drift_and_never_recreates(self):
        for failure in (None,'build','tests','drift'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                m=load();root=Path(directory);calls=[];snapshots=0;scoped=[]
                def run(args,**kwargs):
                    calls.append(args)
                    if args[:2]==['docker','build'] and failure=='build':raise RuntimeError('Synthetic build failure')
                    if args[:2]==['docker','run']:
                        self.assertIn('--network',args);self.assertEqual(args[args.index('--network')+1],'none');self.assertIn('NODE_ENV=test',args)
                        if failure=='tests':raise RuntimeError('Synthetic test failure')
                    if args[:3]==['docker','image','inspect']:return json.dumps([{'Id':'sha256:tested','Config':{'Labels':{'org.opencontainers.image.revision':m.COMMIT},'Env':['NODE_ENV=production']}}]).encode()
                    return b''
                def snapshot(_run):
                    nonlocal snapshots
                    snapshots+=1;return {'live':'changed' if failure=='drift' and snapshots>1 else 'same'}
                support={'run':run,'NODE_BASE':'pinned-node-digest','verify_checkout_scope':lambda p:scoped.append(p),'readable_source':lambda p:None,
                    'isolated_test_command':lambda image:['docker','run','--rm','--network','none','--env','NODE_ENV=test',image,'--test','tests/marketing-production-panel.test.mjs']}
                with patch.object(m,'load',return_value=support),patch.object(m,'snapshot',side_effect=snapshot),patch.object(m.socket,'gethostname',return_value='v79sl'),patch.object(m.os,'getuid',return_value=1000),patch.object(m.pwd,'getpwuid',return_value=SimpleNamespace(pw_name='firelion')),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=10*1024**3)),patch.object(m.tempfile,'mkdtemp',return_value=directory),redirect_stdout(io.StringIO()):
                    if failure:
                        with self.assertRaises(RuntimeError):m.main()
                    else:m.main()
                self.assertEqual((root/'cleanup-build-receipt.json').exists(),failure is None)
                self.assertEqual(len(scoped),1);self.assertFalse(any('up' in c or 'restart' in c or 'compose' in c for c in calls))
                if failure is None:
                    receipt=json.loads((root/'cleanup-build-receipt.json').read_text());self.assertTrue(receipt['publicationEnabled']);self.assertFalse(receipt['cleanupPerformed']);self.assertFalse(receipt['deploymentPerformed']);self.assertTrue(receipt['isolatedTestsPassed'])

if __name__=='__main__':unittest.main()
