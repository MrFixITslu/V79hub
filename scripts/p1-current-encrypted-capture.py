#!/usr/bin/env python3
"""Current P1-only capture: default PLAN is read-only; pause requires approval.

No deployment, image switch, database restore or old rollout-plan reuse.
Secrets enter encrypted streams only. Offhost copying/decryption uses the
previously reviewed source-pinned utility, not its rollout functions.
"""
import argparse
import base64
import fcntl
import hashlib
import importlib.util
import io
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
import tarfile
import tempfile
import time

ACCEPTED=Path('/home/firelion/v79-portfolio-rollout.6kvFDd5e')
CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
CORE_COMMIT='ff575e62697638cedeee65591518318569d6155a'
APPS=('v79-hub','v79-tiquet-manager')
DBS={'v79-hub-postgres':('sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24','17'),
     'tiquet-postgres':('sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685','16')}
ALLOWED_HUB={'/app/data','/app/logs','/run/secrets/v79-agent-token',
 '/run/secrets/v79-workforce-token','/run/secrets/v79-readonly-platform-token',
 '/run/secrets/v79-coo-github-token','/run/v79-workforce-reports'}
RUN_RE=r'/home/firelion/v79-p1-current-capture\.[A-Za-z0-9]{8}'
class Stop(Exception):pass
def need(ok,code):
    if not ok:raise Stop(code)
def blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def plan_safe(line):
    key,sep,value=line.partition('=')
    if not sep:return False
    if key=='P1_CAPTURE_PLAN_SHA256':return bool(re.fullmatch(r'[a-f0-9]{64}',value))
    if re.fullmatch(r'CAPTURE_TIMER_[1-9][0-9]*',key):
        return bool(re.fullmatch(r'v79[-A-Za-z0-9@_.]+\.timer',value) and re.search(r'(workforce|release|task)',value))
    if key in ('TIMER_PAUSE_COUNT','HUB_MOUNT_COUNT','TIQUET_MOUNT_COUNT'):return bool(re.fullmatch(r'[0-9]{1,3}',value))
    return (key,value) in {('PAUSE_REQUIRED','HUB_AND_TIQUET_AND_LISTED_TIMERS'),('PLAN','READ_ONLY_READY'),
        ('DATABASES_REMAIN_RUNNING','YES'),('DATA_CAPTURE_BUDGET_SECONDS','600'),
        ('PRODUCTION_CHANGES','NONE'),('CUSTOMER_RELEASE','NO_GO'),('R1_CUSTOMER_RELEASE','NO_GO')} or bool(key=='STOP' and re.fullmatch(r'[A-Z0-9_]+',value))

def plan_emit(key,value):
    line=key+'='+str(value);need(plan_safe(line),'PLAN_OUTPUT_INVALID');print(line,flush=True)

def load_core(path):
    need(path.is_file() and not path.is_symlink() and blob(path.read_bytes())==CORE_BLOB,'TRUSTED_UTILITY_CHANGED')
    spec=importlib.util.spec_from_file_location('p1_capture_utility',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
def private(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid() and path.stat().st_mode&0o077==0,'PRIVATE_RECEIPT_UNSAFE')
    return json.loads(path.read_bytes())
def config_file(path):
    need(path.is_absolute() and '..' not in path.parts and path.is_file() and not path.is_symlink()
         and path.stat().st_uid in (0,os.getuid()) and path.stat().st_mode&0o002==0 and path.stat().st_size<=2097152,'COMPOSE_INPUT_UNSAFE')
    return path.read_bytes()
def overlap(a,b):
    return os.path.commonpath([a,b]) in (a,b)
def collect(r):
    receipt=private(ACCEPTED/'release-receipt.json')
    names=r.call(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
    rows=json.loads(r.call(['docker','container','inspect',*names]))
    all_before={row['Name'].lstrip('/'):row for row in rows}
    need(len(all_before)==len(names),'CONTAINER_INVENTORY_INVALID')
    selected={name:all_before[name] for name in (*APPS,*DBS)}
    for name,row in selected.items():
        image=receipt['images'][name] if name in APPS else DBS[name][0]
        need(row['Image']==image and row['State'].get('Running') is True
             and row['State'].get('Health',{}).get('Status')=='healthy','CURRENT_P1_IMAGE_OR_HEALTH_CHANGED')
    models={};inputs={}
    for name in APPS:
        row=selected[name];labels=row['Config']['Labels']
        paths=labels['com.docker.compose.project.config_files'].split(',')
        need(0<len(paths)<=40 and len(set(paths))==len(paths),'COMPOSE_CHAIN_INVALID')
        entries=[]
        for text in paths:
            raw=config_file(Path(text));inputs[text]=raw
            entries.append({'path':text,'sha256':hashlib.sha256(raw).hexdigest()})
        env=Path(labels['com.docker.compose.project.working_dir'])/'.env'
        if env.exists():inputs[str(env)]=config_file(env)
        pin={'container':name,'image_id':row['Image'],'compose_project':labels['com.docker.compose.project'],
             'compose_service':labels['com.docker.compose.service'],'compose_inputs':entries}
        models[name]=r.original_model(row,pin)
        mounts=row.get('Mounts') or []
        destinations=[m.get('Destination') for m in mounts]
        allowed=ALLOWED_HUB if name=='v79-hub' else {'/app/data','/app/uploads'}
        required={'/app/data'} if name=='v79-hub' else allowed
        need(len(destinations)==len(set(destinations)) and required<=set(destinations)<=allowed
             and all(m.get('Type') in ('bind','volume') and str(m.get('Source','')).startswith('/') for m in mounts),'APP_MOUNT_SCOPE_UNREVIEWED')
        for mount in mounts:
            for other,foreign in all_before.items():
                if other in APPS or not foreign.get('State',{}).get('Running'):continue
                for fm in foreign.get('Mounts') or []:
                    need(not(fm.get('RW') and fm.get('Source') and overlap(mount['Source'],fm['Source'])),'OTHER_WRITER_SHARES_APP_STORAGE')
    h=r.envmap(selected[APPS[0]]['Config'].get('Env'));t=r.envmap(selected[APPS[1]]['Config'].get('Env'))
    need(h.get('V79_REQUIRE_ADMIN_MFA')=='1' and t.get('V79_ALLOW_LEGACY_AUTH')=='0'
         and t.get('V79_ENTITLEMENT_RECHECK_ENABLED')=='1','SECURITY_FLAGS_CHANGED')
    need(h.get('V79_TIQUET_LAUNCH_SECRET') and h.get('V79_TIQUET_LAUNCH_SECRET')==t.get('V79_TIQUET_LAUNCH_SECRET'),'SSO_KEYS_INCONSISTENT')
    for name,(_,major) in DBS.items():
        version=r.call(['docker','exec',selected[name]['Id'],'pg_dump','--version']).decode()
        need(re.search(r'PostgreSQL\) '+major+r'\.',version),'PG_DUMP_VERSION_UNEXPECTED')
        r.call(['docker','exec',selected[name]['Id'],'sh','-c','pg_isready -q -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}"'])
    timers=sorted(r.active_timers())
    stable={'containers':{n:{'id':x['Id'],'image':x['Image'],'runtime':r.fingerprint(x)} for n,x in selected.items()},
            'inputs':{p:hashlib.sha256(raw).hexdigest() for p,raw in inputs.items()},'timers':timers}
    digest=hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    need(sum(map(len,inputs.values()))<=32*1024**2,'CONFIG_ARCHIVE_TOO_LARGE')
    return digest,selected,all_before,models,inputs,timers
def stream(r,args,destination,keyring,timeout):
    producer=encryptor=None
    with destination.open('xb') as target:
        try:
            producer=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=r.clean_env())
            encryptor=subprocess.Popen(['gpg','--homedir',str(keyring),'--batch','--quiet','--trust-model','always','--encrypt','--recipient',r.RECIPIENT],stdin=producer.stdout,stdout=target,stderr=subprocess.DEVNULL,env=r.clean_env())
            producer.stdout.close()
            need(encryptor.wait(timeout=timeout)==0 and producer.wait(timeout=10)==0,'ENCRYPTED_STREAM_FAILED')
        finally:
            if producer is not None and producer.stdout is not None:producer.stdout.close()
            for child in (producer,encryptor):
                if child is not None:
                    if child.poll() is None:child.kill()
                    child.wait()
    need(destination.stat().st_size>64,'ENCRYPTED_STREAM_EMPTY')
def configuration_archive(r,selected,models,inputs):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as archive:
        records={'runtime.json':json.dumps(selected,sort_keys=True).encode(),
                 'frozen-compose.json':json.dumps(models,sort_keys=True).encode(),
                 'input-map.json':json.dumps({str(i):path for i,path in enumerate(inputs)},sort_keys=True).encode()}
        records.update({'config/'+str(i):raw for i,raw in enumerate(inputs.values())})
        for name,raw in records.items():
            info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o600
            archive.addfile(info,io.BytesIO(raw))
    return output.getvalue()
def restore(r,selected,stopped,timers):
    good=True
    for name in reversed(stopped):
        try:
            current=r.inspect(selected[name]['Id'])
            need(current['Image']==selected[name]['Image'],'ORIGINAL_IDENTITY_CHANGED')
            r.call(['docker','start',selected[name]['Id']],timeout=60)
            current=r.health(name,selected[name]['Image'],timeout=180)
            need(current['Id']==selected[name]['Id'] and r.fingerprint(current)==r.fingerprint(selected[name]),'ORIGINAL_RUNTIME_CHANGED')
            r.emit('RESULT',name+'_SAME_CONTAINER_HEALTHY')
        except BaseException:
            good=False;r.emit('RESULT',name+'_NOT_PROVEN_REQUIRES_REVIEW')
    if good and timers:r.call(['systemctl','--user','start',*timers]);r.emit('PRESERVED','ORIGINALLY_ACTIVE_RESUMED')
    elif timers:r.emit('PRESERVED','HELD_APP_RECOVERY_NOT_PROVEN')
    need(good,'APP_RESUME_NOT_PROVEN')
def resume_apps(r,run,expected_helper):
    need(re.fullmatch(RUN_RE,str(run)) and run.is_dir() and not run.is_symlink()
         and run.stat().st_uid==os.getuid() and run.stat().st_mode&0o077==0,'RESUME_DIRECTORY_UNSAFE')
    journal=private(run/'resume-journal.json')
    helper=run/'capture.py'
    need(helper.is_file() and not helper.is_symlink() and helper.stat().st_uid==os.getuid() and helper.stat().st_mode&0o077==0,'RESUME_HELPER_UNSAFE')
    need(re.fullmatch(r'[a-f0-9]{40}',expected_helper or '') and journal.get('helper_blob')==expected_helper==blob(helper.read_bytes()) and set(journal.get('apps',{}))==set(APPS),'RESUME_JOURNAL_INVALID')
    timers=journal.get('timers')
    need(isinstance(timers,list) and all(isinstance(t,str) and re.fullmatch(r'v79[-A-Za-z0-9@_.]+\.timer',t)
         and re.search(r'(workforce|release|task)',t) for t in timers),'RESUME_TIMERS_INVALID')
    receipt=private(ACCEPTED/'release-receipt.json');selected={}
    for name,entry in journal['apps'].items():
        need(re.fullmatch(r'[a-f0-9]{64}',entry.get('id','')),'RESUME_ID_INVALID')
        row=r.inspect(entry['id'])
        digest=hashlib.sha256(json.dumps(r.fingerprint(row),sort_keys=True).encode()).hexdigest()
        need(row['Id']==entry['id'] and row['Image']==entry['image']==receipt['images'][name]
             and row['Name']=='/'+name and digest==entry['runtime_sha256'],'RESUME_RUNTIME_CHANGED')
        selected[name]=row
    restore(r,selected,list(reversed(APPS)),timers)
    r.emit('RESULT','EXACT_CAPTURED_APP_IDS_HEALTHY')
def capture(r,run,key,approved_digest):
    digest,selected,before,models,inputs,timers=collect(r)
    need(digest==approved_digest,'APPROVED_PLAN_CHANGED')
    for tool in ('gpg','docker'):need(shutil.which(tool),'CAPTURE_TOOL_MISSING')
    memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    need(memory.get('MemAvailable',0)>=1500*1024,'CAPTURE_MEMORY_INSUFFICIENT')
    free=shutil.disk_usage(run).free
    sizes=sum(r.inspect(image,image=True).get('Size',0) for image in {x['Image'] for x in selected.values()})
    need(free>=2*sizes+10*1024**3,'CAPTURE_DISK_INSUFFICIENT')
    keyring=run/'gnupg';keyring.mkdir(mode=0o700)
    r.call(['gpg','--homedir',str(keyring),'--batch','--import'],data=base64.b64decode(key,validate=True))
    keys=r.call(['gpg','--homedir',str(keyring),'--batch','--with-colons','--fingerprint',r.RECIPIENT]).decode()
    need('fpr:::::::::'+r.RECIPIENT+':' in keys,'RECOVERY_KEY_CHANGED')
    cp=run/'checkpoint';cp.mkdir(mode=0o700)
    r.emit('PHASE','ENCRYPT_CURRENT_IMAGES_BEFORE_ANY_PAUSE')
    stream(r,['docker','save',*sorted({x['Image'] for x in selected.values()})],cp/'original-app-images.tar.gpg',keyring,1200)
    need(collect(r)[0]==digest,'PLAN_CHANGED_DURING_IMAGE_EXPORT')
    # Public identity/digest journal only: no environment or customer plaintext.
    r.private_json(run/'resume-journal.json',{'helper_blob':blob(Path(__file__).read_bytes()),'plan_sha256':digest,
        'timers':timers,'apps':{n:{'id':selected[n]['Id'],'image':selected[n]['Image'],
        'runtime_sha256':hashlib.sha256(json.dumps(r.fingerprint(selected[n]),sort_keys=True).encode()).hexdigest()} for n in APPS}})
    stopped=[];paused_timers=[]
    try:
        if timers:
            paused_timers=timers[:];r.call(['systemctl','--user','stop',*timers]);r.timers_idle(timers)
        deadline=time.monotonic()+600
        r.emit('PHASE','APPROVED_PAUSE_ONLY_HUB_AND_TIQUET')
        for name in reversed(APPS):
            stopped.append(name)
            r.call(['docker','stop','--time','60',selected[name]['Id']],timeout=90)
        def budget():
            remaining=deadline-time.monotonic();need(remaining>0,'CAPTURE_PAUSE_BUDGET_EXCEEDED');return min(300,remaining)
        for name in DBS:
            stream(r,['docker','exec',selected[name]['Id'],'sh','-c','exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -Fc'],cp/(name+'.dump.gpg'),keyring,budget())
        for name in APPS:
            for index,mount in enumerate(selected[name]['Mounts']):
                stream(r,['docker','cp',selected[name]['Id']+':'+mount['Destination'],'-'],cp/(name+'-mount-'+str(index)+'.tar.gpg'),keyring,budget())
        with (cp/'runtime-and-config.tar.gpg').open('xb') as out:
            r.call(['gpg','--homedir',str(keyring),'--batch','--quiet','--trust-model','always','--encrypt','--recipient',r.RECIPIENT],data=configuration_archive(r,selected,models,inputs),output=out,timeout=budget())
        need(all(config_file(Path(path))==raw for path,raw in inputs.items()),'CONFIG_CHANGED_DURING_CAPTURE')
    finally:
        restore(r,selected,stopped,paused_timers)
    r.same_others(before,set(APPS))
    need(collect(r)[0]==digest,'P1_RUNTIME_CHANGED_AFTER_CAPTURE')
    files=[{'name':p.name,'sha256':r.sha_file(p),'bytes':p.stat().st_size} for p in sorted(cp.iterdir())]
    need(all(x['bytes']>64 for x in files),'CAPTURE_ARTIFACT_EMPTY')
    r.private_json(cp/'manifest.json',{'status':'CAPTURED_NOT_RESTORE_TESTED','scope':'P1_CURRENT_HUB_TIQUET_ONLY',
       'source_images':{n:x['Image'] for n,x in selected.items()},'plan_sha256':digest,'files':files,
       'configuration_format':'runtime.json_frozen-compose.json_input-map.json_config_index_v1',
       'restore_acceptance':'NOT_PERFORMED'})
    r.emit('RESULT','ENCRYPTED_COMPLETE_APPS_SAME_IDS_HEALTHY')
    r.emit('RESULT','DEPLOYMENT_NONE');r.emit('CUSTOMER_RELEASE','NO_GO')
def server(args):
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'SERVER_NONROOT_REQUIRED')
    os.umask(0o077)
    lock=Path.home()/'.v79-portfolio-rollout.lock'
    need(lock.is_file() and not lock.is_symlink(),'EXISTING_LOCK_UNSAFE')
    with lock.open('rb') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('OTHER_OPERATION_RUNNING')
        r=load_core(ACCEPTED/'rollout.py')
        if args.server_plan:
            digest,selected,_,_,_,timers=collect(r);plan_emit('P1_CAPTURE_PLAN_SHA256',digest)
            plan_emit('PAUSE_REQUIRED','HUB_AND_TIQUET_AND_LISTED_TIMERS')
            plan_emit('TIMER_PAUSE_COUNT',len(timers))
            for index,timer in enumerate(timers,1):plan_emit('CAPTURE_TIMER_'+str(index),timer)
            plan_emit('HUB_MOUNT_COUNT',len(selected[APPS[0]]['Mounts']));plan_emit('TIQUET_MOUNT_COUNT',len(selected[APPS[1]]['Mounts']))
            plan_emit('DATABASES_REMAIN_RUNNING','YES');plan_emit('DATA_CAPTURE_BUDGET_SECONDS','600')
            plan_emit('PLAN','READ_ONLY_READY')
            plan_emit('PRODUCTION_CHANGES','NONE');plan_emit('CUSTOMER_RELEASE','NO_GO');return
        if args.server_resume:
            need(args.approve_pause,'EXPLICIT_RESUME_APPROVAL_REQUIRED')
            return resume_apps(r,Path(args.server_resume),args.helper_blob)
        need(args.approve_pause and args.server_capture and re.fullmatch(r'[a-f0-9]{64}',args.plan_sha or ''),'PAUSE_APPROVAL_REQUIRED')
        run=Path(args.server_capture[0]);need(re.fullmatch(RUN_RE,str(run)) and run==Path(__file__).resolve().parent,'CAPTURE_DIRECTORY_INVALID')
        signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(Stop('TERMINATED_RESUME_REQUIRED')))
        capture(r,run,args.server_capture[1],args.plan_sha)
def acer(args):
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    os.umask(0o077)
    repo=Path.home()/'v79-r1-src.PnZUGsH9/repo'
    with tempfile.TemporaryDirectory(prefix='v79-p1-capture-utility.') as tmp:
        path=Path(tmp)/'core.py'
        proc=subprocess.run(['git','-C',str(repo),'show',CORE_COMMIT+':scripts/portfolio-pinned-rollout.py'],capture_output=True,timeout=30)
        need(proc.returncode==0 and blob(proc.stdout)==CORE_BLOB,'PINNED_UTILITY_UNAVAILABLE')
        path.write_bytes(proc.stdout);r=load_core(path)
        if args.resume:
            need(re.fullmatch(RUN_RE,args.resume),'RESUME_DIRECTORY_INVALID');return r.monitor(args.resume)
        if args.resume_apps:
            need(args.approve_pause and re.fullmatch(RUN_RE,args.resume_apps),'EXPLICIT_RESUME_APPROVAL_REQUIRED')
            command='python3 -B - --server-resume '+shlex.quote(args.resume_apps)+' --approve-pause --helper-blob '+blob(Path(__file__).read_bytes())
            proc=subprocess.run([*r.SSH,command],input=Path(__file__).read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=600)
            for line in proc.stdout.decode('utf8','replace').splitlines():
                need(r.SAFE_LINE.fullmatch(line),'REMOTE_OUTPUT_NOT_SAFE');print(line,flush=True)
            need(proc.returncode==0,'CAPTURE_APP_RESUME_FAILED');return
        if not args.capture:
            proc=subprocess.run([*r.SSH,'python3 -B - --server-plan'],input=Path(__file__).read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=240)
            for line in proc.stdout.decode('utf8','replace').splitlines():
                need(plan_safe(line),'REMOTE_OUTPUT_NOT_SAFE');print(line,flush=True)
            need(proc.returncode==0,'READ_ONLY_CAPTURE_PLAN_FAILED');return
        need(args.approve_pause and re.fullmatch(r'[a-f0-9]{64}',args.capture),'EXPLICIT_PAUSE_APPROVAL_REQUIRED')
        key=r.call(['gpg','--batch','--export',r.RECIPIENT]);need(key,'RECOVERY_PUBLIC_KEY_UNAVAILABLE')
        directory=r.remote(['mktemp','-d','/home/firelion/v79-p1-current-capture.XXXXXXXX']).decode().strip()
        need(re.fullmatch(RUN_RE,directory),'CAPTURE_DIRECTORY_INVALID');r.emit('CHECKPOINT',directory)
        r.call([*r.SSH,'umask 077; cat > '+shlex.quote(directory+'/capture.py')],data=Path(__file__).read_bytes())
        launch=shlex.join(['python3','-B','-u',directory+'/capture.py','--server-capture',directory,base64.b64encode(key).decode(),'--plan-sha',args.capture,'--approve-pause'])
        r.call([*r.SSH,'umask 077; nohup '+launch+' > '+shlex.quote(directory+'/progress.log')+' 2>&1 < /dev/null &'])
        r.monitor(directory)
def self_test():
    assert overlap('/a/b','/a/b/c') and not overlap('/a/b','/a/bc')
    assert not re.fullmatch(RUN_RE,'/home/firelion/other')
    assert set(DBS)=={'v79-hub-postgres','tiquet-postgres'}
    print('SELF_TEST=PASS')
def main():
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');p.add_argument('--server-plan',action='store_true')
    p.add_argument('--server-capture',nargs=2);p.add_argument('--capture');p.add_argument('--resume');p.add_argument('--resume-apps');p.add_argument('--server-resume');p.add_argument('--plan-sha');p.add_argument('--helper-blob');p.add_argument('--approve-pause',action='store_true')
    args=p.parse_args()
    need(sum(bool(x) for x in (args.capture,args.resume,args.resume_apps,args.server_plan,args.server_capture,args.server_resume))<=1,'CONFLICTING_MODES')
    if args.self_test:return self_test()
    if args.server_capture:
        run=Path(args.server_capture[0])
        need(re.fullmatch(RUN_RE,str(run)) and run==Path(__file__).resolve().parent
             and run.is_dir() and not run.is_symlink() and run.stat().st_uid==os.getuid() and run.stat().st_mode&0o077==0,'CAPTURE_DIRECTORY_INVALID')
        code=1
        try:server(args);code=0
        finally:(run/'exit-code').write_text(str(code))
        return
    if args.server_plan or args.server_resume:return server(args)
    return acer(args)
if __name__=='__main__':
    try:main()
    except BaseException as error:
        message=str(error);trusted=isinstance(error,Stop) or type(error).__module__=='p1_capture_utility' and type(error).__name__=='Stop'
        print('STOP='+(message if trusted and re.fullmatch(r'[A-Z0-9_]+',message) else 'P1_CAPTURE_FAILED_REVIEW_SAFE_STATUS'),flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO',flush=True);sys.exit(1)
