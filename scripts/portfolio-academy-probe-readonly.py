#!/usr/bin/env python3
"""Read-only Academy probe reconciliation after strict startup/cleanup refusal.

Acer->v79sl; no Docker changes, no raw Docker output, no secrets. Only reads
the exact owner-labeled disposable probe and six protected live containers.
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
BASE=ROOT/'v79-recovery-replan.2prajz9h'
FAILED=ROOT/'v79-remaining-rollout.GCIN6i1p'
ACCEPTED=ROOT/'v79-portfolio-rollout.6kvFDd5e'
CORE=ACCEPTED/'rollout.py'
CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
OWNER='v79.private-academy-isolated'
NAME=re.compile(r'v79-isolated-academy-([0-9a-f]{14})\Z')
IMAGE=re.compile(r'sha256:[0-9a-f]{64}\Z')
PROTECTED=('v79_course_builder','v79-pos','v79-pos-worker','gaming-studio-j',
           'v79-hub','v79-tiquet-manager')
FALLBACK=('v79_course_builder','v79-pos','v79-pos-worker','gaming-studio-j')
FIELDS={
 'SELF_TEST':('PASS',),
 'MODE':('ACADEMY_CLEANUP_READ_ONLY',),
 'PRODUCTION_RUNTIME':('UNCHANGED','DRIFT','UNVERIFIED'),
 'PRODUCTION_HEALTH':('PASS','FAIL','UNVERIFIED'),
 'PROBE_COUNT':('ZERO','ONE','MULTIPLE'),
 'PROBE_STATUS':('ABSENT','CREATED','RUNNING','EXITED','PAUSED','RESTARTING','REMOVING','DEAD','UNKNOWN'),
 'PROBE_NAME_LABEL':('PASS','FAIL','ABSENT','MULTIPLE'),
 'PROBE_IMAGE':('MATCH','DIFFERENT','ABSENT','MULTIPLE','UNKNOWN'),
 'PROBE_HOST_ISOLATION':('PASS','FAIL','ABSENT','MULTIPLE'),
 'PROBE_TMPFS_DECLARATION':('PASS','FAIL','ABSENT','MULTIPLE'),
 'PROBE_MOUNTS':('NOT_REALIZED','SYNTHETIC_TMPFS','UNEXPECTED','ABSENT','MULTIPLE'),
 'PROBE_ENVIRONMENT':('SYNTHETIC_ONLY','UNSAFE','ABSENT','MULTIPLE'),
 'STRICT_VALIDATOR':('PASS','FAIL','ABSENT','MULTIPLE'),
 'STRICT_FAILURE_ONLY_MOUNTS':('YES','NO','ABSENT','MULTIPLE'),
 'CLEANUP_REQUIRED':('NO','YES_REVIEW','UNKNOWN'),
 'ACTION_TAKEN':('NONE',),
 'R1_CUSTOMER_RELEASE':('NO_GO',),
}
class Stop(Exception):pass
def require(c,code):
    if not c:raise Stop(code)
def safe(s):
    k,sep,v=s.partition('=')
    return bool(sep and ((k in FIELDS and v in FIELDS[k]) or
            (k=='STOP' and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',v))))
def emit(k,v):
    s=k+'='+str(v)
    require(safe(s),'OUTPUT_REDACTED')
    print(s,flush=True)
def call(args,timeout=40):
    try:
        return subprocess.run(args,stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL,timeout=timeout)
    except subprocess.TimeoutExpired:raise Stop('DOCKER_READ_TIMEOUT') from None
def inspect_container(name):
    p=call(['docker','container','inspect',name])
    if p.returncode:return None
    try:
        j=json.loads(p.stdout)
        require(isinstance(j,list) and len(j)==1 and isinstance(j[0],dict),
                'CONTAINER_INSPECT_BAD_SHAPE')
        return j[0]
    except (ValueError,TypeError):raise Stop('CONTAINER_INSPECT_INVALID') from None
def owner_ids():
    p=call(['docker','container','ls','--all','--no-trunc','--quiet',
            '--filter','label='+OWNER])
    require(p.returncode==0,'OWNER_FILTER_QUERY_FAILED')
    result=p.stdout.decode('ascii','replace').splitlines()
    require(all(re.fullmatch(r'[0-9a-f]{64}',x) for x in result) and
            len(set(result))==len(result),'OWNER_FILTER_RESULT_INVALID')
    return result
def private_dir(p):
    require(p.is_dir() and not p.is_symlink() and p.stat().st_uid==os.getuid()
            and p.stat().st_mode & 0o077==0,'PRIVATE_DIRECTORY_UNSAFE')
def private_file(p):
    require(p.is_file() and not p.is_symlink() and p.stat().st_uid==os.getuid()
            and p.stat().st_mode & 0o077==0,'PRIVATE_FILE_UNSAFE')
    return json.loads(p.read_text())
def trusted_core():
    require(CORE.is_file() and not CORE.is_symlink() and CORE.stat().st_uid==os.getuid()
            and CORE.stat().st_mode & 0o077==0,'ACCEPTED_CORE_UNSAFE')
    raw=CORE.read_bytes()
    require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==CORE_BLOB,
            'ACCEPTED_CORE_CHANGED')
    spec=importlib.util.spec_from_file_location('v79_academy_cleanup_core',CORE)
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    return c

def probe_shape(row,candidate):
    conf=row.get('Config') or {}
    host=row.get('HostConfig') or {}
    labels=conf.get('Labels') or {}
    match=NAME.fullmatch(row.get('Name','').lstrip('/'))
    owner=bool(match and labels.get(OWNER)==match[1] and
               'com.docker.compose.project' not in labels)
    image=row.get('Image')==candidate
    networks=set((row.get('NetworkSettings') or {}).get('Networks') or {})
    opts=set(str(x).lower() for x in (host.get('SecurityOpt') or []))
    caps=set(str(x).lower() for x in (host.get('CapDrop') or []))
    secure=(host.get('NetworkMode')=='none' and networks in (set(),{'none'}) and
            not host.get('PortBindings') and not host.get('Privileged') and
            host.get('ReadonlyRootfs') is True and
            not host.get('Binds') and not host.get('Mounts') and
            (host.get('RestartPolicy') or {}).get('Name')=='no' and
            host.get('Memory')==512*1024**2 and
            host.get('PidsLimit')==64 and
            conf.get('User')=='1000:1000' and
            'all' in caps and
            any(x.startswith('no-new-privileges') for x in opts))
    tmpfs=set((host.get('Tmpfs') or {}).keys())=={'/app/data','/tmp'}
    mounts=row.get('Mounts') or []
    if not mounts:mclass='NOT_REALIZED'
    elif (len(mounts)==2 and
          {m.get('Destination') for m in mounts}=={'/app/data','/tmp'} and
          all(m.get('Type')=='tmpfs' for m in mounts)):
        mclass='SYNTHETIC_TMPFS'
    else:mclass='UNEXPECTED'
    env=conf.get('Env') or []
    envmap={}
    for entry in env:
        if not isinstance(entry,str) or '=' not in entry:return (owner,image,secure,tmpfs,mclass,False,False,False)
        k,_,v=entry.partition('=')
        if k in envmap:return (owner,image,secure,tmpfs,mclass,False,False,False)
        envmap[k]=v
    forbid={'DATABASE_URL','REDIS_URL','POSTGRES_PASSWORD','ADMIN_PASSWORD',
            'V79_TIQUET_LAUNCH_SECRET','ADMIN_RESET_TOKEN','GEMINI_API_KEY',
            'GOOGLE_API_KEY','OPENAI_API_KEY'}
    synthetic=not bool(set(envmap)&forbid) and all(
        envmap.get(k)==v for k,v in (
          ('PORT','18081'),('NODE_ENV','production'),
          ('ACADEMY_STANDALONE_ADMIN_ENABLED','0'),
          ('V79_PLATFORM_SHARED_SECRET',''),
          ('ACADEMY_COURSE_PUBLISH_MODE','disabled')))
    strict=(owner and image and
            host.get('NetworkMode')=='none' and not host.get('PortBindings') and
            not host.get('Privileged') and host.get('ReadonlyRootfs') is True and
            not host.get('Binds') and not host.get('Mounts') and
            host.get('Memory')==512*1024**2 and host.get('PidsLimit')==64 and
            (host.get('RestartPolicy') or {}).get('Name')=='no' and
            tmpfs and networks in (set(),{'none'}) and
            {m.get('Destination') for m in mounts}=={'/app/data','/tmp'} and
            all(m.get('Type')=='tmpfs' for m in mounts) and
            not bool(set(envmap)&{'DATABASE_URL','REDIS_URL','POSTGRES_PASSWORD',
                                  'ADMIN_PASSWORD','V79_TIQUET_LAUNCH_SECRET'}) and
            envmap.get('V79_PLATFORM_SHARED_SECRET')=='')
    # The old strict validator may reject the image at create-time solely
    # because Docker hasn't materialized HostConfig.Tmpfs into .Mounts.
    mounts_only=bool(owner and image and secure and tmpfs and synthetic and
                     mclass=='NOT_REALIZED' and
                     (row.get('State') or {}).get('Status')=='created')
    return (owner,image,secure,tmpfs,mclass,synthetic,strict,mounts_only)

def production(c,reference,before):
    unchanged=True;healthy=True
    for name in PROTECTED:
        old=(reference.get(name) if name in reference else before.get(name))
        now=inspect_container(name)
        if not old or not now:return 'UNVERIFIED','UNVERIFIED'
        if (now.get('Id')!=old.get('Id') or now.get('Image')!=old.get('Image') or
            c.fingerprint(now)!=c.fingerprint(old) or
            now.get('State',{}).get('Running') is not True):
            unchanged=False
        if name!='v79-pos-worker' and (now.get('State',{}).get('Health') or {}).get('Status')!='healthy':
            healthy=False
    return ('UNCHANGED' if unchanged else 'DRIFT','PASS' if healthy else 'FAIL')

def audit():
    require(socket.gethostname()=='v79sl' and os.getuid()!=0,'SERVER_NONROOT_REQUIRED')
    for p in (BASE,FAILED,ACCEPTED):private_dir(p)
    lock=ROOT/'.v79-portfolio-rollout.lock'
    require(lock.is_file() and not lock.is_symlink(),'ROLLOUT_LOCK_MISSING')
    with lock.open('rb') as l:
        try:fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('OTHER_ROLLOUT_RUNNING')
        c=trusted_core()
        report=private_file(BASE/'plan-summary.json')
        b=private_file(BASE/'runtime-before.json')
        earlier=private_file(FAILED/'runtime-before.json')
        manifest=private_file(FAILED/'checkpoint/manifest.json')
        cached=private_file(FAILED/'V79acaedmy-built-image.json')
        require(set(b)==set(FALLBACK) and
                report.get('status')=='RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE' and
                report.get('deployment_authorization')=='NO' and
                report.get('current_runtime_container_ids')=={n:b[n]['Id'] for n in FALLBACK} and
                report.get('checkpoint_manifest_sha256')==
                  hashlib.sha256((FAILED/'checkpoint/manifest.json').read_bytes()).hexdigest(),
                'BASELINE_PROVENANCE_CHANGED')
        candidate=cached.get('image_id')
        require(isinstance(candidate,str) and IMAGE.fullmatch(candidate) and
                cached.get('repo')=='V79acaedmy' and
                cached.get('source_commit')=='584e07c9f5186e4aa10e87f931b2ea7194db93d4' and
                manifest.get('candidates',{}).get('v79_course_builder')==candidate,
                'ACADEMY_CANDIDATE_CHANGED')
        emit('MODE','ACADEMY_CLEANUP_READ_ONLY')
        pstate,phealth=production(c,b,earlier)
        emit('PRODUCTION_RUNTIME',pstate)
        emit('PRODUCTION_HEALTH',phealth)
        ids=owner_ids()
        emit('PROBE_COUNT','ZERO' if not ids else 'ONE' if len(ids)==1 else 'MULTIPLE')
        if not ids:
            emit('PROBE_STATUS','ABSENT')
            emit('PROBE_NAME_LABEL','ABSENT')
            emit('PROBE_IMAGE','ABSENT')
            emit('PROBE_HOST_ISOLATION','ABSENT')
            emit('PROBE_TMPFS_DECLARATION','ABSENT')
            emit('PROBE_MOUNTS','ABSENT')
            emit('PROBE_ENVIRONMENT','ABSENT')
            emit('STRICT_VALIDATOR','ABSENT')
            emit('STRICT_FAILURE_ONLY_MOUNTS','ABSENT')
            emit('CLEANUP_REQUIRED','NO')
        elif len(ids)>1:
            for key in ('PROBE_STATUS','PROBE_NAME_LABEL','PROBE_IMAGE',
                        'PROBE_HOST_ISOLATION','PROBE_TMPFS_DECLARATION','PROBE_MOUNTS',
                        'PROBE_ENVIRONMENT','STRICT_VALIDATOR','STRICT_FAILURE_ONLY_MOUNTS'):
                emit(key,'MULTIPLE')
            emit('CLEANUP_REQUIRED','UNKNOWN')
        else:
            row=inspect_container(ids[0])
            require(row is not None,'LABELED_PROBE_INSPECT_FAILED')
            status=str((row.get('State') or {}).get('Status','unknown')).upper()
            emit('PROBE_STATUS',status if status in FIELDS['PROBE_STATUS'] else 'UNKNOWN')
            owner,image,secure,tmpfs,mounts,synthetic,strict,mounts_only=probe_shape(row,candidate)
            emit('PROBE_NAME_LABEL','PASS' if owner else 'FAIL')
            emit('PROBE_IMAGE','MATCH' if image else 'DIFFERENT')
            emit('PROBE_HOST_ISOLATION','PASS' if secure else 'FAIL')
            emit('PROBE_TMPFS_DECLARATION','PASS' if tmpfs else 'FAIL')
            emit('PROBE_MOUNTS',mounts)
            emit('PROBE_ENVIRONMENT','SYNTHETIC_ONLY' if synthetic else 'UNSAFE')
            emit('STRICT_VALIDATOR','PASS' if strict else 'FAIL')
            emit('STRICT_FAILURE_ONLY_MOUNTS','YES' if mounts_only else 'NO')
            emit('CLEANUP_REQUIRED','YES_REVIEW' if owner and image and secure and tmpfs and synthetic and
                 mounts in ('NOT_REALIZED','SYNTHETIC_TMPFS') else 'UNKNOWN')
        second=production(c,b,earlier)
        require(second==(pstate,phealth),'PRODUCTION_CHANGED_DURING_AUDIT')
        emit('ACTION_TAKEN','NONE')
        emit('R1_CUSTOMER_RELEASE','NO_GO')

def self_test():
    image='sha256:'+'a'*64
    identity='b'*14
    base={
      'Name':'/v79-isolated-academy-'+identity,
      'Image':image,'State':{'Status':'created'},
      'Config':{'Labels':{OWNER:identity},'User':'1000:1000',
                'Env':['PORT=18081','NODE_ENV=production',
                       'ACADEMY_STANDALONE_ADMIN_ENABLED=0',
                       'V79_PLATFORM_SHARED_SECRET=',
                       'ACADEMY_COURSE_PUBLISH_MODE=disabled']},
      'HostConfig':{'NetworkMode':'none','PortBindings':None,'Privileged':False,
                    'ReadonlyRootfs':True,'Binds':None,'Mounts':None,
                    'RestartPolicy':{'Name':'no'},'Memory':512*1024**2,
                    'PidsLimit':64,'CapDrop':['ALL'],
                    'SecurityOpt':['no-new-privileges:true'],
                    'Tmpfs':{'/app/data':'abc','/tmp':'xyz'}},
      'NetworkSettings':{'Networks':{}},'Mounts':[]}
    a=probe_shape(base,image)
    assert a==(True,True,True,True,'NOT_REALIZED',True,False,True),a
    obj=json.loads(json.dumps(base))
    obj['Mounts']=[{'Type':'tmpfs','Destination':'/app/data'},
                   {'Type':'tmpfs','Destination':'/tmp'}]
    assert probe_shape(obj,image)[6] is True
    for k,v in [('NetworkMode','proxy_network'),('Privileged',True),
                ('ReadonlyRootfs',False),('PidsLimit',999)]:
        obj=json.loads(json.dumps(base));obj['HostConfig'][k]=v
        assert probe_shape(obj,image)[7] is False
    obj=json.loads(json.dumps(base));obj['Config']['Env'].append('ADMIN_PASSWORD=PRIVATE')
    assert probe_shape(obj,image)[7] is False
    obj=json.loads(json.dumps(base));obj['Image']='sha256:'+'c'*64
    assert probe_shape(obj,image)[7] is False
    assert not safe('SECRET=PRIVATE')
    emit('SELF_TEST','PASS')
def acer():
    require(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
          '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    result=subprocess.run(args,input=Path(__file__).read_bytes(),
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=220)
    for line in result.stdout.decode('utf8','replace').splitlines():
        require(safe(line),'REMOTE_OUTPUT_NOT_SAFE')
        print(line,flush=True)
    require(result.returncode==0,'REMOTE_ACADEMY_INSPECTION_FAILED')
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--server',action='store_true')
    opts=parser.parse_args()
    if opts.self_test:self_test()
    elif opts.server:audit()
    else:acer()
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=(str(error) if isinstance(error,Stop) and
              re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',str(error))
              else 'ACADEMY_READONLY_AUDIT_ERROR')
        print('STOP='+code,flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
        sys.exit(1)
