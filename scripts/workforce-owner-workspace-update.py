#!/usr/bin/env python3
"""Pinned UI-only Hub update. Keeps the existing backend, settings and mounts."""
import copy, hashlib, json, os, shlex, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
SOURCE='b1c2a24e903509d4037d0166bc31813fcf25e228'
BRANCH='feature/p1-workforce-operations-g3-20261016'
BASE='sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698'
OTHER={'v79-business-agent':'sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f','v79-tiquet-manager':'sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42'}
UI=['src/components/OwnerAssistant.tsx','src/components/WorkforceActionPanel.tsx','src/components/OwnerCooWorkboardPanel.tsx']
TEST='tests/owner-workspace-ui.test.mjs'
TIMER='v79-g2-approved-task-worker.timer'
SERVICE='v79-g2-approved-task-worker.service'
STAGE=None

def private(path,data):
    with path.open('x') as f:
        os.chmod(path,0o600)
        f.write(data if isinstance(data,str) else json.dumps(data,indent=2))

def run(args,timeout=60,cwd=None):
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout,cwd=cwd)
    if p.returncode:
        if STAGE:
            private(STAGE/('failure-'+str(time.time_ns())+'.log'),p.stdout+'\n'+p.stderr)
        raise RuntimeError('Command failed; details retained in private stage logs')
    return p.stdout.strip()

def inspect(names):return json.loads(run(['docker','inspect',*names]))
def env(rows):return dict(item.split('=',1) for item in rows or [] if '=' in item)
def healthy(row,image):return row['Image']==image and row['State'].get('Health',{}).get('Status')=='healthy'
def image_only(before,after,service,image):
    normalized=copy.deepcopy(after)
    if normalized['services'][service]['image']!=image:raise RuntimeError('Candidate image missing')
    normalized['services'][service]['image']=before['services'][service]['image']
    if normalized!=before:raise RuntimeError('Update would change more than the Hub image')
def runtime_same(before,after):
    for key in ['Env','Cmd','Entrypoint','User','WorkingDir']:
        a,b=before['Config'].get(key),after['Config'].get(key)
        if key=='Env':a,b=env(a),env(b)
        if a!=b:raise RuntimeError('Runtime application configuration drift')
    for key in ['ReadonlyRootfs','CapAdd','CapDrop','SecurityOpt','Privileged','NetworkMode','PortBindings','Memory','NanoCpus','PidsLimit','RestartPolicy']:
        if before['HostConfig'].get(key)!=after['HostConfig'].get(key):raise RuntimeError('Runtime security, resource or port drift')
    def mounts(row):return sorted(tuple(str(m.get(k,'')) for k in ['Type','Source','Destination','RW','Name']) for m in row['Mounts'])
    if mounts(before)!=mounts(after):raise RuntimeError('Existing mount drift')

def wait_health(image):
    for _ in range(90):
        row=inspect(['v79-hub'])[0]
        if healthy(row,image):return row
        time.sleep(2)
    raise RuntimeError('Hub did not reach healthy state on the exact image')

def main():
    global STAGE
    os.umask(0o077)
    if socket.gethostname()!='v79sl':raise RuntimeError('Run on v79sl only')
    for tool in ['git','docker','systemctl']:
        if not shutil.which(tool):raise RuntimeError('Required local tool missing')
    mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    if int(mem['MemAvailable'].strip().split()[0])<2*1024*1024:raise RuntimeError('Less than 2 GiB available RAM')
    if shutil.disk_usage(Path.home()).free<5*1024**3:raise RuntimeError('Less than 5 GiB free disk')
    originals=inspect(['v79-hub',*OTHER]);hub=originals[0]
    if not healthy(hub,BASE) or any(not healthy(r,OTHER[r['Name'].lstrip('/')]) for r in originals[1:]):raise RuntimeError('Live image or health baseline changed')
    labels=hub['Config']['Labels'];files=labels['com.docker.compose.project.config_files'].split(',')
    if len(files)!=12 or len(set(files))!=12:raise RuntimeError('Expected the verified 12 ordered Compose inputs')
    paths=[Path(p) for p in files]
    if any(not p.is_absolute() or p.is_symlink() or not p.is_file() for p in paths):raise RuntimeError('Unsafe Compose input path')
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    working=labels['com.docker.compose.project.working_dir'];service=labels['com.docker.compose.service']
    compose=['docker','compose','--project-directory',working,'--project-name',labels['com.docker.compose.project']]
    for f in files:compose+=['-f',f]
    baseline=json.loads(run(compose+['config','--format','json'],cwd=working))
    svc=baseline['services'][service]
    if svc.get('image')!=BASE:raise RuntimeError('Effective Compose baseline image differs')
    img=json.loads(run(['docker','image','inspect',BASE]))[0]
    effective={**env(img['Config'].get('Env')),**{k:str(v) for k,v in svc.get('environment',{}).items() if v is not None}}
    if effective!=env(hub['Config'].get('Env')):raise RuntimeError('Compose environment differs from running Hub')
    for field,key in [('command','Cmd'),('entrypoint','Entrypoint'),('user','User'),('working_dir','WorkingDir')]:
        expected=svc.get(field)
        if expected is None:expected=img['Config'].get(key)
        if expected!=hub['Config'].get(key):raise RuntimeError('Compose process configuration differs from running Hub')
    ports={}
    for p in svc.get('ports',[]):ports.setdefault(str(p['target'])+'/'+p.get('protocol','tcp'),[]).append(p)
    actual=hub['HostConfig'].get('PortBindings') or {}
    if set(ports)!=set(actual):raise RuntimeError('Compose port targets differ from running Hub')
    for target,bindings in actual.items():
        for b in bindings:
            if not any(str(p.get('published',''))==b['HostPort'] and (p.get('host_ip')==b['HostIp'] if p.get('host_ip') else b['HostIp'] in ['', '0.0.0.0', '::']) for p in ports[target]):raise RuntimeError('Compose port binding differs from running Hub')
        if {str(p.get('published','')) for p in ports[target]}!={b['HostPort'] for b in bindings}:raise RuntimeError('Compose published ports differ from running Hub')
    for v in svc.get('volumes',[]):
        source=v['source']
        if v['type']=='volume':source=baseline['volumes'][source]['name']
        matches=[m for m in hub['Mounts'] if m['Destination']==v['target']]
        if len(matches)!=1:raise RuntimeError('Compose mount missing from running Hub')
        m=matches[0]
        if m['Type']!=v['type'] or m.get('Name' if v['type']=='volume' else 'Source')!=source or m['RW']==v.get('read_only',False):raise RuntimeError('Compose mount differs from running Hub')
    if len(svc.get('volumes',[]))!=len(hub['Mounts']):raise RuntimeError('Unexpected live mount')
    root=Path.home()/'.local/share/v79-approved-task-worker'
    if (root/'uncertain.json').exists():raise RuntimeError('Worker reconciliation is outstanding; do not restart Hub during an uncertain task')
    STAGE=Path(tempfile.mkdtemp(prefix='v79-owner-workspace.',dir=Path.home()))
    private(STAGE/'runtime-before.json',originals)
    private(STAGE/'compose-before.json',baseline)
    private(STAGE/'compose-hashes.json',hashes)
    print('STAGE_DIRECTORY='+str(STAGE),flush=True)
    print('STAGE=FETCH_PINNED_UI_SOURCE',flush=True)
    source=STAGE/'source'
    run(['git','clone','--quiet','--single-branch','--branch',BRANCH,'https://github.com/MrFixITslu/V79hub.git',str(source)],timeout=180)
    run(['git','-C',str(source),'checkout','--quiet','--detach',SOURCE])
    if run(['git','-C',str(source),'rev-parse','HEAD'])!=SOURCE:raise RuntimeError('Pinned UI source mismatch')
    context=STAGE/'build';context.mkdir()
    for f in UI+[TEST]:
        dest=context/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/f,dest);dest.chmod(0o644)
    tag='v79-owner-ui:'+STAGE.name.split('.')[-1].lower();base_tag=tag+'-base'
    run(['docker','tag',BASE,base_tag])
    (context/'Dockerfile').write_text('FROM '+base_tag+'\nWORKDIR /app\n'+''.join('COPY --chmod=0644 '+f+' /app/'+f+'\n' for f in UI+[TEST])+
        'LABEL org.opencontainers.image.revision="ui-overlay-'+SOURCE+'"\nLABEL v79.ui.source="'+SOURCE+'"\nLABEL v79.ui.parent="'+BASE+'"\nRUN npm run build\n')
    print('STAGE=BUILD_UI_ONLY_NO_NETWORK',flush=True)
    try:run(['docker','build','--network','none','--pull=false','-t',tag,str(context)],timeout=600)
    finally:run(['docker','image','rm',base_tag])
    candidate=json.loads(run(['docker','image','inspect',tag]))[0]['Id']
    print('CANDIDATE_IMAGE='+candidate,flush=True)
    print('STAGE=NETWORK_ISOLATED_UI_AND_APPROVAL_TESTS',flush=True)
    run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','768m','--cpus','1','--pids-limit','128','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','-e','NODE_ENV=development','-e','NODE_OPTIONS=--import=./tests/isolated-env.mjs','--entrypoint','node',candidate,'--test',TEST,'tests/owner-coo-workboard-ui.test.mjs','tests/workforce-briefing-history-ui.test.mjs','tests/workforce-actions.test.mjs','tests/workforce-action-routes.test.mjs'],timeout=180)
    print('ISOLATED_UI_AND_APPROVAL_TESTS=PASS',flush=True)
    overlay=STAGE/'ui-image.compose.json';rollback=STAGE/'rollback-image.compose.json'
    private(overlay,{'services':{service:{'image':candidate}}});private(rollback,{'services':{service:{'image':BASE}}})
    desired=json.loads(run(compose+['-f',str(overlay),'config','--format','json'],cwd=working))
    image_only(baseline,desired,service,candidate)
    rolled=json.loads(run(compose+['-f',str(rollback),'config','--format','json'],cwd=working))
    if rolled!=baseline:raise RuntimeError('Rollback configuration differs from original')
    up=['up','-d','--no-deps','--no-build','--pull','never',service]
    rollback_command=compose+['-f',str(rollback)]+up
    private(STAGE/'rollback-command.txt',shlex.join(rollback_command)+'\n')
    print('CONFIG_DIFF=HUB_IMAGE_ONLY',flush=True)
    print('ROLLBACK_COMMAND_FILE='+str(STAGE/'rollback-command.txt'),flush=True)
    timer_was_active=subprocess.run(['systemctl','--user','is-active','--quiet',TIMER]).returncode==0
    timer_stopped=False;changed=False;safe_to_resume=True
    try:
        if timer_was_active:
            run(['systemctl','--user','stop',TIMER]);timer_stopped=True
        for _ in range(40):
            state=run(['systemctl','--user','show',SERVICE,'--property=ActiveState','--value'])
            if state not in ['active','activating','deactivating']:break
            time.sleep(1)
        else:raise RuntimeError('Task worker is still active; no Hub change made')
        if (root/'uncertain.json').exists():raise RuntimeError('Task worker needs reconciliation; no Hub change made')
        for f,digest in hashes.items():
            if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=digest:raise RuntimeError('Compose input changed during preparation')
        if json.loads(run(compose+['-f',str(overlay),'config','--format','json'],cwd=working))!=desired:raise RuntimeError('Effective configuration changed during preparation')
        current=inspect(['v79-hub',*OTHER])
        for before,after in zip(originals,current):
            if before['Id']!=after['Id'] or not healthy(after,before['Image']):raise RuntimeError('Live baseline changed during preparation')
        print('STAGE=REPLACE_ONLY_HUB_PRESERVE_BACKEND_AND_SETTINGS',flush=True)
        changed=True;safe_to_resume=False
        run(compose+['-f',str(overlay)]+up,timeout=180,cwd=working)
        after=wait_health(candidate);runtime_same(hub,after)
        check="for(const path of ['/api/agent/work-actions','/api/agent/coo-workboard','/api/agent/workforce-briefings']){const r=await fetch('http://127.0.0.1:3040'+path);if(![401,403].includes(r.status))process.exit(1)}console.log('ANONYMOUS_OWNER_DATA=DENIED')"
        print(run(['docker','exec','v79-hub','node','--input-type=module','-e',check]),flush=True)
        for original in originals[1:]:
            other=inspect([original['Name']])[0]
            if other['Id']!=original['Id'] or not healthy(other,original['Image']):raise RuntimeError('Another app changed')
        private(STAGE/'success.json',{'state':'HEALTHY_UI_UPDATE','source':SOURCE,'baseImage':BASE,'candidateImage':candidate,'changedFiles':UI,'browserAcceptance':'OUTSTANDING','at':time.time()})
        safe_to_resume=True
        print('OWNER_WORKSPACE_UPDATE=DEPLOYED_HEALTHY',flush=True)
        print('ENVIRONMENT_AND_MOUNTS=UNCHANGED',flush=True)
        print('AGENT_AND_TIQUET=UNCHANGED_HEALTHY',flush=True)
    except Exception:
        if changed:
            print('STAGE=RESTORE_EXACT_PREVIOUS_HUB_IMAGE',flush=True)
            try:
                run(rollback_command,timeout=180,cwd=working);runtime_same(hub,wait_health(BASE));safe_to_resume=True
                print('ROLLBACK=HEALTHY_ORIGINAL_IMAGE',flush=True)
            except Exception:
                print('ROLLBACK=UNCONFIRMED_OPERATOR_RECOVERY_REQUIRED',flush=True)
        raise
    finally:
        if timer_stopped and safe_to_resume and not (root/'uncertain.json').exists():
            run(['systemctl','--user','start',TIMER]);print('TASK_WORKER_TIMER=RESUMED',flush=True)
        elif timer_stopped:print('TASK_WORKER_TIMER=LEFT_STOPPED_RECONCILE_BEFORE_RESUME',flush=True)
    print('OWNER_BROWSER_CHECK=REFRESH_OWNER_ASSISTANT',flush=True)
    print('RELEASE_WORKER_SCHEDULED=NO_CHANGE',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('OWNER_WORKSPACE_UPDATE=STOPPED_OR_ROLLED_BACK')
        print('REASON='+str(error) if isinstance(error,RuntimeError) else 'REASON='+type(error).__name__)
        if STAGE:print('PRIVATE_STAGE_DIRECTORY='+str(STAGE))
        raise SystemExit(1)
