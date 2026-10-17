#!/usr/bin/env python3
"""Acer-driven, detached Academy/POS/Games rollout from the accepted private plan."""
import argparse
import base64
import copy
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
    receipt=private_read(p.ACCEPTED_RUN/'release-receipt.json')
    for name in ('v79-hub','v79-tiquet-manager'):
        row=r.inspect(name)
        need(row['Image']==receipt['images'][name] and row['State'].get('Health',{}).get('Status')=='healthy','HUB_TIQUET_RELEASE_CHANGED')
    for name,image in {**DATABASES,'v79-pos-redis':REDIS_IMAGE}.items():
        row=r.inspect(name)
        need(row['Image']==image and row['State'].get('Running') is True,'DEPENDENCY_IMAGE_OR_STATE_CHANGED')
        if name!='v79_academy_postgres':need(row['State'].get('Health',{}).get('Status')=='healthy','DEPENDENCY_UNHEALTHY')
    return baseline,models

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
    args=['docker','create','--name',probe,'--label',label+'='+identity,'--pull','never','--network','none',
          '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','128m',
          '--memory-swap','128m','--pids-limit','48','--entrypoint','node']
    if old['Config'].get('User'):args+=['--user',old['Config']['User']]
    try:
        r.call([*args,image,'-e',code])
        row=r.inspect(probe)
        need(not row['Mounts'] and row['HostConfig']['NetworkMode']=='none'
             and not row['HostConfig'].get('PortBindings'),'PROBE_ISOLATION_INVALID')
        output=r.call(['docker','start','--attach',probe])
        need(output.strip()==b'PUBLIC_EXECUTION_FILES_READABLE' and r.inspect(probe)['State']['ExitCode']==0,'CANDIDATE_PUBLIC_FILES_UNREADABLE')
    finally:
        row=optional_container(r,probe)
        if row is not None:
            need((row['Config'].get('Labels') or {}).get(label)==identity,'FOREIGN_PROBE_REFUSE_CLEANUP')
            r.call(['docker','rm','-f','-v',probe])
        need(optional_container(r,probe) is None,'PROBE_CLEANUP_NOT_PROVEN')
    r.emit('RESULT',name+'_PUBLIC_EXECUTION_AND_PROBE_CLEANUP_PASS')

def build_images(r,p,run,before):
    images={}
    for repo,revision in p.SOURCES.items():
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
        for name,pin in p.PINS.items():
            if pin['repo']!=repo:continue
            for field in ('User','Entrypoint','Cmd','WorkingDir'):
                if not before[name]['Config'].get(field):
                    need(not candidate['Config'].get(field),'CANDIDATE_NEW_'+field.upper()+'_DEFAULT')
            need(set(r.envmap(candidate['Config'].get('Env')))<=set(r.envmap(before[name]['Config'].get('Env'))),'CANDIDATE_NEW_ENVIRONMENT_DEFAULT')
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

def server(run,key,r,p):
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
        names=r.call(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
        all_before={x['Name'].lstrip('/'):x for x in json.loads(r.call(['docker','inspect',*names]))}
        r.private_json(run/'runtime-before.json',all_before)
        r.private_json(run/'plan-reference.json',{'directory':str(PLAN),'summary_sha256':r.sha_file(PLAN/'plan-summary.json'),'sources':p.SOURCES})
        images=build_images(r,p,run,before)
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
        launch=shlex.join(['python3','-B','-u',directory+'/rollout.py','--server',directory,base64.b64encode(key).decode()])
        r.call([*r.SSH,'umask 077; nohup '+launch+' > '+shlex.quote(directory+'/progress.log')+' 2>&1 < /dev/null &'])
        return r.monitor(directory)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--server',nargs=2);parser.add_argument('--resume');args=parser.parse_args()
    need(not(args.server and args.resume),'CONFLICTING_MODES')
    if not args.server:return acer(args) or 0
    run=Path(args.server[0]);need(re.fullmatch(RUN_RE,str(run)) and run==Path(__file__).resolve().parent,'REMOTE_DIRECTORY_INVALID')
    code=1;r=p=None
    try:
        r,p=load_modules(run);server(run,args.server[1],r,p);code=0
    except BaseException as error:
        trusted=isinstance(error,Stop) or r is not None and isinstance(error,r.Stop) or p is not None and isinstance(error,p.Stop)
        message=str(error)
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
