#!/usr/bin/env python3
"""Acer-only existing checkpoint metadata inventory; no backup or decryption.

Reads current accepted P1 image IDs via bounded SSH/Docker inspect and known
offhost manifest metadata. Does not hash/decrypt/import/restore any archive.
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

NAMES=('v79-hub','v79-tiquet-manager')
REQUIRED={'original-app-images.tar.gpg','v79-hub-postgres.dump.gpg',
          'tiquet-postgres.dump.gpg','runtime-and-config.tar.gpg'}
SERVER=r'''
import hashlib,json,os,re,socket,subprocess
from pathlib import Path
assert socket.gethostname()=='v79sl' and os.getuid()!=0
root=Path('/home/firelion/v79-portfolio-rollout.6kvFDd5e')
p=root/'release-receipt.json'
assert p.is_file() and not p.is_symlink() and p.stat().st_uid==os.getuid() and p.stat().st_mode&0o077==0
receipt=json.loads(p.read_bytes());names=['v79-hub','v79-tiquet-manager']
def snapshot():
    proc=subprocess.run(['docker','--host','unix:///var/run/docker.sock','container','inspect',*names],capture_output=True,timeout=30,env={k:v for k,v in os.environ.items() if not k.startswith(('DOCKER_','COMPOSE_'))})
    assert proc.returncode==0
    rows=json.loads(proc.stdout);assert len(rows)==2
    result={}
    for row in rows:
        name=row['Name'].lstrip('/');assert name in names
        assert row['Image']==receipt['images'][name] and re.fullmatch(r'sha256:[a-f0-9]{64}',row['Image'])
        assert row['State']['Running'] and row['State']['Health']['Status']=='healthy'
        result[name]={'id':row['Id'],'image':row['Image'],'config':row['Config'],'host':row['HostConfig'],'mounts':row['Mounts'],'networks':row['NetworkSettings']['Networks']}
    assert set(result)==set(names)
    return result
before=snapshot();after=snapshot();assert before==after
print(json.dumps({'images':{k:v['image'] for k,v in before.items()},'unchanged':True}))
'''

class Stop(Exception):pass
def need(ok,code):
    if not ok:raise Stop(code)
def emit(k,v):
    need(re.fullmatch(r'[A-Z0-9_]+',k) and v in ('PASS','UNCHANGED','YES','NO','NONE','NOT_PERFORMED','NO_GO'),'OUTPUT_INVALID')
    print(k+'='+v,flush=True)
def classify(manifest,current):
    if not isinstance(manifest,dict):return False
    source=manifest.get('source_images')
    if not isinstance(source,dict) or any(source.get(k)!=v for k,v in current.items()):return False
    files=manifest.get('files')
    if not isinstance(files,list):return False
    names=[]
    for item in files:
        if not isinstance(item,dict):return False
        name=item.get('name');digest=item.get('sha256');size=item.get('bytes')
        if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.gpg',name) or
            not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest) or
            not isinstance(size,int) or isinstance(size,bool) or size<65):return False
        names.append(name)
    return (len(names)==len(set(names)) and REQUIRED<=set(names) and
            all(any(name.startswith(app+'-mount-') and name.endswith('.tar.gpg') for name in names) for app in NAMES))
def inventory(current,root):
    need(root.is_dir() and not root.is_symlink(),'OFFHOST_ROOT_UNAVAILABLE')
    manifests=[]
    for run in root.iterdir():
        if not re.fullmatch(r'v79-(?:portfolio|remaining)-rollout\.[A-Za-z0-9_-]+',run.name):continue
        need(not run.is_symlink() and run.is_dir(),'OFFHOST_RUN_UNSAFE')
        for candidate in (run/'manifest.json',run/'checkpoint/manifest.json'):
            if not candidate.exists():continue
            need(not candidate.parent.is_symlink() and not candidate.is_symlink() and candidate.is_file() and candidate.stat().st_size<=1048576,'OFFHOST_MANIFEST_UNSAFE')
            need(candidate.stat().st_uid==os.getuid() and candidate.stat().st_mode&0o077==0,'OFFHOST_MANIFEST_PERMISSIONS_UNSAFE')
            need(len(manifests)<32,'OFFHOST_INVENTORY_LIMIT')
            try:data=json.loads(candidate.read_bytes())
            except (ValueError,UnicodeError):raise Stop('OFFHOST_MANIFEST_INVALID') from None
            match=classify(data,current)
            if match:
                for item in data['files']:
                    path=candidate.parent/item['name']
                    need(path.is_file() and not path.is_symlink() and path.stat().st_size==item['bytes'],'MATCHING_ARTIFACT_MISSING_OR_SIZE_CHANGED')
            manifests.append(match)
    return any(manifests)
def self_test():
    current={k:'sha256:'+'a'*64 for k in NAMES}
    files=[{'name':n,'sha256':'b'*64,'bytes':100} for n in REQUIRED|{k+'-mount-0.tar.gpg' for k in NAMES}]
    manifest={'source_images':current,'files':files}
    assert classify(manifest,current)
    assert not classify({'candidates':current,'source_images':{},'files':files},current)
    assert not classify({'source_images':current,'files':files[:-1]},current)
    assert not classify({'source_images':current,'files':files+[files[0]]},current)
    emit('SELF_TEST','PASS')
def main():
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');args=p.parse_args()
    if args.self_test:return self_test()
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    proc=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','firelion@v79sl','python3 -B -'],input=SERVER.encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=100)
    need(proc.returncode==0,'CURRENT_IMAGE_READ_FAILED')
    result=json.loads(proc.stdout);current=result.get('images')
    need(isinstance(current,dict) and set(current)==set(NAMES) and result.get('unchanged') is True and
         all(isinstance(v,str) and re.fullmatch(r'sha256:[a-f0-9]{64}',v) for v in current.values()),'CURRENT_IMAGE_RESPONSE_INVALID')
    match=inventory(current,Path.home()/'V79-Portfolio-Checkpoints')
    emit('CURRENT_PAIR_RECEIPT_HEALTH','PASS');emit('CURRENT_PAIR_SNAPSHOT','UNCHANGED')
    emit('CURRENT_P1_METADATA_MATCH_IN_PORTFOLIO_ROOT','YES' if match else 'NO')
    emit('ARCHIVE_HASH_OR_DECRYPT','NOT_PERFORMED');emit('RESTORE','NOT_PERFORMED')
    emit('PRODUCTION_CHANGES','NONE');emit('R1_CUSTOMER_RELEASE','NO_GO')
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if isinstance(error,Stop) and re.fullmatch(r'[A-Z_]+',str(error)) else 'READ_ONLY_METADATA_ERROR'
        print('STOP='+code,flush=True);print('R1_CUSTOMER_RELEASE=NO_GO',flush=True);sys.exit(1)
