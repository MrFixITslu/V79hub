#!/usr/bin/env python3
"""Create a private immutable recovery-anchored baseline, not a deployable plan.

Only Docker inspect, Docker Compose config, immutable file reads, private plan
creation, and read-only dependency probes. NEVER stop, restart, deploy, or restore.
The prior frozen plan is intentionally not rewritten and cannot be resumed.
"""
import argparse
import copy
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
import tempfile

ACCEPTED_RUN=Path('/home/firelion/v79-portfolio-rollout.6kvFDd5e')
ACCEPTED_CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
BASE_PLAN=Path('/home/firelion/v79-remaining-plan.by50q9w3')
FAILED_RUN=Path('/home/firelion/v79-remaining-rollout.GCIN6i1p')
APPS=('v79_course_builder','v79-pos','v79-pos-worker','gaming-studio-j')
SOURCES={'V79acaedmy':'584e07c9f5186e4aa10e87f931b2ea7194db93d4',
         'V79POS':'e4bf7620f5e6c5cc2e3a6c12d14bb441bf15de37',
         'Gaming-Studio-J':'17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'}
IMAGE_PINS={
 'v79_course_builder':'sha256:f9ab28a4b25fed0445a93e6f3b1548ed2706d9ec7a57176152236fa8708005d0',
 'v79-pos':'sha256:4f864f323e8a9d1d98dd1f26caf82d9b223412115fed7cb154c2d0e0158b88f8',
 'v79-pos-worker':'sha256:24279f6e693a66dca8bdb47f0e0e072d00983a67e74cc5e55a87ea5ecbf5c19d',
 'gaming-studio-j':'sha256:4039d9ab72c0cc99c5d18c92714678a9a8e05ef26177e85bbe3d56da834b07e7'
}
PINNED_DETAILS={
 'v79_course_builder':('v79-course-builder','course-builder','V79acaedmy'),
 'v79-pos':('v79pos','api','V79POS'),
 'v79-pos-worker':('v79pos','worker','V79POS'),
 'gaming-studio-j':('gaming-studio-j','gaming-studio-j','Gaming-Studio-J')
}
BASELINE_PATH=re.compile(r'NEW_RECOVERY_BASELINE=/home/firelion/v79-recovery-replan\.[A-Za-z0-9_-]{8,16}\Z')
MARKERS={'SELF_TEST':'PASS',
         'OLD_ENCRYPTED_CHECKPOINT':'SERVER_HASHES_PASS_RESTORE_NOT_TESTED',
         'RESTORED_SOURCE_PARITY':'PASS','LIVE_APP_CHANGES':'NONE',
         'PLAN_MODE':'EVIDENCE_ONLY_NOT_DEPLOYABLE',
         'R1_CUSTOMER_RELEASE':'NO_GO'}
RECONCILED={'RECOVERED_'+name.upper().replace('-','_') for name in
            ('v79_course_builder','v79-pos','v79-pos-worker','gaming-studio-j')}
DNS_FIELDS=('Dns','DnsOptions','DnsSearch')

class Stop(Exception):pass

def safe_line(s):
    if BASELINE_PATH.fullmatch(s):return True
    key,sep,value=s.partition('=')
    if not sep:return False
    if key=='STOP':return bool(re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',value))
    if key in RECONCILED:return value=='VERIFIED'
    return key in MARKERS and MARKERS[key]==value

def emit(key,value):
    s=key+'='+str(value)
    if not safe_line(s):raise Stop('UNSAFE_OUTPUT')
    print(s,flush=True)

def need(cond,reason):
    if not cond:raise Stop(reason)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def directory(path):
    need(path.is_dir() and not path.is_symlink() and path.stat().st_uid==os.getuid()
         and path.stat().st_mode & 0o077==0,'PRIVATE_DIRECTORY_UNSAFE')

def data(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid()
         and path.stat().st_mode & 0o077==0,'PRIVATE_FILE_UNSAFE')
    return json.loads(path.read_text())

def helper():
    path=ACCEPTED_RUN/'rollout.py'
    need(path.is_file() and not path.is_symlink() and blob(path.read_bytes())==ACCEPTED_CORE_BLOB,
         'ACCEPTED_CORE_CHANGED')
    spec=importlib.util.spec_from_file_location('v79_recovery_core',path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def dns_only_equivalent(left,right):
    """Preserve every other exact fingerprint attribute; refuse DNS configurations."""
    a=copy.deepcopy(left);b=copy.deepcopy(right)
    if a==b:return True
    if any(a.get(k)!=b.get(k) for k in ('config','env','mounts','networks')):return False
    x,y=a.get('host',{}),b.get('host',{})
    fields=set(x)|set(y)
    for k in fields:
        if x.get(k)==y.get(k):continue
        if k not in DNS_FIELDS:return False
        if type(x.get(k)) not in (type(None),list) or type(y.get(k)) not in (type(None),list):
            return False
        if x.get(k) not in ([],None) or y.get(k) not in ([],None):
            return False
    return True

def phase_one(r):
    for path in (ACCEPTED_RUN,BASE_PLAN,FAILED_RUN):directory(path)
    prev=data(BASE_PLAN/'plan-summary.json')
    need(prev['status']=='PLAN_PREPARED_NOT_DEPLOYED' and prev['sources']==SOURCES
         and set(prev['pins'])==set(APPS) and prev['pos_migrations']['status']=='PASS',
         'ACCEPTED_PLAN_INVALID')
    source_before=data(BASE_PLAN/'runtime-before.json')
    attempt_before=data(FAILED_RUN/'runtime-before.json')
    reference=data(FAILED_RUN/'plan-reference.json')
    manifest=data(FAILED_RUN/'checkpoint/manifest.json')
    need((FAILED_RUN/'exit-code').read_text().strip()=='1','FAILED_RUN_NOT_COMPLETE')
    need(reference['directory']==str(BASE_PLAN) and reference['sources']==SOURCES and
         reference['summary_sha256']==sha(BASE_PLAN/'plan-summary.json'),
         'FAILED_RUN_REFERENCE_CHANGED')
    need(manifest['status']=='CAPTURED_NOT_RESTORE_TESTED' and
         manifest['scope']=='REMAINING_ACADEMY_POS_GAMES_PRECHANGE_NOT_FULL_PORTFOLIO' and
         manifest['source_images']==IMAGE_PINS and manifest['sources']==SOURCES,
         'BACKUP_PROVENANCE_CHANGED')
    need(set(attempt_before)>=set(APPS) and set(source_before)==set(APPS),
         'BASELINE_APPS_MISSING')
    files=manifest.get('files')
    need(isinstance(files,list) and len(files)>=8,'CHECKPOINT_MANIFEST_INCOMPLETE')
    present=set()
    for entry in files:
        name=entry.get('name')
        need(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',name)
             and name not in present,'CHECKPOINT_FILE_UNSAFE')
        present.add(name)
        file=FAILED_RUN/'checkpoint'/name
        need(file.is_file() and not file.is_symlink() and file.stat().st_size==entry['bytes']
             and sha(file)==entry['sha256'],'CHECKPOINT_CIPHERTEXT_CHANGED')
    emit('OLD_ENCRYPTED_CHECKPOINT','SERVER_HASHES_PASS_RESTORE_NOT_TESTED')
    need(set(prev['results'])==set(APPS) and all(prev['results'][n]['runtime_parity']=='PASS' for n in APPS),
         'OLD_PLAN_RUNTIME_UNVERIFIED')
    return prev,attempt_before,source_before

def check_app(r,prev,prior,row,name):
    pin=prev['pins'][name]
    project,service,repo=PINNED_DETAILS[name]
    need(pin['compose_project']==project and pin['compose_service']==service and
         pin['repo']==repo and pin['image_id']==IMAGE_PINS[name],
         'PINNED_APP_DEFINITION_CHANGED')
    need(row['Image']==prior['Image']==IMAGE_PINS[name] and
         row['State'].get('Running') is True,'RESTORED_IMAGE_OR_STATE_CHANGED')
    if name!='v79-pos-worker':
        need(row['State'].get('Health',{}).get('Status')=='healthy','RESTORED_APP_UNHEALTHY')
    lhs=r.fingerprint(prior)
    rhs=r.fingerprint(row)
    if name=='gaming-studio-j':
        need(dns_only_equivalent(lhs,rhs),'RESTORED_GAMES_RUNTIME_DIFFERS')
    else:need(lhs==rhs,'RESTORED_APP_RUNTIME_DIFFERS')
    labels=row['Config'].get('Labels') or {}
    need(labels.get('com.docker.compose.project')==project and
         labels.get('com.docker.compose.service')==service and
         labels.get('com.docker.compose.project.config_files')==
           str(FAILED_RUN/(name+'-original.pinned.yml')) and
         labels.get('com.docker.compose.project.working_dir')==str(FAILED_RUN),
         'COMPOSE_RECOVERY_LINEAGE_CHANGED')
    original=data(BASE_PLAN/(name+'-original.pinned.yml'))
    restored=data(FAILED_RUN/(name+'-original.pinned.yml'))
    need(restored==original and original['services'][service]['image']==IMAGE_PINS[name],
         'RESTORED_MODEL_DIFFERS_FROM_ACCEPTED_PLAN')
    # Original live Compose file hash remains pinned even though labels now point
    # at the saved rollback YAML. This is evidence, never a rewrite of labels.
    for f in pin['compose_inputs']:
        path=Path(f['path'])
        need(path.is_file() and not path.is_symlink() and sha(path)==f['sha256'],
             'ORIGINAL_SOURCE_COMPOSE_DRIFT')
    rendered=json.loads(r.call(r.compose(FAILED_RUN/(name+'-original.pinned.yml'),
                                         project,'config','--format','json')))
    rendered_service=rendered['services'][service]
    need(rendered_service.get('image')==IMAGE_PINS[name] and
         rendered_service.get('container_name')==name and
         not rendered_service.get('ports') and not row['HostConfig'].get('PortBindings'),
         'RESTORED_COMPOSE_SERVICE_CHANGED')
    need(r.compose_runtime(rendered_service.get('environment',{}))==
         r.envmap(row['Config'].get('Env')),'RESTORED_COMPOSE_ENV_CHANGED')
    r.validate_storage_and_networks(rendered,rendered_service,row)
    return original

def check_shared(r):
    release=data(ACCEPTED_RUN/'release-receipt.json')
    need(release.get('health')=='PASS_BOTH','SHARED_RELEASE_UNACCEPTED')
    for name in ('v79-hub','v79-tiquet-manager'):
        row=r.inspect(name)
        need(row['Image']==release['images'][name] and
             row['State'].get('Health',{}).get('Status')=='healthy' and
             row['State'].get('Running') is True,'SHARED_APP_CHANGED')

def prepare():
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'RUN_ON_V79SL_NON_ROOT')
    os.umask(0o077)
    with (Path.home()/'.v79-portfolio-rollout.lock').open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('ANOTHER_ROLLOUT_RUNNING')
        r=helper()
        prev,attempt,source=phase_one(r)
        check_shared(r)
        current={name:r.inspect(name) for name in APPS}
        frozen={}
        for name in APPS:
            frozen[name]=check_app(r,prev,attempt[name],current[name],name)
            emit('RECOVERED_'+name.upper().replace('-','_'),'VERIFIED')
        # Compare all container IDs and full fingerprints immediately before
        # creating a new private, intentionally NONDEPLOYABLE evidence plan.
        for name in APPS:
            now=r.inspect(name)
            need(now['Id']==current[name]['Id'] and
                 r.fingerprint(now)==r.fingerprint(current[name]),
                 'LIVE_CHANGED_DURING_PREPARATION')
        check_shared(r)
        directory_new=Path(tempfile.mkdtemp(prefix='v79-recovery-replan.',dir=Path.home()))
        directory_new.chmod(0o700)
        r.private_json(directory_new/'runtime-before.json',current)
        for name in APPS:
            r.private_json(directory_new/(name+'-original.pinned.yml'),frozen[name])
        r.private_json(directory_new/'plan-summary.json',{
            'status':'RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE',
            'sources':SOURCES,'pins':prev['pins'],
            'prior_accepted_plan':str(BASE_PLAN),
            'failed_deployment':str(FAILED_RUN),
            'current_runtime_container_ids':{name:current[name]['Id'] for name in APPS},
            'checkpoint_manifest_sha256':sha(FAILED_RUN/'checkpoint/manifest.json'),
            'old_plan_sha256':sha(BASE_PLAN/'plan-summary.json'),
            'checks':{'four_restored_containers':'PASS','compose_provenance':'PASS',
                      'current_identities':'CAPTURED_NEW_BASELINE',
                      'encrypted_prechange_checkpoint':'HASH_VERIFIED_NOT_RESTORE_TESTED',
                      'pos_migrations':'PRIOR_PASS_FRESH_READ_REQUIRED',
                      'pos_worker_business_jobs':'NOT_TESTED',
                      'security_owner_mfa_sso_tenant':'NOT_TESTED'},
            'deployment_authorization':'NO','restore_acceptance':'NOT_PERFORMED'})
        # No deployability marker or switch helper is written. Do NOT use old
        # --continue-built-academy-pos-games against this new plan.
        emit('NEW_RECOVERY_BASELINE',str(directory_new))
        emit('RESTORED_SOURCE_PARITY','PASS')
        emit('LIVE_APP_CHANGES','NONE')
        emit('PLAN_MODE','EVIDENCE_ONLY_NOT_DEPLOYABLE')
        emit('R1_CUSTOMER_RELEASE','NO_GO')
        return 0

def test():
    base={'config':{'User':'node'},'env':{'SECRET':'DO_NOT_PRINT'},
          'mounts':[],'networks':['net'],'host':{'Dns':[],'DnsOptions':[],'DnsSearch':[]}}
    target=copy.deepcopy(base);target['host']={x:None for x in DNS_FIELDS}
    assert dns_only_equivalent(base,target)
    assert dns_only_equivalent(target,base)
    changed=copy.deepcopy(target);changed['host']['Dns']=['1.2.3.4']
    assert not dns_only_equivalent(base,changed)
    changed=copy.deepcopy(target);changed['host']['Privileged']=True
    assert not dns_only_equivalent(base,changed)
    changed=copy.deepcopy(target);changed['env']['SECRET']='NEW_DO_NOT_PRINT'
    assert not dns_only_equivalent(base,changed)
    assert 'DO_NOT_PRINT' not in str(dns_only_equivalent(base,target))
    assert safe_line('NEW_RECOVERY_BASELINE=/home/firelion/v79-recovery-replan.aBc123_4')
    assert not safe_line('NEW_RECOVERY_BASELINE=/tmp/private_secret')
    assert not safe_line('SECRET=HIDDEN')
    emit('SELF_TEST','PASS')
    return 0

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--server',action='store_true')
    args=p.parse_args()
    if args.self_test:return test()
    if args.server:return prepare()
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    remote=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    process=subprocess.run(remote,input=Path(__file__).read_bytes(),stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL,timeout=1200)
    for line in process.stdout.decode('utf8','replace').splitlines():
        if safe_line(line):print(line,flush=True)
        else:raise Stop('REDACTED_REMOTE_OUTPUT')
    need(process.returncode==0,'RECOVERY_BASELINE_PREPARE_FAILED')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        code=str(e) if isinstance(e,Stop) and re.fullmatch(r'[A-Z0-9_]{3,100}',str(e)) \
             else 'RECOVERY_PREPARE_ERROR_REDACTED'
        print('STOP='+code,flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
        sys.exit(1)
