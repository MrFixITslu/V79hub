#!/usr/bin/env python3
"""Find and verify the already-written GCIN6i1p recovery baseline. READ ONLY.

The prior writer completed private files and then rejected its own lowercase path
in its output filter. This script cannot create a baseline or modify Docker.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT=Path('/home/firelion')
ACCEPTED=ROOT/'v79-portfolio-rollout.6kvFDd5e'
PLAN=ROOT/'v79-remaining-plan.by50q9w3'
FAILED=ROOT/'v79-remaining-rollout.GCIN6i1p'
CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
APPS=('v79_course_builder','v79-pos','v79-pos-worker','gaming-studio-j')
SOURCE={'V79acaedmy':'584e07c9f5186e4aa10e87f931b2ea7194db93d4',
        'V79POS':'e4bf7620f5e6c5cc2e3a6c12d14bb441bf15de37',
        'Gaming-Studio-J':'17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'}
IMAGE={
 'v79_course_builder':'sha256:f9ab28a4b25fed0445a93e6f3b1548ed2706d9ec7a57176152236fa8708005d0',
 'v79-pos':'sha256:4f864f323e8a9d1d98dd1f26caf82d9b223412115fed7cb154c2d0e0158b88f8',
 'v79-pos-worker':'sha256:24279f6e693a66dca8bdb47f0e0e072d00983a67e74cc5e55a87ea5ecbf5c19d',
 'gaming-studio-j':'sha256:4039d9ab72c0cc99c5d18c92714678a9a8e05ef26177e85bbe3d56da834b07e7'
}
ALLOWED_MARKERS={'EXISTING_RECOVERY_BASELINE':'VERIFIED',
                 'RESTORED_SOURCE_PARITY':'PASS',
                 'LIVE_APP_CHANGES':'NONE',
                 'PLAN_MODE':'EVIDENCE_ONLY_NOT_DEPLOYABLE',
                 'R1_CUSTOMER_RELEASE':'NO_GO',
                 'SELF_TEST':'PASS'}
PATH_LINE=re.compile(r'NEW_RECOVERY_BASELINE=/home/firelion/v79-recovery-replan\.[A-Za-z0-9_-]{8,16}\Z')
NAME=re.compile(r'v79-recovery-replan\.[A-Za-z0-9_-]{8,16}\Z')

class Stop(Exception):pass

def need(ok,code):
    if not ok:raise Stop(code)

def allowed(line):
    if PATH_LINE.fullmatch(line):return True
    key,sep,value=line.partition('=')
    if not sep:return False
    if key=='STOP':return bool(re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',value))
    return key in ALLOWED_MARKERS and ALLOWED_MARKERS[key]==value

def emit(key,value):
    line=f'{key}={value}'
    need(allowed(line),'OUTPUT_UNSAFE')
    print(line,flush=True)

def hbytes(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def shafile(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for x in iter(lambda: stream.read(1024*1024),b''):h.update(x)
    return h.hexdigest()

def private_dir(folder):
    need(folder.is_dir() and not folder.is_symlink() and folder.stat().st_uid==os.getuid()
         and folder.stat().st_mode & 0o077==0,'PRIVATE_DIRECTORY_UNSAFE')

def private_file(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid()
         and path.stat().st_mode & 0o077==0,'PRIVATE_FILE_UNSAFE')
    return json.loads(path.read_text())

def core():
    path=ACCEPTED/'rollout.py'
    need(path.is_file() and not path.is_symlink() and hbytes(path.read_bytes())==CORE_BLOB,
         'CORE_PROVENANCE_CHANGED')
    spec=importlib.util.spec_from_file_location('v79_accepted_core_readonly',path)
    r=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    return r

def shape_dns_only(ref,current):
    if ref==current:return True
    if any(ref.get(key)!=current.get(key) for key in ('config','env','mounts','networks')):return False
    before,after=ref.get('host',{}),current.get('host',{})
    for k in before.keys()|after.keys():
        if before.get(k)==after.get(k):continue
        if k not in ('Dns','DnsOptions','DnsSearch'):return False
        if before.get(k) not in ([],None) or after.get(k) not in ([],None):return False
        if {type(before.get(k)),type(after.get(k))}!={type(None),list}:return False
    return True

def validate_receipt(receipt,old,now):
    if not isinstance(receipt,dict) or not isinstance(old,dict):return False
    if (receipt.get('status')!='RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE' or
        receipt.get('deployment_authorization')!='NO' or
        receipt.get('restore_acceptance')!='NOT_PERFORMED' or
        receipt.get('sources')!=SOURCE or
        receipt.get('prior_accepted_plan')!=str(PLAN) or
        receipt.get('failed_deployment')!=str(FAILED)):
        return False
    ids=receipt.get('current_runtime_container_ids')
    if not isinstance(ids,dict) or set(ids)!=set(APPS) or set(old)!=set(APPS):return False
    for name in APPS:
        if (not isinstance(old[name],dict) or old[name].get('Id')!=ids[name] or
            now[name]['Id']!=ids[name] or old[name].get('Image')!=IMAGE[name] or
            now[name]['Image']!=IMAGE[name]):return False
    return True

def audit():
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'WRONG_HOST_OR_ROOT')
    lock=ROOT/'.v79-portfolio-rollout.lock'
    need(lock.is_file() and not lock.is_symlink(),'LOCK_NOT_FOUND')
    with lock.open('rb') as l:
        try:fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('ANOTHER_ROLLOUT_RUNNING')
        for p in (ROOT,ACCEPTED,PLAN,FAILED):
            if p!=ROOT:private_dir(p)
        r=core()
        original_plan=private_file(PLAN/'plan-summary.json')
        manifest=private_file(FAILED/'checkpoint/manifest.json')
        need(original_plan.get('status')=='PLAN_PREPARED_NOT_DEPLOYED' and
             original_plan.get('sources')==SOURCE and
             set(original_plan.get('pins',{}))==set(APPS),'PLAN_PROVENANCE_CHANGED')
        need(manifest.get('status')=='CAPTURED_NOT_RESTORE_TESTED' and
             manifest.get('scope')=='REMAINING_ACADEMY_POS_GAMES_PRECHANGE_NOT_FULL_PORTFOLIO' and
             manifest.get('source_images')==IMAGE,'CHECKPOINT_PROVENANCE_CHANGED')
        now={name:r.inspect(name) for name in APPS}
        for name in APPS:
            require_health=bool(name!='v79-pos-worker')
            need(now[name]['Image']==IMAGE[name] and now[name]['State'].get('Running') is True
                 and (not require_health or now[name]['State'].get('Health',{}).get('Status')=='healthy'),
                 'CURRENT_ORIGINAL_RUNTIME_UNHEALTHY')
        folders=sorted(ROOT.glob('v79-recovery-replan.*'))
        matches=[]
        for folder in folders:
            need(NAME.fullmatch(folder.name),'UNEXPECTED_BASELINE_NAME')
            private_dir(folder)
            need(set(x.name for x in folder.iterdir())==
                 {'plan-summary.json','runtime-before.json'}|
                 {name+'-original.pinned.yml' for name in APPS},'BASELINE_FILE_SET_UNEXPECTED')
            receipt=private_file(folder/'plan-summary.json')
            snapshot=private_file(folder/'runtime-before.json')
            if not validate_receipt(receipt,snapshot,now):continue
            need(receipt.get('pins')==original_plan['pins'] and
                 receipt.get('old_plan_sha256')==shafile(PLAN/'plan-summary.json') and
                 receipt.get('checkpoint_manifest_sha256')==shafile(FAILED/'checkpoint/manifest.json'),
                 'BASELINE_ANCHOR_CHANGED')
            for name in APPS:
                need(private_file(folder/(name+'-original.pinned.yml'))==
                     private_file(PLAN/(name+'-original.pinned.yml')),
                     'RECOVERY_COMPOSE_MODEL_CHANGED')
                live_fp=r.fingerprint(now[name])
                snapshot_fp=r.fingerprint(snapshot[name])
                if name=='gaming-studio-j':
                    need(shape_dns_only(snapshot_fp,live_fp),'GAMES_RUNTIME_DRIFT')
                else:need(snapshot_fp==live_fp,'OTHER_RUNTIME_DRIFT')
                labels=now[name]['Config'].get('Labels') or {}
                need(labels.get('com.docker.compose.project.config_files')==
                     str(FAILED/(name+'-original.pinned.yml')),'COMPOSE_LINEAGE_CHANGED')
            matches.append(folder)
        need(len(matches)==1,'BASELINE_MISSING_OR_AMBIGUOUS')
        for name in APPS:
            again=r.inspect(name)
            need(again['Id']==now[name]['Id'] and
                 r.fingerprint(again)==r.fingerprint(now[name]),
                 'CONTAINERS_CHANGED_DURING_INSPECTION')
        emit('EXISTING_RECOVERY_BASELINE','VERIFIED')
        emit('NEW_RECOVERY_BASELINE',str(matches[0]))
        emit('RESTORED_SOURCE_PARITY','PASS')
        emit('LIVE_APP_CHANGES','NONE')
        emit('PLAN_MODE','EVIDENCE_ONLY_NOT_DEPLOYABLE')
        emit('R1_CUSTOMER_RELEASE','NO_GO')

def acer():
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    cmd=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
         '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    result=subprocess.run(cmd,input=Path(__file__).read_bytes(),
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
    for line in result.stdout.decode('utf8','replace').splitlines():
        need(allowed(line),'REDACTED_REMOTE_OUTPUT')
        print(line,flush=True)
    need(result.returncode==0,'REMOTE_INSPECTION_FAILED')

def self_test():
    base={'config':{'Cmd':['node']},'env':{'SECRET':'NOT_SHOWN'},
          'mounts':[],'networks':['x'],
          'host':{'Dns':[],'DnsOptions':[],'DnsSearch':[],'Privileged':False}}
    ok=json.loads(json.dumps(base))
    for k in ('Dns','DnsOptions','DnsSearch'):ok['host'][k]=None
    assert shape_dns_only(base,ok) and shape_dns_only(ok,base)
    changed=json.loads(json.dumps(ok));changed['host']['Dns']=['private-dns.test']
    assert not shape_dns_only(base,changed)
    changed=json.loads(json.dumps(ok));changed['host']['Privileged']=True
    assert not shape_dns_only(base,changed)
    assert allowed('NEW_RECOVERY_BASELINE=/home/firelion/v79-recovery-replan.aBc123_4')
    assert not allowed('NEW_RECOVERY_BASELINE=/tmp/untrusted')
    assert not allowed('SECRET=NOT_SHOWN')
    cur={name:{'Id':'a'*64,'Image':IMAGE[name]} for name in APPS}
    receipt={'status':'RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE',
             'deployment_authorization':'NO','restore_acceptance':'NOT_PERFORMED',
             'sources':SOURCE,'prior_accepted_plan':str(PLAN),
             'failed_deployment':str(FAILED),
             'current_runtime_container_ids':{name:'a'*64 for name in APPS}}
    assert validate_receipt(receipt,cur,cur)
    changed=dict(receipt,deployment_authorization='YES')
    assert not validate_receipt(changed,cur,cur)
    emit('SELF_TEST','PASS')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--server',action='store_true')
    p.add_argument('--self-test',action='store_true')
    opts=p.parse_args()
    if opts.self_test:self_test()
    elif opts.server:audit()
    else:acer()

if __name__=='__main__':
    try:main()
    except Exception as e:
        code=str(e) if isinstance(e,Stop) and re.fullmatch(r'[A-Z0-9_]{3,100}',str(e)) \
             else 'INSPECT_EXISTING_ERROR_REDACTED'
        print('STOP='+code,flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
        sys.exit(1)
