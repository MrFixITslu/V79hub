#!/usr/bin/env python3
"""Read-only current Hub Compose/runtime parity gate. No secret values in output.

This checks selected high-risk fields; it is not a complete Docker runtime proof.
Only a sealed candidate rehearsal can establish full replacement parity.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

HUB = 'v79-hub'
IMAGE = 'sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4'
COMPOSE_SHA = '2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083'

class Stop(Exception): pass

def call(args, cwd=None):
    try:
        p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired): raise Stop('READ_ONLY_COMMAND_UNAVAILABLE') from None
    if p.returncode or len(p.stdout) > 16*1024*1024: raise Stop('READ_ONLY_COMMAND_FAILED')
    return p.stdout

def one(args, cwd=None):
    try: rows = json.loads(call(args,cwd))
    except (ValueError,UnicodeDecodeError): raise Stop('INVALID_INSPECTION_JSON') from None
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict): raise Stop('INVALID_INSPECTION_SHAPE')
    return rows[0]

def env(rows):
    result={}
    for row in rows or []:
        if not isinstance(row,str) or '=' not in row: raise Stop('ENV_SHAPE_INVALID')
        key,value=row.split('=',1)
        if key in result: raise Stop('DUPLICATE_ENV_KEY')
        result[key]=value
    return result

def compare(actual,image,rendered):
    service=(rendered.get('services') or {}).get('v79-hub')
    if not isinstance(service,dict): raise Stop('COMPOSE_SERVICE_MISSING')
    if actual.get('Image')!=IMAGE or image.get('Id')!=IMAGE: raise Stop('IMAGE_DRIFT')
    if actual.get('State',{}).get('Status')!='running' or actual.get('State',{}).get('Health',{}).get('Status')!='healthy': raise Stop('HUB_UNHEALTHY')
    if service.get('image') and one_image_reference(service['image'],image) is False: raise Stop('COMPOSE_IMAGE_DRIFT')
    configured=service.get('environment') or {}
    if not isinstance(configured,dict): raise Stop('COMPOSE_ENV_SHAPE_INVALID')
    expected=env((image.get('Config') or {}).get('Env'))
    expected.update({k:str(v) for k,v in configured.items() if v is not None})
    if env((actual.get('Config') or {}).get('Env'))!=expected: raise Stop('ENVIRONMENT_PARITY_FAILED')
    mounts={m.get('Destination'):m for m in actual.get('Mounts') or []}
    volumes=service.get('volumes') or []
    if len(mounts)!=len(volumes) or len(mounts)!=len(actual.get('Mounts') or []): raise Stop('MOUNT_COUNT_DRIFT')
    for v in volumes:
        target=v.get('target'); m=mounts.get(target)
        if not m or v.get('type')!=m.get('Type') or bool(v.get('read_only',False))==bool(m.get('RW')): raise Stop('MOUNT_PARITY_FAILED')
        source=v.get('source')
        if v.get('type')=='volume': source=(rendered.get('volumes') or {}).get(source,{}).get('name',source)
        observed=m.get('Name') if v.get('type')=='volume' else m.get('Source')
        if source!=observed: raise Stop('MOUNT_SOURCE_PARITY_FAILED')
    networks=(actual.get('NetworkSettings') or {}).get('Networks') or {}
    configured_networks=service.get('networks') or {}
    if isinstance(configured_networks,list): configured_networks={name:{} for name in configured_networks}
    names={((rendered.get('networks') or {}).get(name) or {}).get('name',name) for name in configured_networks}
    if names!=set(networks): raise Stop('NETWORK_MEMBERSHIP_DRIFT')
    host=actual.get('HostConfig') or {}
    if host.get('PortBindings'): raise Stop('UNEXPECTED_PUBLISHED_PORTS')
    return {'schema':'vision79-v3-compose-parity','result':'PASS_SELECTED_RUNTIME_PARITY',
            'checks':['image','health','resolved_environment','mount_type_source_mode','network_membership','no_published_ports'],
            'full_runtime_parity_verified':False,'production_changes':'NONE','release_gate':'HOLD'}

def one_image_reference(reference,image):
    return reference==IMAGE or reference in (image.get('RepoTags') or []) or reference in (image.get('RepoDigests') or [])

def collect():
    if socket.gethostname().split('.')[0]!='v79sl': raise Stop('WRONG_HOST')
    if os.getenv('DOCKER_HOST') or os.getenv('DOCKER_CONTEXT'): raise Stop('DOCKER_OVERRIDE_REFUSED')
    actual=one(['docker','inspect','--type','container',HUB]);image=one(['docker','inspect','--type','image',IMAGE])
    labels=(actual.get('Config') or {}).get('Labels') or {}
    files=labels.get('com.docker.compose.project.config_files','').split(',')
    if len(files)!=1 or not Path(files[0]).is_absolute() or Path(files[0]).name!='hub-candidate.json': raise Stop('COMPOSE_CHAIN_DRIFT')
    p=Path(files[0]); working=labels.get('com.docker.compose.project.working_dir','')
    project=labels.get('com.docker.compose.project','')
    if not project or not working or not p.is_file() or p.is_symlink() or p.stat().st_size>2_000_000: raise Stop('COMPOSE_INPUT_INVALID')
    if hashlib.sha256(p.read_bytes()).hexdigest()!=COMPOSE_SHA: raise Stop('COMPOSE_INPUT_DRIFT')
    args=['docker','compose','--project-directory',working,'--project-name',project,'-f',str(p),'config','--format','json']
    try: rendered=json.loads(call(args,cwd=working))
    except (ValueError,UnicodeDecodeError): raise Stop('COMPOSE_RENDER_INVALID') from None
    result=compare(actual,image,rendered)
    again=one(['docker','inspect','--type','container',HUB])
    if actual.get('Id')!=again.get('Id') or actual.get('Image')!=again.get('Image') or hashlib.sha256(p.read_bytes()).hexdigest()!=COMPOSE_SHA: raise Stop('BASELINE_CHANGED_DURING_CHECK')
    return result

class Tests(unittest.TestCase):
    def test_wrong_host_no_commands(self):
        with patch('socket.gethostname',return_value='other'),patch(__name__+'.call') as command:
            with self.assertRaises(Stop): collect()
            command.assert_not_called()
    def test_env_duplicate(self):
        with self.assertRaises(Stop): env(['A=1','A=2'])
    def test_only_allowlisted_output(self):
        image={'Id':IMAGE,'Config':{'Env':['SECRET=private']},'RepoTags':['hub:test']}
        row={'Image':IMAGE,'State':{'Status':'running','Health':{'Status':'healthy'}},'Config':{'Env':['SECRET=private']},
             'Mounts':[{'Destination':'/app/data','Type':'bind','Source':'/private/data','RW':True}],
             'NetworkSettings':{'Networks':{'proxy_network':{}}},'HostConfig':{}}
        model={'services':{'v79-hub':{'image':'hub:test','environment':{},'volumes':[{'target':'/app/data','source':'/private/data','type':'bind'}],
                 'networks':{'proxy':{}}}},'networks':{'proxy':{'name':'proxy_network'}}}
        result=compare(row,image,model)
        self.assertNotIn('private',json.dumps(result));self.assertFalse(result['full_runtime_parity_verified'])
        model['services']['v79-hub']['volumes'][0]['source']='/wrong'
        with self.assertRaises(Stop): compare(row,image,model)

def main():
    if len(sys.argv)!=2 or sys.argv[1] not in ('--run','--self-test'): raise Stop('MODE_REQUIRED')
    if sys.argv[1]=='--self-test':
        result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
        return 0 if result.wasSuccessful() else 1
    print(json.dumps(collect(),sort_keys=True));return 0

if __name__=='__main__':
    try: sys.exit(main())
    except Stop as exc:
        print(json.dumps({'result':'STOP','reason':str(exc),'production_changes':'NONE','release_gate':'HOLD'}));sys.exit(3)
    except Exception:
        print(json.dumps({'result':'STOP','reason':'REDACTED_ERROR','production_changes':'NONE','release_gate':'HOLD'}));sys.exit(3)
