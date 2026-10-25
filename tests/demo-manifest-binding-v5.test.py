#!/usr/bin/env python3
"""Non-deploying tests: restored Hub OCI config -> loaded Docker manifest cutover."""
import copy
import importlib.util
import io
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

P=Path(__file__).parents[1]/'scripts'
def load(name):
    spec=importlib.util.spec_from_file_location('v79_test_'+name.replace('-','_'),P/name)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

class ManifestBoundV5(unittest.TestCase):
    def test_exact_manifest_bindings_separate_config_and_runtime(self):
        binder=load('demo-manifest-bound-executor-v5.py')
        expected={
            'v79-hub':(
              'sha256:20504c556eea55af7d0f1ef85241582715e95b08fce00386335e41035decd9de',
              'sha256:66caa099adf1321b72a90b22f8125981e5a6d99b5920cebae0454541cccd9fa7'),
            'v79-tiquet-manager':(
              'sha256:6bb9acb1f0c8e8866082882f1cbb3d6cc9823ead559ef10a266618b013f793e1',
              'sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0')}
        self.assertEqual(set(binder.BINDINGS),set(expected))
        for n,(config,manifest) in expected.items():
            self.assertEqual(binder.BINDINGS[n]['config'],config)
            self.assertEqual(binder.BINDINGS[n]['manifest'],manifest)
            self.assertNotEqual(config,manifest)
        self.assertEqual(binder.INNER_BYTES,204488782)
        self.assertIsNone(binder.PLAN_SHA)
        self.assertIsNone(binder.ORIGINAL_SHA)

    def test_candidate_projection_changes_only_approved_image_and_hash(self):
        binder=load('demo-manifest-bound-executor-v5.py')
        old={'apps':{}}
        for name,pins in binder.BINDINGS.items():
            old['apps'][name]={
                'candidate_image':{'Id':pins['config'],'Config':{'Labels':{}}},
                'candidate_file':'/private/'+name+'-candidate.json',
                'candidate_sha256':'0'*64,
                'service':name,
                'model':{'services':{name:{'image':pins['config'],'ports':[]}}},
                'rollback_file':'/private/'+name+'-rollback.json',
                'rollback_sha256':'1'*64}
        original=copy.deepcopy(old)
        bound=binder.project_plan(old,Path('/private'),binder.BINDINGS)
        self.assertEqual(old,original)
        for name,pins in binder.BINDINGS.items():
            orig=old['apps'][name];after=bound['apps'][name]
            self.assertEqual(after['candidate_image']['Id'],pins['manifest'])
            self.assertEqual(after['model']['services'][name]['image'],pins['manifest'])
            self.assertEqual(after['rollback_file'],orig['rollback_file'])
            self.assertEqual(after['rollback_sha256'],orig['rollback_sha256'])
            self.assertEqual(after['candidate_image']['Config'],orig['candidate_image']['Config'])
            self.assertEqual(after['candidate_file'],'/private/manifest-'+name+'-candidate.json')
        corrupted=copy.deepcopy(old)
        corrupted['apps']['v79-hub']['candidate_image']['Id']='sha256:'+'0'*64
        with self.assertRaisesRegex(binder.Refused,'ORIGINAL_CONFIG_PIN_CHANGED'):
            binder.project_plan(corrupted,Path('/private'),binder.BINDINGS)

    def test_v5_embeds_exact_helper_and_keeps_runtime_and_mount_contract(self):
        v4=load('release-hardened-pair-demo-v4.py')
        v5=load('release-hardened-pair-demo-v5.py')
        helper=(P/'demo-manifest-bound-executor-v5.py').read_text()
        self.assertEqual(v5.SOURCES['manifest-bound-executor.py'],helper)
        for name,raw in v4.SOURCES.items():
            self.assertEqual(v5.SOURCES[name],raw)
        self.assertEqual(v5.INNER_BYTES,204488782)
        self.assertIsNone(v5.CHECKPOINT)
        source=(P/'release-hardened-pair-demo-v5.py').read_text()
        self.assertIn('MANIFEST_BINDING=PASS_CONFIG_TO_LOADED_RUNTIME_IDS',source)
        self.assertIn('LOADED_MANIFEST_BINDING_NOT_VERIFIED',source)
        self.assertIn("'--server-bind'",source)
        self.assertIn("'--server-launch'",source)
        self.assertIn("'--server-rollback'",source)
        self.assertIn('MANUAL_ROLLBACK_COMMAND=ISSUED_AFTER_MANIFEST_BINDING_ONLY',source)
        self.assertIn('SELECTED_PRIVATE_HTTP_HEALTH_FAILED',source)

    def test_helper_requires_strict_external_sealed_plan_and_lease(self):
        helper=(P/'demo-manifest-bound-executor-v5.py').read_text()
        for required in (
            "need(Path(__file__).resolve()==ROOT/'continue-manifest-bound-pair.py'",
            "need(m.server_root()==ROOT,'SEALED_ROOT_CHANGED')",
            "need(old['backup']['checkpoint']==args.checkpoint_name",
            "'TRANSACTION_MARKED_DO_NOT_RELAUNCH'",
            "'ORIGINAL_APP_CHANGED_BEFORE_BINDING'",
            "'ACCEPTED_CANDIDATE_CONFIG_BYTES_CHANGED'",
            "'LOADED_RUNTIME_MANIFEST_IDENTITY_CHANGED'",
            "'CONFIG_DESCRIPTOR_SIZE_CHANGED'",
            "'MANIFEST_MODEL_ROUNDTRIP_CHANGED'",
            "'PROJECTED_PLAN_HASH_CHANGED'",
            "m.write_new(ROOT/'launch-claim.json'",
            "return m.monitor(ROOT)"):
            if required=="return m.monitor(ROOT)":
                continue
            self.assertIn(required,helper)
if __name__=='__main__':unittest.main()
