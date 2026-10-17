#!/usr/bin/env python3
"""Build/test the failed-attempt UI; preserve live generation and publication."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import tempfile
import urllib.request

COMMIT='ec03c77b5b1ae0f7b4ce1be0393f3b80a6633852'
TREE='487d80221ae9b58d91015d898e918291d8b088b7'
BASE='8d82b21a4defe47a3d377a57dcd648b3c9818fea'
HUB_IMAGE='sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e'
MARKETING_IMAGE='sha256:e34d3c22f325c7fef78bc79bf96aa3386c10a45a7d2fd3e4e5081d39e9d4e0e8'
TAG='v79-hub-g3-cleanup:'+COMMIT[:12]
NAMES=('v79-hub','v79marketing-app','v79-business-agent','v79-hub-postgres','v79-tiquet-manager','tiquet-postgres')


def require(ok,message):
    if not ok:raise RuntimeError(message)


def load():
    url='https://raw.githubusercontent.com/MrFixITslu/V79hub/6a14a75bae67b18d1219f4d401d4573776db146c/scripts/marketing-production-panel-build.py'
    with urllib.request.urlopen(url,timeout=30) as response:code=response.read(1048577)
    require(hashlib.sha256(code).hexdigest()=='4ca319f177cc3c10575c619936661a110eb8e1f9fa978bc91aee1b4040cbe8a5','Build support integrity mismatch')
    ns={'__name__':'cleanup_build_support'};exec(compile(code,'<verified-cleanup-build-support>','exec'),ns)
    ns.update(COMMIT=COMMIT,TREE=TREE,BASE_COMMIT=BASE,TAG=TAG)
    return ns


def snapshot(run):
    result={}
    for name in NAMES:
        info=json.loads(run(['docker','inspect',name]))[0]
        require(info['State']['Running'] and info['State'].get('Health',{}).get('Status')=='healthy','Live service is not healthy: '+name)
        result[name]={'id':info['Id'],'image':info['Image'],'startedAt':info['State']['StartedAt'],
            'runtimeSha256':hashlib.sha256(json.dumps({k:info[k] for k in ('Config','HostConfig','Mounts')},sort_keys=True).encode()).hexdigest()}
        if name in ('v79-hub','v79marketing-app'):
            require(info['Image']==(HUB_IMAGE if name=='v79-hub' else MARKETING_IMAGE),'Accepted live image differs')
            env=dict(item.split('=',1) for item in info['Config']['Env'])
            require(env.get('V79_MARKETING_PRODUCTION_ENABLED')=='1','Generation flag differs')
            if name=='v79marketing-app':require(env.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED')=='1','Accepted publication flag differs')
    return result


def main():
    os.umask(0o077)
    require(socket.gethostname().split('.')[0]=='v79sl' and os.getuid()==1000 and pwd.getpwuid(os.getuid()).pw_name=='firelion','Run as firelion on v79sl')
    ns=load();run=ns['run'];before=snapshot(run)
    require(shutil.disk_usage('/home/firelion').free>4*1024**3,'Insufficient build space')
    root=Path(tempfile.mkdtemp(prefix='v79-g3-cleanup-build-',dir='/home/firelion'))
    print('BUILD_DIRECTORY='+str(root),flush=True)
    checkout=root/'V79hub';checkout.mkdir()
    print('STAGE=verify-exact-cleanup-ui-source',flush=True)
    run(['git','init','--quiet',str(checkout)])
    for commit in (COMMIT,BASE):run(['git','-C',str(checkout),'fetch','--depth','1','https://github.com/MrFixITslu/V79hub.git',commit],timeout=180)
    run(['git','-C',str(checkout),'checkout','--quiet','--detach',COMMIT])
    ns['verify_checkout_scope'](checkout);ns['readable_source'](checkout)
    print('STAGE=build-cleanup-ui-image',flush=True)
    run(['docker','build','--build-arg','NODE_BASE='+ns['NODE_BASE'],'--label','org.opencontainers.image.revision='+COMMIT,'--tag',TAG,str(checkout)],visible=True,timeout=1800)
    image=json.loads(run(['docker','image','inspect',TAG]))[0]
    require(image['Config']['Labels'].get('org.opencontainers.image.revision')==COMMIT and 'NODE_ENV=production' in image['Config']['Env'],'Built image revision/environment differs')
    print('STAGE=isolated-cleanup-ui-mfa-and-approval-tests',flush=True)
    run(ns['isolated_test_command'](image['Id']),visible=True,timeout=180)
    require(snapshot(run)==before,'Live containers changed during build; inspect before proceeding')
    receipt={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'deploymentPerformed':False,
        'candidate':{'commit':COMMIT,'tree':TREE,'image':image['Id'],'tag':TAG},'liveRuntime':before,
        'sourceScopeVerified':True,'isolatedTestsPassed':True,'testEnvironment':'test','publicationEnabled':True,'cleanupPerformed':False}
    with (root/'cleanup-build-receipt.json').open('x') as output:
        json.dump(receipt,output,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
    print('CLEANUP_UI_BUILD_AND_20_ISOLATED_TESTS_PASS')
    print('CANDIDATE_IMAGE='+image['Id'])
    print('BUILD_RECEIPT='+str(root/'cleanup-build-receipt.json'))
    print('LIVE_CONTAINERS_AND_PUBLICATION_UNCHANGED')
    print('UI_DEPLOYMENT_AND_OWNER_CLEANUP_PENDING')


if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as exc:
        print('STOP: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__))
        print('NO_LIVE_RECREATION_OR_CAMPAIGN_CLEANUP_ATTEMPTED')
        raise SystemExit(1)
