#!/usr/bin/env python3
"""Acer->v79sl read-only, redacted audit after GCIN6i1p partial Games rollback.

No docker mutations, no raw logs, no app network requests, no secret output.
The accepted release helper's fingerprint fields are compared without printing values.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

RUN=Path('/home/firelion/v79-remaining-rollout.GCIN6i1p')
APPS=('gaming-studio-j','v79-pos','v79-pos-worker','v79_course_builder')
SHARED=('v79-hub','v79-tiquet-manager')
EXPECTED_GAMES='sha256:4039d9ab72c0cc99c5d18c92714678a9a8e05ef26177e85bbe3d56da834b07e7'
SAFE=re.compile(r'^[A-Z][A-Z0-9_]{0,79}=[A-Z0-9_,.-]{1,300}$')
FIELDS=('Cmd','Entrypoint','User','WorkingDir','ExposedPorts',
        'Healthcheck','StopSignal','StopTimeout','Tty','OpenStdin',
        'StdinOnce','Volumes')
MOUNT_FIELDS=('Type','Source','Destination','RW','Propagation')

def emit(key,value):
    line=key+'='+str(value)
    if not SAFE.fullmatch(line):raise RuntimeError('UNSAFE_DIAGNOSTIC_OUTPUT')
    print(line,flush=True)

def error(code):
    emit('STOP',code)
    return 1

def restricted_json(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_uid!=os.getuid() \
       or path.stat().st_mode & 0o077:
        raise ValueError('PRIVATE_EVIDENCE_UNAVAILABLE')
    return json.loads(path.read_text())

def inspect(name):
    process=subprocess.run(['docker','container','inspect',name],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,
        env={k:v for k,v in os.environ.items() if not k.startswith(('COMPOSE_','DOCKER_','GIT_'))})
    if process.returncode!=0:return None
    data=json.loads(process.stdout)
    if not isinstance(data,list) or len(data)!=1:raise ValueError('INSPECT_AMBIGUOUS')
    return data[0]

def envmap(config):
    result={}
    for item in config.get('Env') or []:
        key,delimiter,value=item.partition('=')
        if not delimiter or key in result:raise ValueError('ENVIRONMENT_AMBIGUOUS')
        result[key]=value
    return result

def normhost(host):
    data=copy.deepcopy(host)
    binds=data.get('Binds')
    if isinstance(binds,list):
        parsed=[v.split(':') for v in binds if isinstance(v,str)]
        if len(parsed)==len(binds) and all(len(p) in (2,3) and p[1].startswith('/') for p in parsed):
            data['Binds']=sorted(binds)
    mounts=data.get('Mounts')
    if isinstance(mounts,list) and all(isinstance(m,dict) and isinstance(m.get('Target'),str)
                                      and m['Target'].startswith('/') for m in mounts):
        data['Mounts']=sorted(mounts,key=lambda m:json.dumps(m,sort_keys=True))
    return data

def differences(old,new):
    left,right=old['Config'],new['Config']
    config=[k.upper() for k in FIELDS if left.get(k)!=right.get(k)]
    e1,e2=envmap(left),envmap(right)
    env=(len(e2.keys()-e1.keys()),len(e1.keys()-e2.keys()),
         sum(e1[k]!=e2[k] for k in e1.keys()&e2.keys()))
    h1,h2=normhost(old['HostConfig']),normhost(new['HostConfig'])
    host=sorted(k.upper() for k in h1.keys()|h2.keys() if h1.get(k)!=h2.get(k))
    m1=sorted([{k:m.get(k) for k in MOUNT_FIELDS} for m in old['Mounts']],
              key=lambda m:str(m['Destination']))
    m2=sorted([{k:m.get(k) for k in MOUNT_FIELDS} for m in new['Mounts']],
              key=lambda m:str(m['Destination']))
    mount_diff=len(m1)!=len(m2) or m1!=m2
    networks=set(old['NetworkSettings']['Networks']) != set(new['NetworkSettings']['Networks'])
    matched=not config and not any(env) and not host and not mount_diff and not networks
    return matched,config,env,host,mount_diff,networks

DNS_KEYS=('Dns','DnsOptions','DnsSearch')

def dns_shape(value):
    if value is None:return 'NULL'
    if type(value) is list:
        return 'EMPTY' if not value else 'CONFIGURED'
    return 'UNEXPECTED'

def dns_representation_only(old,new):
    """True only when the WHOLE fingerprint differs solely in null/[] DNS defaults."""
    same,config,env,host,mounts,network=differences(old,new)
    if same:return False
    if config or any(env) or mounts or network:return False
    if not host or any(field not in (x.upper() for x in DNS_KEYS) for field in host):
        return False
    a,b=old['HostConfig'],new['HostConfig']
    for key in DNS_KEYS:
        if a.get(key)==b.get(key):continue
        if set((dns_shape(a.get(key)),dns_shape(b.get(key))))!={'NULL','EMPTY'}:
            return False
    return True

def present(name,old,row,game_candidate=None):
    tag={'gaming-studio-j':'GAMES','v79-pos':'POS_API',
         'v79-pos-worker':'POS_WORKER','v79_course_builder':'ACADEMY',
         'v79-hub':'HUB','v79-tiquet-manager':'TIQUET'}[name]
    if row is None:
        emit(tag+'_PRESENT','NO');return False
    emit(tag+'_PRESENT','YES')
    state=row.get('State') or {}
    status=state.get('Status','unknown').upper()
    emit(tag+'_STATE',status if re.fullmatch('[A-Z_]{1,24}',status) else 'UNKNOWN')
    health=(state.get('Health') or {}).get('Status','none').upper()
    emit(tag+'_HEALTH',health if re.fullmatch('[A-Z_]{1,24}',health) else 'UNKNOWN')
    emit(tag+'_OOM','YES' if state.get('OOMKilled') else 'NO')
    emit(tag+'_RESTART_COUNT',str(max(0,min(99999,int(row.get('RestartCount',0))))))
    if old is None:
        emit(tag+'_BASELINE','NOT_PRESENT');return False
    emit(tag+'_ORIGINAL_IMAGE','MATCH' if old.get('Image')==row.get('Image') else 'DIFFERENT')
    emit(tag+'_CONTAINER_ID','MATCH' if old.get('Id') and old.get('Id')==row.get('Id') else 'RECREATED_OR_CHANGED')
    if tag=='GAMES':
        category=('ORIGINAL' if row.get('Image')==old.get('Image') else
                  'CANDIDATE' if game_candidate and row.get('Image')==game_candidate else 'OTHER')
        emit('GAMES_IMAGE_CLASS',category)
    same,fields,env,host,mounts,network=differences(old,row)
    emit(tag+'_RUNTIME_FINGERPRINT','MATCH' if same else 'DRIFT')
    emit(tag+'_CONFIG_CHANGED',','.join(fields) if fields else 'NONE')
    emit(tag+'_ENV_ADDED_REMOVED_CHANGED',','.join(str(x) for x in env))
    emit(tag+'_HOST_CHANGED',','.join(host) if host else 'NONE')
    emit(tag+'_MOUNTS_CHANGED','YES' if mounts else 'NO')
    emit(tag+'_NETWORKS_CHANGED','YES' if network else 'NO')
    good=(old.get('Image')==row.get('Image') and same and state.get('Running') is True and
          (health=='HEALTHY' or name=='v79-pos-worker' and health=='NONE'))
    emit(tag+'_ORIGINAL_VERIFIED','YES' if good else 'NO')
    if tag=='GAMES':
        shapes=[]
        for field in DNS_KEYS:
            shape_old=dns_shape(old['HostConfig'].get(field))
            shape_live=dns_shape(row['HostConfig'].get(field))
            shapes.append(shape_old+'_'+shape_live)
        emit('GAMES_DNS_DNS_SHAPES',shapes[0])
        emit('GAMES_DNS_OPTIONS_SHAPES',shapes[1])
        emit('GAMES_DNS_SEARCH_SHAPES',shapes[2])
        dns_ok=(row['Image']==old['Image'] and state.get('Running') is True
                and health=='HEALTHY' and dns_representation_only(old,row))
        emit('GAMES_EMPTY_DNS_REPRESENTATION_ONLY','YES' if dns_ok else 'NO')
        emit('GAMES_RECOVERY_CONFIG_ELIGIBLE','YES' if good or dns_ok else 'NO')

    return good

def server():
    if socket.gethostname()!='v79sl' or os.getuid()==0:return error('SERVER_IDENTITY_REJECTED')
    if not RUN.is_dir() or RUN.is_symlink() or RUN.stat().st_uid!=os.getuid() \
       or RUN.stat().st_mode & 0o077:return error('RUN_DIRECTORY_UNSAFE')
    try:
        before=restricted_json(RUN/'runtime-before.json')
        game_record=restricted_json(RUN/'Gaming-Studio-J-built-image.json')
        game_candidate=game_record['image_id']
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',game_candidate):
            return error('GAME_CANDIDATE_RECEIPT_INVALID')
        if before['gaming-studio-j']['Image']!=EXPECTED_GAMES:
            return error('GAME_BASELINE_IMAGE_UNEXPECTED')
    except Exception:
        return error('RUN_EVIDENCE_UNAVAILABLE')
    emit('MODE','READ_ONLY_NO_LOGS_NO_MUTATIONS')
    all_good=True
    recovery_compatible=True
    exact_preflight_identities=True
    for name in (*APPS,*SHARED):
        try:
            row=inspect(name)
            good=present(name,before.get(name),row,game_candidate)
            if name in APPS:
                all_good=all_good and good
                exact_preflight_identities=exact_preflight_identities and bool(row and
                    before.get(name,{}).get('Id')==row.get('Id'))
                if name=='gaming-studio-j' and row and before.get(name):
                    games_recovered=(good or
                        (row['Image']==before[name]['Image'] and
                         row['State'].get('Running') is True and
                         (row['State'].get('Health') or {}).get('Status')=='healthy' and
                         dns_representation_only(before[name],row)))
                    recovery_compatible=recovery_compatible and games_recovered
                else:
                    recovery_compatible=recovery_compatible and good
        except Exception:
            emit('STOP','INSPECT_OR_DIFF_FAILED')
            return 1
    try:
        diag=restricted_json(RUN/'gaming-studio-j-failed-startup-safe.json')
        categories=diag.get('categories')
        if isinstance(categories,list) and categories and all(isinstance(x,str) and
                         re.fullmatch('[A-Z_]{2,40}',x) for x in categories):
            emit('GAMES_FAILED_CANDIDATE_LOG_CATEGORY',','.join(categories))
        else:emit('GAMES_FAILED_CANDIDATE_LOG_CATEGORY','UNAVAILABLE')
    except Exception:
        emit('GAMES_FAILED_CANDIDATE_LOG_CATEGORY','UNAVAILABLE')
    emit('REMAINING_ORIGINALS_VERIFIED_NOW','YES' if all_good else 'NO')
    emit('REMAINING_RECOVERY_COMPATIBLE_NOW','YES' if recovery_compatible else 'NO')
    emit('EXACT_PREFAILURE_CONTAINER_IDENTITIES_MATCH','YES' if exact_preflight_identities else 'NO')
    emit('FROZEN_PLAN_IDENTITY_GATE','PASS' if exact_preflight_identities and all_good else 'FAIL_REPLAN_REQUIRED')
    emit('CUSTOMER_RELEASE','NO_GO')
    return 0

def acer():
    if socket.gethostname()=='v79sl' or os.getuid()==0:return error('ACER_NONROOT_REQUIRED')
    host='firelion@v79sl'
    ssh=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
         '-o','ConnectTimeout=12',host,'python3 -B - --server']
    try:
        p=subprocess.run(ssh,input=Path(__file__).read_bytes(),
             stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=120)
    except Exception:
        return error('SSH_AUDIT_UNAVAILABLE')
    for line in p.stdout.decode('utf8','replace').splitlines():
        if SAFE.fullmatch(line):print(line)
        else:return error('REDACTED_REMOTE_OUTPUT')
    if p.returncode:return error('REMOTE_AUDIT_FAILED')
    return 0

def self_test():
    row={'Config':{'Cmd':['node','server.js'],'Env':['PRIVATE_KEY=PRIVATE_SECRET']},
         'HostConfig':{'NetworkMode':'old'},'Mounts':[],
         'NetworkSettings':{'Networks':{'one':{}}}}
    changed=copy.deepcopy(row)
    changed['Config']['Env']=['PRIVATE_KEY=NEW_PRIVATE_SECRET']
    changed['HostConfig']['NetworkMode']='new'
    result=differences(row,changed)
    assert result[0] is False and result[2]==(0,0,1) and result[3]==['NETWORKMODE']
    assert 'PRIVATE_SECRET' not in str(result) and 'NEW_PRIVATE_SECRET' not in str(result)
    base=copy.deepcopy(row)
    base['HostConfig']={'Dns':None,'DnsOptions':None,'DnsSearch':None}
    live=copy.deepcopy(base)
    live['HostConfig']={'Dns':[],'DnsOptions':[],'DnsSearch':[]}
    assert dns_representation_only(base,live)
    assert dns_representation_only(live,base)
    assert not dns_representation_only(base,base)
    for key in DNS_KEYS:
        changed=copy.deepcopy(live)
        changed['HostConfig'][key]=['test.invalid']
        assert not dns_representation_only(base,changed)
    changed=copy.deepcopy(live)
    changed['HostConfig']['Privileged']=True
    assert not dns_representation_only(base,changed)
    changed=copy.deepcopy(live)
    changed['Config']['Env']=['PRIVATE_KEY=DIFFERENT_PRIVATE_SECRET']
    assert not dns_representation_only(base,changed)
    assert dns_shape(['PRIVATE_VALUE'])=='CONFIGURED'
    assert 'PRIVATE_SECRET' not in str(differences(base,live))
    assert base.get('Id')==live.get('Id') and not base.get('Id')
    assert not (base.get('Id') and base.get('Id')==live.get('Id'))
    emit('SELF_TEST','PASS')
    return 0

def main():
    args=argparse.ArgumentParser()
    args.add_argument('--server',action='store_true')
    args.add_argument('--self-test',action='store_true')
    selected=args.parse_args()
    if selected.self_test:return self_test()
    return server() if selected.server else acer()

if __name__=='__main__':
    sys.exit(main())
