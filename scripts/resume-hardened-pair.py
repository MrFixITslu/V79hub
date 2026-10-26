#!/usr/bin/env python3
"""Resume only the confirmed partial transfer in the already sealed release.

Original runner, plan, models and checkpoint are never rewritten. Once the full
accepted archive is verified/loaded, the original supervised guarded transaction
and rollback path are used unchanged. No app restart occurs during transfer.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
import stat
import subprocess
import sys
import zipfile

ROOT=Path('/home/firelion/.v79-hardened-pair-releases/pair-20261025T191057Z-f4ef383ad071')
PLAN_SHA='4ca27746c1296d359c550eb0351105d98cfc6f8d8d021970ba026062719e89c5'
ORIGINAL_SHA='36478b10415b113da67ea88eb485eea7881ab2053ac71e87315ffc7407df7840'
OUTER_SHA='5dccf932e8693fecbe0082dd3a78658f97aadb52b251152b9f3df2fdef7e6586'
INNER_BYTES=204488782
SSH=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','firelion@192.168.100.163']
ACER_SOURCE=Path('/home/firelion/v79-hardened-cutover.2MvEOU2m/release-hardened-pair.py')
ACER_POINTER=Path('/home/firelion/v79-hardpair-client-epl9y843/release-pointer.json')


class Refused(ValueError):pass


def need(ok,reason):
    if not ok:raise Refused(reason)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def original(path):
    need(not path.is_symlink() and sha(path)==ORIGINAL_SHA,'ORIGINAL_RUNNER_CHECKSUM_CHANGED')
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('accepted_original_runner',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def transfer_state(path):
    info=path.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1
         and not info.st_mode&0o077 and 0<=info.st_size<=INNER_BYTES,'PARTIAL_ARTIFACT_UNSAFE')
    return {'bytes':info.st_size,'sha256':sha(path)}


def complete_transfer(path,source,*,expected_size,expected_sha256,offset,prefix_sha256):
    """Append only after verifying a private regular file's exact existing prefix."""
    need(isinstance(expected_size,int) and expected_size>0 and 0<=offset<=expected_size,'TRANSFER_BOUNDS_INVALID')
    fd=os.open(path,os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW)
    with os.fdopen(fd,'r+b',buffering=0) as target:
        info=os.fstat(target.fileno())
        need(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1
             and not info.st_mode&0o077 and info.st_size==offset,'PARTIAL_ARTIFACT_CHANGED')
        h=hashlib.sha256();target.seek(0)
        for block in iter(lambda:target.read(1024**2),b''):h.update(block)
        need(h.hexdigest()==prefix_sha256,'EXISTING_PREFIX_HASH_MISMATCH')
        remaining=expected_size-offset;received=0
        try:
            while remaining:
                block=source.read(min(1024**2,remaining))
                need(bool(block),'RESUME_STREAM_ENDED_EARLY')
                target.write(block);h.update(block);received+=len(block);remaining-=len(block)
            need(not source.read(1),'RESUME_STREAM_EXCEEDS_EXPECTED_INNER_SIZE')
            need(h.hexdigest()==expected_sha256,'COMPLETE_ARCHIVE_HASH_MISMATCH')
            need(os.fstat(target.fileno()).st_size==expected_size,'COMPLETE_ARCHIVE_SIZE_MISMATCH')
        finally:os.fsync(target.fileno())
    return received


def guard(args):
    need(socket.gethostname()=='v79sl' and os.geteuid()!=0 and Path.home()==Path('/home/firelion'),
         'RUN_SERVER_ON_V79SL_ONLY')
    need(Path(__file__).resolve()==ROOT/'resume-hardened-pair.py'
         and sha(Path(__file__))==args.helper_sha256,'RESUME_HELPER_CHECKSUM_CHANGED')
    m=original(ROOT/'release-hardened-pair.py');need(m.server_root()==ROOT,'SEALED_ROOT_CHANGED')
    transaction,plan,backend=m.validate_plan(ROOT,PLAN_SHA)
    m.remote_backup(plan['backup'])
    for marker in ('events.jsonl','outcome.json','progress.log','exit-code','launch-claim.json'):
        need(not (ROOT/marker).exists(),'TRANSACTION_ALREADY_MARKED_USE_EXISTING_MONITOR')
    backend.protected()
    for name,entry in plan['apps'].items():
        row=backend.inspect(name)
        need(transaction.protected_fingerprint(row)==transaction.protected_fingerprint(entry['baseline'])
             and row['State'].get('Health',{}).get('Status')=='healthy','ORIGINAL_APP_CHANGED_NO_RESUME')
    return m,plan,backend


def loaded_images(m,plan,*,require=False):
    result={}
    for name,entry in plan['apps'].items():
        p=subprocess.run(['docker','image','inspect',entry['candidate_image']['Id']],capture_output=True,timeout=30)
        if p.returncode:
            need(b'no such' in p.stderr.lower(),'CANDIDATE_IMAGE_READ_UNAVAILABLE')
            result[name]=False
        else:
            row=json.loads(p.stdout)[0]
            revision=(entry['candidate_image']['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')
            need(row['Id']==entry['candidate_image']['Id'] and
                 (row['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')==revision,
                 'LOADED_CANDIDATE_IDENTITY_CHANGED')
            result[name]=True
    if require:need(all(result.values()),'COMPLETE_CANDIDATE_PAIR_NOT_LOADED')
    return result


def load_archive(path):
    try:p=subprocess.run(['docker','image','load','--input',str(path)],capture_output=True,timeout=900)
    except subprocess.TimeoutExpired:raise Refused('DOCKER_LOAD_TIMEOUT_STATE_REQUIRES_READ') from None
    if p.returncode:
        text=(p.stderr+p.stdout).lower()
        for words,reason in [(['no space left'],'DOCKER_LOAD_DISK_FULL'),
                             (['permission denied'],'DOCKER_LOAD_PERMISSION_DENIED'),
                             (['unexpected eof','invalid tar','invalid gzip','checksum'],'DOCKER_LOAD_ARCHIVE_REJECTED'),
                             (['cannot connect','connection refused'],'DOCKER_LOAD_ENDPOINT_UNAVAILABLE')]:
            if any(word.encode() in text for word in words):raise Refused(reason)
        raise Refused('DOCKER_LOAD_FAILED_REDACTED')


def server(args):
    m,plan,backend=guard(args)
    with m.release_lock():
        artifact=ROOT/'accepted-images.tar.gz'
        state=transfer_state(artifact)
        if args.server_state:
            return {'status':'PASS_EXISTING_PLAN_AND_CORE_UNCHANGED','partial':state,
                    'candidate_images':loaded_images(m,plan),'application_services_changed':False}
        if args.server_append:
            need(args.expected_bytes==INNER_BYTES,'UNAPPROVED_INNER_ARCHIVE_SIZE')
            received=complete_transfer(artifact,sys.stdin.buffer,expected_size=INNER_BYTES,
                expected_sha256=args.archive_sha256,offset=args.offset,prefix_sha256=args.prefix_sha256)
            images=loaded_images(m,plan)
            if not all(images.values()):load_archive(artifact)
            images=loaded_images(m,plan,require=True)
            backend.protected()
            transaction=m.module('paired-compose-transaction',ROOT)
            for name,entry in plan['apps'].items():
                row=backend.inspect(name)
                need(transaction.protected_fingerprint(row)==transaction.protected_fingerprint(entry['baseline'])
                     and row['State'].get('Health',{}).get('Status')=='healthy',
                     'ORIGINAL_APP_CHANGED_DURING_LOAD')
            result={'status':'PASS_RESUMED_TRANSFER_AND_EXACT_IMAGES_LOADED','new_bytes_transferred':received,
                'complete_archive_bytes':INNER_BYTES,'complete_archive_sha256':args.archive_sha256,
                'candidate_images_verified':images,'application_services_changed':False,
                'plan_sha256':PLAN_SHA,'original_runner_sha256':ORIGINAL_SHA,'release_decision':'HOLD'}
            import secrets
            m.write_new(ROOT/('transfer-resume-receipt-'+secrets.token_hex(6)+'.json'),result)
            return result
        loaded_images(m,plan,require=True)
        need(state['bytes']==INNER_BYTES and state['sha256']==args.archive_sha256,'FINAL_ARCHIVE_NOT_VERIFIED')
        m.write_new(ROOT/'launch-claim.json',{'plan_sha256':PLAN_SHA,'resume_helper_sha256':args.helper_sha256})
        worker=['python3','-u',str(ROOT/'release-hardened-pair.py'),'--server-execute',PLAN_SHA]
        wrapper=("import os,subprocess;p=subprocess.run("+repr(worker)+
            ");f=os.open("+repr(str(ROOT/'exit-code'))+",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
            "os.write(f,str(p.returncode).encode());os.fsync(f);os.close(f)")
        fd=os.open(ROOT/'progress.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as log:
            subprocess.Popen(['python3','-u','-c',wrapper],stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        return {'status':'LAUNCHED_ORIGINAL_GUARDED_TRANSACTION_MONITOR_REQUIRED','plan_sha256':PLAN_SHA}


def rpc(command,*,data=None,source=None):
    if source is None:
        p=subprocess.run([*SSH,command],input=data,capture_output=True,timeout=180)
        raw=p.stdout;code=p.returncode
    else:
        p=subprocess.Popen([*SSH,command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            try:
                for block in iter(lambda:source.read(1024**2),b''):p.stdin.write(block)
            except BrokenPipeError:pass
            finally:
                try:p.stdin.close()
                except BrokenPipeError:pass
                p.stdin=None
            raw,_=p.communicate(timeout=1200);code=p.returncode
        finally:
            if p.poll() is None:p.kill()
            p.wait()
    try:result=json.loads(raw)
    except (ValueError,TypeError):raise Refused('REMOTE_RESPONSE_UNAVAILABLE_NO_TRANSACTION_ASSUMED') from None
    if code or result.get('status')=='BLOCKED':
        reason=result.get('reason','REMOTE_REFUSAL_REDACTED')
        import re
        need(isinstance(reason,str) and re.fullmatch('[A-Z][A-Za-z0-9_:,.]+',reason),'REMOTE_REFUSAL_REDACTED')
        raise Refused('REMOTE_'+reason)
    return result


def client(args):
    need(socket.gethostname()=='firelion-Aspire-A315-51' and os.geteuid()!=0,'RUN_ON_ACER_ONLY')
    os.umask(0o077);m=original(ACER_SOURCE)
    pointer=json.loads(m.private_file(ACER_POINTER))
    need(pointer['release_directory']==str(ROOT) and pointer['plan_sha256']==PLAN_SHA
         and pointer['source_sha256']==ORIGINAL_SHA,'EXISTING_ACER_POINTER_CHANGED')
    if args.monitor:return m.monitor(ROOT)
    m.custody(Path.home())
    archive=Path.home()/'Downloads/hardened-pair-candidate.zip'
    need(not archive.is_symlink() and archive.stat().st_size==203470115 and sha(archive)==OUTER_SHA,
         'ACCEPTED_OUTER_ARCHIVE_CHANGED')
    source=Path(__file__).read_text();helper_sha=hashlib.sha256(source.encode()).hexdigest()
    bootstrap=r'''import hashlib,json,os,socket,stat,sys
from pathlib import Path
assert socket.gethostname()=='v79sl' and os.geteuid()!=0
p=json.load(sys.stdin);r=Path(ROOT_VALUE)
s=r.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o700
assert hashlib.sha256((r/'release-hardened-pair.py').read_bytes()).hexdigest()==ORIGINAL_VALUE
assert hashlib.sha256((r/'transaction.json').read_bytes()).hexdigest()==PLAN_VALUE
raw=p['source'].encode();assert len(raw)<100000 and hashlib.sha256(raw).hexdigest()==p['sha256']
path=r/'resume-hardened-pair.py'
if path.exists() or path.is_symlink():
 s=path.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and not s.st_mode&0o077 and path.read_bytes()==raw
else:
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps({'status':'PASS_SEPARATE_RESUME_HELPER_INSTALLED_ORIGINAL_PLAN_UNCHANGED'}))
'''.replace('ROOT_VALUE',repr(str(ROOT))).replace('ORIGINAL_VALUE',repr(ORIGINAL_SHA)).replace('PLAN_VALUE',repr(PLAN_SHA))
    rpc('python3 -B -c '+shlex.quote(bootstrap),data=json.dumps({'source':source,'sha256':helper_sha}).encode())
    base=['python3','-B',str(ROOT/'resume-hardened-pair.py'),'--helper-sha256',helper_sha]
    state=rpc(shlex.join([*base,'--server-state']))
    offset=state['partial']['bytes']
    with zipfile.ZipFile(archive) as z:
        need(z.namelist().count('patched-pair.docker.tar.gz')==1,'ACCEPTED_MEMBER_SCOPE_INVALID')
        need(z.getinfo('patched-pair.docker.tar.gz').file_size==INNER_BYTES,'ACCEPTED_INNER_SIZE_CHANGED')
        full=hashlib.sha256();prefix=hashlib.sha256();position=0
        with z.open('patched-pair.docker.tar.gz') as stream:
            for block in iter(lambda:stream.read(1024**2),b''):
                full.update(block);prefix.update(block[:max(0,min(len(block),offset-position))]);position+=len(block)
        need(prefix.hexdigest()==state['partial']['sha256'],'EXISTING_REMOTE_PREFIX_DOES_NOT_MATCH_ACCEPTED_ARCHIVE')
        print('VERIFIED_EXISTING_PREFIX_BYTES='+str(offset),flush=True)
        print('REMAINING_TRANSFER_BYTES='+str(INNER_BYTES-offset),flush=True)
        command=shlex.join([*base,'--server-append','--expected-bytes',str(INNER_BYTES),
            '--archive-sha256',full.hexdigest(),'--offset',str(offset),'--prefix-sha256',prefix.hexdigest()])
        with z.open('patched-pair.docker.tar.gz') as stream:
            stream.seek(offset)
            result=rpc(command,source=stream)
        need(result.get('status')=='PASS_RESUMED_TRANSFER_AND_EXACT_IMAGES_LOADED','RESUME_LOAD_RECEIPT_INVALID')
        print(json.dumps(result,indent=2),flush=True)
    launched=rpc(shlex.join([*base,'--server-launch','--archive-sha256',full.hexdigest()]))
    need(launched.get('status')=='LAUNCHED_ORIGINAL_GUARDED_TRANSACTION_MONITOR_REQUIRED','TRANSACTION_LAUNCH_NOT_VERIFIED')
    print('ORIGINAL_SEALED_PLAN_REUSED='+PLAN_SHA,flush=True)
    return m.monitor(ROOT)


def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    for flag in ('resume','monitor','server-state','server-append','server-launch'):
        mode.add_argument('--'+flag,action='store_true')
    p.add_argument('--helper-sha256');p.add_argument('--expected-bytes',type=int)
    p.add_argument('--archive-sha256');p.add_argument('--offset',type=int);p.add_argument('--prefix-sha256')
    args=p.parse_args();sys.dont_write_bytecode=True
    if args.server_state or args.server_append or args.server_launch:print(json.dumps(server(args)),flush=True)
    else:client(args)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if isinstance(error,SystemExit):raise
        import re
        reason=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z][A-Za-z0-9_:,.]+',str(error)) else 'RESUME_BLOCKED_REDACTED'
        print(json.dumps({'status':'BLOCKED','reason':reason,'release_decision':'HOLD'}),flush=True)
        raise SystemExit(2)
