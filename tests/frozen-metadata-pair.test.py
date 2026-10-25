#!/usr/bin/env python3
"""Frozen metadata stays in exact equality; every unrelated gate is unchanged."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('frozen',Path(__file__).parents[1]/'scripts/continue-frozen-metadata-pair.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('transaction',Path(__file__).parents[1]/'scripts/paired-compose-transaction.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)


class FrozenMetadata(unittest.TestCase):
    def fixture(self):
        return {'requires_supervision':True,'protected':{'db':{'Id':'fixed'}},'timers':['fixed.timer'],
          'apps':{'app':{'service':'app','model':{'services':{'app':{'image':'manifest',
             'environment':{'NODE_VERSION':'synthetic','YARN_VERSION':'synthetic','SECRET':'unchanged'},
             'read_only':True,'cap_drop':['ALL']}}},
             'removed_metadata':['NODE_VERSION','YARN_VERSION'],
             'baseline':{'Config':{'Env':['NODE_VERSION=synthetic','YARN_VERSION=synthetic','SECRET=unchanged']}},
             'candidate_image':{'Id':'manifest','Config':{'Env':['PATH=/bin']}},
             'rollback_image':{'Id':'original'},'candidate_file':'/old/candidate.json',
             'rollback_file':'/old/rollback.json','candidate_sha256':'a','rollback_sha256':'b'}}}

    def test_both_frozen_keys_remain_exactly_configured_and_not_ignored(self):
        old=self.fixture();snapshot=copy.deepcopy(old)
        result=m.frozen_projection(old,Path('/new'))
        self.assertEqual(result['apps']['app']['removed_metadata'],[])
        self.assertEqual(old,snapshot)
        self.assertEqual(result['apps']['app']['model'],old['apps']['app']['model'])
        self.assertEqual(result['apps']['app']['baseline'],old['apps']['app']['baseline'])
        self.assertEqual(result['protected'],old['protected'])
        self.assertEqual(result['timers'],old['timers'])
        self.assertTrue(result['requires_supervision'])
        for key in ('candidate_sha256','rollback_sha256','rollback_image','candidate_image'):
            self.assertEqual(result['apps']['app'][key],old['apps']['app'][key])

    def test_inherited_absent_metadata_keeps_original_reviewed_exception(self):
        old=self.fixture();old['apps']['app']['model']['services']['app']['environment'].pop('YARN_VERSION')
        result=m.frozen_projection(old,Path('/new'))
        self.assertEqual(result['apps']['app']['removed_metadata'],['YARN_VERSION'])

    def test_frozen_value_drift_refuses(self):
        old=self.fixture();old['apps']['app']['model']['services']['app']['environment']['NODE_VERSION']='changed'
        with self.assertRaisesRegex(m.Refused,'BASELINE_MISMATCH'):m.frozen_projection(old,Path('/new'))

    def test_missing_baseline_value_refuses(self):
        old=self.fixture();old['apps']['app']['baseline']['Config']['Env']=['YARN_VERSION=synthetic']
        with self.assertRaisesRegex(m.Refused,'BASELINE_MISMATCH'):m.frozen_projection(old,Path('/new'))

    def test_unreviewed_key_refuses(self):
        old=self.fixture();old['apps']['app']['removed_metadata'].append('SECRET')
        with self.assertRaisesRegex(m.Refused,'UNREVIEWED_METADATA_NAME'):m.frozen_projection(old,Path('/new'))

    def test_candidate_default_not_actually_removed_refuses(self):
        old=self.fixture();old['apps']['app']['candidate_image']['Config']['Env'].append('NODE_VERSION=other')
        with self.assertRaisesRegex(m.Refused,'NOT_REMOVED_FROM_IMAGE'):m.frozen_projection(old,Path('/new'))

    def test_copied_model_files_must_keep_same_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);root.chmod(0o700);old=self.fixture()
            for which in ('candidate','rollback'):
                raw=(which+' exact original model').encode();(root/(which+'.json')).write_bytes(raw)
                old['apps']['app'][which+'_sha256']=hashlib.sha256(raw).hexdigest()
            projected=m.frozen_projection(old,root)
            backend=t.ComposeBackend(root,projected)
            for which in ('candidate','rollback'):
                path=Path(projected['apps']['app'][which+'_file']);path.write_bytes((which+' exact original model').encode());path.chmod(0o600)
            backend.check_files()
            Path(projected['apps']['app']['candidate_file']).write_bytes(b'changed')
            with self.assertRaisesRegex(t.Refused,'SEALED_MODEL_FILE_CHANGED'):backend.check_files()

    def test_original_runtime_guard_still_rejects_missing_or_changed_env_values(self):
        fixture_module=m.load_module(Path(__file__).with_name('paired-compose-transaction.test.py'),'runtime_fixture')
        before,after,entry=fixture_module.TransactionTests().runtime_fixture()
        for row in (before,after):
            row['Config']['Env']+=['NODE_VERSION=synthetic','YARN_VERSION=synthetic']
        entry['baseline']=before
        entry['model']['services']['hub']['environment']={'NODE_VERSION':'synthetic','YARN_VERSION':'synthetic'}
        entry['removed_metadata']=['NODE_VERSION','YARN_VERSION']
        entry['rollback_file']='/private/rollback.json'
        with self.assertRaisesRegex(t.Refused,'UNREVIEWED_IMAGE_ENVIRONMENT_CHANGE'):
            t.runtime_matches(before,after,entry,'candidate',selinux_enabled=False)
        corrected=m.frozen_projection({'apps':{'hub':entry}},Path('/private'))['apps']['hub']
        after['Config']['Labels']['com.docker.compose.project.config_files']=corrected['candidate_file']
        self.assertTrue(t.runtime_matches(before,after,corrected,'candidate',selinux_enabled=False))
        for env in (['SECRET=synthetic-only','NODE_VERSION=changed','YARN_VERSION=synthetic'],
                    ['SECRET=synthetic-only','YARN_VERSION=synthetic'],
                    ['SECRET=changed','NODE_VERSION=synthetic','YARN_VERSION=synthetic']):
            changed=copy.deepcopy(after);changed['Config']['Env']=env
            with self.subTest(env=env),self.assertRaisesRegex(t.Refused,'ACTUAL_ENVIRONMENT_CHANGED'):
                t.runtime_matches(before,changed,corrected,'candidate',selinux_enabled=False)

    def test_original_runner_and_manifest_helper_remain_pinned_unchanged(self):
        scripts=Path(m.__file__).parent
        self.assertEqual(m.sha(scripts/'release-hardened-pair.py'),m.ORIGINAL_SHA)
        self.assertEqual(m.sha(scripts/'continue-manifest-bound-pair.py'),m.BINDER_SHA)


if __name__=='__main__':unittest.main()
