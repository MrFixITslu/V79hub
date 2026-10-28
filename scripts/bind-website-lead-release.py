#!/usr/bin/env python3
"""Bind reviewed inputs to the unchanged paired engine; stopped proof only."""
import contextlib
import copy
import fcntl
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import threading
import time
import urllib.request

ROOT = Path('/home/firelion/v79-lead-release-2pvsb2mo')
INPUT_SHA = '628d37220b899422b0ff2ef957f428e5ed5d2aec45f208e9aa867bb5eefedd52'
SOURCE = 'b233cbfb57960412acc408e833053d75001d0e14'
MODULES = {'paired-compose-transaction.py':'a0d42890a4ad3f39203893dc166e2717545ebe4b',
    'paired-mount-contract.py':'00f46b9284a982748b697b253a4e34317d77f074',
    'paired-release-context.py':'fb32367a8f316884646980bc38f13dc0b43e50f0'}
PINS = {'v79-hub':('2e5f872914bb85f98651ce00a4a90b1880e44076',
    'sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec'),
    'V79website':('43de17780357e776c86a7f8898168a50fa5e2820',
    'sha256:a5ef48c1b1a4dfd29fe33b19f689adae4ca1d1ed344e2bef8b6a16c1684a848c')}
ALLOWED = {'v79-hub':{'V79_WEBSITE_EVENTS_ENABLED','V79_WEBSITE_EVENT_SECRET','V79_WEBSITE_ORGANIZATION_REF'},
    'V79website':{'V79_HUB_EVENT_SECRET','V79_HUB_ORGANIZATION_REF','V79_HUB_EVENT_REPLAY_LEAD_IDS'}}
TIMERS = ('v79-g2-approved-task-worker.timer','v79-workforce-morning.timer','v79-workforce-evening.timer')
REVIEWED_COMPOSE = frozenset(('5.6.0','5.6.1','v5.6.0','v5.6.1'))


def verify_compose_version(installed, prepared=None):
    # docker/compose v5.6.0...v5.6.1 changes only the Go toolchain files.
    # build.go, images.go and executor_ops.go have identical Git blob IDs.
    require(installed in REVIEWED_COMPOSE, 'UNREVIEWED_COMPOSE_VERSION')
    if prepared is not None:
        require(prepared == installed, 'PREPARED_COMPOSE_VERSION_CHANGED')


def require(ok, code):
    if not ok: raise ValueError(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def private(path):
    st=path.lstat()
    require(stat.S_ISREG(st.st_mode) and not path.is_symlink() and st.st_uid==os.geteuid()
        and st.st_nlink==1 and not st.st_mode&0o077, 'PRIVATE_FILE_REQUIRED')
    return path.read_bytes()


def write(path, data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def install_compat(engine):
    original=engine.runtime_matches
    def compatible(before, after, entry, which, **kwargs):
        name=entry['release_name']
        require(name in ALLOWED, 'UNREVIEWED_CODEC')
        verify_compose_version(entry['compose_version'])
        approved=entry['approved_environment']
        require(set(approved)==ALLOWED[name], 'ENVIRONMENT_ALLOWANCE_SCOPE_CHANGED')
        baseline=engine.environment(before['Config'].get('Env') or [])
        require(baseline==engine.environment(entry['baseline']['Config'].get('Env') or []),
            'BASELINE_ENVIRONMENT_CHANGED')
        expected={**baseline,**approved} if which=='candidate' else baseline
        require(engine.environment(after['Config'].get('Env') or [])==expected, 'EFFECTIVE_ENVIRONMENT_CHANGED')
        require(entry['model']['services'][entry['service']]['environment']==expected,
            'SEALED_ENVIRONMENT_CHANGED')
        adjusted_before=copy.deepcopy(before)
        adjusted_before['Config']['Env']=[k+'='+v for k,v in expected.items()]
        normalized=copy.deepcopy(after)
        pin=entry[which+'_image']['Id']
        require(after['Image']==pin, 'ACTUAL_IMAGE_CHANGED')
        labels=normalized['Config']['Labels']
        # These two labels identify the actual Compose resource. Old images
        # may carry stale copies (for example from a committed container), but
        # those image defaults must never remove or replace runtime identity.
        identity={'com.docker.compose.project':entry['project'],
            'com.docker.compose.service':entry['service']}
        for key,value in identity.items():
            require(value and labels.get(key)==value and
                (before['Config'].get('Labels') or {}).get(key)==value,
                'EXACT_COMPOSE_IDENTITY_REQUIRED')
        normalized_entry=copy.deepcopy(entry)
        for image_key in ('candidate_image','rollback_image'):
            inherited=normalized_entry[image_key]['Config'].get('Labels') or {}
            for key in identity:inherited.pop(key,None)
        require(labels.get('com.docker.compose.image')==entry['image_manifests'][pin], 'IMAGE_LABEL_MAPPING_CHANGED')
        labels['com.docker.compose.image']=pin
        replaced=entry.get('_replaced_id')
        if replaced is not None:
            require(re.fullmatch('[0-9a-f]{64}',replaced or '') is not None, 'REPLACEMENT_CONTEXT_INVALID')
            expected_name=entry['model']['services'][entry['service']].get('container_name')
            require(expected_name and labels.get('com.docker.compose.replace')==expected_name,
                'REPLACEMENT_NAME_CHANGED')
            labels['com.docker.compose.replace']=replaced
        try:return original(adjusted_before,normalized,normalized_entry,which,**kwargs)
        except Exception as error:
            prefix=str(error).split(':',1)[0]
            if re.fullmatch('[A-Z][A-Z0-9_]+',prefix):
                print(json.dumps({'phase':'runtime_validation','reason':prefix}),flush=True)
            raise
    engine.runtime_matches=compatible


class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(30);self.sock.connect('/var/run/docker.sock')


def image_metadata(pin):
    connection=DockerConnection('localhost')
    try:
        connection.request('GET','/v1.48/images/'+pin+'/json?manifests=true')
        response=connection.getresponse()
        require(response.status==200,'IMAGE_METADATA_UNAVAILABLE')
        data=json.loads(response.read())
    finally:connection.close()
    require(data.get('Id')==pin and data.get('Os')=='linux' and data.get('Architecture')=='amd64',
        'IMAGE_IDENTITY_OR_PLATFORM_CHANGED')
    manifests=[m for m in data.get('Manifests',[]) if m.get('Kind')=='image' and m.get('Available') is True]
    require(len(manifests)==1,'SOLE_RUNNABLE_IMAGE_MANIFEST_REQUIRED')
    manifest=manifests[0].get('ID') or manifests[0].get('Id')
    require(re.fullmatch('sha256:[0-9a-f]{64}',manifest or '') is not None,'IMAGE_MANIFEST_INVALID')
    return data,manifest


def run(args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
    require(p.returncode==0,'READ_ONLY_COMMAND_FAILED')
    return p.stdout


def timer_states():
    env={**os.environ,'XDG_RUNTIME_DIR':'/run/user/'+str(os.geteuid()),
        'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/'+str(os.geteuid())+'/bus'}
    result={}
    for name in TIMERS:
        p=subprocess.run(['systemctl','--user','show',name,'--property=ActiveState','--value'],
            env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20)
        require(p.returncode==0,'TIMER_STATE_UNAVAILABLE')
        result[name]=p.stdout.decode().strip()
    return result


def protect_core_health(backend):
    original=backend.protected
    def checked():
        original()
        for name in ('v79-business-agent','v79-hub-postgres','tiquet-postgres','v79-tiquet-manager'):
            require(name in backend.plan['protected'],'PROTECTED_CORE_MISSING')
            row=backend.inspect(backend.plan['protected'][name]['Id'])
            require(row['State'].get('Running') and row['State'].get('Health',{}).get('Status')=='healthy',
                'PROTECTED_CORE_NOT_HEALTHY')
    backend.protected=checked


@contextlib.contextmanager
def heartbeat(root):
    def pulse():
        data=canonical({'monotonic':time.monotonic()})
        temporary=root/('.lease-'+str(os.getpid()))
        write(temporary,data);os.replace(temporary,root/'supervision.json')
    halt=threading.Event();failure=[]
    def worker():
        while not halt.wait(4):
            try:pulse()
            except BaseException as error:failure.append(error);return
    pulse();thread=threading.Thread(target=worker,daemon=True);thread.start()
    try:
        yield
        require(not failure,'HEARTBEAT_PERSISTENCE_FAILED')
    finally:halt.set();thread.join(timeout=10)


def bind():
    os.umask(0o077)
    st=ROOT.lstat()
    require(stat.S_ISDIR(st.st_mode) and not ROOT.is_symlink() and st.st_uid==os.geteuid()
        and stat.S_IMODE(st.st_mode)==0o700,'PRIVATE_RELEASE_DIRECTORY_REQUIRED')
    raw=private(ROOT/'configuration-inputs.json')
    require(hashlib.sha256(raw).hexdigest()==INPUT_SHA,'CONFIGURATION_INPUT_DIGEST_CHANGED')
    inputs=json.loads(raw)
    require(inputs.get('schema')=='v79-website-lead-configuration-inputs-v1'
        and inputs.get('engine_bound') is False and inputs.get('deployed') is False
        and inputs.get('selected_lead_id')==2 and set(inputs['prepared'])==set(PINS), 'INPUT_SCOPE_CHANGED')
    require(re.fullmatch('[0-9a-f]{64}',inputs['credential'] or '') is not None,'DEDICATED_SECRET_INVALID')
    lock=os.open(ROOT/'binding.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not (ROOT/'binding-result.json').exists() and not (ROOT/'transaction.json').exists(),
            'BINDING_ALREADY_EXISTS_PRESERVE_EVIDENCE')
        for name,pin in MODULES.items():
            url='https://raw.githubusercontent.com/MrFixITslu/V79hub/'+SOURCE+'/scripts/'+name
            with urllib.request.urlopen(url,timeout=30) as response:data=response.read(1_000_000)
            blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            require(blob==pin,'ENGINE_SOURCE_DIGEST_CHANGED')
            compile(data,name,'exec')
            if (ROOT/name).exists():require(private(ROOT/name)==data,'EXISTING_ENGINE_DIFFERS')
            else:write(ROOT/name,data)
        spec=importlib.util.spec_from_file_location('existing_pair_engine',ROOT/'paired-compose-transaction.py')
        engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
        version=run(['docker','compose','version','--short']).decode().strip()
        verify_compose_version(version)
        options=json.loads(run(['docker','info','--format','{{json .SecurityOptions}}']))
        plan={'schema':'v79-website-lead-pair-v1','requires_supervision':True,
            'selinux_enabled':any('selinux' in s for s in options),'apps':{},
            'protected':{n:r for n,r in inputs['baseline'].items() if n not in PINS}}
        allrows=json.loads(run(['docker','inspect',*[r['Id'] for r in inputs['baseline'].values()]]))
        current={r['Name'].lstrip('/'):r for r in allrows}
        require(set(current)==set(inputs['baseline']),'BASELINE_INVENTORY_CHANGED')
        for name,old in inputs['baseline'].items():
            require(engine.protected_fingerprint(old)==engine.protected_fingerprint(current[name]),
                'PREPARED_BASELINE_CHANGED')
        for name,(revision,pin) in PINS.items():
            p=inputs['prepared'][name];baseline=inputs['baseline'][name];service=p['service']
            verify_compose_version(version,p['compose_version'])
            before_env=engine.environment(baseline['Config'].get('Env') or [])
            candidate=copy.deepcopy(p['candidate']);rollback=copy.deepcopy(p['rollback'])
            expected_changes=({'V79_WEBSITE_EVENTS_ENABLED':'1','V79_WEBSITE_EVENT_SECRET':inputs['credential'],
                'V79_WEBSITE_ORGANIZATION_REF':inputs['organization']} if name=='v79-hub' else
                {'V79_HUB_EVENT_SECRET':inputs['credential'],'V79_HUB_ORGANIZATION_REF':inputs['organization'],
                 'V79_HUB_EVENT_REPLAY_LEAD_IDS':'2'})
            expected=copy.deepcopy(rollback)
            require(rollback['services'][service]['image']==baseline['Image']
                and rollback['services'][service]['environment']==before_env,'ROLLBACK_MODEL_CHANGED')
            expected['services'][service]['image']=pin
            expected['services'][service]['environment']={**before_env,**expected_changes}
            require(candidate==expected and set(p['approved_environment_keys'])==ALLOWED[name],
                'UNREVIEWED_MODEL_DIFFERENCE')
            images={};mapping={}
            for image in (baseline['Image'],pin):images[image],mapping[image]=image_metadata(image)
            require((images[pin]['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')==revision,
                'CANDIDATE_SOURCE_CHANGED')
            entry={'release_name':name,'service':service,'directory':p['directory'],'project':p['project'],
                'baseline':baseline,'model':candidate,'compose_version':version,
                'candidate_image':images[pin],'rollback_image':images[baseline['Image']],
                'image_manifests':mapping,'approved_environment':expected_changes}
            for which,model in (('candidate',candidate),('rollback',rollback)):
                target=ROOT/(name+'.'+which+'.json');data=canonical(model)
                write(target,data);entry[which+'_file']=str(target)
                entry[which+'_sha256']=hashlib.sha256(data).hexdigest()
            plan['apps'][name]=entry
        backend=engine.ComposeBackend(ROOT,plan)
        protect_core_health(backend)
        backend.protected();backend.check_files()
        for name in PINS:
            backend.eligible(name)
            require(current[name]['State'].get('Health',{}).get('Status')=='healthy','TARGET_NOT_HEALTHY')
        timers=timer_states();plan['workforce_timers']=timers
        manifest=engine.seal_plan(ROOT,plan)
        install_compat(engine)
        with heartbeat(ROOT):proof=engine.stopped_profiles(backend)
        require(proof.get('profiles_verified')==4,'FOUR_NEW_CONFIGURATION_PROFILES_REQUIRED')
        require(timer_states()==timers,'WORKFORCE_TIMER_STATE_CHANGED')
        for name in PINS:
            require(engine.protected_fingerprint(backend.inspect(name))==
                engine.protected_fingerprint(plan['apps'][name]['baseline']),'TARGET_BASELINE_CHANGED')
        backend.protected()
        result={'result':'PASS_BOUND_ENGINE_AND_NEW_CONFIGURATION_PROFILES','directory':str(ROOT),
            'inputs_sha256':INPUT_SHA,'manifest_sha256':manifest,'protected_container_count':len(plan['protected']),
            'profiles_verified':4,'live_data_mounted':False,'application_processes_started':False,
            'temporary_cleanup_verified':True,'workforce_timers_preserved':True,'engine_bound':True,'deployed':False}
        write(ROOT/'binding-result.json',canonical(result))
        return result
    finally:os.close(lock)


if __name__=='__main__':
    try:print(json.dumps(bind(),indent=2))
    except Exception as error:
        text=str(error)
        prefix=text.split(':',1)[0]
        reason=prefix if re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else type(error).__name__
        print(json.dumps({'result':'STOP_BINDING','reason':reason,'deployed':False}))
        raise SystemExit(1)
