#!/usr/bin/env python3
"""Narrow, pinned Compose image bookkeeping normalization; no cutover CLI."""
import copy
import hashlib
import http.client
import importlib.util
import json
import re
import socket
from pathlib import Path

ROOT=Path('/home/firelion/v79-v3-hardened-hub-manifest-20261026')
MAPPING={
 'sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6':
 'sha256:bf5bf4424c1cb860e099441799653ea0586874d82b6a6b71e3737faa93f07254',
 'sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4':
 'sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4',
}
LABEL='com.docker.compose.image'
class Refused(ValueError): pass
def require(ok,code):
 if not ok: raise Refused(code)
def validate_image(row,pin):
 require(pin in MAPPING and row.get('Id')==pin,'IMAGE_TOP_LEVEL_PIN_CHANGED')
 manifests=[m for m in row.get('Manifests',[]) if m.get('Kind')=='image' and m.get('Available') is True]
 require(len(manifests)==1 and (manifests[0].get('ID') or manifests[0].get('Id'))==MAPPING[pin],
         'IMAGE_RUNNABLE_MANIFEST_MAPPING_CHANGED')
 require(row.get('Os')=='linux' and row.get('Architecture')=='amd64','IMAGE_PLATFORM_CHANGED')
 if pin!=MAPPING[pin]:
  require((row.get('Config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')==
          '114841271d4f8b9c4b63df6aedfd55bde2e82f40','APPROVED_SOURCE_REVISION_CHANGED')
 return True
def install(engine):
 original=engine.runtime_matches
 engine._v79_profile_replacements={}
 def compatible(before,after,entry,which,**kwargs):
  pin=entry[which+'_image']['Id']
  require(pin in MAPPING,'UNREVIEWED_IMAGE_LABEL_MAPPING')
  require(after.get('Image')==pin,'ACTUAL_IMAGE_IDENTITY_CHANGED')
  require((after.get('Config',{}).get('Labels') or {}).get(LABEL)==MAPPING[pin],
          'COMPOSE_IMAGE_LABEL_MAPPING_CHANGED')
  normalized=copy.deepcopy(after)
  normalized['Config']['Labels'][LABEL]=pin
  proof_previous=engine._v79_profile_replacements.get(after.get('Id'))
  if proof_previous is not None:
   entry=copy.deepcopy(entry)
   entry['_replaced_id']=proof_previous
  replaced=entry.get('_replaced_id')
  if replaced is not None:
   require(re.fullmatch('[0-9a-f]{64}',replaced or '') is not None,
           'REPLACEMENT_CONTEXT_INVALID')
   require(entry.get('compose_version','').lstrip('v')=='5.6.0',
           'UNREVIEWED_COMPOSE_REPLACEMENT_CODEC')
   name=entry['model']['services'][entry['service']].get('container_name')
   require(isinstance(name,str) and bool(name),'EXPLICIT_CONTAINER_NAME_REQUIRED')
   require(normalized['Config']['Labels'].get('com.docker.compose.replace')==name,
           'COMPOSE_REPLACEMENT_NAME_CHANGED')
   normalized['Config']['Labels']['com.docker.compose.replace']=replaced
  # Original validator still compares image, Config, Env, HostConfig/storage,
  # networks and every other label. Never mutate input snapshots or manifest.
  return original(before,normalized,entry,which,**kwargs)
 engine.runtime_matches=compatible
 return original
def replacement_profiles(engine,backend):
 """Extend existing stopped proof with one exact synthetic recreate per image."""
 original_call=backend.call
 def call(args,**kwargs):
  result=original_call(args,**kwargs)
  if args[:2]==['docker','compose'] and '--no-start' in args:
   require('--no-deps' in args and '--no-build' in args and '--pull' in args
           and args[args.index('--pull')+1]=='never','PROBE_COMMAND_SCOPE_CHANGED')
   project=args[args.index('--project-name')+1]
   require(re.fullmatch('v79profile[0-9a-f]{16}-[01]',project) is not None,
           'PROBE_PROJECT_SCOPE_CHANGED')
   model=json.loads(Path(args[args.index('-f')+1]).read_bytes())
   name=model['services'][args[-1]]['container_name']
   require(name==project,'PROBE_CONTAINER_NAME_CHANGED')
   before=backend.inspect(name)
   require(not before['State'].get('Running') and str(before['State'].get('StartedAt','0001')).startswith('0001'),
           'PROBE_PROCESS_STARTED')
   original_call([*args[:-1],'--force-recreate',args[-1]],**kwargs)
   after=backend.inspect(name)
   require(after['Id']!=before['Id'] and after['Image']==before['Image']
           and not after['State'].get('Running')
           and str(after['State'].get('StartedAt','0001')).startswith('0001'),
           'PROBE_RECREATE_IDENTITY_OR_STATE_CHANGED')
   engine._v79_profile_replacements[after['Id']]=before['Id']
  return result
 backend.call=call
 try:return engine.stopped_profiles(backend)
 finally:
  backend.call=original_call
  engine._v79_profile_replacements.clear()

class Docker(http.client.HTTPConnection):
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
  self.sock.settimeout(30);self.sock.connect('/var/run/docker.sock')
def inspect_image(pin):
 c=Docker('localhost')
 try:
  c.request('GET','/v1.48/images/'+pin+'/json?manifests=true')
  r=c.getresponse();require(r.status==200,'IMAGE_MAPPING_INSPECTION_UNAVAILABLE')
  return json.loads(r.read())
 finally:c.close()
def proof():
 path=ROOT/'v79_v3_hardened_hub_release.py'
 require(hashlib.sha256(path.read_bytes()).hexdigest()==
         '89f5e1a0a72da32bebda84068cae7e0f790ba62cdf386e84f98bbe0a3c33bc62','SUPERVISOR_DIGEST_CHANGED')
 spec=importlib.util.spec_from_file_location('existing_supervisor',path)
 sup=importlib.util.module_from_spec(spec);spec.loader.exec_module(sup)
 require(sup.os.getenv('V79_V3_OWNER_PRESENT')=='I_AM_PRESENT_FOR_MFA_SSO_AND_VISUAL_CHECKS',
         'OWNER_SUPERVISION_REQUIRED')
 with sup.locked():
  engine,plan,backend=sup.engine_plan()
  require(sup.state() is None and len(plan['protected'])==43,'RELEASE_SCOPE_OR_STATE_CHANGED')
  sup.assert_prior_snapshot(engine,plan,backend)
  for pin in MAPPING:validate_image(inspect_image(pin),pin)
  print('EXACT_IMAGE_MANIFEST_MAPPING=PASS_BOTH',flush=True)
  install(engine)
  try:
   with sup.heartbeat(): result=replacement_profiles(engine,backend)
   require(result.get('profiles_verified')==2,'TWO_PROFILES_REQUIRED')
   print(json.dumps({'phase':'COMPATIBILITY_PROOF','proof':result}),flush=True)
  except Exception as error:
   value=str(error);safe=value if re.fullmatch('[A-Z][A-Z0-9_]+',value) else 'REDACTED_ENGINE_FAILURE'
   print(json.dumps({'phase':'COMPATIBILITY_PROOF','safe_error':safe}),flush=True)
   raise
  finally:
   sup.assert_prior_snapshot(engine,plan,backend)
   print('POST_PROOF_PRIOR_AND_PROTECTED_43=PASS',flush=True)
  return {'result':'PASS_PINNED_IMAGE_LABEL_COMPATIBILITY','production_cutover_attempted':False,'release_gate':'HOLD'}
if __name__=='__main__':
 try: print(json.dumps(proof(),sort_keys=True))
 except Exception as error:
  value=str(error)
  print(json.dumps({'result':'COMPATIBILITY_STOP','safe_error':value if re.fullmatch('[A-Z][A-Z0-9_]+',value) else 'REDACTED_FAILURE','exception_type':type(error).__name__,'release_gate':'HOLD'}))
  raise SystemExit(2)
