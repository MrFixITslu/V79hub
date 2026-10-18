#!/usr/bin/env python3
"""Verify exact cached Academy candidate startup with synthetic data and no network.

DISPOSABLE Docker probe only. No production credentials, mounts, ports,
network, database, Compose or app changes. Auth-denial and health checked
inside the probe. Fail closed and preserve evidence when cleanup is uncertain.
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
import socket
import subprocess
import sys
import time

ROOT=Path('/home/firelion')
BASE=ROOT/'v79-recovery-replan.2prajz9h'
FAILED=ROOT/'v79-remaining-rollout.GCIN6i1p'
CORE=ROOT/'v79-portfolio-rollout.6kvFDd5e'/'rollout.py'
CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
NAME='v79_course_builder'
REVISION='584e07c9f5186e4aa10e87f931b2ea7194db93d4'
OWNED='v79.private-academy-isolated'
PROTECTED=('v79_course_builder','v79-pos','v79-pos-worker',
           'gaming-studio-j','v79-hub','v79-tiquet-manager')
MARKERS={
'SELF_TEST':{'PASS'},
'MODE':{'ISOLATED_ACADEMY_STARTUP'},
'ACADEMY_CANDIDATE':{'PINNED'},
'ACADEMY_ISOLATION':{'PASS'},
'ACADEMY_HEALTH':{'PASS'},
'ACADEMY_UNSIGNED_ADMIN':{'DENIED'},
'ACADEMY_OWNED_CLEANUP':{'PASS'},
'PRODUCTION_CONTAINERS':{'UNCHANGED'},
'DEPLOYMENT':{'NONE'},
'R1_CUSTOMER_RELEASE':{'NO_GO'},
}
class Stop(Exception):pass

def need(ok,code):
    if not ok:raise Stop(code)

def allowed(line):
    k,sep,v=line.partition('=')
    return bool(sep and (k in MARKERS and v in MARKERS[k] or
           k=='STOP' and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',v)))

def emit(k,v):
    line=f'{k}={v}'
    need(allowed(line),'OUTPUT_NOT_ALLOWED')
    print(line,flush=True)

def command(args,seconds=40):
    try:return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=seconds)
    except subprocess.TimeoutExpired:raise Stop('DOCKER_COMMAND_TIMEOUT') from None

def inspect(kind,key):
    p=command(['docker',kind,'inspect',key],seconds=35)
    if p.returncode!=0:return None
    try:
        rows=json.loads(p.stdout)
        need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),
             'INSPECT_INVALID')
        return rows[0]
    except (ValueError,TypeError):raise Stop('INSPECT_INVALID') from None

def privdir(p):
    need(p.is_dir() and not p.is_symlink() and p.stat().st_uid==os.getuid()
         and p.stat().st_mode & 0o077==0,'PRIVATE_DIRECTORY_CHANGED')

def privfile(p):
    need(p.is_file() and not p.is_symlink() and p.stat().st_uid==os.getuid()
         and p.stat().st_mode & 0o077==0,'PRIVATE_FILE_CHANGED')
    return json.loads(p.read_text())

def trusted_core():
    need(CORE.is_file() and not CORE.is_symlink(),'CORE_NOT_FOUND')
    b=CORE.read_bytes()
    need(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==CORE_BLOB,
         'CORE_HASH_CHANGED')
    spec=importlib.util.spec_from_file_location('trusted_portfolio_aca',CORE)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def create_args(image,token):
    probe='v79-isolated-academy-'+token
    return ['docker','create','--name',probe,'--label',OWNED+'='+token,
            '--pull','never','--network','none','--no-healthcheck',
            '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--memory','512m','--memory-swap','512m','--pids-limit','64','--cpus','0.75',
            '--user','1000:1000',
            '--tmpfs','/app/data:rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0700',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=16m,uid=1000,gid=1000,mode=0700',
            '--env','PORT=18081','--env','NODE_ENV=production',
            '--env','ACADEMY_STANDALONE_ADMIN_ENABLED=0',
            '--env','V79_PLATFORM_SHARED_SECRET=',
            '--env','ACADEMY_COURSE_PUBLISH_MODE=disabled',
            image]

def isolated(row,image,token):
    if not isinstance(row,dict):return False
    conf=row.get('Config') or {}
    host=row.get('HostConfig') or {}
    labels=conf.get('Labels') or {}
    if (row.get('Name')!='/v79-isolated-academy-'+token or
        labels.get(OWNED)!=token or row.get('Image')!=image):return False
    if 'com.docker.compose.project' in labels:return False
    if (host.get('NetworkMode')!='none' or host.get('PortBindings') or
        host.get('Privileged') or host.get('ReadonlyRootfs') is not True or
        host.get('Binds') or host.get('Mounts')):return False
    if host.get('Memory')!=512*1024**2 or host.get('PidsLimit')!=64:return False
    if (host.get('RestartPolicy') or {}).get('Name')!='no':return False
    if (host.get('Tmpfs') or {}).keys()!={'/app/data','/tmp'}:return False
    if set((row.get('NetworkSettings') or {}).get('Networks',{})) not in (set(),{'none'}):return False
    if {m.get('Destination') for m in row.get('Mounts') or []}!={'/app/data','/tmp'}:return False
    if any(m.get('Type')!='tmpfs' for m in row.get('Mounts') or []):return False
    env=conf.get('Env') or []
    keys={x.partition('=')[0] for x in env}
    if {'DATABASE_URL','REDIS_URL','POSTGRES_PASSWORD','ADMIN_PASSWORD','V79_TIQUET_LAUNCH_SECRET'}&keys:
        return False
    for x in env:
        if x.startswith('V79_PLATFORM_SHARED_SECRET=') and x!='V79_PLATFORM_SHARED_SECRET=':
            return False
    return True

def cleanup(probe,token,image):
    row=inspect('container',probe)
    if row is None:return True
    need(isolated(row,image,token),'FOREIGN_RESOURCE_REFUSE_CLEANUP')
    try:
        ret=command(['docker','rm','-f','-v',probe],seconds=105)
        if ret.returncode==0 and inspect('container',probe) is None:return True
    except Stop:pass
    # Docker may complete daemon-side removal after the command client times out.
    for _ in range(10):
        if inspect('container',probe) is None:return True
        time.sleep(2)
    raise Stop('ISOLATED_ACADEMY_CLEANUP_UNCONFIRMED')

def synthetic_health():
    return ("test \"$(wget -q -O - http://127.0.0.1:18081/healthz)\" = "
            "'{\"status\":\"ok\"}'")

def unsigned_denial():
    # BusyBox wget returns nonzero for HTTP 401. Test status code via stderr
    # suppression avoided: use Node bundled in the actual candidate, no secret
    # response body or raw logs printed, and require exact 401 status.
    return ("const h=require('http');"
            "h.get('http://127.0.0.1:18081/api/courses',r=>{"
            "r.resume();process.exitCode=(r.statusCode===401?0:3)})."
            "on('error',()=>{process.exitCode=4})")

def server():
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'SERVER_NONROOT_REQUIRED')
    os.umask(0o077)
    for p in (BASE,FAILED,CORE.parent,FAILED/'checkpoint'):privdir(p)
    lock=ROOT/'.v79-portfolio-rollout.lock'
    need(lock.is_file() and not lock.is_symlink(),'LOCK_MISSING')
    with lock.open('rb') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('OTHER_ROLLOUT_RUNNING')
        r=trusted_core()
        baseline=privfile(BASE/'runtime-before.json')
        receipt=privfile(BASE/'plan-summary.json')
        built=privfile(FAILED/'V79acaedmy-built-image.json')
        manifest=privfile(FAILED/'checkpoint/manifest.json')
        need(set(baseline)==set(PROTECTED[:4]) and
             receipt.get('status')=='RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE' and
             receipt.get('deployment_authorization')=='NO' and
             receipt.get('restore_acceptance')=='NOT_PERFORMED' and
             receipt.get('current_runtime_container_ids',{}).get(NAME)==baseline[NAME]['Id'] and
             receipt.get('checkpoint_manifest_sha256')==
               hashlib.sha256((FAILED/'checkpoint/manifest.json').read_bytes()).hexdigest(),
             'BASELINE_CHANGED')
        image=built.get('image_id')
        need(isinstance(image,str) and re.fullmatch(r'sha256:[0-9a-f]{64}',image) and
             built.get('repo')=='V79acaedmy' and built.get('source_commit')==REVISION and
             manifest.get('status')=='CAPTURED_NOT_RESTORE_TESTED' and
             manifest.get('candidates',{}).get(NAME)==image,'CACHED_IMAGE_CHANGED')
        img=inspect('image',image)
        need(img and img.get('Id')==image and
             (img.get('Config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')==REVISION,
             'CANDIDATE_IMAGE_INVALID')
        before={name:inspect('container',name) for name in PROTECTED}
        for name in PROTECTED:
            now=before[name]
            need(now and now['State'].get('Running') is True,'PRODUCTION_CONTAINER_MISSING')
            if name!='v79-pos-worker':
                need(now['State'].get('Health',{}).get('Status')=='healthy',
                     'PRODUCTION_HEALTH_CHANGED')
            if name in baseline:
                need(now['Id']==baseline[name]['Id'] and
                     r.fingerprint(now)==r.fingerprint(baseline[name]),
                     'RECOVERY_BASELINE_DRIFT')
        emit('MODE','ISOLATED_ACADEMY_STARTUP')
        emit('ACADEMY_CANDIDATE','PINNED')
        token=secrets.token_hex(7)
        probe='v79-isolated-academy-'+token
        need(inspect('container',probe) is None,'PROBE_NAME_COLLISION')
        cleanup_ok=False
        try:
            result=command(create_args(image,token),seconds=45)
            need(result.returncode==0,'ACADEMY_CREATE_FAILED')
            need(isolated(inspect('container',probe),image,token),
                 'ISOLATION_NOT_PROVEN')
            emit('ACADEMY_ISOLATION','PASS')
            started=command(['docker','start',probe],seconds=45)
            need(started.returncode==0,'ACADEMY_START_FAILED')
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                result=command(['docker','exec','--user','1000:1000',probe,
                                '/bin/sh','-c',synthetic_health()],seconds=10)
                if result.returncode==0:
                    emit('ACADEMY_HEALTH','PASS')
                    break
                state=inspect('container',probe)
                need(state and state['State'].get('Running') is True and
                     not state['State'].get('OOMKilled'),'ACADEMY_PROCESS_EXITED')
                time.sleep(3)
            else:raise Stop('ACADEMY_HEALTH_TIMEOUT')
            denied=command(['docker','exec','--user','1000:1000',probe,
                            'node','-e',unsigned_denial()],seconds=12)
            need(denied.returncode==0,'ACADEMY_UNSIGNED_ADMIN_NOT_DENIED')
            emit('ACADEMY_UNSIGNED_ADMIN','DENIED')
        finally:
            cleanup_ok=cleanup(probe,token,image)
            if cleanup_ok:emit('ACADEMY_OWNED_CLEANUP','PASS')
        for name in PROTECTED:
            now=inspect('container',name)
            prev=before[name]
            need(now and now['Id']==prev['Id'] and now['Image']==prev['Image'] and
                 now['State'].get('Running') is True and
                 r.fingerprint(now)==r.fingerprint(prev),
                 'PRODUCTION_RUNTIME_CHANGED')
            if name!='v79-pos-worker':
                need(now['State'].get('Health',{}).get('Status')=='healthy',
                     'PRODUCTION_HEALTH_CHANGED')
        emit('PRODUCTION_CONTAINERS','UNCHANGED')
        emit('DEPLOYMENT','NONE')
        emit('R1_CUSTOMER_RELEASE','NO_GO')

def self_test():
    image='sha256:'+'f'*64;token='a'*14
    args=create_args(image,token)
    assert args[:2]==['docker','create']
    assert all(x in args for x in ('none','--no-healthcheck','--read-only',
          '--cap-drop','ALL','--pids-limit','64','--user','1000:1000'))
    assert not any(x in args for x in ('--publish','-p','--volume','-v','--mount',
          '--privileged','proxy_network','DATABASE_URL','REDIS_URL'))
    valid={'Name':'/v79-isolated-academy-'+token,'Image':image,
      'Config':{'Labels':{OWNED:token},'Env':['PORT=18081','NODE_ENV=production']},
      'HostConfig':{'NetworkMode':'none','PortBindings':None,'Privileged':False,
         'ReadonlyRootfs':True,'Binds':None,'Mounts':None,'RestartPolicy':{'Name':'no'},
         'Memory':512*1024**2,'PidsLimit':64,'Tmpfs':{'/app/data':'a','/tmp':'b'}},
      'Mounts':[{'Type':'tmpfs','Destination':'/app/data'},
                {'Type':'tmpfs','Destination':'/tmp'}],
      'NetworkSettings':{'Networks':{}}}
    assert isolated(valid,image,token)
    changed=json.loads(json.dumps(valid));changed['HostConfig']['NetworkMode']='proxy_network'
    assert not isolated(changed,image,token)
    changed=json.loads(json.dumps(valid));changed['Mounts'].append({'Type':'bind','Destination':'/secret'})
    assert not isolated(changed,image,token)
    changed=json.loads(json.dumps(valid));changed['Config']['Env'].append('ADMIN_PASSWORD=TOPSECRET')
    assert not isolated(changed,image,token)
    changed=json.loads(json.dumps(valid));changed['HostConfig']['Memory']=0
    assert not isolated(changed,image,token)
    changed=json.loads(json.dumps(valid));changed['Config']['Labels'][OWNED]='b'*14
    assert not isolated(changed,image,token)
    assert not allowed('ENV=SECRET')
    emit('SELF_TEST','PASS')
def acer():
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
          '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    response=subprocess.run(args,input=Path(__file__).read_bytes(),
                            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=330)
    for line in response.stdout.decode('utf8','replace').splitlines():
        need(allowed(line),'REMOTE_OUTPUT_NOT_ALLOWED')
        print(line,flush=True)
    need(response.returncode==0,'ACADEMY_ISOLATED_REHEARSAL_FAILED')
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--server',action='store_true')
    options=p.parse_args()
    if options.self_test:self_test()
    elif options.server:server()
    else:acer()
if __name__=='__main__':
    try:main()
    except Exception as ex:
        code=str(ex) if isinstance(ex,Stop) and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',str(ex)) \
             else 'ACADEMY_ISOLATED_ERROR_REDACTED'
        print('STOP='+code,flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
        sys.exit(1)
