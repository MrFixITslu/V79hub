#!/usr/bin/env python3
"""Only read Docker state after the Games GCIN6i1p isolated cleanup timeout.

No Docker create/start/stop/rm/exec/logs; never print container IDs,
labels, environment, file paths from Docker or non-whitelisted output.
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
CORE=ROOT/'v79-portfolio-rollout.6kvFDd5e'/'rollout.py'
CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
OWNER='v79.private-games-isolated'
APP=('v79_course_builder','v79-pos','v79-pos-worker',
     'gaming-studio-j','v79-hub','v79-tiquet-manager')
IMAGE=re.compile(r'sha256:[0-9a-f]{64}\Z')
NAME=re.compile(r'v79-isolated-games-([0-9a-f]{14})\Z')
STATUS={'created','running','paused','restarting','removing','exited','dead','unknown'}
MARKERS={
    'SELF_TEST':{'PASS'},
    'MODE':{'READ_ONLY_CLEANUP_RECONCILIATION'},
    'PRODUCTION_RUNTIME':{'UNCHANGED','DRIFT','UNVERIFIED'},
    'PRODUCTION_HEALTH':{'PASS','FAIL','UNVERIFIED'},
    'GAMES_ISOLATED_PROBE_COUNT':{str(x) for x in range(0,6)}|{'MANY'},
    'PROBE_CLASS':{'NONE','OWNED_MATCH','UNVERIFIED','MULTIPLE'},
    'PROBE_STATE':{x.upper() for x in STATUS}|{'ABSENT','UNINSPECTABLE','MULTIPLE'},
    'PROBE_IMAGE':{'MATCH','DIFFERENT','UNVERIFIED','ABSENT','MULTIPLE'},
    'PROBE_SECURITY':{'PASS','FAIL','UNVERIFIED','ABSENT','MULTIPLE'},
    'PROBE_CLEANUP_REQUIRED':{'NO','YES','UNKNOWN'},
    'CLEANUP_ACTION':{'NONE'},
    'REHEARSAL_CLEANUP_ACCEPTED':{'YES','NO'},
    'R1_CUSTOMER_RELEASE':{'NO_GO'},
}
class Stop(Exception): pass
def need(x,code):
    if not x:raise Stop(code)
def accepted(line):
    key,sep,value=line.partition('=')
    return bool(sep and (key in MARKERS and value in MARKERS[key] or
       key=='STOP' and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',value)))
def emit(key,value):
    out=key+'='+str(value)
    need(accepted(out),'OUTPUT_NOT_SAFE')
    print(out,flush=True)
def command(args,secs=45):
    try:
        return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              timeout=secs)
    except subprocess.TimeoutExpired:
        raise Stop('DOCKER_INSPECT_TIMEOUT') from None
def private(path):
    need(path.is_file() and not path.is_symlink() and
         path.stat().st_uid==os.getuid() and path.stat().st_mode & 0o077==0,
         'PRIVATE_EVIDENCE_CHANGED')
    return json.loads(path.read_text())
def private_dir(path):
    need(path.is_dir() and not path.is_symlink() and
         path.stat().st_uid==os.getuid() and path.stat().st_mode & 0o077==0,
         'PRIVATE_DIRECTORY_CHANGED')
def core():
    need(CORE.is_file() and not CORE.is_symlink() and
         CORE.stat().st_uid==os.getuid() and CORE.stat().st_mode & 0o077==0,
         'TRUSTED_CORE_MISSING')
    raw=CORE.read_bytes()
    need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==CORE_BLOB,
         'TRUSTED_CORE_CHANGED')
    spec=importlib.util.spec_from_file_location('verified_games_recovery_inspect',CORE)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result
def inspect(name):
    p=command(['docker','container','inspect',name],secs=35)
    if p.returncode:return None
    try:
        val=json.loads(p.stdout)
        need(isinstance(val,list) and len(val)==1 and isinstance(val[0],dict),
             'DOCKER_INSPECT_INVALID')
        return val[0]
    except ValueError:raise Stop('DOCKER_INSPECT_INVALID') from None
def discovery():
    p=command(['docker','container','ls','--all','--no-trunc','--quiet',
               '--filter','label='+OWNER],secs=35)
    need(p.returncode==0,'OWNED_PROBE_DISCOVERY_FAILED')
    ids=p.stdout.decode('ascii','replace').splitlines()
    need(all(re.fullmatch(r'[0-9a-f]{64}',x) for x in ids) and
         len(ids)==len(set(ids)),'PROBE_ID_LIST_INVALID')
    return ids
def is_safe_probe(row,image):
    if not isinstance(row,dict):return False
    config=row.get('Config') or {}
    labels=config.get('Labels') or {}
    host=row.get('HostConfig') or {}
    name=row.get('Name','').lstrip('/')
    match=NAME.fullmatch(name)
    if not match or labels.get(OWNER)!=match[1] or row.get('Image')!=image:return False
    if 'com.docker.compose.project' in labels:return False
    if host.get('NetworkMode')!='none' or host.get('PortBindings') or host.get('Privileged'):return False
    if host.get('ReadonlyRootfs') is not True or host.get('Binds') or host.get('Mounts'):return False
    if (host.get('RestartPolicy') or {}).get('Name')!='no':return False
    if (host.get('Tmpfs') or {}).get('/app/runtime') is None:return False
    if not host.get('Memory')==256*1024*1024 or host.get('PidsLimit')!=64:return False
    if set(row.get('NetworkSettings',{}).get('Networks',{})) not in (set(),{'none'}):return False
    if any(m.get('Type')!='tmpfs' or m.get('Destination')!='/app/runtime'
           for m in row.get('Mounts') or []):return False
    # No secrets from the inherited production environment, read only key names.
    env=config.get('Env') or []
    names={x.partition('=')[0] for x in env}
    if {'DATABASE_URL','REDIS_URL','POSTGRES_PASSWORD','V79_PLATFORM_SHARED_SECRET'} & names:
        return False
    return True
def verify_prod(trusted,stored,old_shared,live):
    state_ok=True;health_ok=True
    for name in APP:
        before=stored[name] if name in stored else old_shared.get(name)
        now=live.get(name)
        if not isinstance(before,dict) or not isinstance(now,dict):
            return 'UNVERIFIED','UNVERIFIED'
        if (before.get('Id')!=now.get('Id') or before.get('Image')!=now.get('Image') or
            trusted.fingerprint(before)!=trusted.fingerprint(now) or
            now.get('State',{}).get('Running') is not True):
            state_ok=False
        if name!='v79-pos-worker' and (now.get('State',{}).get('Health') or {}).get('Status')!='healthy':
            health_ok=False
    return ('UNCHANGED' if state_ok else 'DRIFT','PASS' if health_ok else 'FAIL')
def audit():
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'SERVER_NONROOT_REQUIRED')
    for d in (BASE,FAILED,CORE.parent):private_dir(d)
    lock=ROOT/'.v79-portfolio-rollout.lock'
    need(lock.is_file() and not lock.is_symlink(),'ROLLOUT_LOCK_MISSING')
    with lock.open('rb') as fp:
        try:fcntl.flock(fp,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('ANOTHER_ROLLOUT_RUNNING')
        trusted=core()
        summary=private(BASE/'plan-summary.json')
        baseline=private(BASE/'runtime-before.json')
        prior=private(FAILED/'runtime-before.json')
        receipt=private(FAILED/'Gaming-Studio-J-built-image.json')
        manifest=private(FAILED/'checkpoint/manifest.json')
        need(summary.get('status')=='RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE'
             and summary.get('deployment_authorization')=='NO'
             and summary.get('restore_acceptance')=='NOT_PERFORMED'
             and summary.get('current_runtime_container_ids')==
               {n:baseline[n]['Id'] for n in baseline}
             and summary.get('checkpoint_manifest_sha256')==
               hashlib.sha256((FAILED/'checkpoint/manifest.json').read_bytes()).hexdigest(),
             'BASELINE_PROVENANCE_CHANGED')
        need(set(baseline)==set(APP[:4]) and
             receipt.get('repo')=='Gaming-Studio-J' and
             receipt.get('source_commit')=='17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'
             and manifest.get('status')=='CAPTURED_NOT_RESTORE_TESTED' and
             manifest.get('candidates',{}).get('gaming-studio-j')==receipt.get('image_id') and
             IMAGE.fullmatch(receipt.get('image_id','')),
             'CANDIDATE_PROVENANCE_CHANGED')
        emit('MODE','READ_ONLY_CLEANUP_RECONCILIATION')
        live={n:inspect(n) for n in APP}
        prod,health=verify_prod(trusted,baseline,prior,live)
        emit('PRODUCTION_RUNTIME',prod)
        emit('PRODUCTION_HEALTH',health)
        ids=discovery()
        emit('GAMES_ISOLATED_PROBE_COUNT',str(len(ids)) if len(ids)<=5 else 'MANY')
        safe_count=0
        if len(ids)==0:
            emit('PROBE_CLASS','NONE')
            emit('PROBE_STATE','ABSENT')
            emit('PROBE_IMAGE','ABSENT')
            emit('PROBE_SECURITY','ABSENT')
            emit('PROBE_CLEANUP_REQUIRED','NO')
        elif len(ids)==1:
            row=inspect(ids[0])
            if row is None:
                emit('PROBE_CLASS','UNVERIFIED')
                emit('PROBE_STATE','UNINSPECTABLE')
                emit('PROBE_IMAGE','UNVERIFIED')
                emit('PROBE_SECURITY','UNVERIFIED')
                emit('PROBE_CLEANUP_REQUIRED','UNKNOWN')
            else:
                owner=(row.get('Config') or {}).get('Labels') or {}
                valid_name=NAME.fullmatch(row.get('Name','').lstrip('/'))
                owns=bool(valid_name and owner.get(OWNER)==valid_name[1])
                state=str((row.get('State') or {}).get('Status','unknown'))
                if state not in STATUS:state='unknown'
                safe=is_safe_probe(row,receipt['image_id'])
                emit('PROBE_CLASS','OWNED_MATCH' if owns else 'UNVERIFIED')
                emit('PROBE_STATE',state.upper())
                emit('PROBE_IMAGE','MATCH' if row.get('Image')==receipt['image_id'] else 'DIFFERENT')
                emit('PROBE_SECURITY','PASS' if safe else 'FAIL')
                emit('PROBE_CLEANUP_REQUIRED','YES' if safe else 'UNKNOWN')
        else:
            emit('PROBE_CLASS','MULTIPLE')
            emit('PROBE_STATE','MULTIPLE')
            emit('PROBE_IMAGE','MULTIPLE')
            emit('PROBE_SECURITY','MULTIPLE')
            emit('PROBE_CLEANUP_REQUIRED','UNKNOWN')
        second={n:inspect(n) for n in APP}
        prod_second,health_second=verify_prod(trusted,baseline,prior,second)
        need(prod_second==prod and health_second==health and
             all(second[n] and live[n] and second[n]['Id']==live[n]['Id'] and
                 trusted.fingerprint(second[n])==trusted.fingerprint(live[n])
                 for n in APP),'PRODUCTION_CHANGED_DURING_AUDIT')
        emit('CLEANUP_ACTION','NONE')
        emit('REHEARSAL_CLEANUP_ACCEPTED','YES' if not ids and prod=='UNCHANGED' and health=='PASS' else 'NO')
        emit('R1_CUSTOMER_RELEASE','NO_GO')
def self_test():
    im='sha256:'+'f'*64
    identity='a'*14
    valid={'Name':'/v79-isolated-games-'+identity,'Image':im,
           'Config':{'Labels':{OWNER:identity},'Env':['PORT=18080']},
           'HostConfig':{'NetworkMode':'none','PortBindings':None,'Privileged':False,
                         'ReadonlyRootfs':True,'Binds':None,'Mounts':None,
                         'RestartPolicy':{'Name':'no'},'Tmpfs':{'/app/runtime':'rw'},
                         'Memory':268435456,'PidsLimit':64},
           'Mounts':[],'NetworkSettings':{'Networks':{}}}
    assert is_safe_probe(valid,im)
    for prop,bad in [('NetworkMode','proxy_network'),('Privileged',True),
                     ('ReadonlyRootfs',False),('Memory',0),('PidsLimit',999)]:
        clone=json.loads(json.dumps(valid))
        clone['HostConfig'][prop]=bad
        assert not is_safe_probe(clone,im)
    clone=json.loads(json.dumps(valid));clone['Mounts']=[{'Type':'bind','Destination':'/secret'}]
    assert not is_safe_probe(clone,im)
    clone=json.loads(json.dumps(valid));clone['Config']['Env'].append('DATABASE_URL=SECRET')
    assert not is_safe_probe(clone,im)
    clone=json.loads(json.dumps(valid));clone['Config']['Labels'][OWNER]='b'*14
    assert not is_safe_probe(clone,im)
    assert not accepted('DOCKER_SECRET=secret')
    assert not accepted('PROBE_IMAGE=sha256:'+'f'*64)
    emit('SELF_TEST','PASS')
def acer():
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
          '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    done=subprocess.run(args,input=Path(__file__).read_bytes(),
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=240)
    for row in done.stdout.decode('utf-8','replace').splitlines():
        need(accepted(row),'REMOTE_OUTPUT_REDACTED')
        print(row,flush=True)
    need(done.returncode==0,'REMOTE_AUDIT_FAILED')
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--server',action='store_true')
    args=p.parse_args()
    if args.self_test:self_test()
    elif args.server:audit()
    else:acer()
if __name__=='__main__':
    try:main()
    except Exception as error:
        reason=(str(error) if isinstance(error,Stop) and
                re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',str(error))
                else 'CLEANUP_AUDIT_ERROR_REDACTED')
        print('STOP='+reason,flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
        sys.exit(1)
