#!/usr/bin/env python3
"""Inspect cached Academy/POS/Games release candidates against accepted recovery baseline.

Read-only, Acer->v79sl. No rebuild, Docker create, database query, Compose up,
deployment, restoration or output of secret values. NO_GO always.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT=Path('/home/firelion')
BASE=ROOT/'v79-recovery-replan.2prajz9h'
FAILED=ROOT/'v79-remaining-rollout.GCIN6i1p'
SOURCE={'V79acaedmy':'584e07c9f5186e4aa10e87f931b2ea7194db93d4',
        'V79POS':'e4bf7620f5e6c5cc2e3a6c12d14bb441bf15de37',
        'Gaming-Studio-J':'17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'}
APP={'v79_course_builder':'V79acaedmy',
     'v79-pos':'V79POS',
     'v79-pos-worker':'V79POS',
     'gaming-studio-j':'Gaming-Studio-J'}
OLD_IMAGES={
 'v79_course_builder':'sha256:f9ab28a4b25fed0445a93e6f3b1548ed2706d9ec7a57176152236fa8708005d0',
 'v79-pos':'sha256:4f864f323e8a9d1d98dd1f26caf82d9b223412115fed7cb154c2d0e0158b88f8',
 'v79-pos-worker':'sha256:24279f6e693a66dca8bdb47f0e0e072d00983a67e74cc5e55a87ea5ecbf5c19d',
 'gaming-studio-j':'sha256:4039d9ab72c0cc99c5d18c92714678a9a8e05ef26177e85bbe3d56da834b07e7'
}
DIGEST=re.compile(r'sha256:[0-9a-f]{64}\Z')
MARKERS={'SELF_TEST':'PASS','MODE':'READ_ONLY_CANDIDATE_INVENTORY',
         'RECOVERY_BASELINE':'UNCHANGED',
         'ENCRYPTED_CHECKPOINT':'PRECHANGE_PRESENT_NOT_RESTORE_TESTED',
         'ALL_CANDIDATES':'PINNED_PROVENANCE_PASS',
         'ISOLATED_APP_RUNTIME':'NOT_RUN',
         'NEW_RELEASE_DEPLOYMENT':'NOT_AUTHORIZED',
         'R1_CUSTOMER_RELEASE':'NO_GO'}
TAGS={'v79_course_builder':'ACADEMY','v79-pos':'POS_API',
      'v79-pos-worker':'POS_WORKER','gaming-studio-j':'GAMES'}

class Stop(Exception):pass
def need(ok,code):
    if not ok:raise Stop(code)
def safe_line(line):
    key,sep,value=line.partition('=')
    return bool(sep and (key in MARKERS and MARKERS[key]==value or
            key in {'CANDIDATE_'+v for v in TAGS.values()} and value=='PROVENANCE_PASS' or
            key=='STOP' and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',value)))
def emit(key,value):
    line=f'{key}={value}'
    need(safe_line(line),'UNSAFE_OUTPUT')
    print(line,flush=True)
def read_private(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid()
         and path.stat().st_mode & 0o077==0,'PRIVATE_FILE_CHANGED')
    return json.loads(path.read_text())
def check_directory(directory):
    need(directory.is_dir() and not directory.is_symlink()
         and directory.stat().st_uid==os.getuid()
         and directory.stat().st_mode & 0o077==0,'PRIVATE_DIRECTORY_CHANGED')
def hashfile(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
def docker(kind,identifier):
    if kind=='image':command=['docker','image','inspect',identifier]
    else:command=['docker','container','inspect',identifier]
    p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
    need(p.returncode==0,'DOCKER_INSPECT_FAILED')
    data=json.loads(p.stdout)
    need(len(data)==1,'INSPECT_AMBIGUOUS')
    return data[0]
def image_candidate_ok(img,id,revision,original):
    if not DIGEST.fullmatch(id) or img.get('Id')!=id:return False
    config=img.get('Config') or {}
    old=original.get('Config') or {}
    if (config.get('Labels') or {}).get('org.opencontainers.image.revision')!=revision:return False
    if config.get('Volumes'):return False
    def env_keys(values):
        result=set()
        for item in values or []:
            key,sep,_=item.partition('=')
            if not sep or key in result:raise Stop('INVALID_IMAGE_ENVIRONMENT')
            result.add(key)
        return result
    if not env_keys(config.get('Env'))<=env_keys(old.get('Env')):return False
    for field in ('User','Entrypoint','Cmd','WorkingDir'):
        if not old.get(field) and config.get(field):return False
    return True

def inspect():
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'RUN_ON_V79SL_NONROOT')
    for folder in (BASE,FAILED):check_directory(folder)
    report=read_private(BASE/'plan-summary.json')
    baseline=read_private(BASE/'runtime-before.json')
    manifest=read_private(FAILED/'checkpoint/manifest.json')
    need(report.get('status')=='RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE'
         and report.get('deployment_authorization')=='NO'
         and report.get('restore_acceptance')=='NOT_PERFORMED'
         and report.get('sources')==SOURCE
         and report.get('failed_deployment')==str(FAILED)
         and report.get('checkpoint_manifest_sha256')==
             hashfile(FAILED/'checkpoint/manifest.json'),'BASELINE_RECEIPT_CHANGED')
    need(set(baseline)==set(APP)
         and report.get('current_runtime_container_ids')==
         {k:baseline[k].get('Id') for k in APP},'BASELINE_IDENTITIES_INVALID')
    need(manifest.get('status')=='CAPTURED_NOT_RESTORE_TESTED'
         and manifest.get('scope')=='REMAINING_ACADEMY_POS_GAMES_PRECHANGE_NOT_FULL_PORTFOLIO'
         and manifest.get('sources')==SOURCE
         and manifest.get('source_images')==OLD_IMAGES
         and isinstance(manifest.get('candidates'),dict)
         and set(manifest['candidates'])==set(APP),'CHECKPOINT_MANIFEST_CHANGED')
    emit('MODE','READ_ONLY_CANDIDATE_INVENTORY')
    emit('ENCRYPTED_CHECKPOINT','PRECHANGE_PRESENT_NOT_RESTORE_TESTED')
    current={}
    for name in APP:
        current[name]=docker('container',name)
        old=baseline[name];live=current[name]
        need(live['Id']==old['Id'] and live['Image']==old['Image']==OLD_IMAGES[name]
             and live['State'].get('Running') is True,'CURRENT_RUNTIME_IDENTITY_CHANGED')
        if name!='v79-pos-worker':
            need(live['State'].get('Health',{}).get('Status')=='healthy','CURRENT_HEALTH_CHANGED')
    emit('RECOVERY_BASELINE','UNCHANGED')
    by_repo={}
    for name,repo in APP.items():
        entry=read_private(FAILED/(repo+'-built-image.json'))
        need(entry=={'repo':repo,'source_commit':SOURCE[repo],
                     'image_id':manifest['candidates'][name]},
             'CACHED_RECEIPT_CHANGED')
        ident=entry['image_id']
        if repo in by_repo:need(by_repo[repo]==ident,'REPO_BUILT_IMAGE_AMBIGUOUS')
        by_repo[repo]=ident
        image=docker('image',ident)
        original=docker('image',OLD_IMAGES[name])
        need(image_candidate_ok(image,ident,SOURCE[repo],original),'CANDIDATE_IMAGE_CHANGED')
        emit('CANDIDATE_'+TAGS[name],'PROVENANCE_PASS')
    for name in APP:
        now=docker('container',name)
        need(now['Id']==current[name]['Id'] and now['Image']==current[name]['Image']
             and now['State'].get('Running') is True,'RUNTIME_CHANGED_DURING_INSPECTION')
    emit('ALL_CANDIDATES','PINNED_PROVENANCE_PASS')
    emit('ISOLATED_APP_RUNTIME','NOT_RUN')
    emit('NEW_RELEASE_DEPLOYMENT','NOT_AUTHORIZED')
    emit('R1_CUSTOMER_RELEASE','NO_GO')
def self_test():
    base={'Config':{'User':'node','Env':['A=secret'], 'Volumes':None}}
    img={'Id':'sha256:'+'a'*64,'Config':{'User':'node','Env':['A=secret'],
                                    'Labels':{'org.opencontainers.image.revision':'f'*40}}}
    assert image_candidate_ok(img,img['Id'],'f'*40,base)
    changed=json.loads(json.dumps(img))
    changed['Config']['Env'].append('OTHER=secret')
    assert not image_candidate_ok(changed,img['Id'],'f'*40,base)
    changed=json.loads(json.dumps(img))
    changed['Config']['Volumes']={'/data':{}}
    assert not image_candidate_ok(changed,img['Id'],'f'*40,base)
    changed=json.loads(json.dumps(img))
    changed['Config']['Labels']={'org.opencontainers.image.revision':'e'*40}
    assert not image_candidate_ok(changed,img['Id'],'f'*40,base)
    assert not image_candidate_ok(img,'sha256:'+'b'*64,'f'*40,base)
    assert safe_line('CANDIDATE_GAMES=PROVENANCE_PASS')
    assert not safe_line('CANDIDATE_GAMES=SECRET')
    assert not safe_line('PASSWORD=secret')
    emit('SELF_TEST','PASS')
def acer():
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    command=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
             '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    done=subprocess.run(command,input=Path(__file__).read_bytes(),
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
    for line in done.stdout.decode('utf8','replace').splitlines():
        need(safe_line(line),'REDACTED_REMOTE_OUTPUT')
        print(line,flush=True)
    need(done.returncode==0,'CANDIDATE_INVENTORY_FAILED')
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--server',action='store_true')
    p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    if args.self_test:self_test()
    elif args.server:inspect()
    else:acer()
if __name__=='__main__':
    try:main()
    except Exception as e:
        reason=str(e) if isinstance(e,Stop) and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',str(e))\
               else 'INVENTORY_ERROR_REDACTED'
        print('STOP='+reason,flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
        sys.exit(1)
