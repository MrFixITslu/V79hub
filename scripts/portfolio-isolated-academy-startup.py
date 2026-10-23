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
# BEGIN PURE CONTRACT (byte-compared by CI; standalone source-pinned helper)
OWNER = 'v79.private-academy-isolated'
SYNTHETIC = {'PORT': '18081', 'NODE_ENV': 'production',
             'ACADEMY_STANDALONE_ADMIN_ENABLED': '0',
             'V79_PLATFORM_SHARED_SECRET': '',
             'ACADEMY_COURSE_PUBLISH_MODE': 'disabled'}
TMPFS = {'/app/data': '64m', '/tmp': '16m'}


def environment(entries):
    if not isinstance(entries, list):
        return None
    result = {}
    for item in entries:
        if not isinstance(item, str) or '=' not in item:
            return None
        key, value = item.split('=', 1)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or key in result:
            return None
        result[key] = value
    return result


def temporary_storage(value, size):
    if not isinstance(value, str):
        return False
    parts = value.split(',')
    if len(parts) != 7 or len(set(parts)) != 7:
        return False
    return set(parts) == {'rw', 'nosuid', 'nodev', 'size=' + size,
                          'uid=1000', 'gid=1000', 'mode=0700'}


def _validate(row, image, token, public_image_env):
    """Validate only CREATED/RUNNING. Not authorization to remove/start a resource.

    public_image_env must be independently reviewed, pinned image defaults.
    Never derive that allowlist from the container being validated.
    """
    if not isinstance(row, dict) or not isinstance(public_image_env, dict):
        return 'INVALID_INPUT'
    if not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        return 'INVALID_EXPECTED_IMAGE'
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{14}', token):
        return 'INVALID_EXPECTED_OWNER'
    conf = row.get('Config')
    host = row.get('HostConfig')
    state = row.get('State')
    network = row.get('NetworkSettings')
    if not all(isinstance(x, dict) for x in (conf, host, state, network)):
        return 'INVALID_INPUT'
    labels = conf.get('Labels')
    if not isinstance(labels, dict):
        return 'INVALID_INPUT'
    if (row.get('Name') != '/v79-isolated-academy-' + token or
            labels.get(OWNER) != token or 'com.docker.compose.project' in labels):
        return 'OWNERSHIP_MISMATCH'
    if row.get('Image') != image:
        return 'IMAGE_MISMATCH'
    if state.get('Status') not in ('created', 'running'):
        return 'STATE_NOT_ACCEPTED'
    if (any(state.get(k) for k in ('Paused', 'Restarting', 'Dead', 'OOMKilled')) or
            state.get('Running') is not (state['Status'] == 'running')):
        return 'STATE_INCONSISTENT'
    if conf.get('User') != '1000:1000':
        return 'USER_MISMATCH'
    if not isinstance(network.get('Networks'), dict):
        return 'INVALID_INPUT'
    networks = set(network['Networks'])
    if host.get('NetworkMode') != 'none' or networks not in (set(), {'none'}):
        return 'NETWORK_MISMATCH'
    if host.get('PortBindings'):
        return 'PORTS_NOT_ACCEPTED'
    if (host.get('Privileged') or host.get('ReadonlyRootfs') is not True or
            host.get('Binds') or host.get('Mounts') or host.get('VolumesFrom') or
            host.get('Devices') or host.get('DeviceRequests') or host.get('CapAdd') or
            host.get('PidMode') or host.get('UTSMode') or host.get('IpcMode') not in ('private', '') or
            host.get('Sysctls') or host.get('Links') or host.get('ExtraHosts') or
            host.get('GroupAdd') or host.get('UsernsMode') or
            host.get('CgroupnsMode') not in ('private', '')):
        return 'HOST_ISOLATION_MISMATCH'
    if host.get('CapDrop') != ['ALL'] or host.get('SecurityOpt') not in (
            ['no-new-privileges:true'], ['no-new-privileges']):
        return 'PRIVILEGE_RESTRICTION_MISMATCH'
    if ((host.get('RestartPolicy') or {}).get('Name') != 'no' or
            host.get('Memory') != 512 * 1024**2 or host.get('MemorySwap') != 512 * 1024**2 or
            host.get('PidsLimit') != 64 or host.get('NanoCpus') != 750000000):
        return 'RESOURCE_LIMIT_MISMATCH'
    declared = host.get('Tmpfs')
    if not isinstance(declared, dict):
        return 'INVALID_INPUT'
    if set(declared) != set(TMPFS) or any(
            not temporary_storage(declared[path], size) for path, size in TMPFS.items()):
        return 'TMPFS_DECLARATION_MISMATCH'
    mounts = row.get('Mounts')
    if not isinstance(mounts, list) or any(not isinstance(m, dict) for m in mounts):
        return 'INVALID_INPUT'
    realized = (isinstance(mounts, list) and len(mounts) == 2 and
                {m.get('Destination') for m in mounts} == set(TMPFS) and
                all(m.get('Type') == 'tmpfs' and m.get('RW') is True and
                    not m.get('Source') for m in mounts))
    if not realized and not (state['Status'] == 'created' and mounts == []):
        return 'REALIZED_MOUNTS_MISMATCH'
    # Only reviewed noncredential image defaults are eligible for inheritance.
    for key, value in public_image_env.items():
        if (not isinstance(key, str) or not isinstance(value, str) or key in SYNTHETIC or
                re.search(r'SECRET|TOKEN|PASSWORD|API_KEY|DATABASE_URL|REDIS_URL', key, re.I)):
            return 'IMAGE_ENV_ALLOWLIST_UNSAFE'
    if environment(conf.get('Env')) != {**public_image_env, **SYNTHETIC}:
        return 'SYNTHETIC_ENV_MISMATCH'
    return 'PASS_CREATED' if state['Status'] == 'created' else 'PASS_RUNNING'


def validate(row, image, token, public_image_env):
    try:
        return _validate(row, image, token, public_image_env)
    except (TypeError, ValueError, AttributeError, KeyError):
        return 'INVALID_INPUT'


def realized_tmpfs(evidence):
    """Validate captured in-container mountinfo/stat evidence; no host operations."""
    try:
        info=evidence['mountinfo'];stats=evidence['stats']
        if not isinstance(info,str) or not isinstance(stats,dict):return None
        found={}
        for line in info.splitlines():
            fields=line.split();separator=fields.index('-')
            if len(fields)<separator+4:return None
            path=fields[4]
            if path not in TMPFS:continue
            if path in found:return None
            if fields[separator+1:separator+3]!=['tmpfs','tmpfs']:return None
            if not {'rw','nosuid','nodev'}<=set(fields[5].split(',')):return None
            options=fields[separator+3].split(',')
            sizes=[x[5:] for x in options if x.startswith('size=')]
            if len(sizes)!=1:return None
            match=re.fullmatch(r'(\d+)([kKmM]?)',sizes[0])
            if not match:return None
            size=int(match[1])*{'':1,'k':1024,'m':1024**2}[match[2].lower()]
            expected=64*1024**2 if path=='/app/data' else 16*1024**2
            if size!=expected:return None
            if stats.get(path)!={'uid':1000,'gid':1000,'mode':448,'directory':True}:return None
            found[path]={'Type':'tmpfs','Destination':path,'RW':True,'Source':''}
        if set(found)!=set(TMPFS):return None
        return list(found.values())
    except (TypeError,ValueError,KeyError,IndexError,AttributeError):return None
# END PURE CONTRACT
PUBLIC_ENV = {}
EXPECTED_CONFIG = {}

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
    if p.returncode!=0:
        need(kind=='container','IMAGE_INSPECT_FAILED')
        result=command(['docker','container','ls','--all','--no-trunc','--format','{{.ID}}|{{.Names}}'])
        need(result.returncode==0,'CONTAINER_ABSENCE_QUERY_FAILED')
        rows=[line.split('|',1) for line in result.stdout.decode('ascii','replace').splitlines()]
        need(all(len(row)==2 and re.fullmatch(r'[0-9a-f]{64}',row[0]) for row in rows),'CONTAINER_ABSENCE_QUERY_INVALID')
        need(not any(key in row for row in rows),'CONTAINER_INSPECT_FAILED')
        return None
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

def image_environment(img):
    conf=img.get('Config') or {}
    env=environment(conf.get('Env'))
    need(env is not None and set(env)=={'PATH','NODE_VERSION','YARN_VERSION','NODE_ENV','PORT'},'IMAGE_ENV_DEFAULTS_UNREVIEWED')
    need(env['NODE_ENV']=='production' and env['PORT']=='3030'
         and re.fullmatch(r'20\.\d+\.\d+',env['NODE_VERSION'])
         and re.fullmatch(r'\d+\.\d+\.\d+',env['YARN_VERSION'])
         and env['PATH']=='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
         'IMAGE_ENV_DEFAULTS_UNREVIEWED')
    need(conf.get('Cmd')==['node','dist/server.cjs'] and conf.get('WorkingDir')=='/app'
         and conf.get('Entrypoint')==['docker-entrypoint.sh'] and not conf.get('Volumes'),
         'IMAGE_EXECUTION_DEFAULTS_UNREVIEWED')
    return {k:v for k,v in env.items() if k not in SYNTHETIC}

def isolated(row,image,token,cleanup_mode=False):
    if not isinstance(row,dict):return False
    check=row
    state=row.get('State') or {}
    # An exited probe is eligible only for cleanup, never startup acceptance.
    if cleanup_mode and state.get('Status')=='exited':
        check=dict(row);check['State']=dict(state)
        check['State'].update(Status='created',Running=False,OOMKilled=False)
    if state.get('Status')=='running' and row.get('Mounts')==[]:
        # Establish all non-mount guards before executing a bounded read-only
        # probe inside this exact isolated container. Docker --tmpfs can remain
        # absent from inspect.Mounts even after start.
        check=dict(row);check['State']=dict(state,Status='created',Running=False)
        if validate(check,image,token,PUBLIC_ENV)!='PASS_CREATED':return False
        evidence=command(['docker','exec','--user','1000:1000',row['Id'],'node','-e',
            "const fs=require('fs');const stats={};for(const p of ['/app/data','/tmp']){const s=fs.statSync(p);stats[p]={uid:s.uid,gid:s.gid,mode:s.mode&511,directory:s.isDirectory()}}process.stdout.write(JSON.stringify({mountinfo:fs.readFileSync('/proc/self/mountinfo','utf8'),stats}))"],seconds=12)
        if evidence.returncode!=0:return False
        try:mounts=realized_tmpfs(json.loads(evidence.stdout))
        except (ValueError,TypeError):return False
        if mounts is None:return False
        check=dict(row);check['Mounts']=mounts
    if not validate(check,image,token,PUBLIC_ENV).startswith('PASS_'):return False
    conf=row['Config']
    if any(conf.get(k)!=EXPECTED_CONFIG.get(k) for k in ('Cmd','Entrypoint','WorkingDir')):return False
    if (conf.get('Healthcheck') or {}).get('Test')!=['NONE']:return False
    return True

def owner_ids():
    p=command(['docker','container','ls','--all','--no-trunc','--quiet','--filter','label='+OWNED])
    need(p.returncode==0,'PROBE_QUERY_FAILED')
    ids=p.stdout.decode('ascii','replace').splitlines()
    need(all(re.fullmatch(r'[0-9a-f]{64}',x) for x in ids),'PROBE_QUERY_INVALID')
    return ids

def cleanup(probe,token,image,container_id):
    row=inspect('container',container_id)
    if row is None:return True
    need(row.get('Id')==container_id and isolated(row,image,token,cleanup_mode=True),
         'FOREIGN_RESOURCE_REFUSE_CLEANUP')
    try:
        ret=command(['docker','rm','-f',container_id],seconds=105)
        if ret.returncode==0 and inspect('container',container_id) is None:return True
    except Stop:pass
    for _ in range(5):
        if inspect('container',container_id) is None:return True
        time.sleep(2)
    raise Stop('ISOLATED_ACADEMY_CLEANUP_UNCONFIRMED')

def verify_production(r,before):
    for name in PROTECTED:
        now=inspect('container',name);prev=before[name]
        need(now and now['Id']==prev['Id'] and now['Image']==prev['Image'] and
             now['State'].get('Running') is True and r.fingerprint(now)==r.fingerprint(prev),
             'PRODUCTION_RUNTIME_CHANGED')
        if name!='v79-pos-worker':
            need(now['State'].get('Health',{}).get('Status')=='healthy','PRODUCTION_HEALTH_CHANGED')
    emit('PRODUCTION_CONTAINERS','UNCHANGED')

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
    global PUBLIC_ENV,EXPECTED_CONFIG
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
        PUBLIC_ENV=image_environment(img)
        EXPECTED_CONFIG={k:img['Config'].get(k) for k in ('Cmd','Entrypoint','WorkingDir')}
        need(not owner_ids(),'PREVIOUS_ACADEMY_PROBE_REMAINS')
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
        exercise_probe(r,before,image)

def exercise_probe(r,before,image):
    token=secrets.token_hex(7)
    probe='v79-isolated-academy-'+token
    need(inspect('container',probe) is None,'PROBE_NAME_COLLISION')
    cleanup_ok=False
    container_id=None
    try:
        result=command(create_args(image,token),seconds=45)
        need(result.returncode==0,'ACADEMY_CREATE_FAILED')
        container_id=result.stdout.decode('ascii','replace').strip()
        need(re.fullmatch(r'[0-9a-f]{64}',container_id),'CREATE_ID_INVALID')
        need(isolated(inspect('container',probe),image,token),
             'ISOLATION_NOT_PROVEN')
        emit('ACADEMY_ISOLATION','PASS')
        started=command(['docker','start',probe],seconds=45)
        need(started.returncode==0,'ACADEMY_START_FAILED')
        need(isolated(inspect('container',container_id),image,token),'RUNNING_ISOLATION_NOT_PROVEN')
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
    except BaseException as error:
        code=str(error) if isinstance(error,Stop) and re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',str(error)) else 'REDACTED'
        emit('STOP','PRIMARY_'+code)
        raise
    finally:
        try:
            if container_id:
                cleanup_ok=cleanup(probe,token,image,container_id)
                if cleanup_ok:emit('ACADEMY_OWNED_CLEANUP','PASS')
        finally:
            verify_production(r,before)
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
    assert validate({},image,token,{})=='INVALID_INPUT'
    assert not allowed('ENV=SECRET')
    emit('SELF_TEST','PASS')
def acer():
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
          '-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server']
    response=subprocess.run(args,input=Path(__file__).read_bytes(),
                            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=650)
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

