#!/usr/bin/env python3
"""Config/manifest identity, image-only projection and unchanged execution guards."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('bound',Path(__file__).parents[1]/'scripts/continue-manifest-bound-pair.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class BindingTests(unittest.TestCase):
    def fixture(self,root,*,wrong_pointer=False,wrong_arch=False,wrong_revision=False):
        config={'os':'linux','architecture':'arm64' if wrong_arch else 'amd64',
            'config':{'Labels':{'org.opencontainers.image.revision':'wrong' if wrong_revision else 'approved'}},
            'rootfs':{'type':'layers','diff_ids':['sha256:'+'c'*64]}}
        config_raw=json.dumps(config).encode();config_id='sha256:'+hashlib.sha256(config_raw).hexdigest()
        manifest={'schemaVersion':2,'config':{'digest':'sha256:'+'f'*64 if wrong_pointer else config_id,
                                            'size':len(config_raw)},'layers':[]}
        manifest_raw=json.dumps(manifest).encode();manifest_id='sha256:'+hashlib.sha256(manifest_raw).hexdigest()
        path=root/'accepted.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            for digest,raw in ((config_id,config_raw),(manifest_id,manifest_raw)):
                info=tarfile.TarInfo('blobs/sha256/'+digest.removeprefix('sha256:'));info.size=len(raw)
                archive.addfile(info,io.BytesIO(raw))
        binding={'app':{'config':config_id,'manifest':manifest_id,'revision':'approved'}}
        return path,binding,config

    def test_exact_archive_proves_config_to_manifest_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            path,binding,config=self.fixture(Path(temp))
            self.assertEqual(m.verify_archive(path,m.sha(path),binding),{'app':config})

    def test_changed_archive_or_blob_identity_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            path,binding,_=self.fixture(Path(temp))
            with self.assertRaisesRegex(m.Refused,'ARCHIVE_HASH_CHANGED'):m.verify_archive(path,'0'*64,binding)
            binding['app']['manifest']='sha256:'+'f'*64
            with self.assertRaisesRegex(m.Refused,'BLOBS_MISSING'):m.verify_archive(path,m.sha(path),binding)

    def test_wrong_config_pointer_platform_and_revision_are_not_accepted(self):
        for key,reason in [('wrong_pointer','CONFIG_BINDING_MISMATCH'),('wrong_arch','IMAGE_PLATFORM'),
                           ('wrong_revision','SOURCE_REVISION_CHANGED')]:
            with tempfile.TemporaryDirectory() as temp:
                path,binding,_=self.fixture(Path(temp),**{key:True})
                with self.subTest(key=key),self.assertRaisesRegex(m.Refused,reason):
                    m.verify_archive(path,m.sha(path),binding)

    def plan(self):
        config='sha256:'+'a'*64
        return {'protected':{'db':{'Id':'original-db'}},'requires_supervision':True,'timers':['approved.timer'],
            'apps':{'app':{'service':'app','candidate_image':{'Id':config,'Config':{'User':'appuser'}},
                'model':{'services':{'app':{'image':config,'environment':{'MFA':'1','PRICE':'$$150'},
                    'volumes':['original:data'],'cap_drop':['ALL']},'db':{'image':'original-db'}}},
                'candidate_file':'/old/candidate.json','candidate_sha256':'old',
                'rollback_image':{'Id':'original-image'},'rollback_file':'/old/rollback.json',
                'rollback_sha256':'retained','baseline':{'Id':'original-container'}}}}

    def test_projection_changes_only_candidate_image_reference_and_new_file_hash(self):
        old=self.plan();snapshot=copy.deepcopy(old)
        binding={'app':{'config':'sha256:'+'a'*64,'manifest':'sha256:'+'b'*64}}
        new=m.project_plan(old,Path('/private'),binding)
        self.assertEqual(old,snapshot)
        self.assertEqual(new['protected'],old['protected'])
        self.assertTrue(new['requires_supervision'])
        entry=new['apps']['app'];before=old['apps']['app']
        self.assertEqual(entry['rollback_image'],before['rollback_image'])
        self.assertEqual(entry['rollback_file'],before['rollback_file'])
        self.assertEqual(entry['baseline'],before['baseline'])
        changed=copy.deepcopy(entry['model']);changed['services']['app']['image']=before['candidate_image']['Id']
        self.assertEqual(changed,before['model'])
        self.assertEqual(entry['candidate_sha256'],hashlib.sha256(m.model_bytes(entry['model'])).hexdigest())

    def test_unapproved_original_config_pin_refuses(self):
        with self.assertRaisesRegex(m.Refused,'ORIGINAL_CONFIG_PIN_CHANGED'):
            m.project_plan(self.plan(),Path('/private'),{'app':{'config':'wrong','manifest':'other'}})

    def test_original_execute_bytecode_and_other_globals_are_unchanged(self):
        original=m.original(Path(m.__file__).with_name('release-hardened-pair.py'))
        before=original.validate_plan;validator=lambda root,pin:None
        reused=m.executor(original,validator)
        self.assertIs(reused.__code__,original.execute.__code__)
        self.assertIs(original.validate_plan,before)
        self.assertEqual(set(reused.__globals__),set(original.__dict__))
        for key,value in original.__dict__.items():
            self.assertIs(reused.__globals__[key],validator if key=='validate_plan' else value)

    def test_loaded_manifest_requires_matching_descriptor_platform_and_layers(self):
        binding={'app':{'manifest':'sha256:'+'b'*64,'revision':'approved'}}
        config={'os':'linux','architecture':'amd64','rootfs':{'diff_ids':['sha256:'+'c'*64]}}
        row={'Id':binding['app']['manifest'],'Descriptor':{'digest':binding['app']['manifest'],
             'mediaType':'application/vnd.oci.image.manifest.v1+json'},'Os':'linux','Architecture':'amd64',
             'RootFS':{'Layers':config['rootfs']['diff_ids']},'Config':{'Labels':{'org.opencontainers.image.revision':'approved'}}}
        api=types.SimpleNamespace(call=lambda args:json.dumps([row]).encode())
        m.verify_loaded(api,binding,{'app':config})
        descriptor=row.pop('Descriptor');m.verify_loaded(api,binding,{'app':config})
        row['Id']='sha256:'+'a'*64
        with self.assertRaisesRegex(m.Refused,'MANIFEST_IDENTITY_CHANGED'):m.verify_loaded(api,binding,{'app':config})
        row['Id']=binding['app']['manifest'];row['Descriptor']=descriptor
        row['Descriptor']['digest']='sha256:'+'d'*64
        with self.assertRaisesRegex(m.Refused,'DESCRIPTOR_CHANGED'):m.verify_loaded(api,binding,{'app':config})
        row['Descriptor']['digest']=binding['app']['manifest']
        row['RootFS']['Layers']=['sha256:'+'d'*64]
        with self.assertRaisesRegex(m.Refused,'FILESYSTEM_LAYER_IDENTITIES_CHANGED'):
            m.verify_loaded(api,binding,{'app':config})


if __name__=='__main__':unittest.main()
