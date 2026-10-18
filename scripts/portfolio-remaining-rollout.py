#!/usr/bin/env python3
"""Acer-driven, detached Academy/POS/Games rollout from the accepted private plan."""
import argparse
import base64
import copy
from datetime import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

MODULE_COMMIT='0cf1fad981d59ab1269ff9133472062e7587ccfb'
MODULES={'core.py':('scripts/portfolio-pinned-rollout.py','6a3a5bd30f4e66b3415891f654a7e142d04dbd79'),
         'plan.py':('scripts/portfolio-remaining-preflight.py','803bce37760ca1da98011f05d836cbd1f5014966')}
PLAN=Path('/home/firelion/v79-remaining-plan.by50q9w3')
FAILED_BUILD_RUN=Path('/home/firelion/v79-remaining-rollout.T2HHBqwg')
FAILED_HELPER_BLOB='b0fb7386d4b71db54421f81dd517df1af04c3d7d'
FAILED_POS_RUN=Path('/home/firelion/v79-remaining-rollout.uQ1BertQ')
FAILED_POS_HELPER_BLOB='31e574568aafee30b9a2cd90e1ec9a16190d4317'
FAILED_GAMES_RUN=Path('/home/firelion/v79-remaining-rollout.pu2FVF7b')
FAILED_GAMES_HELPER_BLOB='e464d72a57b83a96eaa086af84eb2f6c77ef2581'
RUN_RE=r'/home/firelion/v79-remaining-rollout\.[A-Za-z0-9]{8}'
STOP_ORDER=('v79-pos-worker','v79-pos','v79_course_builder','gaming-studio-j')
SWITCH_ORDER=('v79-pos','v79-pos-worker','v79_course_builder','gaming-studio-j')
DATABASES={'v79-pos-db':'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
           'v79_academy_postgres':'sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f'}
REDIS_IMAGE='sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499'
ENTRY_FILES={'v79_course_builder':'/app/dist/server.cjs','v79-pos':'/app/apps/api/dist/server.js',
             'v79-pos-worker':'/app/apps/api/dist/worker.js','gaming-studio-j':'/app/server.js'}

class Stop(Exception): pass

def need(value,code):
    if not value: raise Stop(code)

def blob(data): return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def load_modules(directory):
    loaded=[]
    for filename,(_,digest) in MODULES.items():
        path=directory/filename
        need(path.is_file() and not path.is_symlink() and blob(path.read_bytes())==digest,'MODULE_INTEGRITY_FAILURE')
        spec=importlib.util.spec_from_file_location('verified_rollout' if filename=='core.py' else 'verified_remaining_plan',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);loaded.append(module)
    return loaded

def private_read(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid()
         and path.stat().st_mode & 0o077==0,'PRIVATE_PLAN_FILE_UNSAFE')
    return json.loads(path.read_text())

def check_plan(r,p):
    need(PLAN.is_dir() and not PLAN.is_symlink() and PLAN.stat().st_uid==os.getuid()
         and PLAN.stat().st_mode & 0o077==0,'ACCEPTED_PLAN_DIRECTORY_UNSAFE')
    summary=private_read(PLAN/'plan-summary.json')
    need(summary['status']=='PLAN_PREPARED_NOT_DEPLOYED' and summary['sources']==p.SOURCES
         and summary['pins']==p.PINS and summary['pos_migrations']['status']=='PASS','ACCEPTED_PLAN_CHANGED')
    baseline=private_read(PLAN/'runtime-before.json')
    need(set(baseline)==set(p.PINS),'ACCEPTED_PLAN_INCOMPLETE')
    models={}
    for name,pin in p.PINS.items():
        need(summary['results'][name]['runtime_parity']=='PASS','ACCEPTED_PARITY_NOT_PASS')
        row=r.inspect(name)
        need(row['Image']==pin['image_id'] and row['Id']==baseline[name]['Id']
             and row['State'].get('Running') is True and r.fingerprint(row)==r.fingerprint(baseline[name]),'ACCEPTED_RUNTIME_CHANGED')
        if name!='v79-pos-worker':need(row['State'].get('Health',{}).get('Status')=='healthy','REMAINING_APP_UNHEALTHY')
        model=private_read(PLAN/(name+'-original.pinned.yml'))
        need(model==r.original_model(row,pin),'ACCEPTED_COMPOSE_PLAN_CHANGED')
        models[name]=model
    need(p.pos_migrations(r)['status']=='PASS','POS_MIGRATION_HISTORY_CHANGED')
    check_shared_releases(r,p)
    return baseline,models

def check_shared_releases(r,p):
    receipt=private_read(p.ACCEPTED_RUN/'release-receipt.json')
    for name in ('v79-hub','v79-tiquet-manager'):
        row=r.inspect(name)
        need(row['Image']==receipt['images'][name] and row['State'].get('Health',{}).get('Status')=='healthy','HUB_TIQUET_RELEASE_CHANGED')
    for name,image in {**DATABASES,'v79-pos-redis':REDIS_IMAGE}.items():
        row=r.inspect(name)
        need(row['Image']==image and row['State'].get('Running') is True,'DEPENDENCY_IMAGE_OR_STATE_CHANGED')
        if name!='v79_academy_postgres':need(row['State'].get('Health',{}).get('Status')=='healthy','DEPENDENCY_UNHEALTHY')


def check_pos_environment(row):
    env=dict(x.split('=',1) for x in row['Config'].get('Env',[]) if '=' in x)
    need(env.get('NODE_ENV')=='production' and env.get('AUTH_MODE','hub')=='hub','POS_PRODUCTION_AUTH_MODE_INVALID')
    for key,length in [('GIFT_CARD_PEPPER',16),('ENCRYPTION_KEY',32),('V79_PLATFORM_SHARED_SECRET',1)]:
        value=env.get(key,'')
        need(value.strip() and len(value)>=length and not re.search(r'change[-_ ]?me|replace[-_ ]?(with)?',value,re.I),'POS_REQUIRED_'+key+'_UNAVAILABLE')
    need(env.get('CORS_ORIGINS','').strip(),'POS_REQUIRED_CORS_ORIGINS_UNAVAILABLE')
    need(env.get('DATABASE_URL') or env.get('POSTGRES_PASSWORD'),'POS_DATABASE_ENV_UNAVAILABLE')
    if env.get('V79_ENTITLEMENT_RECHECK_ENABLED')=='1':
        need(len(env.get('V79_POS_PLATFORM_SHARED_SECRET') or env.get('V79_PLATFORM_SHARED_SECRET',''))>=32,'POS_ENTITLEMENT_SECRET_UNAVAILABLE')

def optional_container(r,name):
    proc=subprocess.run(['docker','container','inspect',name],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=r.clean_env(),timeout=20)
    if proc.returncode==0:
        rows=json.loads(proc.stdout);need(len(rows)==1,'PROBE_INSPECT_AMBIGUOUS');return rows[0]
    need(not r.call(['docker','container','ls','--all','--quiet','--filter','name=^/'+name+'$']).strip(),'PROBE_INSPECT_NOT_ABSENCE')
    return None

def report_exception(r,error,context):
    """Only trusted codes or type/function/line; never exception message values."""
    trusted=isinstance(error,(Stop,r.Stop))
    message=str(error)
    if trusted and re.fullmatch(r'[A-Z0-9_]+',message):
        r.emit('RESULT',context+'_'+message);return
    kind=type(error).__name__
    if not re.fullmatch(r'[A-Za-z0-9_]{1,80}',kind):kind='UNKNOWN'
    function='UNKNOWN';line=0;trace=error.__traceback__
    while trace:
        if Path(trace.tb_frame.f_code.co_filename).name in (Path(__file__).name,'core.py','plan.py'):
            function=trace.tb_frame.f_code.co_name;line=trace.tb_lineno
        trace=trace.tb_next
    if not re.fullmatch(r'[A-Za-z0-9_]{1,80}',function):function='UNKNOWN'
    r.emit('RESULT',context+'_'+kind+'_IN_'+function+'_LINE_'+str(line))

def probe_call(r,args,timeout,code):
    try:
        return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,env=r.clean_env())
    except subprocess.TimeoutExpired:
        raise Stop(code) from None

def probe_metadata(r,name):
    result=probe_call(r,['docker','container','inspect',name],10,'CANDIDATE_PROBE_INSPECT_TIMEOUT')
    need(result.returncode==0,'CANDIDATE_PROBE_INSPECT_FAILED')
    rows=json.loads(result.stdout)
    need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),'CANDIDATE_PROBE_METADATA_INVALID')
    return rows[0]

def cleanup_probe(r,name,identity,image=None):
    row=optional_container(r,name)
    if row is not None:
        need((row['Config'].get('Labels') or {}).get('v79.remaining-release-probe')==identity,'FOREIGN_PROBE_REFUSE_CLEANUP')
        need(not row.get('Mounts') and row['HostConfig']['NetworkMode']=='none'
             and not row['HostConfig'].get('PortBindings') and not row['HostConfig'].get('Privileged'),'REFUSE_CLEANUP_NONISOLATED_PROBE')
        if image is not None:need(row['Image']==image,'REFUSE_CLEANUP_DIFFERENT_PROBE_IMAGE')
        state=row.get('State',{})
        status=state.get('Status')
        need(status in ('created','running','paused','restarting','removing','exited','dead'),'PROBE_STATE_INVALID')
        r.emit('RESULT','OWNED_PROBE_STATE_'+status.upper())
        # A timed-out client does not prove daemon-side removal failed. Reconcile
        # absence explicitly; never accept a timeout as successful cleanup.
        try:
            result=probe_call(r,['docker','rm','-f','-v',name],120,'CANDIDATE_PROBE_REMOVE_TIMEOUT')
        except Stop:
            need(optional_container(r,name) is None,'CANDIDATE_PROBE_REMOVE_TIMEOUT_RESOURCE_REMAINS')
            r.emit('RESULT','PROBE_REMOVAL_COMPLETED_AFTER_CLIENT_TIMEOUT')
        else:
            need(result.returncode==0 or optional_container(r,name) is None,'CANDIDATE_PROBE_REMOVE_FAILED')
    need(optional_container(r,name) is None,'PROBE_CLEANUP_NOT_PROVEN')


# Node in the pinned Games image has cap_net_bind_service on its executable.
# Executing that binary inside a cap-drop ALL / no-new-privileges probe can fail
# despite readable application source. Verify from the same non-root user using
# a minimal POSIX shell, without executing the file-capability-bearing binary.
# No application process, mount, network, or production credential is involved.
GAME_READABILITY_PROBE=(
    'for f do '
    'if [ ! -e "$f" ]; then echo PUBLIC_EXECUTION_ENOENT; exit 2; fi; '
    'if [ ! -r "$f" ]; then echo PUBLIC_EXECUTION_EACCES; exit 2; fi; '
    'done; '
    'if ! command -v node >/dev/null 2>&1; then echo PUBLIC_EXECUTION_ENOENT; exit 2; fi; '
    'case "$0" in '
    '  */*) if [ ! -e "$0" ]; then echo PUBLIC_EXECUTION_ENOENT; exit 2; fi; '
    '       if [ ! -x "$0" ]; then echo PUBLIC_EXECUTION_EACCES; exit 2; fi ;; '
    '  *) if ! command -v "$0" >/dev/null 2>&1; then echo PUBLIC_EXECUTION_ENOENT; exit 2; fi ;; '
    'esac; echo PUBLIC_EXECUTION_FILES_READABLE'
)

def probe_image(r,run,name,image,old):
    # No production environment, credentials, data mounts or network enter this probe.
    identity=run.name.split('.')[-1]
    probe='v79-release-probe-'+identity+'-'+str(list(ENTRY_FILES).index(name))
    label='v79.remaining-release-probe'
    paths=['/app/package.json',ENTRY_FILES[name]]
    command=old['Config'].get('Cmd') or []
    if isinstance(command,list) and len(command)>1 and Path(command[0]).name=='node':
        target=command[1]
        if re.fullmatch(r'[A-Za-z0-9_./-]+\.(?:js|cjs|mjs)',target) and '..' not in target.split('/'):
            paths.append(target if target.startswith('/') else (old['Config'].get('WorkingDir') or '/app')+'/'+target)
    entry=old['Config'].get('Entrypoint') or []
    executable=entry[0] if isinstance(entry,list) and entry else ''
    need(not executable or re.fullmatch(r'[A-Za-z0-9_./-]+',executable),'ENTRYPOINT_EXECUTABLE_UNREVIEWED')
    code="const fs=require('fs');for(const p of "+json.dumps(paths)+"){fs.accessSync(p,fs.constants.R_OK)}"
    if executable:
        code+="const entry="+json.dumps(executable)+";const paths=entry.includes('/')?[entry]:(process.env.PATH||'').split(':').map(p=>p+'/'+entry);if(!paths.some(p=>{try{fs.accessSync(p,fs.constants.X_OK);return true}catch{return false}}))process.exit(2);"
    code+="console.log('PUBLIC_EXECUTION_FILES_READABLE')"
    code="try{"+code+"}catch(e){console.log('PUBLIC_EXECUTION_'+(['EACCES','EPERM','ENOENT'].includes(e.code)?e.code:'UNCLASSIFIED'));process.exitCode=2}"
    is_games=name=='gaming-studio-j'
    execution_entry='/bin/sh' if is_games else 'node'
    execution_args=['-c',GAME_READABILITY_PROBE,executable or 'node',*paths] if is_games else ['-e',code]
    args=['docker','create','--name',probe,'--label',label+'='+identity,'--pull','never','--network','none',
          '--no-healthcheck','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','128m',
          '--memory-swap','128m','--pids-limit','48','--entrypoint',execution_entry]
    if old['Config'].get('User'):args+=['--user',old['Config']['User']]
    r.emit('PHASE','PROBE_'+name.upper().replace('-','_'))
    try:
        r.call([*args,image,*execution_args])
        row=probe_metadata(r,probe)
        need(not row['Mounts'] and row['HostConfig']['NetworkMode']=='none'
             and not row['HostConfig'].get('PortBindings'),'PROBE_ISOLATION_INVALID')
        r.emit('PHASE','PROBE_START_'+name.upper().replace('-','_'))
        started=probe_call(r,['docker','start',probe],20,'CANDIDATE_PROBE_START_TIMEOUT')
        if started.returncode!=0:
            category='USER_NOT_PRESENT' if re.search(rb'unable to find user|no matching entries in passwd',started.stderr,re.I) else 'START_FAILED'
            r.emit('RESULT',name+'_PUBLIC_EXECUTION_'+category)
            raise Stop('CANDIDATE_EXECUTION_PROBE_FAILED')
        r.emit('PHASE','PROBE_WAIT_'+name.upper().replace('-','_'))
        deadline=time.monotonic()+20
        while True:
            state=probe_metadata(r,probe)['State']
            if state.get('Status') in ('exited','dead'):break
            need(time.monotonic()<deadline,'CANDIDATE_PROBE_EXIT_TIMEOUT')
            time.sleep(0.2)
        result=probe_call(r,['docker','logs','--tail','4',probe],15,'CANDIDATE_PROBE_LOG_TIMEOUT')
        need(result.returncode==0,'CANDIDATE_PROBE_LOG_QUERY_FAILED')
        output=result.stdout.strip()
        if output!=b'PUBLIC_EXECUTION_FILES_READABLE' or state['ExitCode']!=0:
            category=output.decode() if output in (b'PUBLIC_EXECUTION_EACCES',b'PUBLIC_EXECUTION_EPERM',b'PUBLIC_EXECUTION_ENOENT') else 'PUBLIC_EXECUTION_UNCLASSIFIED'
            if state.get('OOMKilled'):category='PUBLIC_EXECUTION_OOM_KILLED'
            r.emit('RESULT',name+'_'+category)
            raise Stop('CANDIDATE_EXECUTION_PROBE_FAILED')
        r.emit('RESULT',name+'_PUBLIC_EXECUTION_PASS_CLEANUP_PENDING')
    except BaseException as error:
        report_exception(r,error,'PROBE_PRIMARY_FAILURE');raise
    finally:
        r.emit('PHASE','PROBE_CLEANUP_'+name.upper().replace('-','_'))
        try:cleanup_probe(r,probe,identity,image)
        except BaseException as error:
            report_exception(r,error,'PROBE_CLEANUP_FAILURE');raise
    r.emit('RESULT',name+'_PUBLIC_EXECUTION_AND_PROBE_CLEANUP_PASS')

def recover_academy_build(r,p,run):
    old=FAILED_BUILD_RUN
    need(old.is_dir() and not old.is_symlink() and old.stat().st_uid==os.getuid()
         and old.stat().st_mode & 0o077==0,'FAILED_BUILD_DIRECTORY_UNSAFE')
    helper=old/'rollout.py'
    need(helper.is_file() and not helper.is_symlink() and blob(helper.read_bytes())==FAILED_HELPER_BLOB,'FAILED_HELPER_INTEGRITY_CHANGED')
    load_modules(old)
    need((old/'exit-code').read_text().strip()=='1' and not (old/'checkpoint').exists(),'FAILED_RUN_NOT_PREDEPLOY_COMPLETE')
    lines=(old/'progress.log').read_text().splitlines()
    need('PHASE=PROBE_V79_COURSE_BUILDER' in lines and
         not any(line.startswith(('PHASE=SWITCH_','PHASE=QUIESCE_','DEPLOYED=')) for line in lines),'FAILED_RUN_PHASE_NOT_ACCEPTED')
    reference=private_read(old/'plan-reference.json')
    need(reference['directory']==str(PLAN) and reference['sources']==p.SOURCES
         and reference['summary_sha256']==r.sha_file(PLAN/'plan-summary.json'),'FAILED_PLAN_REFERENCE_CHANGED')
    baseline=private_read(old/'runtime-before.json')
    for name,pin in p.PINS.items():
        row=r.inspect(name)
        need(row['Id']==baseline[name]['Id'] and row['Image']==pin['image_id']
             and r.fingerprint(row)==r.fingerprint(baseline[name]),'FAILED_RUN_RUNTIME_DRIFT')
    repo='V79acaedmy';revision=p.SOURCES[repo];stage=old/repo
    need(r.call(['git','-C',str(stage),'rev-parse','HEAD']).decode().strip()==revision,'CACHED_ACADEMY_SOURCE_CHANGED')
    r.call(['git','-C',str(stage),'diff','--exit-code','HEAD','--'])
    need(not r.call(['git','-C',str(stage),'ls-files','--others','-z']),'CACHED_ACADEMY_UNTRACKED_CONTEXT')
    image=r.inspect('v79-portfolio/'+repo.lower()+':'+revision,image=True)
    need(r.IMAGE.fullmatch(image['Id']) and (image['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')==revision,'CACHED_ACADEMY_IMAGE_SOURCE_CHANGED')
    created=datetime.fromisoformat(image['Created'].replace('Z','+00:00')).timestamp()
    need(helper.stat().st_mtime-2<=created<=(old/'exit-code').stat().st_mtime+2,'CACHED_ACADEMY_BUILD_TIME_NOT_PROVEN')
    identity=old.name.split('.')[-1]
    cleanup_probe(r,'v79-release-probe-'+identity+'-0',identity,image['Id'])
    r.emit('RESULT','FAILED_RUN_OWNED_PROBE_CLEANUP_PASS')
    r.private_json(run/'cached-academy-proof.json',{'prior_run':str(old),'helper_blob':FAILED_HELPER_BLOB,
                   'source_commit':revision,'image_id':image['Id'],'scope':'VERIFIED_COMPLETED_BUILD_REPROBE_REQUIRED'})
    r.emit('RESULT','CACHED_ACADEMY_BUILD_VERIFIED_NO_REBUILD')
    return {repo:image['Id']}


def recover_academy_pos_builds(r,p,run):
    old=FAILED_POS_RUN
    need(old.is_dir() and not old.is_symlink() and old.stat().st_uid==os.getuid()
         and old.stat().st_mode & 0o077==0,'FAILED_POS_DIRECTORY_UNSAFE')
    helper=old/'rollout.py'
    need(helper.is_file() and not helper.is_symlink() and blob(helper.read_bytes())==FAILED_POS_HELPER_BLOB,'FAILED_POS_HELPER_INTEGRITY_CHANGED')
    load_modules(old)
    need((old/'exit-code').read_text().strip()=='1' and not (old/'checkpoint').exists(),'FAILED_POS_RUN_NOT_PREDEPLOY_COMPLETE')
    lines=(old/'progress.log').read_text().splitlines()
    need('RESULT=v79_course_builder_PUBLIC_EXECUTION_AND_PROBE_CLEANUP_PASS' in lines
         and 'PHASE=PROBE_CLEANUP_V79_POS' in lines
         and not any(line.startswith(('PHASE=SWITCH_','PHASE=QUIESCE_','DEPLOYED=')) for line in lines),'FAILED_POS_PHASE_NOT_ACCEPTED')
    reference=private_read(old/'plan-reference.json')
    need(reference['directory']==str(PLAN) and reference['sources']==p.SOURCES
         and reference['summary_sha256']==r.sha_file(PLAN/'plan-summary.json'),'FAILED_POS_PLAN_REFERENCE_CHANGED')
    baseline=private_read(old/'runtime-before.json')
    for name,pin in p.PINS.items():
        current=r.inspect(name)
        need(current['Id']==baseline[name]['Id'] and current['Image']==pin['image_id']
             and r.fingerprint(current)==r.fingerprint(baseline[name]),'FAILED_POS_RUNTIME_DRIFT')
    cached=recover_academy_build(r,p,run)
    academy=private_read(old/'V79acaedmy-built-image.json')
    need(academy=={'repo':'V79acaedmy','source_commit':p.SOURCES['V79acaedmy'],
                  'image_id':cached['V79acaedmy']},'CACHED_ACADEMY_RECEIPT_CHANGED')
    repo='V79POS';revision=p.SOURCES[repo];stage=old/repo
    need(r.call(['git','-C',str(stage),'rev-parse','HEAD']).decode().strip()==revision,'CACHED_POS_SOURCE_CHANGED')
    r.call(['git','-C',str(stage),'diff','--exit-code','HEAD','--'])
    need(not r.call(['git','-C',str(stage),'ls-files','--others','-z']),'CACHED_POS_UNTRACKED_CONTEXT')
    record=private_read(old/(repo+'-built-image.json'))
    need(record.get('repo')==repo and record.get('source_commit')==revision
         and r.IMAGE.fullmatch(record.get('image_id','')),'CACHED_POS_RECEIPT_INVALID')
    image=r.inspect(record['image_id'],image=True)
    need(image['Id']==record['image_id'] and (image['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')==revision,'CACHED_POS_IMAGE_SOURCE_CHANGED')
    created=datetime.fromisoformat(image['Created'].replace('Z','+00:00')).timestamp()
    need(helper.stat().st_mtime-2<=created<=(old/'exit-code').stat().st_mtime+2,'CACHED_POS_BUILD_TIME_NOT_PROVEN')
    identity=old.name.split('.')[-1]
    cleanup_probe(r,'v79-release-probe-'+identity+'-0',identity,cached['V79acaedmy'])
    cleanup_probe(r,'v79-release-probe-'+identity+'-1',identity,image['Id'])
    cached[repo]=image['Id']
    r.private_json(run/'cached-academy-pos-proof.json',{'prior_run':str(old),'helper_blob':FAILED_POS_HELPER_BLOB,
                   'sources':p.SOURCES,'images':cached,'scope':'VERIFIED_COMPLETED_BUILDS_REPROBE_REQUIRED'})
    r.emit('RESULT','CACHED_ACADEMY_AND_POS_BUILDS_VERIFIED_NO_REBUILD')
    return cached


def recover_all_builds(r,p,run):
    """Reuse three immutable candidates only after exact failed-run provenance."""
    old=FAILED_GAMES_RUN
    need(old.is_dir() and not old.is_symlink() and old.stat().st_uid==os.getuid()
         and old.stat().st_mode & 0o077==0,'FAILED_GAMES_DIRECTORY_UNSAFE')
    helper=old/'rollout.py'
    need(helper.is_file() and not helper.is_symlink() and blob(helper.read_bytes())==FAILED_GAMES_HELPER_BLOB,
         'FAILED_GAMES_HELPER_INTEGRITY_CHANGED')
    load_modules(old)
    need((old/'exit-code').read_text().strip()=='1' and not (old/'checkpoint').exists(),
         'FAILED_GAMES_RUN_NOT_PREDEPLOY_COMPLETE')
    lines=(old/'progress.log').read_text().splitlines()
    for name in ('v79_course_builder','v79-pos','v79-pos-worker'):
        need('RESULT='+name+'_PUBLIC_EXECUTION_AND_PROBE_CLEANUP_PASS' in lines,
             'PRIOR_SUCCESSFUL_EXECUTION_NOT_PROVEN')
    need('PHASE=BUILD_GAMING_STUDIO_J' in lines
         and 'RESULT=gaming-studio-j_PUBLIC_EXECUTION_UNCLASSIFIED' in lines
         and 'PHASE=PROBE_CLEANUP_GAMING_STUDIO_J' in lines
         and 'STOP=CANDIDATE_EXECUTION_PROBE_FAILED' in lines
         and not any(line.startswith(('PHASE=SWITCH_','PHASE=QUIESCE_','DEPLOYED='))
                     for line in lines),'FAILED_GAMES_PHASE_NOT_ACCEPTED')
    reference=private_read(old/'plan-reference.json')
    need(reference['directory']==str(PLAN) and reference['sources']==p.SOURCES
         and reference['summary_sha256']==r.sha_file(PLAN/'plan-summary.json'),
         'FAILED_GAMES_PLAN_REFERENCE_CHANGED')
    baseline=private_read(old/'runtime-before.json')
    for name,pin in p.PINS.items():
        current=r.inspect(name)
        need(current['Id']==baseline[name]['Id'] and current['Image']==pin['image_id']
             and r.fingerprint(current)==r.fingerprint(baseline[name]),'FAILED_GAMES_RUNTIME_DRIFT')
    cached=recover_academy_pos_builds(r,p,run)
    for repo in ('V79acaedmy','V79POS'):
        record=private_read(old/(repo+'-built-image.json'))
        need(record=={'repo':repo,'source_commit':p.SOURCES[repo],'image_id':cached[repo]},
             'PRIOR_CACHED_IMAGE_RECEIPT_CHANGED')
    repo='Gaming-Studio-J';revision=p.SOURCES[repo];stage=old/repo
    need(r.call(['git','-C',str(stage),'rev-parse','HEAD']).decode().strip()==revision,
         'CACHED_GAMES_SOURCE_CHANGED')
    r.call(['git','-C',str(stage),'diff','--exit-code','HEAD','--'])
    need(not r.call(['git','-C',str(stage),'ls-files','--others','-z']),
         'CACHED_GAMES_UNTRACKED_CONTEXT')
    record=private_read(old/(repo+'-built-image.json'))
    need(record.get('repo')==repo and record.get('source_commit')==revision
         and r.IMAGE.fullmatch(record.get('image_id','')),'CACHED_GAMES_RECEIPT_INVALID')
    image=r.inspect(record['image_id'],image=True)
    need(image['Id']==record['image_id']
         and (image['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')==revision,
         'CACHED_GAMES_IMAGE_SOURCE_CHANGED')
    created=datetime.fromisoformat(image['Created'].replace('Z','+00:00')).timestamp()
    need(helper.stat().st_mtime-2<=created<=(old/'exit-code').stat().st_mtime+2,
         'CACHED_GAMES_BUILD_TIME_NOT_PROVEN')
    identity=old.name.split('.')[-1]
    cleanup_probe(r,'v79-release-probe-'+identity+'-3',identity,image['Id'])
    cached[repo]=image['Id']
    r.private_json(run/'cached-all-builds-proof.json',{'prior_run':str(old),
        'helper_blob':FAILED_GAMES_HELPER_BLOB,'sources':p.SOURCES,'images':cached,
        'scope':'THREE_VERIFIED_CANDIDATES_GAMES_REPROBE_REQUIRED'})
    r.emit('RESULT','CACHED_ACADEMY_POS_GAMES_BUILDS_VERIFIED_NO_REBUILD')
    return cached


def build_images(r,p,run,before,cached=None,skip_cached_probes=()):
    images={}
    for repo,revision in p.SOURCES.items():
        if cached and repo in cached:
            r.emit('PHASE','REUSE_VERIFIED_'+repo.upper())
            candidate=r.inspect(cached[repo],image=True)
            need(candidate['Id']==cached[repo],'CACHED_IMAGE_ID_CHANGED')
        else:
            r.emit('PHASE','BUILD_'+repo.upper().replace('-','_'))
            stage=run/repo
            r.call(['git','init','-q',str(stage)])
            r.call(['git','-C',str(stage),'fetch','--depth','1','--no-tags','https://github.com/MrFixITslu/'+repo+'.git',revision],timeout=300)
            need(r.call(['git','-C',str(stage),'rev-parse','FETCH_HEAD']).decode().strip()==revision,'SOURCE_PIN_FAILED')
            r.call(['git','-C',str(stage),'checkout','--detach','-q',revision])
            r.public_checkout_modes(stage)
            tag='v79-portfolio/'+repo.lower()+':'+revision
            r.call(['docker','build','--label','org.opencontainers.image.revision='+revision,'--build-arg','V79_SOURCE_COMMIT='+revision,'--tag',tag,str(stage)],timeout=3600)
            candidate=r.inspect(tag,image=True)
        need(r.IMAGE.fullmatch(candidate['Id']) and not candidate['Config'].get('Volumes')
             and (candidate['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')==revision,'CANDIDATE_SOURCE_OR_VOLUMES_INVALID')
        r.private_json(run/(repo+'-built-image.json'),{'repo':repo,'source_commit':revision,'image_id':candidate['Id']})
        for name,pin in p.PINS.items():
            if pin['repo']!=repo:continue
            for field in ('User','Entrypoint','Cmd','WorkingDir'):
                if not before[name]['Config'].get(field):
                    need(not candidate['Config'].get(field),'CANDIDATE_NEW_'+field.upper()+'_DEFAULT')
            need(set(r.envmap(candidate['Config'].get('Env')))<=set(r.envmap(before[name]['Config'].get('Env'))),'CANDIDATE_NEW_ENVIRONMENT_DEFAULT')
            if cached and repo in cached and name in skip_cached_probes:
                r.emit('RESULT',name+'_PRIOR_EXECUTION_AND_PROBE_CLEANUP_ACCEPTED_NO_REPROBE')
            else:
                probe_image(r,run,name,candidate['Id'],before[name])
            images[name]=candidate['Id']
    return images

WORKER_PROBE=r"""
const fs=require('fs');let pid;
for(const name of fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x))){
 try{const args=fs.readFileSync('/proc/'+name+'/cmdline').toString().split('\0');
 if(require('path').basename(args[0])==='node'&&args.some(x=>/(?:^|\/)worker\.js$/.test(x))){pid=name;break}}
 catch{}
}
if(!pid)process.exit(2);
const entries=fs.readFileSync('/proc/'+pid+'/environ').toString().split('\0');
const value=entries.find(x=>x.startsWith('DATABASE_URL='));if(value)process.env.DATABASE_URL=value.slice(13);
import('/app/apps/api/dist/lib/prisma.js').then(async({prisma})=>{
 try{await prisma.$transaction(async(tx)=>{await tx.$executeRawUnsafe('SET TRANSACTION READ ONLY');await tx.$queryRawUnsafe('SELECT 1')});console.log('WORKER_PROCESS_AND_READ_ONLY_DATABASE_PASS')}
 finally{await prisma.$disconnect()}
}).catch(()=>process.exit(3));
"""

def wait_service(r,name,image,worker_probe=False):
    if name!='v79-pos-worker':return r.health(name,image,timeout=240)
    for _ in range(10):
        row=r.inspect(name)
        need(row['Image']==image and row['State'].get('Running') is True,'POS_WORKER_NOT_STABLE_RUNNING')
        time.sleep(2)
    if worker_probe:
        output=r.call(['docker','exec',name,'node','-e',WORKER_PROBE],timeout=35)
        need(output.strip()==b'WORKER_PROCESS_AND_READ_ONLY_DATABASE_PASS','POS_WORKER_DATABASE_PROBE_FAILED')
        r.emit('RESULT','POS_WORKER_PROCESS_AND_DB_READ_ONLY_PASS')
        r.emit('RESULT','POS_WORKER_JOB_DELIVERY_NOT_TESTED')
    return r.inspect(name)

def frozen_candidates(r,p,run,before,models,images):
    plans={}
    for name,pin in p.PINS.items():
        original=run/(name+'-original.pinned.yml');r.private_json(original,models[name])
        model=copy.deepcopy(models[name]);model['services'][pin['compose_service']]['image']=images[name]
        candidate=run/(name+'-candidate.pinned.yml');r.private_json(candidate,model)
        rendered=json.loads(r.call(r.compose(candidate,pin['compose_project'],'config','--format','json')))
        service=rendered['services'][pin['compose_service']]
        need(r.compose_runtime(service.get('environment',{}))==r.envmap(before[name]['Config'].get('Env')),'FROZEN_ENVIRONMENT_DRIFT')
        r.validate_storage_and_networks(rendered,service,before[name])
        plans[name]=(original,candidate)
    return plans

def checkpoint_and_switch(r,p,run,before,models,images,key,all_before):
    plans=frozen_candidates(r,p,run,before,models,images)
    gnupg=run/'gnupg';gnupg.mkdir(mode=0o700)
    r.call(['gpg','--homedir',str(gnupg),'--batch','--import'],data=base64.b64decode(key,validate=True))
    keys=r.call(['gpg','--homedir',str(gnupg),'--batch','--with-colons','--fingerprint',r.RECIPIENT]).decode()
    need('fpr:::::::::'+r.RECIPIENT+':' in keys,'RECOVERY_KEY_MISMATCH')
    directory=run/'checkpoint';directory.mkdir(mode=0o700)
    r.emit('PHASE','ENCRYPT_REMAINING_APP_AND_DEPENDENCY_IMAGES')
    r.encrypted_stream(['docker','image','save',*sorted({before[n]['Image'] for n in p.PINS} | set(DATABASES.values()) | {REDIS_IMAGE})],directory/'original-images-with-dependencies.tar.gpg',gnupg)
    check_plan(r,p);r.same_others(all_before,set())
    timers=r.active_timers();stopped=[];changed=[];success=False
    try:
        if timers:
            r.call(['systemctl','--user','stop',*timers]);r.timers_idle(timers)
        check_plan(r,p)
        r.emit('PHASE','QUIESCE_ONLY_REMAINING_APPS_FOR_CHECKPOINT')
        for name in STOP_ORDER:
            stopped.append(name);r.call(['docker','stop','--time','60',name],timeout=90)
        for db in DATABASES:
            r.encrypted_stream(['docker','exec',db,'sh','-c','exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -Fc'],directory/(db+'.dump.gpg'),gnupg)
        # Redis replication snapshot streams to stdout; no plaintext local copy.
        # Redis source: https://github.com/redis/redis/blob/7.2/src/redis-cli.c (getRDB).
        r.encrypted_stream(['docker','exec','v79-pos-redis','redis-cli','--rdb','-'],directory/'v79-pos-redis.rdb.gpg',gnupg)
        for name,row in before.items():
            for index,mount in enumerate(row['Mounts']):
                r.encrypted_stream(['docker','cp',name+':'+mount['Destination'],'-'],directory/(name+'-mount-'+str(index)+'.tar.gpg'),gnupg)
        r.encrypted_stream(['tar','-C',str(run),'-cf','-','runtime-before.json','plan-reference.json',*[n+'-original.pinned.yml' for n in p.PINS]],directory/'runtime-and-config.tar.gpg',gnupg)
        files=[{'name':x.name,'sha256':r.sha_file(x),'bytes':x.stat().st_size} for x in sorted(directory.iterdir())]
        r.private_json(directory/'manifest.json',{'files':files,'status':'CAPTURED_NOT_RESTORE_TESTED',
                        'scope':'REMAINING_ACADEMY_POS_GAMES_PRECHANGE_NOT_FULL_PORTFOLIO',
                        'source_images':{n:before[n]['Image'] for n in p.PINS},'dependency_images':{**DATABASES,'v79-pos-redis':REDIS_IMAGE},'candidates':images,'sources':p.SOURCES})
        r.emit('CHECKPOINT','ENCRYPTED_REMAINING_COMPLETE_NOT_RESTORE_TESTED')
        r.same_others(all_before,set(p.PINS))
        for name in SWITCH_ORDER:
            pin=p.PINS[name];r.emit('PHASE','SWITCH_'+name.upper().replace('-','_'));changed.append(name)
            try:
                r.up(plans[name][1],pin)
                current=wait_service(r,name,images[name],worker_probe=True)
                need(r.fingerprint(current)==r.fingerprint(before[name]),'RUNTIME_CONFIGURATION_CHANGED')
            except BaseException:
                r.capture_failed_startup(run,name,images[name]);raise
            r.emit('DEPLOYED',name+('_STABLE_PROCESS_DB_VERIFIED_RUNTIME_PRESERVED' if name=='v79-pos-worker' else '_HEALTHY_CONFIGURATION_PRESERVED'))
        r.same_others(all_before,set(p.PINS))
        check_shared_releases(r,p)
        need(p.pos_migrations(r)['status']=='PASS','POS_MIGRATION_HISTORY_CHANGED')
        r.private_json(run/'release-receipt.json',{'images':images,'sources':p.SOURCES,'health':'PASS_THREE_APPS',
                        'pos_worker':'STABLE_PROCESS_READ_ONLY_DATABASE_PASS_JOB_DELIVERY_NOT_TESTED',
                        'checkpoint':'REMAINING_PRECHANGE_CAPTURE_NOT_RESTORE_TESTED','security_acceptance':'NOT_PERFORMED'})
        success=True;r.emit('RESULT','ACADEMY_POS_GAMES_DEPLOYED_WITH_WORKER_PROCESS_DB_CHECK')
    finally:
        if not success:
            failed=False
            # Every stopped original is restored, including those never switched.
            recovery=list(reversed(changed))+[n for n in reversed(stopped) if n not in changed]
            for name in recovery:
                try:
                    if name in changed:r.up(plans[name][0],p.PINS[name])
                    else:r.call(['docker','start',name])
                    current=wait_service(r,name,before[name]['Image'])
                    need(r.fingerprint(current)==r.fingerprint(before[name]),'ROLLBACK_RUNTIME_CHANGED')
                    r.emit('ROLLBACK',name+'_ORIGINAL_RUNNING_RUNTIME_PRESERVED' if name=='v79-pos-worker' else name+'_ORIGINAL_HEALTHY_RUNTIME_PRESERVED')
                except Exception:
                    failed=True;r.emit('ROLLBACK',name+'_NOT_PROVEN_MANUAL_REVIEW_REQUIRED')
            r.emit('ROLLBACK','FAILED_MANUAL_RECOVERY_REQUIRED' if failed else 'ALL_STOPPED_ORIGINALS_RESTORED')
            r.emit('DATA_RESTORE','NOT_AUTOMATIC_IMAGE_ROLLBACK_ONLY')
        r.emit('CUSTOMER_RELEASE','NO_GO')
        if timers:
            r.call(['systemctl','--user','start',*timers]);r.emit('PRESERVED','ORIGINALLY_ACTIVE_USER_TIMERS_RESUMED')

def server(run,key,r,p,continue_academy=False,continue_pos=False,continue_games=False):
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'RUN_ON_V79SL_NON_ROOT')
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(Stop('TERMINATED')))
    os.umask(0o077)
    with (Path.home()/'.v79-portfolio-rollout.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('OTHER_ROLLOUT_OR_DIAGNOSTIC_RUNNING')
        for executable in ('docker','git','gpg'):need(shutil.which(executable),'DEPENDENCY_MISSING')
        memory={x.split(':')[0]:int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines()}
        need(memory['MemAvailable']>=1500*1024,'BUILD_MEMORY_INSUFFICIENT')
        need(shutil.disk_usage(run).free>=15*1024**3,'BUILD_DISK_INSUFFICIENT')
        help_text=r.call(['docker','compose','up','--help']).decode()
        need(all(x in help_text for x in ('--no-deps','--no-build','--pull')),'COMPOSE_OPTIONS_UNSUPPORTED')
        redis_help=r.call(['docker','exec','v79-pos-redis','redis-cli','--help']).decode()
        need('--rdb' in redis_help,'REDIS_SNAPSHOT_OPTION_UNSUPPORTED')
        need(r.call(['docker','exec','v79-pos-redis','redis-cli','--raw','PING']).strip()==b'PONG','REDIS_BACKUP_AUTH_UNAVAILABLE')
        r.emit('PHASE','REVALIDATE_ACCEPTED_PRIVATE_PLAN')
        before,models=check_plan(r,p)
        check_pos_environment(before['v79-pos']);check_pos_environment(before['v79-pos-worker'])
        cached=(recover_all_builds(r,p,run) if continue_games else
                recover_academy_pos_builds(r,p,run) if continue_pos else
                recover_academy_build(r,p,run) if continue_academy else None)
        names=r.call(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
        all_before={x['Name'].lstrip('/'):x for x in json.loads(r.call(['docker','inspect',*names]))}
        r.private_json(run/'runtime-before.json',all_before)
        r.private_json(run/'plan-reference.json',{'directory':str(PLAN),'summary_sha256':r.sha_file(PLAN/'plan-summary.json'),'sources':p.SOURCES})
        skip=('v79_course_builder','v79-pos','v79-pos-worker') if continue_games else ()
        images=build_images(r,p,run,before,cached=cached,skip_cached_probes=skip)
        # Expensive builds do not authorize stale runtime/config or new migrations.
        check_plan(r,p);r.same_others(all_before,set())
        checkpoint_and_switch(r,p,run,before,models,images,key,all_before)

def acer(args):
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'RUN_ON_NON_ROOT_ACER')
    os.umask(0o077)
    repo=Path.home()/'v79-r1-src.PnZUGsH9/repo'
    with tempfile.TemporaryDirectory(prefix='v79-release-modules.') as tmp:
        stage=Path(tmp)
        for filename,(path,digest) in MODULES.items():
            proc=subprocess.run(['git','-C',str(repo),'show',MODULE_COMMIT+':'+path],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
            need(proc.returncode==0 and blob(proc.stdout)==digest,'PINNED_MODULE_UNAVAILABLE_OR_CHANGED')
            (stage/filename).write_bytes(proc.stdout)
        r,p=load_modules(stage)
        if args.resume:
            need(re.fullmatch(RUN_RE,args.resume),'RESUME_DIRECTORY_INVALID');return r.monitor(args.resume)
        key=r.call(['gpg','--batch','--export',r.RECIPIENT]);need(key,'RECOVERY_PUBLIC_KEY_UNAVAILABLE')
        directory=r.remote(['mktemp','-d','/home/firelion/v79-remaining-rollout.XXXXXXXX']).decode().strip()
        need(re.fullmatch(RUN_RE,directory),'REMOTE_DIRECTORY_INVALID')
        r.emit('CHECKPOINT',directory)
        for filename,data in [('rollout.py',Path(__file__).read_bytes()),*[(n,(stage/n).read_bytes()) for n in MODULES]]:
            r.call([*r.SSH,'umask 077; cat > '+shlex.quote(directory+'/'+filename)],data=data)
        launch_args=['python3','-B','-u',directory+'/rollout.py','--server',directory,base64.b64encode(key).decode()]
        if args.continue_built_academy:launch_args.append('--continue-built-academy')
        if args.continue_built_academy_pos:launch_args.append('--continue-built-academy-pos')
        if args.continue_built_academy_pos_games:launch_args.append('--continue-built-academy-pos-games')
        launch=shlex.join(launch_args)
        r.call([*r.SSH,'umask 077; nohup '+launch+' > '+shlex.quote(directory+'/progress.log')+' 2>&1 < /dev/null &'])
        return r.monitor(directory)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--server',nargs=2);parser.add_argument('--resume');parser.add_argument('--continue-built-academy',action='store_true');parser.add_argument('--continue-built-academy-pos',action='store_true');parser.add_argument('--continue-built-academy-pos-games',action='store_true');args=parser.parse_args()
    need(not(args.server and args.resume) and not(args.resume and (args.continue_built_academy or args.continue_built_academy_pos or args.continue_built_academy_pos_games)) and sum((args.continue_built_academy,args.continue_built_academy_pos,args.continue_built_academy_pos_games))<=1,'CONFLICTING_MODES')
    if not args.server:return acer(args) or 0
    run=Path(args.server[0]);need(re.fullmatch(RUN_RE,str(run)) and run==Path(__file__).resolve().parent,'REMOTE_DIRECTORY_INVALID')
    code=1;r=p=None
    try:
        r,p=load_modules(run);server(run,args.server[1],r,p,continue_academy=args.continue_built_academy,continue_pos=args.continue_built_academy_pos,continue_games=args.continue_built_academy_pos_games);code=0
    except BaseException as error:
        trusted=isinstance(error,Stop) or r is not None and isinstance(error,r.Stop) or p is not None and isinstance(error,p.Stop)
        message=str(error)
        if not trusted and r is not None:report_exception(r,error,'UNEXPECTED_ROLLOUT_EXCEPTION')
        print('STOP='+ (message if trusted and re.fullmatch(r'[A-Z0-9_]+',message) else 'REMAINING_ROLLOUT_ERROR_REDACTED'),flush=True)
    finally:
        print('CUSTOMER_RELEASE=NO_GO',flush=True);(run/'exit-code').write_text(str(code))
    return code

if __name__=='__main__':
    try:sys.exit(main())
    except KeyboardInterrupt:print('STOP=ACER_MONITOR_INTERRUPTED_CHECK_REMOTE_STATUS');sys.exit(1)
    except Exception as error:
        trusted=isinstance(error,Stop) or type(error).__module__ in ('verified_rollout','verified_remaining_plan') and type(error).__name__=='Stop'
        message=str(error)
        print('STOP='+(message if trusted and re.fullmatch(r'[A-Z0-9_]+',message) else 'LOCAL_ERROR_REDACTED_REMOTE_WORKER_MAY_CONTINUE'));sys.exit(1)
