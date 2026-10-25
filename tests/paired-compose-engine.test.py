#!/usr/bin/env python3
"""Real candidate/recreated-rollback using only disposable synthetic CI apps."""
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import tarfile
import unittest
import uuid

spec=importlib.util.spec_from_file_location('transaction',
    Path(__file__).parents[1]/'scripts/paired-compose-transaction.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def run(args,**kwargs):
    return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=180,**kwargs)


class RealCompose(unittest.TestCase):
    def test_image_switch_and_durable_rollback_preserve_data_and_dependency(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true','Run only on disposable GitHub CI')
        self.assertNotEqual(socket.gethostname(),'v79sl')
        with tempfile.TemporaryDirectory(prefix='v79-transaction-') as temp:
            root=Path(temp);project='v79tx'+uuid.uuid4().hex[:12]
            tags=[project+':old',project+':new']
            for tag,stage in zip(tags,('old','new')):
                dockerfile=('FROM alpine:3.24\nLABEL org.opencontainers.image.revision='+stage+'\n'
                    +('ENV NODE_VERSION=synthetic YARN_VERSION=synthetic\n' if stage=='old' else ''))
                run(['docker','build','--provenance=false','--output','type=docker,oci-mediatypes=true',
                     '-t',tag,'-'],input=dockerfile.encode())
            old,new=[json.loads(run(['docker','image','inspect',tag]))[0] for tag in tags]
            data=root/'data';data.mkdir();(data/'sentinel').write_text('unchanged synthetic data')
            token=root/'token';token.write_text('synthetic-file-secret-only');token.chmod(0o600)
            names={service:project+'-'+service for service in ('hub','tiquet','db')}
            services={}
            for service,name in names.items():
                services[service]={'image':old['Id'],'container_name':name,
                    'command':['sh','-c',"test -f /ledger/sentinel || printf durable > /ledger/sentinel; trap 'exit 0' TERM; while :; do sleep 1; done"],
                    'environment':{'PRICE':'$${literal} $$$$\nline two'},
                    'volumes':[str(data)+':/data:ro','ledger:/ledger'],'read_only':True,
                    'networks':{'isolated':{}},
                    'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
                    'healthcheck':{'test':['CMD','test','-f','/data/sentinel'],
                                   'interval':'1s','timeout':'1s','retries':10},
                    'restart':'unless-stopped'}
                services[service]['secrets']=[{'source':'operator-token'}]
            services['hub']['depends_on']={'db':{'condition':'service_started'}}
            services['tiquet']['depends_on']={'db':{'condition':'service_started'}}
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
            services['hub']['ports']=['127.0.0.1:'+str(port)+':8080']
            initial=root/'initial.json';initial.write_text(json.dumps({'services':services,
                'volumes':{'ledger':{'name':project+'-ledger'}},
                'secrets':{'operator-token':{'file':str(token)}},
                'networks':{'isolated':{'name':project+'-network','internal':True}}}));initial.chmod(0o600)
            args=['docker','compose','--project-name',project,'--project-directory',str(root),'-f',str(initial)]
            try:
                run([*args,'up','-d','--wait','--wait-timeout','30','--no-build','--pull','never'])
                before={n:json.loads(run(['docker','inspect',n]))[0] for n in names.values()}
                model=json.loads(run([*args,'config','--format','json']))
                all_names=run(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
                all_rows={n:json.loads(run(['docker','inspect',n]))[0] for n in all_names}
                app_names=[names['hub'],names['tiquet']]
                plan={'apps':{},'selinux_enabled':False,
                      'protected':{n:r for n,r in all_rows.items() if n not in app_names}}
                for service in ('hub','tiquet'):
                    name=names[service]
                    entry={'project':project,'service':service,'directory':str(root),
                        'model':model,'baseline':before[name],
                        'rollback_image':old,'candidate_image':new,
                        'removed_metadata':['NODE_VERSION','YARN_VERSION'],
                        'compose_version':run(['docker','compose','version','--short']).decode().strip().removeprefix('v')}
                    for which,image in (('candidate',new),('rollback',old)):
                        rendered=copy.deepcopy(model);rendered['services'][service]['image']=image['Id']
                        path=root/(service+'-'+which+'.json')
                        path.write_text(json.dumps(rendered));path.chmod(0o600)
                        entry[which+'_file']=str(path)
                        entry[which+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                    plan['apps'][name]=entry
                pin=m.seal_plan(root,plan)
                backend=m.ComposeBackend(root,m.load_plan(root,pin))
                profiles=m.stopped_profiles(backend)
                self.assertEqual(profiles['profiles_verified'],4)
                self.assertTrue(profiles['temporary_resource_cleanup_verified'])
                self.assertFalse(list(root.glob('v79profile*')))
                result=m.deploy(backend)
                self.assertEqual(result['status'],'PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING')
                self.assertEqual((data/'sentinel').read_text(),'unchanged synthetic data')
                self.assertEqual(run(['docker','exec',names['hub'],'cat','/ledger/sentinel']),b'durable')
                # A completely new process reads only the sealed durable plan.
                child='''import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('t',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
p=m.load_plan(Path(sys.argv[2]),sys.argv[3]);b=m.ComposeBackend(Path(sys.argv[2]),p)
result=m.rollback(b,list(p['apps']));assert result['status']=='PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED'
'''
                run([sys.executable,'-c',child,str(Path(m.__file__).resolve()),str(root),pin])
                for name in app_names:
                    now=json.loads(run(['docker','inspect',name]))[0]
                    self.assertEqual(now['Image'],old['Id']);self.assertNotEqual(now['Id'],before[name]['Id'])
                # Inject failure only AFTER the real second candidate create.
                # Automatic rollback must recover the healthy first app and
                # the never-started second app without changing the dependency.
                class FailAfterSecondCreate(m.ComposeBackend):
                    injected=False
                    def call(self,args,**kwargs):
                        result=super().call(args,**kwargs)
                        if (not self.injected and 'up' in args
                                and plan['apps'][names['tiquet']]['candidate_file'] in args):
                            self.injected=True
                            raise m.Refused('INJECTED_AFTER_ACTUAL_CREATION')
                        return result
                failure=m.deploy(FailAfterSecondCreate(root,m.load_plan(root,pin)))
                self.assertEqual(failure['status'],'PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED')
                self.assertTrue(failure['candidate_deployment_failed'])
                for name in app_names:
                    self.assertEqual(json.loads(run(['docker','inspect',name]))[0]['Image'],old['Id'])
                self.assertEqual(json.loads(run(['docker','inspect',names['db']]))[0]['Id'],before[names['db']]['Id'])
                self.assertEqual((data/'sentinel').read_text(),'unchanged synthetic data')
                self.assertEqual(run(['docker','exec',names['tiquet'],'cat','/ledger/sentinel']),b'durable')
                # Exercise the corrected transport against a real Docker image
                # archive too, not just a synthetic byte stream.
                resume_spec=importlib.util.spec_from_file_location('resume',
                    Path(__file__).parents[1]/'scripts/resume-hardened-pair.py')
                resume=importlib.util.module_from_spec(resume_spec);resume_spec.loader.exec_module(resume)
                packed=gzip.compress(run(['docker','image','save',new['Id']]),compresslevel=1)
                offset=max(1,len(packed)-1065038);partial=root/'synthetic-partial.tar.gz'
                partial.write_bytes(packed[:offset]);partial.chmod(0o600)
                import io
                count=resume.complete_transfer(partial,io.BytesIO(packed[offset:]),
                    expected_size=len(packed),expected_sha256=hashlib.sha256(packed).hexdigest(),
                    offset=offset,prefix_sha256=hashlib.sha256(packed[:offset]).hexdigest())
                self.assertEqual(count,len(packed)-offset)
                run(['docker','image','load','--input',str(partial)])
                self.assertEqual(json.loads(run(['docker','image','inspect',new['Id']]))[0]['Id'],new['Id'])
                store=json.loads(run(['docker','info','--format','{{json .DriverStatus}}']))
                if any('containerd' in str(item) for item in store):
                    binder_spec=importlib.util.spec_from_file_location('binder',
                        Path(__file__).parents[1]/'scripts/continue-manifest-bound-pair.py')
                    binder=importlib.util.module_from_spec(binder_spec);binder_spec.loader.exec_module(binder)
                    metadata={}
                    with tarfile.open(fileobj=io.BytesIO(packed),mode='r|gz') as archive:
                        for member in archive:
                            if member.isfile() and member.name.startswith('blobs/sha256/') and member.size<1024**2:
                                raw=archive.extractfile(member).read()
                                try:value=json.loads(raw)
                                except (ValueError,UnicodeError):continue
                                metadata['sha256:'+hashlib.sha256(raw).hexdigest()]=value
                    manifest=metadata[new['Id']];config_id=manifest['config']['digest']
                    self.assertNotEqual(config_id,new['Id'])
                    bindings={name:{'config':config_id,'manifest':new['Id'],'revision':'new'} for name in app_names}
                    configs=binder.verify_archive(partial,hashlib.sha256(packed).hexdigest(),bindings)
                    api=type('API',(),{'call':staticmethod(lambda args:run(args))})()
                    binder.verify_loaded(api,bindings,configs)
                    legacy=copy.deepcopy(plan)
                    for name,entry in legacy['apps'].items():
                        entry['model']=json.loads(Path(entry['candidate_file']).read_bytes())
                        entry['candidate_image']['Id']=config_id
                        entry['model']['services'][entry['service']]['image']=config_id
                    bound=binder.project_plan(legacy,root,bindings)
                    for entry in bound['apps'].values():
                        path=Path(entry['candidate_file']);path.write_bytes(binder.model_bytes(entry['model']));path.chmod(0o600)
                    result=m.deploy(m.ComposeBackend(root,bound))
                    self.assertEqual(result['status'],'PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING')
                    proof=root/'binding-plan.json';proof.write_text(json.dumps(bound));proof.chmod(0o600)
                    bound_child='''import importlib.util,sys,json,hashlib
from pathlib import Path
s=importlib.util.spec_from_file_location('t',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raw=Path(sys.argv[2]).read_bytes();assert hashlib.sha256(raw).hexdigest()==sys.argv[3]
p=json.loads(raw);b=m.ComposeBackend(Path(sys.argv[4]),p)
assert m.rollback(b,list(p['apps']))['status']=='PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED'
'''
                    run([sys.executable,'-c',bound_child,str(Path(m.__file__).resolve()),str(proof),
                         hashlib.sha256(proof.read_bytes()).hexdigest(),str(root)])
                    self.assertEqual(json.loads(run(['docker','inspect',names['db']]))[0]['Id'],before[names['db']]['Id'])
                    self.assertEqual(run(['docker','exec',names['hub'],'cat','/ledger/sentinel']),b'durable')
            finally:
                # Only exact synthetic fixture containers; never remove volumes.
                for name in names.values():
                    result=subprocess.run(['docker','inspect',name],capture_output=True,timeout=20)
                    if result.returncode:continue
                    row=json.loads(result.stdout)[0]
                    self.assertIn(row['Image'],(old['Id'],new['Id']))
                    self.assertEqual(row['Config']['Labels']['com.docker.compose.project'],project)
                    subprocess.run(['docker','stop','--time','5',row['Id']],capture_output=True,timeout=15,check=True)
                    run(['docker','rm',row['Id']])
                volume=project+'-ledger'
                result=subprocess.run(['docker','volume','inspect',volume],capture_output=True,timeout=20)
                if result.returncode==0:
                    info=json.loads(result.stdout)[0]
                    self.assertEqual((info.get('Labels') or {}).get('com.docker.compose.project'),project)
                    run(['docker','volume','rm',volume])
                network=project+'-network'
                result=subprocess.run(['docker','network','inspect',network],capture_output=True,timeout=20)
                if result.returncode==0:
                    info=json.loads(result.stdout)[0]
                    self.assertEqual((info.get('Labels') or {}).get('com.docker.compose.project'),project)
                    run(['docker','network','rm',network])


if __name__=='__main__':unittest.main()
