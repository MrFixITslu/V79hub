#!/usr/bin/env python3
"""Pure regression tests: async Docker cleanup and original failure preservation."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

P=Path(__file__).parents[1]/'scripts'
def module(name):
    spec=importlib.util.spec_from_file_location('demo_'+name.replace('-','_'),P/name)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

class CleanupBackend:
    def __init__(self,root,started_mismatch=False):
        self.root=root
        self.volumes={}
        self.probes={}
        self.remove_wait={}
        self.events=[]
        self.started_mismatch=started_mismatch
        origin='sha256:'+'f'*64
        image='sha256:'+'e'*64
        base={
          'Mounts':[{'Type':'volume','Destination':'/data','Name':'synthetic-orig',
                      'Driver':'local','Source':'/not-real'}],
          'HostConfig':{'Binds':None,'Mounts':[]},
          'Config':{'Labels':{'com.docker.compose.project':'original'}},
          'Name':'/original'}
        model={'services':{'app':{'volumes':[{'type':'volume','source':'localdata',
                                            'target':'/data'}]}},
               'volumes':{'localdata':{'name':'synthetic-orig','external':True}}}
        entry={'baseline':base,'model':model,'service':'app',
               'directory':str(root),'project':'original',
               'candidate_file':str(root/'candidate.json'),
               'rollback_file':str(root/'rollback.json'),
               'candidate_image':{'Id':image},
               'rollback_image':{'Id':origin}}
        for which in ('candidate','rollback'):
            (root/(which+'.json')).write_text(json.dumps(model))
        self.plan={'apps':{'v79-hub':entry},'selinux_enabled':False}
    def supervised(self):pass
    def protected(self):pass
    def check_files(self):pass
    def journal(self,event,name=None,reason=None):
        self.events.append((event,name,reason))
    def call(self,args,**kwargs):
        if args[:3]==['docker','volume','create']:
            volume=args[-1]
            scope=args[-2].split('=',1)[1]
            self.volumes[volume]={'Name':volume,'Labels':{'v79.profile.scope':scope},
                                  'Mountpoint':'/synthetic-volume/'+volume}
            return volume.encode()
        if args[:3]==['docker','volume','inspect']:
            return json.dumps([self.volumes[args[-1]]]).encode()
        if args[:3]==['docker','volume','rm']:
            del self.volumes[args[-1]]
            return b''
        if args[:3]==['docker','ps','--all']:
            # all test containers disappeared before detach check; no foreign attachment
            return b''
        if args[:2]==['docker','rm']:
            target=args[2]
            for probe,row in self.probes.items():
                if row['Id']==target:
                    self.remove_wait[probe]=1
                    raise M.Refused('COMMAND_OUTCOME_REQUIRES_ROLLBACK')
        raise AssertionError(str(args))
    def inspect(self,name,*,allow_missing=False):
        if name in self.remove_wait:
            if self.remove_wait[name]>0:
                self.remove_wait[name]-=1
                return self.probes[name]
            return None
        return self.probes.get(name)
    def compose(self,args,**kwargs):
        path=Path(args[args.index('-f')+1])
        model=json.loads(path.read_text())
        spec=model['services']['app']
        name=spec['container_name']
        # Only the first candidate test is exercised by this failure-case test.
        image=self.plan['apps']['v79-hub']['candidate_image']['Id']
        if name not in self.probes:
            self.probes[name]={'Id':'container-'+name,'Name':'/'+name,
               'Image':image,'State':{'Running':False,'StartedAt':'0001-01-01'},
               'Config':{'Labels':{'com.docker.compose.project':name}}}
        if self.started_mismatch:
            # Attribute the actual compatibility error, independently of cleanups.
            raise M.Refused('PROFILE_RUNTIME_TEST_ERROR')
        return SimpleNamespace(returncode=0,stderr=b'')

M=module('paired-compose-transaction-demo-v4.py')
class TestEventualCleanup(unittest.TestCase):
    def test_container_removal_timeout_then_disappearance_does_not_leak_volume(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);root.chmod(0o700)
            backend=CleanupBackend(root)
            # First test only: make runtime matching stop with an exact refusal.
            with patch.object(M.subprocess,'run',side_effect=backend.compose), \
                 patch.object(M,'runtime_matches',side_effect=M.Refused('PROFILE_EXPECTED_MISMATCH')), \
                 patch.object(M.time,'sleep'):
                with self.assertRaisesRegex(M.Refused,'PROFILE_EXPECTED_MISMATCH'):
                    M.stopped_profiles(backend)
            self.assertFalse(backend.volumes)
            self.assertFalse(any(p.name.startswith('v79profile') for p in root.iterdir()
                                 if p.is_dir()))
            self.assertIn(('PROFILE_PRIMARY_FAILED','v79-hub','PROFILE_EXPECTED_MISMATCH'),backend.events)
            self.assertTrue(any(x[0]=='PROFILE_CONTAINER_REMOVE_AMBIGUOUS' for x in backend.events))
            self.assertFalse(any(x[0]=='PROFILE_OWNED_CLEANUP_INCOMPLETE' for x in backend.events))

    def test_v7_keeps_v6_noncleanup_guards(self):
        v7=module('release-hardened-pair-demo-v7.py')
        v6=module('release-hardened-pair-demo-v6.py')
        self.assertEqual(v7.SOURCES['paired-compose-transaction.py'],
                         (P/'paired-compose-transaction-demo-v4.py').read_text())
        for name,source in v6.SOURCES.items():
            if name!='paired-compose-transaction.py':
                self.assertEqual(v7.SOURCES[name],source)
        import ast
        old=ast.parse((P/'paired-compose-transaction-demo-v3.py').read_text())
        new=ast.parse((P/'paired-compose-transaction-demo-v4.py').read_text())
        functions=lambda tree:{x.name:ast.dump(x,include_attributes=False)
                               for x in tree.body if isinstance(x,ast.FunctionDef)}
        original=functions(old);latest=functions(new)
        self.assertEqual(original.keys(),latest.keys())
        for func in ('rollback','deploy','runtime_matches','protected_fingerprint'):
            self.assertEqual(original[func],latest[func])
        self.assertIsNone(v7.CHECKPOINT)
        self.assertEqual(v7.INNER_BYTES,204488782)

if __name__=='__main__':unittest.main()
