#!/usr/bin/env python3
"""On Acer: decrypt the pre-switch snapshot in memory and inspect live differences."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import tempfile

REMOTE = '/home/firelion/v79-g3-ui-cutover-8d82b21a4def-v3'
FILES = ('hub-pg.dump.gpg', 'hub-data.tar.gpg', 'hub-runtime-and-config.json.gpg', 'encrypted-checksums.sha256', 'manifest.json')
IMAGE = 'sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e'

REMOTE_PROGRAM = r'''
import copy,hashlib,json,pathlib,subprocess,sys,urllib.request
try:
 payload=json.load(sys.stdin)
 url='https://raw.githubusercontent.com/MrFixITslu/V79hub/abb89d1ff263ab1699be44f76cbed2e1db8c4689/scripts/marketing-production-panel-cutover.py'
 with urllib.request.urlopen(url,timeout=30) as r:code=r.read(1048577)
 if hashlib.sha256(code).hexdigest()!='e5e291d0270ba7b4725a118cc034086520ae70c51a05de938f0b6bdcff2c85a1':raise RuntimeError('Support integrity')
 ns={'__name__':'read_only_post_switch_diagnostic'};exec(compile(code,'<verified-read-only-support>','exec'),ns)
 h=ns['load_helper'](ns['HELPERS'][1]);ns['helper']=h
 current=h['inspect']('v79-hub');root=ns['WORK'];manifest=json.loads((root/'manifest.json').read_text())
 emit=lambda x:print(json.dumps(x,separators=(',',':')),flush=True)
 env=h['env_map'](current['Config']['Env']);marketing=h['inspect']('v79marketing-app');me=h['env_map'](marketing['Config']['Env'])
 emit({'hubHealthy':h['healthy'](current),'exactCandidateImage':current['Image']==ns['IMAGE'],'hubGeneration':env.get('V79_MARKETING_PRODUCTION_ENABLED'),'marketingHealthy':h['healthy'](marketing),'marketingPublication':me.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED'),'switchMarkerExists':(root/'switch-attempted.json').exists(),'deploymentReceiptExists':(root/'deployed.json').exists()})
 def compare(a,b,path):
  if a==b:return
  if isinstance(a,dict) and isinstance(b,dict):
   for key in sorted(set(a)|set(b)):
    if key not in a or key not in b:emit({'field':path+'.'+key,'difference':'field_presence'})
    else:compare(a[key],b[key],path+'.'+key)
  elif isinstance(a,list) and isinstance(b,list):
   canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'))
   if sorted(map(canonical,a))==sorted(map(canonical,b)):emit({'field':path,'difference':'list_order_only','entries':len(a)})
   elif len(a)!=len(b):emit({'field':path,'difference':'list_length','before':len(a),'after':len(b)})
   else:
    for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'['+str(i)+']')
  elif path in ('HostConfig.NetworkMode','HostConfig.Runtime') or all(v is None or isinstance(v,(bool,int,float)) for v in (a,b)):
   emit({'field':path,'before':a,'after':b})
  else:emit({'field':path,'difference':'value','beforeType':type(a).__name__,'afterType':type(b).__name__})
 compare(payload['hostConfig'],current['HostConfig'],'HostConfig')
 compare(payload['mounts'],h['mounts'](current),'Mounts')
 compare(payload['networks'],sorted(current['NetworkSettings']['Networks']),'NetworkMembership')
 config=copy.deepcopy(current['Config'])
 for key in ('Image','Labels','Hostname'):config.pop(key,None)
 config['Env']=sorted(config.get('Env',[]))
 emit({'applicationConfigPreserved':h['fingerprint'](config)==payload['applicationConfigSha256'],
       'resolvedImageOnlyConfigMatches':h['fingerprint'](ns['resolve'](ns['FILES']+[root/'ui-image.yml']))==payload['desiredResolvedSha256']})
 checks=[('accounts-billing-and-g2',lambda:h['protected_state']('v79-hub-postgres')==manifest['hubProtectedStateSha256']),
 ('marketing-customer-provider-records',lambda:h['sqlite_state']('v79marketing-app')['digest']==manifest['marketingProtectedStateSha256']),
 ('signed-marketing-brand-plan-and-campaigns',lambda:ns['semantic_marketing']()==manifest['signedMarketingPackagesSha256'])]
 for label,check in checks:
  try:emit({'preservationCheck':label,'pass':check()})
  except Exception as e:emit({'preservationCheck':label,'pass':False,'errorType':type(e).__name__})
 for name,expected in payload['unrelatedRuntimeHashes'].items():
  info=h['inspect'](name);emit({'unchangedService':name,'pass':h['healthy'](info) and h['fingerprint'](h['stable_runtime'](info))==expected})
 try:h['probe_live']();emit({'liveG2AndAuthenticationBoundariesPass':True})
 except Exception as e:emit({'liveG2AndAuthenticationBoundariesPass':False,'errorType':type(e).__name__})
 print('READ_ONLY_POST_SWITCH_DIAGNOSTIC_COMPLETE_NO_RESTART_OR_ROLLBACK')
except Exception as e:
 print('STOP: read-only inspection failed; error_type='+type(e).__name__);sys.exit(1)
'''


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main():
    os.umask(0o077)
    if socket.gethostname().split('.')[0]!='firelion-Aspire-A315-51':
        raise RuntimeError('Run on the Acer laptop for owner-key decryption')
    local=Path(tempfile.mkdtemp(prefix='v79-g3-ui-recovery-',dir=Path.home()))
    print('ACER_UI_RECOVERY_COPY='+str(local),flush=True)
    sources=['firelion@v79sl:'+REMOTE+'/'+name for name in FILES]
    subprocess.run(['scp',*sources,str(local)+'/'],check=True)
    recorded={}
    for line in (local/'encrypted-checksums.sha256').read_text().splitlines():
        digest,name=line.split(None,1);recorded[name.strip()]=digest
    for name in FILES[:3]:
        if hashlib.sha256((local/name).read_bytes()).hexdigest()!=recorded.get(name):raise RuntimeError('Encrypted backup checksum mismatch')
    print('ALL_THREE_ENCRYPTED_BACKUP_CHECKSUMS_PASS',flush=True)
    decrypted=subprocess.run(['gpg','--quiet','--decrypt',str(local/'hub-runtime-and-config.json.gpg')],stdout=subprocess.PIPE,check=True)
    if len(decrypted.stdout)>8388608:raise RuntimeError('Runtime snapshot size bound')
    document=json.loads(decrypted.stdout)
    print('PRE_SWITCH_RUNTIME_DECRYPT_PASS',flush=True)
    before=document['runtime']['v79-hub']
    mounted=sorted([{key:m.get(key) for key in ('Type','Name','Source','Destination','Driver','Mode','RW','Propagation')} for m in before['Mounts']],key=lambda m:m['Destination'])
    config=copy.deepcopy(before['Config'])
    for key in ('Image','Labels','Hostname'):config.pop(key,None)
    config['Env']=sorted(config.get('Env',[]))
    desired=copy.deepcopy(document['resolved']);desired['services']['v79-hub']['image']=IMAGE
    hashes={}
    for name,meta in document['runtime'].items():
        if name=='v79-hub':continue
        stable={key:meta[key] for key in ('Id','Image','Config','HostConfig','Mounts')}
        stable.update(StartedAt=meta['State']['StartedAt'],networks=sorted(meta['NetworkSettings']['Networks']))
        hashes[name]=fingerprint(stable)
    payload={'hostConfig':before['HostConfig'],'mounts':mounted,'networks':sorted(before['NetworkSettings']['Networks']),
             'applicationConfigSha256':fingerprint(config),'desiredResolvedSha256':fingerprint(desired),'unrelatedRuntimeHashes':hashes}
    # Application environment values, tokens and customer records are not sent.
    subprocess.run(['ssh','firelion@v79sl','python3 -B -c '+shlex.quote(REMOTE_PROGRAM)],input=json.dumps(payload).encode(),check=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('STOP: read-only inspection failed; error_type='+type(exc).__name__)
        raise SystemExit(1)
