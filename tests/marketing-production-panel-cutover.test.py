"""Exact UI-only scope, runtime preservation and durable failure boundaries."""
import copy
import datetime
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

SOURCE=Path(__file__).resolve().parents[1]/'scripts/marketing-production-panel-cutover.py'

def load():
    s=importlib.util.spec_from_file_location('ui_cutover',SOURCE)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


class UiCutoverTests(unittest.TestCase):
    def setUp(self): self.m=load()

    def runtime(self, name='v79-hub'):
        m=self.m;old={'Id':'a'*64,'Image':m.OLD_IMAGE,'Config':{'Image':m.OLD_IMAGE,'Hostname':'a'*12,'User':'',
            'Cmd':['tsx','server.ts'],'Env':['NODE_ENV=production','AUDIT_KEY=preserved'], 'Labels':{
                'com.docker.compose.project.config_files':','.join(m.FILES),'com.docker.compose.image':'old-bookkeeping',
                'org.opencontainers.image.revision':'c42f671f4ccd4b268f6701989cceba0ba27b5dbd', 'com.docker.compose.service':name}},
            'HostConfig':{'Memory':0,'Binds':['protected:/run/secrets/token:ro']},'Mounts':[],
            'NetworkSettings':{'Networks':{'proxy_network':{}}},'State':{'Running':True,'StartedAt':'old','Health':{'Status':'healthy'}}}
        new=copy.deepcopy(old);new.update(Id='b'*64,Image=m.IMAGE);new['Config'].update(Image=m.IMAGE,Hostname='b'*12)
        new['Config']['Labels'].update({'com.docker.compose.project.config_files':','.join(m.FILES+[str(m.WORK/'ui-image.yml')]),
            'com.docker.compose.image':'new-bookkeeping','org.opencontainers.image.revision':m.COMMIT})
        return old,new

    def test_resolved_configuration_allows_only_the_exact_hub_image(self):
        m=self.m;old={'services':{'v79-hub':{'image':m.OLD_IMAGE,'environment':{'publication':'0','audit':'preserved'},'volumes':['data']},'db':{'image':'db'}}}
        new=copy.deepcopy(old);new['services']['v79-hub']['image']=m.IMAGE;m.parity(old,new)
        for field in ('environment','volumes','image','unrelated'):
            bad=copy.deepcopy(new)
            if field=='unrelated':bad['services']['db']['image']='changed'
            elif field=='environment':bad['services']['v79-hub'][field]['publication']='1'
            else:bad['services']['v79-hub'][field]='changed'
            with self.assertRaises(RuntimeError):m.parity(old,bad)

    def test_runtime_changes_are_limited_to_image_provenance_and_generated_hostname(self):
        m=self.m;m.helper={'healthy':lambda x:x['State']['Health']['Status']=='healthy','mounts':lambda x:x['Mounts']}
        old,new=self.runtime();m.runtime_parity(old,new,None)
        for field in ('Env','Cmd','User','Hostname'):
            bad=copy.deepcopy(new);bad['Config'][field]='changed'
            with self.assertRaises(RuntimeError):m.runtime_parity(old,bad,None)
        bad=copy.deepcopy(new);bad['HostConfig']['Memory']=1
        with self.assertRaises(RuntimeError):m.runtime_parity(old,bad,None)
        old['Config']['Hostname']=new['Config']['Hostname']='explicit';m.runtime_parity(old,new,'explicit')
        new['Config']['Hostname']='different'
        with self.assertRaises(RuntimeError):m.runtime_parity(old,new,'explicit')

    def test_success_and_failures_do_not_retry_or_rollback_or_recreate_other_services(self):
        for failure in (None,'config','restart','data'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                m=load();root=Path(directory);m.BUILD=root/'build';m.BUILD.mkdir();m.WORK=root/'cutover'
                m.FILES=[str(root/'base.yml')];Path(m.FILES[0]).write_text('original compose')
                m.HELPERS=['builder','support']
                old,new=self.runtime();old['Config']['Labels']['com.docker.compose.project.config_files']=','.join(m.FILES)
                old['Config']['Labels'].update({'com.docker.compose.project':'v79-hub','com.docker.compose.service':'v79-hub','com.docker.compose.project.working_dir':'/opt/v79/hub'})
                new=copy.deepcopy(old);new.update(Id='b'*64,Image=m.IMAGE);new['Config'].update(Image=m.IMAGE,Hostname='b'*12)
                new['Config']['Labels'].update({'com.docker.compose.project.config_files':','.join(m.FILES+[str(m.WORK/'ui-image.yml')]),'com.docker.compose.image':'new','org.opencontainers.image.revision':m.COMMIT})
                before={'id':'accepted'};calls=[];switched=False
                receipt={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate':{'commit':m.COMMIT,'tree':m.TREE,'image':m.IMAGE,'tag':'v79-hub-g3-ui:8d82b21a4def'},'deploymentPerformed':False,'isolatedTestsPassed':True,'sourceScopeVerified':True,'testEnvironment':'test','liveRuntime':before}
                (m.BUILD/'ui-build-receipt.json').write_text(json.dumps(receipt))
                config={'services':{'v79-hub':{'image':m.OLD_IMAGE,'environment':{'publication':'0','audit':'same'}}}}
                def inspect(name):return copy.deepcopy(new if name=='v79-hub' and switched else old)
                def run(args, data=None, **kwargs):
                    nonlocal switched
                    calls.append(args)
                    if args[:3]==['docker','image','inspect']:return json.dumps([{'Id':m.IMAGE,'Config':{'Labels':{'org.opencontainers.image.revision':m.COMMIT}}}]).encode()
                    if 'config' in args:
                        result=copy.deepcopy(config)
                        if str(m.WORK/'ui-image.yml') in args:
                            result['services']['v79-hub']['image']=m.IMAGE
                            if failure=='config':result['services']['v79-hub']['environment']['publication']='1'
                        return json.dumps(result).encode()
                    if 'up' in args:
                        self.assertTrue((m.WORK/'switch-attempted.json').is_file());self.assertTrue((m.WORK/'manifest.json').is_file())
                        self.assertEqual(args[-1],'v79-hub');self.assertIn('--no-deps',args);self.assertIn('--no-build',args)
                        self.assertEqual(args[args.index('--pull')+1],'never');switched=True
                        if failure=='restart':raise RuntimeError('Synthetic restart error')
                        return b''
                    if args[0]=='gpg':Path(args[args.index('--output')+1]).write_bytes(b'encrypted');return b''
                    if args[:2]==['docker','exec'] and data==m.MARKETING_STATE.encode():return b'signed-campaign-digest'
                    if args[:2]==['docker','exec'] and data and b'PINNED_UI_ASSET_SERVED_PASS' in data:return b'PINNED_UI_ASSET_SERVED_PASS'
                    if args[0]=='tar' or 'pg_dump' in args:return b'captured backup'
                    raise AssertionError('Unexpected command: '+repr(args))
                def write_json(path,value):
                    with Path(path).open('x') as f:json.dump(value,f)
                support={'run':run,'file_hash':lambda p,*a:'hash-'+str(p),'inspect':inspect,'protected_state':lambda db:'changed' if failure=='data' and switched else 'protected-hub',
                    'sqlite_state':lambda name:{'digest':'protected-marketing'},'write_json':write_json,'healthy':lambda x:True,
                    'stable_runtime':lambda x:x,'mounts':lambda x:x['Mounts'],'probe_live':lambda:None}
                builder={'NAMES':('v79-hub','v79marketing-app'),'snapshot':lambda:before,'verify_checkout_scope':lambda p:None}
                with patch.object(m,'load_helper',side_effect=[builder,support]),patch.object(m.socket,'gethostname',return_value='v79sl'),patch.object(m.os,'getuid',return_value=1000),patch.object(m.pwd,'getpwuid',return_value=SimpleNamespace(pw_name='firelion')),redirect_stdout(io.StringIO()):
                    if failure:
                        with self.assertRaises(RuntimeError):m.main()
                    else:m.main()
                switches=[c for c in calls if 'up' in c]
                self.assertEqual(len(switches),0 if failure=='config' else 1)
                self.assertEqual((m.WORK/'deployed.json').exists(),failure is None)
                self.assertEqual(m.attempted,failure!='config')
                self.assertEqual(Path(m.FILES[0]).read_text(),'original compose')
                if failure is None:
                    result=json.loads((m.WORK/'deployed.json').read_text());self.assertFalse(result['publicationEnabled']);self.assertTrue(result['campaignPackagesPreserved'])
                    self.assertEqual(len(list(m.WORK.glob('*.gpg'))),3)


if __name__=='__main__':unittest.main()
