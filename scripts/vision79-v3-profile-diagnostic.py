#!/usr/bin/env python3
"""One targeted proof using unchanged pinned supervisor/engine; no cutover API."""
import argparse
import ast
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT=Path('/home/firelion/v79-v3-hardened-hub-manifest-20261026')
SUPERVISOR='v79_v3_hardened_hub_release.py'
SUPERVISOR_SHA='89f5e1a0a72da32bebda84068cae7e0f790ba62cdf386e84f98bbe0a3c33bc62'
OLD_SCOPE='v79profile07f5dde175de4b1a'
class Stop(Exception): pass
def require(ok,code):
    if not ok: raise Stop(code)
def emit(**items): print(json.dumps(items,sort_keys=True),flush=True)
def safe_code(error,allowed):
    value=str(error);base=value.split(':',1)[0]
    if base not in allowed: return 'UNCLASSIFIED_ERROR'
    if value==base: return base
    # Only known Docker Config/HostConfig field names; never application labels.
    suffix=value.split(':',1)[1]
    fields={'Binds','Mounts','NetworkMode','OomKillDisable','ReadonlyRootfs',
            'SecurityOpt','CapAdd','CapDrop','RestartPolicy','LogConfig',
            'Hostname','Domainname','User','WorkingDir','Cmd','Entrypoint',
            'Healthcheck','StopSignal','StopTimeout','Volumes','ExposedPorts',
            'AttachStdin','AttachStdout','AttachStderr','Tty','OpenStdin',
            'StdinOnce','ArgsEscaped','MacAddress'}
    if base in {'HOST_FIELDS_CHANGED','ACTUAL_CONFIG_FIELDS_CHANGED'}:
        parts=suffix.split(',')
        if parts and all(p in fields for p in parts): return base+':'+','.join(parts)
    return base
def codes_from_source(*paths):
    codes=set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_bytes())):
            if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                    and node.func.id=='Refused' and node.args):
                value=node.args[0]
                if isinstance(value,ast.BinOp): value=value.left
                if isinstance(value,ast.Constant) and isinstance(value.value,str):
                    code=value.value.rstrip(':')
                    if re.fullmatch('[A-Z][A-Z0-9_]+',code): codes.add(code)
    return codes
def bookkeeping_checks(row,entry,which):
    labels=row.get('Config',{}).get('Labels') or {}
    expected={
        'config_files':('com.docker.compose.project.config_files',str(entry[which+'_file'])),
        'image':('com.docker.compose.image',entry[which+'_image']['Id']),
        'version':('com.docker.compose.version',entry['compose_version']),
        'environment_file':('com.docker.compose.project.environment_file','/dev/null'),
    }
    return {name:{'present':key in labels,'matches':labels.get(key)==value}
            for name,(key,value) in expected.items()}
def docker(*args):
    p=subprocess.run(['docker',*args],capture_output=True,timeout=30)
    require(p.returncode==0,'DOCKER_READ_UNAVAILABLE')
    return p.stdout.decode()
def residue(scope):
    names=docker('ps','--all','--format','{{.Names}}').splitlines()
    volumes=docker('volume','ls','--filter','label=v79.profile.scope='+scope,'--format','{{.Name}}').splitlines()
    return {'containers':sum(n.startswith(scope+'-') for n in names),
            'volumes':len(volumes),'directory':(ROOT/scope).exists() or (ROOT/scope).is_symlink()}
def evidence(allowed):
    found=set();count=0
    # Bounded immediate release receipts only. Do not print file names/contents.
    for p in sorted(ROOT.iterdir()):
        if p.name in {'transaction.json','supervision.json'} or p.suffix not in {'.json','.jsonl','.log'}: continue
        st=p.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode&0o077 or st.st_size>1024*1024: continue
        count+=1
        text=p.read_text(errors='replace')
        for token in re.findall(r'\b[A-Z][A-Z0-9_]{5,100}\b',text):
            if token in allowed: found.add(token)
    return count,sorted(found)

def recover_known_scope():
    """Remove only unused nonce-labelled local scratch volumes; retain files."""
    require(not docker('ps','--all','--filter','name='+OLD_SCOPE,
                       '--format','{{.ID}}').strip(),'PROFILE_CONTAINER_REQUIRES_REVIEW')
    directory=ROOT/OLD_SCOPE
    archive=ROOT/(OLD_SCOPE+'.evidence')
    require(not archive.exists() and not archive.is_symlink(),'PROFILE_EVIDENCE_ALREADY_ARCHIVED')
    info=directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and not directory.is_symlink()
            and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,
            'PROFILE_DIRECTORY_UNSAFE')
    # Preserve all private model/bind files, including any original error evidence.
    volumes=docker('volume','ls','--filter','label=v79.profile.scope='+OLD_SCOPE,
                   '--format','{{.Name}}').splitlines()
    require(len(volumes)==1,'EXPECTED_SINGLE_SYNTHETIC_VOLUME')
    for name in volumes:
        require(re.fullmatch(re.escape(OLD_SCOPE)+r'-[01]-volume-[0-9]+',name) is not None,
                'SYNTHETIC_VOLUME_NAME_MISMATCH')
        v=json.loads(docker('volume','inspect',name))[0]
        require(v.get('Name')==name and v.get('Driver')=='local'
                and not v.get('Options')
                and (v.get('Labels') or {}).get('v79.profile.scope')==OLD_SCOPE,
                'SYNTHETIC_VOLUME_OWNERSHIP_MISMATCH')
        require(not docker('ps','--all','--filter','volume='+name,
                           '--format','{{.ID}}').strip(),'SYNTHETIC_VOLUME_IN_USE')
    # No force, no prune, no recursive deletion, no real mount path access.
    for name in volumes:
        docker('volume','rm',name)
    require(not docker('volume','ls','--filter','label=v79.profile.scope='+OLD_SCOPE,
                       '--format','{{.Name}}').strip(),'SYNTHETIC_VOLUME_REMAINS')
    directory.rename(archive)
    emit(phase='KNOWN_SCOPE_CLEANUP',synthetic_volumes_removed=len(volumes),
         private_evidence_preserved=True,application_containers_changed=False)

def main(proof=False,cleanup=False):
    require(os.uname().nodename=='v79sl','AUTHORIZED_DELL_ONLY')
    require(ROOT.is_dir() and not ROOT.is_symlink(),'RELEASE_DIRECTORY_UNAVAILABLE')
    path=ROOT/SUPERVISOR;st=path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid() and not st.st_mode&0o077,
            'SUPERVISOR_FILE_UNSAFE')
    require(hashlib.sha256(path.read_bytes()).hexdigest()==SUPERVISOR_SHA,'SUPERVISOR_DIGEST_CHANGED')
    spec=importlib.util.spec_from_file_location('v79_existing_supervisor',path)
    sup=importlib.util.module_from_spec(spec);spec.loader.exec_module(sup)
    # Same lock as the supervisor, nonblocking: never race a release or recovery.
    fd=os.open(sup.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Stop('RELEASE_LOCK_BUSY') from None
        engine,plan,backend=sup.engine_plan()
        require(sup.state() is None,'RELEASE_STATE_EXISTS_REVIEW_REQUIRED')
        require(len(plan['protected'])==43,'PROTECTED_SCOPE_NOT_EXACTLY_43')
        sup.assert_prior_snapshot(engine,plan,backend)
        if cleanup:
            require(os.getenv('V79_V3_OWNER_PRESENT')=='I_AM_PRESENT_FOR_MFA_SSO_AND_VISUAL_CHECKS',
                    'OWNER_SUPERVISION_REQUIRED')
            recover_known_scope()
            sup.assert_prior_snapshot(engine,plan,backend)
        old=residue(OLD_SCOPE)
        emit(phase='EXISTING_SCOPE_CHECK',old_scope_residue=old,prior_healthy=True,protected_43_match=True)
        require(not any(old.values()),'FAILED_PROFILE_RESIDUE_REVIEW_REQUIRED')
        allowed=codes_from_source(ROOT/'paired-compose-transaction.py',ROOT/'paired-mount-contract.py')
        count,found=evidence(allowed)
        emit(phase='EXISTING_RECEIPTS',receipts_scanned=count,safe_engine_codes=found)
        if found:
            return {'result':'EXISTING_ERROR_EVIDENCE_REVIEW_REQUIRED','release_gate':'HOLD'}
        if not proof:
            return {'result':'EXACT_PREDICATE_NOT_PERSISTED','release_gate':'HOLD'}
        require(os.getenv('V79_V3_OWNER_PRESENT')=='I_AM_PRESENT_FOR_MFA_SSO_AND_VISUAL_CHECKS',
                'OWNER_SUPERVISION_REQUIRED')
        original=engine.runtime_matches
        failures=[]
        def observed(before,after,entry,which,**kwargs):
            try: return original(before,after,entry,which,**kwargs)
            except Exception as error:
                failures.append({'profile':which,'safe_error':safe_code(error,allowed),
                                 'bookkeeping_fields':bookkeeping_checks(after,entry,which)})
                emit(phase='FAILED_RUNTIME_PREDICATE',**failures[-1])
                raise
        engine.runtime_matches=observed
        error_code=None;result=None
        try:
            with sup.heartbeat(): result=engine.stopped_profiles(backend)
        except Exception as error:
            error_code=safe_code(error,allowed)
            emit(phase='ENGINE_OUTCOME_BEFORE_POSTCHECK',engine_error=error_code,
                 exception_type=type(error).__name__,profile_predicates=failures)
        finally: engine.runtime_matches=original
        # Proof owns its cleanup. No fallback deletion or production changes here.
        sup.assert_prior_snapshot(engine,plan,backend)
        pending=docker('ps','--all','--format','{{.Names}}').splitlines()
        remaining=[n for n in pending if n.startswith('v79profile')]
        emit(phase='POST_PROOF',prior_healthy=True,protected_43_match=True,
             profile_predicates=failures,engine_error=error_code,
             remaining_profile_containers=len(remaining),proof=result)
        return {'result':'TARGETED_PROOF_FAILED' if error_code else 'TARGETED_PROOF_PASSED',
                'release_gate':'HOLD','production_cutover_attempted':False}
    finally:
        os.close(fd)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--proof-once',action='store_true')
    parser.add_argument('--cleanup-known-scope',action='store_true')
    args=parser.parse_args()
    try:
        result=main(args.proof_once,args.cleanup_known_scope);emit(**result)
        sys.exit(0 if result['result']=='TARGETED_PROOF_PASSED' else 2)
    except Exception as error:
        emit(result='DIAGNOSTIC_STOP',safe_error=str(error) if isinstance(error,Stop) else 'PRECONDITION_FAILED',exception_type=type(error).__name__,release_gate='HOLD')
        sys.exit(2)
