#!/usr/bin/env python3
"""Real candidate/recreated-rollback using only disposable synthetic CI apps."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
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
                run(['docker','build','-t',tag,'-'],input=dockerfile.encode())
            old,new=[json.loads(run(['docker','image','inspect',tag]))[0] for tag in tags]
            data=root/'data';data.mkdir();(data/'sentinel').write_text('unchanged synthetic data')
            names={service:project+'-'+service for service in ('hub','tiquet','db')}
            services={}
            for service,name in names.items():
                services[service]={'image':old['Id'],'container_name':name,
                    'command':['sh','-c',"trap 'exit 0' TERM; while :; do sleep 1; done"],
                    'environment':{'PRICE':'$${literal} $$$$\nline two'},
                    'volumes':[str(data)+':/data:ro'],'read_only':True,'network_mode':'none',
                    'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
                    'healthcheck':{'test':['CMD','test','-f','/data/sentinel'],
                                   'interval':'1s','timeout':'1s','retries':10},
                    'restart':'unless-stopped'}
            services['hub']['depends_on']={'db':{'condition':'service_started'}}
            services['tiquet']['depends_on']={'db':{'condition':'service_started'}}
            initial=root/'initial.json';initial.write_text(json.dumps({'services':services}));initial.chmod(0o600)
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
                result=m.deploy(backend)
                self.assertEqual(result['status'],'PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING')
                self.assertEqual((data/'sentinel').read_text(),'unchanged synthetic data')
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
                self.assertEqual(json.loads(run(['docker','inspect',names['db']]))[0]['Id'],before[names['db']]['Id'])
                self.assertEqual((data/'sentinel').read_text(),'unchanged synthetic data')
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


if __name__=='__main__':unittest.main()
