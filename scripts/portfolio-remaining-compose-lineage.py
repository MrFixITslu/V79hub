#!/usr/bin/env python3
"""Read-only Compose label and saved-plan lineage audit after GCIN6i1p rollback.

NO APP/DB/TIMER/CONTAINER CHANGES. Never print paths, envs, labels, hashes
of private files, raw logs, network endpoints, or Compose contents.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

RUN=Path('/home/firelion/v79-remaining-rollout.GCIN6i1p')
PLAN=Path('/home/firelion/v79-remaining-plan.by50q9w3')
PINS={
 'v79_course_builder':('v79-course-builder','course-builder','V79acaedmy'),
 'v79-pos':('v79pos','api','V79POS'),
 'v79-pos-worker':('v79pos','worker','V79POS'),
 'gaming-studio-j':('gaming-studio-j','gaming-studio-j','Gaming-Studio-J')
}
SOURCE={
 'V79acaedmy':'584e07c9f5186e4aa10e87f931b2ea7194db93d4',
 'V79POS':'e4bf7620f5e6c5cc2e3a6c12d14bb441bf15de37',
 'Gaming-Studio-J':'17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'
}
OLD_IMAGES={
 'v79_course_builder':'sha256:f9ab28a4b25fed0445a93e6f3b1548ed2706d9ec7a57176152236fa8708005d0',
 'v79-pos':'sha256:4f864f323e8a9d1d98dd1f26caf82d9b223412115fed7cb154c2d0e0158b88f8',
 'v79-pos-worker':'sha256:24279f6e693a66dca8bdb47f0e0e072d00983a67e74cc5e55a87ea5ecbf5c19d',
 'gaming-studio-j':'sha256:4039d9ab72c0cc99c5d18c92714678a9a8e05ef26177e85bbe3d56da834b07e7'
}
PRINT_LINE=re.compile(r'[A-Z][A-Z0-9_]{0,95}=[A-Z0-9_,.-]{1,250}\Z')
DNS_KEYS=('Dns','DnsOptions','DnsSearch')
CONFIG_KEYS=('Cmd','Entrypoint','User','WorkingDir','ExposedPorts','Healthcheck',
 'StopSignal','StopTimeout','Tty','OpenStdin','StdinOnce','Volumes')
MOUNT_KEYS=('Type','Source','Destination','RW','Propagation')

def emit(key,value):
    line=key+'='+str(value)
    if not PRINT_LINE.fullmatch(line):raise ValueError('OUTPUT_NOT_SAFE')
    print(line,flush=True)

def stop(code):
    emit('STOP',code)
    emit('R1_CUSTOMER_RELEASE','NO_GO')
    return 1

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_private(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('PRIVATE_EVIDENCE_UNSAFE')
    return json.loads(path.read_text())

def inspect(name):
    p=subprocess.run(['docker','container','inspect',name],capture_output=True,timeout=30)
    if p.returncode or len(json.loads(p.stdout))!=1:raise ValueError('LIVE_INSPECT_FAILED')
    return json.loads(p.stdout)[0]

def render(path,project):
    # docker compose config only: no services, networking, volume writes, or up.
    p=subprocess.run(['docker','compose','--project-name',project,'-f',str(path),
       'config','--format','json'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
    if p.returncode:raise ValueError('FROZEN_COMPOSE_RENDER_FAILED')
    return json.loads(p.stdout)

def environment(items):
    result={}
    for item in items or []:
        k,sep,v=item.partition('=')
        if not sep or k in result:raise ValueError('ENV_AMBIGUOUS')
        result[k]=v
    return result

def normalize_host(host):
    data=copy.deepcopy(host)
    binds=data.get('Binds')
    if isinstance(binds,list):
        parsed=[v.split(':') for v in binds if isinstance(v,str)]
        if len(parsed)==len(binds) and all(len(x) in (2,3) and x[1].startswith('/') for x in parsed):
            data['Binds']=sorted(binds)
    mounts=data.get('Mounts')
    if isinstance(mounts,list) and all(isinstance(m,dict) and isinstance(m.get('Target'),str)
         and m['Target'].startswith('/') for m in mounts):
        data['Mounts']=sorted(mounts,key=lambda m:json.dumps(m,sort_keys=True))
    return data

def fingerprint(row):
    cfg=row['Config']
    return {
        'config':{k:cfg.get(k) for k in CONFIG_KEYS},
        'env':environment(cfg.get('Env')),
        'host':normalize_host(row['HostConfig']),
        'mounts':sorted([{k:m.get(k) for k in MOUNT_KEYS} for m in row['Mounts']],
                        key=lambda x:x['Destination']),
        'networks':sorted(row['NetworkSettings']['Networks'])
    }

def empty_dns_representation_only(before,live):
    a,b=fingerprint(before),fingerprint(live)
    if a==b:return False
    if any(a[k]!=b[k] for k in ('config','env','mounts','networks')):return False
    x,y=a['host'],b['host']
    differing=[k for k in x.keys()|y.keys() if x.get(k)!=y.get(k)]
    if not differing or any(k not in DNS_KEYS for k in differing):return False
    return all(x.get(k) in (None,[]) and y.get(k) in (None,[]) for k in differing)

def classify_path(value,name,pin):
    if not isinstance(value,str):return 'INVALID'
    paths=value.split(',')
    original=str(RUN/(name+'-original.pinned.yml'))
    candidate=str(RUN/(name+'-candidate.pinned.yml'))
    if paths==[original]:return 'SAVED_ROLLBACK_ORIGINAL'
    if paths==[candidate]:return 'FAILED_CANDIDATE'
    if paths==[pin]:return 'LEGACY_SOURCE'
    return 'UNKNOWN'

def compose_parity(rendered,row,service_name,image):
    services=rendered.get('services') or {}
    service=services.get(service_name)
    if not isinstance(service,dict) or service.get('image')!=image:return False
    if service.get('ports') or row['HostConfig'].get('PortBindings'):return False
    env=service.get('environment')
    if not isinstance(env,dict):return False
    if {k:(v.replace('$$','$') if isinstance(v,str) else v) for k,v in env.items()}!=environment(row['Config'].get('Env')):return False
    desired=service.get('volumes') or []
    actual={m['Destination']:m for m in row['Mounts']}
    if len(desired)!=len(actual):return False
    for mount in desired:
        if not isinstance(mount,dict) or mount.get('target') not in actual:return False
        live=actual[mount['target']]
        if mount.get('type')!=live['Type'] or bool(live['RW'])==bool(mount.get('read_only',False)):return False
        if mount['type']=='bind' and mount.get('source')!=live.get('Source'):return False
        if mount['type']=='volume':
            definition=(rendered.get('volumes') or {}).get(mount.get('source'),{})
            if definition.get('name')!=live.get('Name'):return False
    networks=service.get('networks') or {}
    if not isinstance(networks,dict):return False
    available=rendered.get('networks') or {}
    try:
        names={available[alias]['name'] for alias in networks}
    except (KeyError,TypeError):return False
    return names==set(row['NetworkSettings']['Networks'])

def evidence(server=True):
    if server and (socket.gethostname()!='v79sl' or os.getuid()==0):
        return stop('SERVER_OR_USER_REJECTED')
    for folder in (RUN,PLAN):
        if not folder.is_dir() or folder.is_symlink() or folder.stat().st_uid!=os.getuid() or folder.stat().st_mode & 0o077:
            return stop('PRIVATE_DIRECTORY_UNSAFE')
    try:
        before=safe_private(RUN/'runtime-before.json')
        reference=safe_private(RUN/'plan-reference.json')
        summary=safe_private(PLAN/'plan-summary.json')
        manifest=safe_private(RUN/'checkpoint/manifest.json')
        if (RUN/'exit-code').read_text().strip()!='1' or summary['status']!='PLAN_PREPARED_NOT_DEPLOYED':
            return stop('RUN_OR_PLAN_STATUS_CHANGED')
        if reference['directory']!=str(PLAN) or reference['sources']!=SOURCE or reference['summary_sha256']!=sha(PLAN/'plan-summary.json'):
            return stop('PLAN_REFERENCE_PROOF_CHANGED')
        if summary['sources']!=SOURCE or manifest['status']!='CAPTURED_NOT_RESTORE_TESTED' \
           or manifest['scope']!='REMAINING_ACADEMY_POS_GAMES_PRECHANGE_NOT_FULL_PORTFOLIO':
            return stop('SOURCE_OR_CHECKPOINT_PROVENANCE_CHANGED')
        if set(PINS)-set(before):return stop('BASELINE_INCOMPLETE')
    except Exception:
        return stop('PRIVATE_EVIDENCE_INVALID')
    emit('AUDIT','READ_ONLY_COMPOSE_LINEAGE')
    trusted=True
    for name,(project,service,repo) in PINS.items():
        tag={'v79-pos':'POS_API','v79-pos-worker':'POS_WORKER','v79_course_builder':'ACADEMY','gaming-studio-j':'GAMES'}[name]
        try:
            row=inspect(name)
            old=before[name]
            if row['Image']!=OLD_IMAGES[name] or old['Image']!=OLD_IMAGES[name] or \
               row['State'].get('Running') is not True or (name!='v79-pos-worker' and row['State'].get('Health',{}).get('Status')!='healthy'):
                emit(tag+'_ORIGINAL','NOT_VERIFIED');trusted=False;continue
            config=old['Config'].get('Labels') or {}
            labels=row['Config'].get('Labels') or {}
            expect=config.get('com.docker.compose.project.config_files')
            original_path=expect.split(',')[0] if isinstance(expect,str) and ',' not in expect else ''
            kind=classify_path(labels.get('com.docker.compose.project.config_files'),name,original_path)
            emit(tag+'_COMPOSE_LABEL',kind)
            emit(tag+'_COMPOSE_PROJECT','MATCH' if labels.get('com.docker.compose.project')==project else 'CHANGED')
            dir_name=labels.get('com.docker.compose.project.working_dir')
            emit(tag+'_COMPOSE_DIRECTORY','ROLLBACK_RUN' if dir_name==str(RUN)
                 else 'BASELINE' if dir_name==config.get('com.docker.compose.project.working_dir')
                 else 'OTHER')
            matching=(fingerprint(old)==fingerprint(row) or name=='gaming-studio-j' and empty_dns_representation_only(old,row))
            emit(tag+'_RECOVERY_PARITY','PASS' if matching else 'FAIL')
            approved_path=PLAN/(name+'-original.pinned.yml')
            run_path=RUN/(name+'-original.pinned.yml')
            approved=safe_private(approved_path)
            frozen=safe_private(run_path)
            model_ok=(approved==frozen and (frozen.get('services') or {}).get(service,{}).get('image')==OLD_IMAGES[name])
            emit(tag+'_SAVED_PLAN_MODEL','MATCH' if model_ok else 'DIFFERS')
            parsed=render(run_path,project)
            model_runtime=compose_parity(parsed,row,service,OLD_IMAGES[name])
            emit(tag+'_SAVED_COMPOSE_RUNTIME','PASS' if model_runtime else 'FAIL')
            valid=(kind=='SAVED_ROLLBACK_ORIGINAL' and labels.get('com.docker.compose.project')==project
                   and matching and model_ok and model_runtime)
            emit(tag+'_PROVENANCE','PASS' if valid else 'REVIEW_REQUIRED')
            trusted=trusted and valid
        except Exception:
            emit(tag+'_PROVENANCE','REVIEW_REQUIRED')
            trusted=False
    emit('ALL_RESTORED_COMPOSE_PROVENANCE','PASS' if trusted else 'REVIEW_REQUIRED')
    emit('LIVE_CHANGES','NONE')
    emit('FRESH_PLAN_CREATED','NO')
    emit('R1_CUSTOMER_RELEASE','NO_GO')
    return 0

def acer():
    if socket.gethostname()=='v79sl' or os.getuid()==0:return stop('ACER_NON_ROOT_REQUIRED')
    args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
          '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    try:
        done=subprocess.run(args,input=Path(__file__).read_bytes(),
                            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
        for line in done.stdout.decode('utf-8','replace').splitlines():
            if not PRINT_LINE.fullmatch(line):return stop('REMOTE_OUTPUT_NOT_SAFE')
            print(line,flush=True)
        if done.returncode:return stop('REMOTE_AUDIT_FAILED')
        return 0
    except Exception:
        return stop('READONLY_AUDIT_UNAVAILABLE')

def self_test():
    a={'Config':{'Env':['SECRET=DO_NOT_PRINT']},'HostConfig':{'Dns':[],'DnsOptions':[],'DnsSearch':[]},
       'Mounts':[],'NetworkSettings':{'Networks':{'proxy':{}}}}
    b=copy.deepcopy(a)
    b['HostConfig']={k:None for k in DNS_KEYS}
    assert empty_dns_representation_only(a,b)
    assert not empty_dns_representation_only(a,a)
    b['HostConfig']['Dns']=['8.8.8.8']
    assert not empty_dns_representation_only(a,b)
    assert classify_path(str(RUN/'gaming-studio-j-original.pinned.yml'),'gaming-studio-j','x')=='SAVED_ROLLBACK_ORIGINAL'
    assert classify_path(str(RUN/'gaming-studio-j-candidate.pinned.yml'),'gaming-studio-j','x')=='FAILED_CANDIDATE'
    assert classify_path('/unexpected','gaming-studio-j','x')=='UNKNOWN'
    assert 'DO_NOT_PRINT' not in str(empty_dns_representation_only(a,b))
    emit('SELF_TEST','PASS')
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--server',action='store_true')
    flags=parser.parse_args()
    try:
        sys.exit(self_test() if flags.self_test else evidence() if flags.server else acer())
    except Exception:
        sys.exit(stop('DIAGNOSTIC_ERROR_REDACTED'))
