#!/usr/bin/env python3
"""G3? No: GCIN6i1p Gaming Studio J isolated actual startup rehearsal only.

Acer->v79sl; *exact pinned Games candidate* starts without networking, ports,
production env, binds or volumes. Disposable read-only rootfs + synthetic tmpfs.
No Docker Compose up, no DB, no prod probes, no customer deployment.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import time

ROOT=Path('/home/firelion')
BASE=ROOT/'v79-recovery-replan.2prajz9h'
FAILED=ROOT/'v79-remaining-rollout.GCIN6i1p'
CORE=ROOT/'v79-portfolio-rollout.6kvFDd5e'/'rollout.py'
CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
NAME='gaming-studio-j'
OLD_IMAGE='sha256:4039d9ab72c0cc99c5d18c92714678a9a8e05ef26177e85bbe3d56da834b07e7'
REVISION='17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'
OWNERSHIP='v79.private-games-isolated'
SAFE=re.compile(r'[A-Z][A-Z0-9_]{0,100}=[A-Z0-9_,.-]{1,160}\Z')
STATE={'SELF_TEST':'PASS','MODE':'ISOLATED_GAMES_STARTUP',
       'RECOVERY_BASELINE':'UNCHANGED',
       'GAMES_IMAGE_PROVENANCE':'PASS',
       'GAMES_ISOLATION':'VERIFIED',
       'GAMES_ACTUAL_HTTP_HEALTH':'PASS',
       'GAMES_OWNED_PROBE_CLEANUP':'PASS',
       'PRODUCTION_CONTAINERS':'UNCHANGED',
       'NEW_RELEASE_DEPLOYMENT':'NONE',
       'R1_CUSTOMER_RELEASE':'NO_GO'}
class Stop(Exception):pass

def need(ok,code):
    if not ok:raise Stop(code)
def allowed(line):
    k,sep,v=line.partition('=')
    if not sep or not SAFE.fullmatch(line):return False
    if k=='STOP':return bool(re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',v))
    return k in STATE and STATE[k]==v
def emit(k,v):
    s=f'{k}={v}'
    need(allowed(s),'OUTPUT_REDACTED')
    print(s,flush=True)
def run(argv,timeout=35):
    try:
        return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Stop('DOCKER_OPERATION_TIMEOUT') from None
def private(path):
    need(path.is_file() and not path.is_symlink()
         and path.stat().st_uid==os.getuid()
         and path.stat().st_mode & 0o077==0,'PRIVATE_EVIDENCE_UNSAFE')
    return json.loads(path.read_text())
def privatedir(path):
    need(path.is_dir() and not path.is_symlink()
         and path.stat().st_uid==os.getuid()
         and path.stat().st_mode & 0o077==0,'PRIVATE_DIRECTORY_UNSAFE')
def trusted_core():
    data=CORE.read_bytes()
    h=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    need(h==CORE_BLOB,'VERIFIED_CORE_CHANGED')
    spec=importlib.util.spec_from_file_location('v79_core_isolated_games',CORE)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj
def docker_inspect(kind,name):
    command=['docker',kind,'inspect',name]
    p=run(command)
    if p.returncode:return None
    try:
        obj=json.loads(p.stdout)
        return obj[0] if isinstance(obj,list) and len(obj)==1 else None
    except Exception:raise Stop('DOCKER_INSPECT_UNAVAILABLE') from None

def isolated_command(candidate,identity,probe):
    return ['docker','create','--name',probe,
            '--label',OWNERSHIP+'='+identity,
            '--pull','never','--network','none',
            '--read-only','--cap-drop','ALL','--cap-add','NET_BIND_SERVICE',
            '--memory','256m','--memory-swap','256m','--pids-limit','64',
            '--cpus','0.5',
            '--tmpfs','/app/runtime:rw,nosuid,nodev,size=16m,uid=1000,gid=1000,mode=0700',
            '--env','PORT=18080','--env','NODE_ENV=production',
            '--env','OLLAMA_URL=','--env','ADMIN_PASSWORD=',
            '--env','ADMIN_SESSION_SECRET=',
            '--env','V79_PLATFORM_SHARED_SECRET_FILE=/nonexistent-synthetic-token',
            candidate]

def isolated(row,identity,image):
    if not row:return False
    labels=(row.get('Config') or {}).get('Labels') or {}
    host=row.get('HostConfig') or {}
    if labels.get(OWNERSHIP)!=identity or row.get('Image')!=image:return False
    if host.get('NetworkMode')!='none' or host.get('PortBindings'):return False
    if host.get('Privileged') or host.get('ReadonlyRootfs') is not True:return False
    if host.get('Binds') or host.get('Mounts'):return False
    if host.get('RestartPolicy',{}).get('Name')!='no':return False
    if (host.get('Tmpfs') or {}).get('/app/runtime') is None:return False
    if any(m.get('Type')!='tmpfs' or m.get('Destination')!='/app/runtime'
           for m in (row.get('Mounts') or [])):return False
    networks=set(row.get('NetworkSettings',{}).get('Networks',{}))
    if networks not in (set(),{'none'}):return False
    return True

def cleanup(probe,identity,image):
    row=docker_inspect('container',probe)
    if row is None:return True
    need(isolated(row,identity,image),'UNSAFE_FOREIGN_PROBE_REFUSE_CLEANUP')
    try:
        result=run(['docker','rm','-fv',probe],timeout=90)
    except Stop:
        need(docker_inspect('container',probe) is None,'ISOLATED_CLEANUP_TIMEOUT')
        return True
    need(result.returncode==0 or docker_inspect('container',probe) is None,
         'ISOLATED_CLEANUP_FAILED')
    need(docker_inspect('container',probe) is None,'ISOLATED_PROBE_REMAINS')
    return True

def server():
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'SERVER_NONROOT_REQUIRED')
    os.umask(0o077)
    protected=tuple(dict.fromkeys((*('v79_course_builder','v79-pos','v79-pos-worker','gaming-studio-j'),
                                    'v79-hub','v79-tiquet-manager')))
    for p in (BASE,FAILED,CORE.parent):privatedir(p)
    privatedir(FAILED/'checkpoint')
    need(CORE.is_file() and not CORE.is_symlink(),'VERIFIED_CORE_MISSING')
    with (ROOT/'.v79-portfolio-rollout.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('ANOTHER_ROLLOUT_RUNNING')
        r=trusted_core()
        receipt=private(BASE/'plan-summary.json')
        old=private(BASE/'runtime-before.json')
        saved=private(FAILED/'Gaming-Studio-J-built-image.json')
        manifest=private(FAILED/'checkpoint/manifest.json')
        need(receipt.get('status')=='RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE'
             and receipt.get('deployment_authorization')=='NO'
             and receipt.get('restore_acceptance')=='NOT_PERFORMED'
             and receipt.get('checkpoint_manifest_sha256')==
                 hashlib.sha256((FAILED/'checkpoint/manifest.json').read_bytes()).hexdigest(),
             'RECOVERY_BASELINE_CHANGED')
        need(receipt.get('current_runtime_container_ids',{}).get(NAME)==old[NAME]['Id']
             and old[NAME]['Image']==OLD_IMAGE,'RECOVERY_IDENTITY_CHANGED')
        need(manifest.get('status')=='CAPTURED_NOT_RESTORE_TESTED' and
             manifest.get('candidates',{}).get(NAME)==saved.get('image_id') and
             saved.get('repo')=='Gaming-Studio-J' and
             saved.get('source_commit')==REVISION,'CANDIDATE_PROVENANCE_CHANGED')
        candidate=saved['image_id']
        need(re.fullmatch(r'sha256:[0-9a-f]{64}',candidate),'CANDIDATE_ID_INVALID')
        record=docker_inspect('image',candidate)
        need(record and record.get('Id')==candidate and
             (record.get('Config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')==REVISION,
             'CANDIDATE_IMAGE_INVALID')
        live_before={item:docker_inspect('container',item) for item in protected}
        for item in protected:
            current=live_before[item]
            need(current and current['State'].get('Running') is True,
                 'LIVE_PROTECTED_CONTAINER_NOT_RUNNING')
            if item!='v79-pos-worker':
                need(current['State'].get('Health',{}).get('Status')=='healthy',
                     'LIVE_PROTECTED_CONTAINER_UNHEALTHY')
            if item in old:
                need(current['Id']==old[item]['Id'] and
                     current['Image']==old[item]['Image'] and
                     r.fingerprint(current)==r.fingerprint(old[item]),
                     'LIVE_RECOVERY_BASELINE_CHANGED')
        emit('MODE','ISOLATED_GAMES_STARTUP')
        emit('RECOVERY_BASELINE','UNCHANGED')
        emit('GAMES_IMAGE_PROVENANCE','PASS')
        identity=secrets.token_hex(7)
        probe='v79-isolated-games-'+identity
        need(docker_inspect('container',probe) is None,'OWNED_PROBE_NAME_COLLISION')
        cleaned=False
        try:
            result=run(isolated_command(candidate,identity,probe),timeout=45)
            need(result.returncode==0,'ISOLATED_GAMES_CREATE_FAILED')
            row=docker_inspect('container',probe)
            need(isolated(row,identity,candidate),'ISOLATED_GAMES_CONFIG_NOT_VERIFIED')
            emit('GAMES_ISOLATION','VERIFIED')
            result=run(['docker','start',probe],timeout=40)
            need(result.returncode==0,'ISOLATED_GAMES_START_FAILED')
            deadline=time.monotonic()+75
            health_cmd=['docker','exec','--user','1000:1000',probe,'/bin/sh','-c',
                        'test "$(wget -q -O - http://127.0.0.1:18080/healthz)" = "ok"']
            while time.monotonic()<deadline:
                p=run(health_cmd,timeout=10)
                if p.returncode==0:
                    emit('GAMES_ACTUAL_HTTP_HEALTH','PASS')
                    break
                probe_state=docker_inspect('container',probe)
                need(probe_state and probe_state['State'].get('Running') is True
                     and not probe_state['State'].get('OOMKilled'),'ISOLATED_GAMES_PROCESS_EXITED')
                time.sleep(3)
            else:raise Stop('ISOLATED_GAMES_HTTP_NOT_READY')
        finally:
            cleaned=cleanup(probe,identity,candidate)
            if cleaned:emit('GAMES_OWNED_PROBE_CLEANUP','PASS')
        for item in protected:
            now=docker_inspect('container',item)
            before=live_before[item]
            need(now and now['Id']==before['Id'] and
                 now['Image']==before['Image'] and
                 now['State'].get('Running') is True and
                 r.fingerprint(now)==r.fingerprint(before),
                 'PROTECTED_RUNTIME_CHANGED')
            if item!='v79-pos-worker':
                need(now['State'].get('Health',{}).get('Status')=='healthy',
                     'PROTECTED_HEALTH_CHANGED')
        emit('PRODUCTION_CONTAINERS','UNCHANGED')
        emit('NEW_RELEASE_DEPLOYMENT','NONE')
        emit('R1_CUSTOMER_RELEASE','NO_GO')

def self_test():
    im='sha256:'+'a'*64;idx='b'*14
    args=isolated_command(im,idx,'v79-isolated-games-'+idx)
    assert args[0:2]==['docker','create']
    for token in ('--network','none','--read-only','--pull','never','--cap-drop',
                  'ALL','--cap-add','NET_BIND_SERVICE','--pids-limit','64'):
        assert token in args
    assert not any(a in args for a in ('--publish','--volume','-v','--mount','--privileged',
                                      'proxy_network','DATABASE_URL','REDIS_URL'))
    row={'Image':im,'Config':{'Labels':{OWNERSHIP:idx}},
         'HostConfig':{'NetworkMode':'none','PortBindings':None,'Privileged':False,
                       'ReadonlyRootfs':True,'Binds':None,'Mounts':None,
                       'RestartPolicy':{'Name':'no'},'Tmpfs':{'/app/runtime':'synthetic'}},
         'Mounts':[],'NetworkSettings':{'Networks':{}}}
    assert isolated(row,idx,im)
    row['NetworkSettings']['Networks']={'none':{}}
    assert isolated(row,idx,im)
    row['NetworkSettings']['Networks']={'proxy_network':{}}
    assert not isolated(row,idx,im)
    row['NetworkSettings']['Networks']={'none':{}}
    row['HostConfig']['NetworkMode']='proxy_network'
    assert not isolated(row,idx,im)
    row['HostConfig']['NetworkMode']='none'
    row['Mounts']=[{'Type':'bind','Destination':'/app/runtime'}]
    assert not isolated(row,idx,im)
    assert not allowed('PRIVATE_SECRET=something')
    emit('SELF_TEST','PASS')

def acer():
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    cmd=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
         '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    p=subprocess.run(cmd,input=Path(__file__).read_bytes(),
         stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=240)
    for line in p.stdout.decode('utf8','replace').splitlines():
        need(allowed(line),'REMOTE_OUTPUT_REDACTED')
        print(line,flush=True)
    need(p.returncode==0,'GAMES_ISOLATED_REHEARSAL_FAILED')

def main():
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true')
    p.add_argument('--server',action='store_true');args=p.parse_args()
    if args.self_test:self_test()
    elif args.server:server()
    else:acer()
if __name__=='__main__':
    try:main()
    except Exception as e:
        code=str(e) if isinstance(e,Stop) and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',str(e)) \
             else 'GAMES_ISOLATED_ERROR_REDACTED'
        print('STOP='+code,flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
        sys.exit(1)
