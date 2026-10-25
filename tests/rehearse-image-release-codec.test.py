import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('codec',ROOT/'scripts/rehearse-image-release-codec.py')
codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)


class CodecTests(unittest.TestCase):
    def test_embedded_storage_contract_is_exact_source(self):
        self.assertEqual(codec.MOUNT_CONTRACT_SOURCE,(ROOT/'scripts/paired-mount-contract.py').read_text())

    def test_private_context_rejects_mutation_permissions_symlinks_and_extra_env(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'context';raw=json.dumps(codec.FIXTURE).encode();p.write_bytes(raw);p.chmod(0o600)
            digest=hashlib.sha256(raw).hexdigest()
            self.assertEqual(codec.read_context(p,digest),codec.FIXTURE)
            p.chmod(0o644)
            with self.assertRaises(codec.Refused):codec.read_context(p,digest)
            p.chmod(0o600);p.write_bytes(raw+b' ')
            with self.assertRaises(codec.Refused):codec.read_context(p,digest)
            values={**codec.FIXTURE,'LD_PRELOAD':'unapproved'};raw=json.dumps(values).encode();p.write_bytes(raw)
            with self.assertRaises(codec.Refused):codec.read_context(p,hashlib.sha256(raw).hexdigest())
            link=Path(td)/'link';link.symlink_to(p)
            with self.assertRaises(codec.Refused):codec.read_context(link,hashlib.sha256(raw).hexdigest())

    def test_literal_and_doubled_codecs_are_unambiguous_and_real_changes_reject(self):
        values=codec.prices(codec.FIXTURE)
        self.assertEqual(codec.codec_mode(values,values),'literal')
        doubled={k:v.replace('$','$$') for k,v in values.items()}
        self.assertEqual(codec.codec_mode(doubled,values),'doubled')
        doubled['PLAN_PRICE_PRO']='changed'
        with self.assertRaises(codec.Refused):codec.codec_mode(doubled,values)

    def probe(self):
        return {'Image':'fixed-image','Config':{'Labels':{'v79.codec.proof':'owned-nonce'},
                'Entrypoint':['/bin/true'],'Cmd':['__v79_probe_never_started__']},
                'State':{'Running':False,'StartedAt':'0001-01-01T00:00:00Z'},
                'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True},
                'Mounts':[{'Destination':'/proof'},{'Destination':'/data'}]}

    def test_only_owned_unstarted_networkless_readonly_scoped_probes_pass(self):
        codec.validate_probe(self.probe(),'fixed-image','owned-nonce')
        for target in ('owner','image','running','started_before','network','rootfs','entrypoint','ports','mounts'):
            row=self.probe()
            if target=='owner':row['Config']['Labels']['v79.codec.proof']='someone-else'
            elif target=='image':row['Image']='different'
            elif target=='running':row['State']['Running']=True
            elif target=='started_before':row['State']['StartedAt']='2025-01-01T00:00:00Z'
            elif target=='network':row['HostConfig']['NetworkMode']='host'
            elif target=='rootfs':row['HostConfig']['ReadonlyRootfs']=False
            elif target=='entrypoint':row['Config']['Entrypoint']=['node']
            elif target=='ports':row['HostConfig']['PortBindings']={'80/tcp':[{}]}
            else:row['Mounts'].append({'Destination':'/production'})
            with self.subTest(target=target),self.assertRaises(codec.Refused):codec.validate_probe(row,'fixed-image','owned-nonce')


if __name__=='__main__':unittest.main()
