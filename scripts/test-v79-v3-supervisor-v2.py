#!/usr/bin/env python3
"""Synthetic fresh-process supervisor regressions; never contacts Docker/systemd."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE=Path(__file__).resolve().parent
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path)
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def fixture(root):
 sup=load('sup',HERE/'v79_v3_hardened_hub_release_v2.py')
 engine=load('engine',HERE/'paired-compose-transaction.py')
 compat=load('compat',HERE/'vision79-v3-image-label-compat.py')
 sup.ROOT=root;sup.STATE=root/'state.json';sup.LOCK=root/'lock'
 baseline={'Id':'a'*64,'Image':sup.PRIOR,'HostConfig':{},'Mounts':[],
  'Config':{'Image':sup.PRIOR,'Env':['K=synthetic'],'Labels':{}},
  'State':{'Running':True,'Status':'running','Health':{'Status':'healthy'}}}
 entry={'baseline':baseline,'candidate_image':{'Id':sup.CANDIDATE,'Config':{}},
  'rollback_image':{'Id':sup.PRIOR,'Config':{}},'model':{'services':{'v79-hub':{'container_name':'v79-hub'}}},
  'service':'v79-hub','candidate_file':'candidate.json','rollback_file':'rollback.json','compose_version':'5.6.0'}
 plan={'apps':{'v79-hub':entry},'requires_supervision':True,'selinux_enabled':False,'protected':{}}
 class Backend:
  def __init__(self):self.root=root;self.plan=plan
  def inspect(self,name,allow_missing=False):
   return json.loads((root/'row.json').read_text()) if (root/'row.json').exists() else copy.deepcopy(baseline)
  def protected(self):pass
  def journal(self,*args):pass
  def verify(self,name,which,row=None):
   return engine.runtime_matches(baseline,row or self.inspect(name),entry,which,selinux_enabled=False)
  def switch(self,name,which):
   row=copy.deepcopy(baseline);row['Id']=('b' if which=='candidate' else 'c')*64
   pin=entry[which+'_image']['Id'];row['Image']=pin;row['Config']['Image']=pin
   row['Config']['Labels']={'com.docker.compose.image':compat.MAPPING[pin],
    'com.docker.compose.project.config_files':entry[which+'_file'],
    'com.docker.compose.version':'5.6.0','com.docker.compose.project.environment_file':'/dev/null',
    'com.docker.compose.config-hash':'d'*64,'com.docker.compose.replace':'v79-hub'}
   (root/'row.json').write_text(json.dumps(row))
   self.verify(name,which,row)
 backend=Backend()
 backend.supervised=types.MethodType(engine.ComposeBackend.supervised,backend)
 backend.healthy=types.MethodType(engine.ComposeBackend.healthy,backend)
 compat.install(engine);sup.bind_durable_context(backend,plan)
 sup.engine_plan=lambda:(engine,plan,backend)
 sup.prop=lambda unit,key:'active'
 sup.disarm=lambda:True
 return sup,engine,compat,backend,plan
def child(mode,root):
 sup,engine,compat,b,plan=fixture(root)
 if mode=='switch':
  sup.put({'phase':'WATCHDOG_ARMED','manifest_sha256':sup.MANIFEST,
           'deadline_epoch':time.time()+1200,'owner_accepted':False})
  with sup.heartbeat():b.switch('v79-hub','candidate');b.healthy('v79-hub','candidate')
  s=sup.state();s['phase']='OWNER_REVIEW_PENDING';sup.put(s)
  q=root/'supervision.json';q.write_text(json.dumps({'monotonic':time.monotonic()-60}));q.chmod(0o600)
  return
 if mode=='accept':return sup.accept(sorted(sup.REQUIRED))
 if mode=='expire':return sup.expire()
 raise AssertionError(mode)
class Tests(unittest.TestCase):
 def subprocess(self,mode,root):
  r=subprocess.run([sys.executable,'-B',__file__,'--child',mode,str(root)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_new_process_accepts_with_stale_old_lease(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);self.subprocess('switch',p);self.subprocess('accept',p)
   s=json.loads((p/'state.json').read_text());self.assertTrue(s['owner_accepted'])
   self.assertEqual(s['replacement_ids']['candidate'],'a'*64)
 def test_new_process_expiry_uses_original_rollback(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);self.subprocess('switch',p)
   s=json.loads((p/'state.json').read_text());s['deadline_epoch']=0
   (p/'state.json').write_text(json.dumps(s));self.subprocess('expire',p)
   s=json.loads((p/'state.json').read_text());self.assertEqual(s['phase'],'ROLLED_BACK')
   self.assertEqual(s['replacement_ids']['rollback'],'b'*64)
 def test_missing_context_is_denied(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);s,e,c,b,plan=fixture(p)
   s.put({'phase':'OWNER_REVIEW_PENDING','manifest_sha256':s.MANIFEST,'deadline_epoch':time.time()+1200})
   with self.assertRaisesRegex(s.Stop,'DURABLE_REPLACEMENT_ID_MISSING'):
    b.verify('v79-hub','candidate')
 def test_partial_attestation_denied(self):
  s=load('s',HERE/'v79_v3_hardened_hub_release_v2.py')
  with self.assertRaisesRegex(s.Stop,'FOUR_GENUINE_OWNER_CHECKS_REQUIRED'):s.accept(['--mfa-ok'])
 def test_expired_acceptance_denied(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);self.subprocess('switch',p);s,e,c,b,plan=fixture(p)
   d=s.state();d['deadline_epoch']=0;s.put(d)
   with self.assertRaisesRegex(s.Stop,'OWNER_ACCEPTANCE_DEADLINE_EXPIRED'):s.accept(sorted(s.REQUIRED))
 def test_wrong_replacement_name_denied(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);self.subprocess('switch',p);s,e,c,b,plan=fixture(p)
   r=b.inspect('v79-hub');r['Config']['Labels']['com.docker.compose.replace']='foreign'
   with self.assertRaisesRegex(c.Refused,'COMPOSE_REPLACEMENT_NAME_CHANGED'):b.verify('v79-hub','candidate',r)
 def test_foreign_image_and_environment_denied(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);self.subprocess('switch',p);s,e,c,b,plan=fixture(p)
   r=b.inspect('v79-hub');r['Image']='foreign'
   with self.assertRaisesRegex(c.Refused,'ACTUAL_IMAGE_IDENTITY_CHANGED'):b.verify('v79-hub','candidate',r)
   r=b.inspect('v79-hub');r['Config']['Env']=['K=changed']
   with self.assertRaisesRegex(e.Refused,'ACTUAL_ENVIRONMENT_CHANGED'):b.verify('v79-hub','candidate',r)
 def test_accepted_release_does_not_rollback(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);self.subprocess('switch',p);self.subprocess('accept',p);s,e,c,b,plan=fixture(p)
   with self.assertRaisesRegex(s.Stop,'ACCEPTED_RELEASE_NO_ROLLBACK'):s.expire()
 def test_switch_intent_durable_before_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);s,e,c,b,plan=fixture(p)
   s.put({'phase':'WATCHDOG_ARMED','manifest_sha256':s.MANIFEST})
   # Invalid codec fails original verification after durable ID is recorded.
   plan['apps']['v79-hub']['compose_version']='unsupported'
   with self.assertRaisesRegex(c.Refused,'UNREVIEWED_COMPOSE_REPLACEMENT_CODEC'):b.switch('v79-hub','candidate')
   self.assertEqual(s.state()['replacement_ids']['candidate'],'a'*64)
 def test_stopped_recreation_codec_and_hook_cleanup(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);sup,engine,compat,unused,plan=fixture(root)
   entry=plan['apps']['v79-hub'];name='v79profile'+'0'*16+'-0'
   model={'services':{'v79-hub':{'container_name':name}}}
   path=root/'probe.json';path.write_text(json.dumps(model))
   current=copy.deepcopy(entry);current['model']=model;current['candidate_file']=str(path)
   class ProbeBackend:
    def __init__(self):self.calls=0;self.row=None
    def inspect(self,n):return copy.deepcopy(self.row)
    def call(self,args,**kwargs):
     self.calls+=1;self.row=copy.deepcopy(entry['baseline'])
     self.row['Id']=('b' if self.calls==1 else 'c')*64
     self.row['Image']=sup.CANDIDATE
     self.row['State']={'Running':False,'StartedAt':'0001-01-01T00:00:00Z'}
     self.row['Config']['Image']=sup.CANDIDATE
     self.row['Config']['Labels']={'com.docker.compose.image':compat.MAPPING[sup.CANDIDATE],
      'com.docker.compose.project.config_files':str(path),'com.docker.compose.version':'5.6.0',
      'com.docker.compose.project.environment_file':'/dev/null','com.docker.compose.config-hash':'d'*64}
     if self.calls>1:self.row['Config']['Labels']['com.docker.compose.replace']=name
     return b''
   b=ProbeBackend();original=b.call
   def stopped(backend):
    backend.call(['docker','compose','--project-name',name,'-f',str(path),
     'up','--no-start','--no-deps','--no-build','--pull','never','v79-hub'])
    self.assertTrue(engine.runtime_matches(entry['baseline'],backend.inspect(name),current,
                    'candidate',selinux_enabled=False))
    return {'profiles_verified':1}
   engine.stopped_profiles=stopped
   self.assertEqual(compat.replacement_profiles(engine,b)['profiles_verified'],1)
   self.assertEqual(b.calls,2);self.assertEqual(b.call,original)
   self.assertEqual(engine._v79_profile_replacements,{})
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--child':
  result=child(sys.argv[2],Path(sys.argv[3]));print(json.dumps(result));sys.exit(0)
 unittest.main()
