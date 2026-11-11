#!/usr/bin/env python3
"""Continue the verified pair with exact frozen metadata, preserving failed evidence.

No ignored environment differences are added. Explicit frozen metadata is removed
from the ignored-difference list, so the unchanged runtime guard compares it in
full. Original plan, binding, failed outcome, modules and image bytes stay intact.
"""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import subprocess
import sys

ORIGINAL_ROOT=Path('/home/firelion/.v79-hardened-pair-releases/pair-20261025T191057Z-f4ef383ad071')
BINDER_SHA='421568a5f9861e2999a55a0981f16c8fd17eaa2b54d719a8995eee5b79421c10'
BINDING_SHA='6b71ad5190d264ebf6c4d43f4151794d85f4db3ac3b24c2add1f244d803b9f68'
PLAN_SHA='4ca27746c1296d359c550eb0351105d98cfc6f8d8d021970ba026062719e89c5'
ORIGINAL_SHA='36478b10415b113da67ea88eb485eea7881ab2053ac71e87315ffc7407df7840'
FILENAME='continue-frozen-metadata-pair.py'
ACER_SOURCE=Path('/home/firelion/v79-hardened-cutover.2MvEOU2m/release-hardened-pair.py')
SSH=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','firelion@192.168.100.163']


class Refused(ValueError):pass


def need(condition,reason):
    if not condition:raise Refused(reason)


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def frozen_projection(old,root):
    """Narrow the ignorable metadata set; change model paths, never model content."""
    plan=copy.deepcopy(old)
    for name,entry in plan['apps'].items():
        configured=entry['model']['services'][entry['service']].get('environment') or {}
        def env(items):return dict(item.split('=',1) for item in items or [] if '=' in item)
        baseline=env(entry['baseline']['Config'].get('Env'))
        candidate=env(entry['candidate_image']['Config'].get('Env'))
        retained=[]
        for key in entry.get('removed_metadata',[]):
            need(key in ('NODE_VERSION','YARN_VERSION'),'UNREVIEWED_METADATA_NAME')
            need(key not in candidate,'METADATA_NOT_REMOVED_FROM_IMAGE')
            if key in configured:
                need(key in baseline and configured[key]==baseline[key],'FROZEN_METADATA_BASELINE_MISMATCH')
            else:retained.append(key)
        entry['removed_metadata']=retained
        for which in ('candidate','rollback'):
            entry[which+'_file']=str(Path(root)/(name+'-'+which+'.json'))
    inverse=copy.deepcopy(plan)
    for name,entry in inverse['apps'].items():
        previous=old['apps'][name]
        if 'removed_metadata' in previous:entry['removed_metadata']=previous['removed_metadata']
        else:entry.pop('removed_metadata',None)
        for which in ('candidate','rollback'):entry[which+'_file']=previous[which+'_file']
    need(inverse==old,'NONMETADATA_PLAN_DELTA_REFUSED')
    return plan


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def prior_attempt():
    need(socket.gethostname()=='v79sl' and os.geteuid()!=0 and Path.home()==Path('/home/firelion'),
         'RUN_SERVER_ON_NONROOT_V79SL_ONLY')
    binder_path=ORIGINAL_ROOT/'continue-manifest-bound-pair.py'
    need(not binder_path.is_symlink() and sha(binder_path)==BINDER_SHA,'ORIGINAL_BINDER_CHECKSUM_CHANGED')
    binder=load_module(binder_path,'verified_manifest_binder')
    args=argparse.Namespace(helper_sha256=BINDER_SHA,binding_sha256=BINDING_SHA,server_rollback=False)
    m,_,_,_=binder.guard(args)
    need(not (ORIGINAL_ROOT/'events.jsonl').exists(),'PRIOR_TRANSACTION_STARTED_NO_CONTINUATION')
    need(json.loads(m.private_file(ORIGINAL_ROOT/'outcome.json'))=={
        'reason':'UNREVIEWED_IMAGE_ENVIRONMENT_CHANGE','release_decision':'HOLD','status':'BLOCKED'},
        'PRIOR_STOP_NOT_APPROVED_FOR_CONTINUATION')
    need(m.private_file(ORIGINAL_ROOT/'exit-code').strip()==b'0','PRIOR_WORKER_NOT_CONFIRMED_EXITED')
    return binder,m


def bound_original(binder,m,manual=False):
    args=argparse.Namespace(helper_sha256=BINDER_SHA,binding_sha256=BINDING_SHA,server_rollback=manual)
    return binder.bound_validator(m,args)


def own_source(args,root):
    need(Path(__file__).resolve()==Path(root)/FILENAME and sha(Path(__file__))==args.helper_sha256,
         'CONTINUATION_HELPER_CHECKSUM_CHANGED')


def prepare(args):
    binder,m=prior_attempt();own_source(args,ORIGINAL_ROOT)
    with m.release_lock():
        transaction,old,backend=bound_original(binder,m)
        binder.fresh_originals(m,transaction,old,backend)
        name='pair-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(6)
        root=ORIGINAL_ROOT.parent/name;root.mkdir(mode=0o700)
        plan=frozen_projection(old,root)
        for filename,source in m.SOURCES.items():m.write_new(root/filename,source.encode())
        m.write_new(root/FILENAME,Path(__file__).read_bytes())
        for name,entry in plan['apps'].items():
            for which in ('candidate','rollback'):
                data=m.private_file(Path(old['apps'][name][which+'_file']))
                need(hashlib.sha256(data).hexdigest()==entry[which+'_sha256'],'MODEL_COPY_HASH_CHANGED')
                m.write_new(Path(entry[which+'_file']),data)
                rendered=json.loads(m.call(['docker','compose','--env-file','/dev/null','--project-name',entry['project'],
                    '--project-directory',entry['directory'],'-f',entry[which+'_file'],'config','--format','json']))
                need(rendered==json.loads(data),'COPIED_MODEL_ROUNDTRIP_CHANGED')
        pin=transaction.seal_plan(root,plan)
        proof={'schema':'v79-frozen-metadata-continuation-v1','prior_release':str(ORIGINAL_ROOT),
            'original_plan_sha256':PLAN_SHA,'manifest_binding_sha256':BINDING_SHA,
            'helper_sha256':args.helper_sha256,'plan_sha256':pin,
            'prior_outcome_sha256':sha(ORIGINAL_ROOT/'outcome.json')}
        m.write_new(root/'continuation-proof.json',proof)
        transaction.ComposeBackend(root,plan).check_files()
        binder.fresh_originals(m,transaction,old,backend)
        return {'status':'PASS_FROZEN_METADATA_EXACT_COMPARISON_PREPARED',
            'attempt':str(root),'plan_sha256':pin,'helper_sha256':args.helper_sha256,
            'proof_sha256':sha(root/'continuation-proof.json'),'prior_evidence_preserved':True,
            'application_services_changed':False,'release_decision':'HOLD'}


def validate(args):
    binder,m=prior_attempt();root=m.remote_directory(args.attempt)
    need(root!=ORIGINAL_ROOT,'ORIGINAL_ATTEMPT_IMMUTABLE');own_source(args,root)
    for filename,source in m.SOURCES.items():
        need(m.private_file(root/filename)==source.encode(),'CONTINUATION_MODULE_CHANGED')
    transaction,old,old_backend=bound_original(binder,m,args.server_rollback)
    expected=frozen_projection(old,root)
    plan=transaction.load_plan(root,args.plan_sha256)
    need(plan==expected,'CONTINUATION_PLAN_PROJECTION_CHANGED')
    proof=json.loads(m.private_file(root/'continuation-proof.json'))
    need(proof=={'schema':'v79-frozen-metadata-continuation-v1','prior_release':str(ORIGINAL_ROOT),
        'original_plan_sha256':PLAN_SHA,'manifest_binding_sha256':BINDING_SHA,
        'helper_sha256':args.helper_sha256,'plan_sha256':args.plan_sha256,
        'prior_outcome_sha256':sha(ORIGINAL_ROOT/'outcome.json')},'CONTINUATION_PROOF_CHANGED')
    backend=transaction.ComposeBackend(root,plan);backend.check_files()
    return binder,m,transaction,plan,backend


def launch(args):
    binder,m,transaction,plan,backend=validate(args);root=Path(args.attempt)
    with m.release_lock():
        for marker in ('launch-claim.json','events.jsonl','outcome.json','exit-code','progress.log'):
            need(not (root/marker).exists(),'ATTEMPT_MARKED_DO_NOT_RELAUNCH')
        binder.fresh_originals(m,transaction,plan,backend)
        m.write_new(root/'launch-claim.json',{'plan_sha256':args.plan_sha256,'helper_sha256':args.helper_sha256})
        worker=['python3','-B','-u',str(root/FILENAME),'--server-execute','--attempt',str(root),
            '--plan-sha256',args.plan_sha256,'--helper-sha256',args.helper_sha256]
        wrapper=("import os,subprocess;p=subprocess.run("+repr(worker)+
            ");f=os.open("+repr(str(root/'exit-code'))+",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
            "os.write(f,str(p.returncode).encode());os.fsync(f);os.close(f)")
        fd=os.open(root/'progress.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as log:subprocess.Popen(['python3','-u','-c',wrapper],
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        return {'status':'LAUNCHED_FROZEN_METADATA_SUPERVISED_CONTINUATION','attempt':str(root)}


def run_server(args):
    binder,m,_,_,_=validate(args);root=Path(args.attempt)
    with m.release_lock():
        try:
            def validator(directory,pin):
                need(Path(directory)==root and pin==args.plan_sha256,'EXECUTION_SCOPE_CHANGED')
                _,_,transaction,plan,backend=validate(args)
                return transaction,plan,backend
            result=binder.executor(m,validator)(root,args.plan_sha256,manual=args.server_rollback)
            result['prior_release_preserved']=str(ORIGINAL_ROOT)
            result['manifest_binding_sha256']=BINDING_SHA
        except BaseException as error:
            result={'status':'BLOCKED','reason':m.safe_reason(error),'release_decision':'HOLD'}
        path=root/('manual-rollback-'+secrets.token_hex(6)+'.json' if args.server_rollback else 'outcome.json')
        m.write_new(path,result);print(json.dumps(result),flush=True)


def rpc(command,data=None):
    p=subprocess.run([*SSH,command],input=data,capture_output=True,timeout=300)
    try:result=json.loads(p.stdout)
    except ValueError:raise Refused('REMOTE_RESPONSE_UNAVAILABLE') from None
    if p.returncode or result.get('status')=='BLOCKED':
        import re
        reason=result.get('reason','REMOTE_REFUSAL_REDACTED')
        need(isinstance(reason,str) and re.fullmatch('[A-Z][A-Za-z0-9_:,.]+',reason),'REMOTE_REFUSAL_REDACTED')
        raise Refused('REMOTE_'+reason)
    return result


def client(args):
    need(socket.gethostname()=='firelion-Aspire-A315-51' and os.geteuid()!=0,'RUN_ON_ACER_ONLY')
    os.umask(0o077)
    need(not ACER_SOURCE.is_symlink() and sha(ACER_SOURCE)==ORIGINAL_SHA,'ORIGINAL_ACER_SOURCE_CHANGED')
    m=load_module(ACER_SOURCE,'original_acer')
    if args.monitor:return m.monitor(args.attempt)
    raw=Path(__file__).read_bytes();helper_sha=hashlib.sha256(raw).hexdigest()
    bootstrap=r'''import hashlib,json,os,socket,stat,sys
from pathlib import Path
assert socket.gethostname()=='v79sl' and os.geteuid()!=0
p=json.load(sys.stdin);root=Path(ROOT_VALUE)
s=root.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o700
assert hashlib.sha256((root/'transaction.json').read_bytes()).hexdigest()==PLAN_VALUE
assert hashlib.sha256((root/'release-hardened-pair.py').read_bytes()).hexdigest()==ORIGINAL_VALUE
raw=p['source'].encode();assert len(raw)<100000 and hashlib.sha256(raw).hexdigest()==p['sha256']
path=root/FILE_VALUE
if path.exists() or path.is_symlink():
 s=path.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and not s.st_mode&0o077 and path.read_bytes()==raw
else:
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps({'status':'PASS_SEPARATE_FROZEN_METADATA_HELPER_INSTALLED'}))
'''.replace('ROOT_VALUE',repr(str(ORIGINAL_ROOT))).replace('PLAN_VALUE',repr(PLAN_SHA)).replace('ORIGINAL_VALUE',repr(ORIGINAL_SHA)).replace('FILE_VALUE',repr(FILENAME))
    rpc('python3 -B -c '+shlex.quote(bootstrap),json.dumps({'source':raw.decode(),'sha256':helper_sha}).encode())
    prepared=rpc(shlex.join(['python3','-B',str(ORIGINAL_ROOT/FILENAME),'--server-prepare','--helper-sha256',helper_sha]))
    need(prepared.get('status')=='PASS_FROZEN_METADATA_EXACT_COMPARISON_PREPARED','PREPARATION_NOT_VERIFIED')
    import tempfile
    work=Path(tempfile.mkdtemp(prefix='v79-frozen-metadata-client-',dir=Path.home()))
    m.write_new(work/'release-pointer.json',prepared)
    root=m.remote_directory(prepared['attempt']);base=['python3','-B',str(root/FILENAME),
        '--attempt',str(root),'--helper-sha256',helper_sha,'--plan-sha256',prepared['plan_sha256']]
    print(json.dumps(prepared,indent=2),flush=True);print('ACER_RELEASE_POINTER='+str(work/'release-pointer.json'),flush=True)
    print('FROZEN_METADATA_ROLLBACK_COMMAND='+shlex.join(['ssh','-o','StrictHostKeyChecking=yes',
        'firelion@192.168.100.163',shlex.join([*base,'--server-rollback'])]),flush=True)
    result=rpc(shlex.join([*base,'--server-launch']))
    need(result.get('status')=='LAUNCHED_FROZEN_METADATA_SUPERVISED_CONTINUATION','LAUNCH_NOT_VERIFIED')
    return m.monitor(root)


def main():
    os.umask(0o077);sys.dont_write_bytecode=True
    p=argparse.ArgumentParser(description=__doc__);group=p.add_mutually_exclusive_group(required=True)
    for flag in ('continue','monitor','server-prepare','server-launch','server-execute','server-rollback'):
        group.add_argument('--'+flag,action='store_true')
    p.add_argument('--attempt');p.add_argument('--helper-sha256');p.add_argument('--plan-sha256')
    args=p.parse_args()
    if args.server_prepare:print(json.dumps(prepare(args)),flush=True)
    elif args.server_launch:print(json.dumps(launch(args)),flush=True)
    elif args.server_execute or args.server_rollback:run_server(args)
    else:client(args)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if isinstance(error,SystemExit):raise
        import re
        reason=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z][A-Za-z0-9_:,.]+',str(error)) else 'FROZEN_METADATA_CONTINUATION_BLOCKED_REDACTED'
        print(json.dumps({'status':'BLOCKED','reason':reason,'release_decision':'HOLD'}),flush=True)
        raise SystemExit(2)
