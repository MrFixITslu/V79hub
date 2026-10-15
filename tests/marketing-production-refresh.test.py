"""Checkpoint refresh guard/key reuse checks; no Docker/server access."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]/'scripts/marketing-production-refresh-checkpoint.py'

def load():
    spec = importlib.util.spec_from_file_location('refresh', SOURCE)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class RefreshTests(unittest.TestCase):
    def setUp(self):self.m=load()

    def test_current_g3_images_and_original_rollback_images_are_distinct(self):
        m=self.m
        self.assertEqual(m.BASELINES['v79-hub'],m.CANDIDATE)
        self.assertEqual(m.BASELINES['v79marketing-app'],m.MARKETING_CANDIDATE)
        self.assertNotEqual(m.ROLLBACK_IMAGES['v79-hub'],m.CANDIDATE)
        self.assertNotEqual(m.ROLLBACK_IMAGES['v79marketing-app'],m.MARKETING_CANDIDATE)
        for name in set(m.BASELINES)-{'v79-hub','v79marketing-app'}:
            self.assertEqual(m.BASELINES[name],m.ROLLBACK_IMAGES[name])

    def fixture(self):
        m=self.m
        metadata={name:{'Id':'unchanged-'+name,'Image':image,'State':{'Running':True,'Health':{'Status':'healthy'}},
                       'Config':{'Env':[]}} for name,image in m.BASELINES.items()}
        record={'originalContainerIds':{name:meta['Id'] for name,meta in metadata.items()}}
        metadata['v79-hub']['Id']='already-active-hub'
        metadata['v79-hub']['Config']['Env']=['V79_MARKETING_PRODUCTION_ENABLED=1','V79_WORKFORCE_ACTIONS_ENABLED=1']
        metadata['v79marketing-app']['Config']['Env']=['V79_MARKETING_PRODUCTION_ENABLED=0','V79_MARKETING_PRODUCTION_PUBLISH_ENABLED=0']
        return record,metadata

    def test_reviewed_partial_state_is_required(self):
        m=self.m;record,metadata=self.fixture();m.validate_partial_identity(record,metadata)
        for name,change in [('v79-hub','image'),('v79marketing-app','id'),('v79-hub-postgres','id'),('v79-hub','flag'),('v79marketing-app','publication')]:
            bad=copy.deepcopy(metadata)
            if change=='image':bad[name]['Image']='wrong-image'
            if change=='id':bad[name]['Id']='unexpected-recreation'
            if change=='flag':bad[name]['Config']['Env'][0]='V79_MARKETING_PRODUCTION_ENABLED=0'
            if change=='publication':bad[name]['Config']['Env'][1]='V79_MARKETING_PRODUCTION_PUBLISH_ENABLED=1'
            with self.assertRaises(RuntimeError):m.validate_partial_identity(record,bad)

    def test_copy_reuses_exact_protected_bytes_and_refuses_tampering(self):
        m=self.m
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m.SOURCE_RECOVERY=root/'source';m.SOURCE_RECOVERY.mkdir();m.work=root/'fresh';m.work.mkdir()
            files={'g3-protected-keys.json':b'{"shared":"existing","audit":"existing-separate"}\n',
                   'g3-hub-disabled.yml':b'{"services":{"v79-hub":{"image":"pinned"}}}\n',
                   'g3-marketing-disabled.yml':b'{"services":{"v79-marketing":{"image":"pinned"}}}\n'}
            for name,data in files.items():(m.SOURCE_RECOVERY/name).write_bytes(data)
            m.source_activation_record={'preparedOverlayHashes':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
            with patch.object(m,'resolve_stack',return_value={'services':{}}):m.prepare_overlays()
            for name,data in files.items():self.assertEqual((m.work/name).read_bytes(),data)
            m.work=root/'tampered-attempt';m.work.mkdir()
            (m.SOURCE_RECOVERY/'g3-hub-disabled.yml').write_bytes(b'changed')
            with patch.object(m,'resolve_stack',return_value={'services':{}}):
                with self.assertRaises(RuntimeError):m.prepare_overlays()
            self.assertFalse((m.work/'g3-hub-disabled.yml').exists())

    def test_refresh_does_not_generate_g3_keys_or_invoke_live_activation(self):
        tree=ast.parse(SOURCE.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='secrets' and node.func.attr=='token_hex':
                self.assertEqual(ast.literal_eval(node.args[0]),8,'Only scratch resource nonce generation is allowed')
        self.assertNotIn('legacy_prepare_overlays_unused',SOURCE.read_text())
        self.assertIsInstance(tree.body[-1],ast.If)
        self.assertNotIn("['up',",SOURCE.read_text())

    def test_live_drift_checks_cover_config_mounts_and_restart_identity(self):
        m=self.m;record,metadata=self.fixture()
        for name,meta in metadata.items():
            meta['State']['StartedAt']='fixed';meta['Config']['Labels']={};meta['HostConfig']={};meta['Mounts']=[]
        metadata['v79-hub']['Config']['Labels']['com.docker.compose.project.config_files']=','.join(m.HUB_FILES)
        metadata['v79marketing-app']['Config']['Labels']['com.docker.compose.project.config_files']=','.join(m.MARKETING_FILES)
        m.runtime=copy.deepcopy(metadata);m.FILES={}
        with patch.object(m,'inspect',side_effect=lambda name:copy.deepcopy(metadata[name])):
            m.verify_live()
            for field,value in [('Mounts',[{'Source':'new'}]),('HostConfig',{'Privileged':True})]:
                before=copy.deepcopy(metadata['v79-hub'][field]);metadata['v79-hub'][field]=value
                with self.assertRaises(RuntimeError):m.verify_live()
                metadata['v79-hub'][field]=before
            metadata['v79-hub']['State']['StartedAt']='restarted'
            with self.assertRaises(RuntimeError):m.verify_live()

if __name__=='__main__':unittest.main()
