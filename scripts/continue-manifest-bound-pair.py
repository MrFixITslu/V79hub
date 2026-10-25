#!/usr/bin/env python3
"""Continue the existing exact-pair release using verified runtime manifest IDs.

No transfer/load/rebuild or old-plan rewrite. A separate immutable binding record
links accepted OCI config digests to their exact loaded manifests. The original
transaction code and every remaining guard are reused with that stricter validator.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tarfile
import types
import zipfile

ROOT=Path('/home/firelion/.v79-hardened-pair-releases/pair-20261025T191057Z-f4ef383ad071')
PLAN_SHA='4ca27746c1296d359c550eb0351105d98cfc6f8d8d021970ba026062719e89c5'
ORIGINAL_SHA='36478b10415b113da67ea88eb485eea7881ab2053ac71e87315ffc7407df7840'
OUTER_SHA='5dccf932e8693fecbe0082dd3a78658f97aadb52b251152b9f3df2fdef7e6586'
INNER_BYTES=204488782
ACER_SOURCE=Path('/home/firelion/v79-hardened-cutover.2MvEOU2m/release-hardened-pair.py')
ACER_POINTER=Path('/home/firelion/v79-hardpair-client-epl9y843/release-pointer.json')
SSH=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','firelion@192.168.100.163']
BINDINGS={
 'v79-hub':{'config':'sha256:20504c556eea55af7d0f1ef85241582715e95b08fce00386335e41035decd9de',
  'manifest':'sha256:66caa099adf1321b72a90b22f8125981e5a6d99b5920cebae0454541cccd9fa7',
  'revision':'c12e54bdb52f8996fae19688d74354d731e7de27'},
 'v79-tiquet-manager':{'config':'sha256:6bb9acb1f0c8e8866082882f1cbb3d6cc9823ead559ef10a266618b013f793e1',
  'manifest':'sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0',
  'revision':'f47bbb65d1c81918017648a0a9b0464e4c167414'}
}


class Refused(ValueError):pass


def need(ok,reason):
    if not ok:raise Refused(reason)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def original(path):
    need(not path.is_symlink() and sha(path)==ORIGINAL_SHA,'ORIGINAL_RUNNER_CHECKSUM_CHANGED')
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('sealed_original',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def verify_archive(path,expected_sha,bindings):
    need(sha(path)==expected_sha,'ACCEPTED_ARCHIVE_HASH_CHANGED')
    wanted={b[k] for b in bindings.values() for k in ('config','manifest')};raws={}
    with tarfile.open(path,'r|gz') as archive:
        for member in archive:
            digest='sha256:'+member.name.removeprefix('blobs/sha256/')
            if not member.name.startswith('blobs/sha256/') or digest not in wanted:continue
            need(member.isfile() and member.size<=1024**2 and digest not in raws,'ARCHIVE_IDENTITY_MEMBER_INVALID')
            raw=archive.extractfile(member).read()
            need('sha256:'+hashlib.sha256(raw).hexdigest()==digest,'ARCHIVE_IDENTITY_BLOB_HASH_MISMATCH')
            raws[digest]=raw
    need(set(raws)==wanted,'REQUIRED_CONFIG_MANIFEST_BLOBS_MISSING')
    configs={}
    for name,binding in bindings.items():
        manifest=json.loads(raws[binding['manifest']]);config=json.loads(raws[binding['config']])
        need(manifest.get('schemaVersion')==2 and manifest.get('config',{}).get('digest')==binding['config'],
             'MANIFEST_CONFIG_BINDING_MISMATCH')
        need(manifest['config'].get('size')==len(raws[binding['config']]),'CONFIG_DESCRIPTOR_SIZE_CHANGED')
        need(config.get('os')=='linux' and config.get('architecture')=='amd64','UNAPPROVED_IMAGE_PLATFORM')
        need((config.get('config',{}).get('Labels') or {}).get('org.opencontainers.image.revision')==binding['revision'],
             'CONFIG_SOURCE_REVISION_CHANGED')
        configs[name]=config
    return configs


def verify_loaded(m,bindings,configs):
    for name,binding in bindings.items():
        row=json.loads(m.call(['docker','image','inspect',binding['manifest']]))[0]
        need(row['Id']==binding['manifest'] and row.get('Descriptor',{}).get('digest')==binding['manifest']
             and row['Descriptor'].get('mediaType')=='application/vnd.oci.image.manifest.v1+json',
             'LOADED_RUNTIME_MANIFEST_IDENTITY_CHANGED')
        config=configs[name]
        need(row.get('Os')==config['os'] and row.get('Architecture')==config['architecture'],
             'LOADED_IMAGE_PLATFORM_CHANGED')
        need(row.get('RootFS',{}).get('Layers')==config.get('rootfs',{}).get('diff_ids'),
             'LOADED_FILESYSTEM_LAYER_IDENTITIES_CHANGED')
        need((row['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')==binding['revision'],
             'LOADED_IMAGE_REVISION_CHANGED')


def model_bytes(model):return json.dumps(model,sort_keys=True).encode()


def project_plan(old,root,bindings):
    """Only runtime candidate identity, image reference and derived-file hashes differ."""
    need(set(old['apps'])==set(bindings),'BOUND_APPLICATION_SCOPE_CHANGED')
    projected=copy.deepcopy(old)
    for name,binding in bindings.items():
        old_entry=old['apps'][name];entry=projected['apps'][name]
        need(old_entry['candidate_image']['Id']==binding['config'],'ORIGINAL_CONFIG_PIN_CHANGED')
        need(entry['model']['services'][entry['service']]['image']==binding['config'],
             'ORIGINAL_MODEL_CONFIG_REFERENCE_CHANGED')
        entry['candidate_image']['Id']=binding['manifest']
        entry['model']['services'][entry['service']]['image']=binding['manifest']
        entry['candidate_file']=str(Path(root)/('manifest-'+name+'-candidate.json'))
        entry['candidate_sha256']=hashlib.sha256(model_bytes(entry['model'])).hexdigest()
    # An inverse transformation must reproduce the ENTIRE validated old plan.
    restored=copy.deepcopy(projected)
    for name,binding in bindings.items():
        entry=restored['apps'][name];before=old['apps'][name]
        entry['candidate_image']['Id']=binding['config']
        entry['model']['services'][entry['service']]['image']=binding['config']
        for key in ('candidate_file','candidate_sha256'):entry[key]=before[key]
    need(restored==old,'NONIMAGE_PLAN_DELTA_REFUSED')
    return projected


def guard(args):
    need(socket.gethostname()=='v79sl' and os.geteuid()!=0 and Path.home()==Path('/home/firelion'),
         'RUN_SERVER_ON_V79SL_ONLY')
    need(Path(__file__).resolve()==ROOT/'continue-manifest-bound-pair.py'
         and sha(Path(__file__))==args.helper_sha256,'BINDING_HELPER_CHECKSUM_CHANGED')
    m=original(ROOT/'release-hardened-pair.py');need(m.server_root()==ROOT,'SEALED_ROOT_CHANGED')
    transaction,old,backend=m.validate_plan(ROOT,PLAN_SHA)
    return m,transaction,old,backend


def fresh_originals(m,transaction,old,backend):
    m.remote_backup(old['backup']);backend.protected()
    for name,entry in old['apps'].items():
        row=backend.inspect(name)
        need(transaction.protected_fingerprint(row)==transaction.protected_fingerprint(entry['baseline'])
             and row['State'].get('Health',{}).get('Status')=='healthy','ORIGINAL_APP_CHANGED_BEFORE_BINDING')


def immutable(m,path,data):
    raw=data if isinstance(data,bytes) else model_bytes(data)
    if path.exists() or path.is_symlink():need(m.private_file(path)==raw,'EXISTING_BINDING_FILE_CHANGED')
    else:m.write_new(path,raw)


def prepare_binding(args):
    m,transaction,old,backend=guard(args)
    with m.release_lock():
        for marker in ('events.jsonl','outcome.json','progress.log','exit-code','launch-claim.json'):
            need(not (ROOT/marker).exists(),'TRANSACTION_MARKED_DO_NOT_RELAUNCH')
        fresh_originals(m,transaction,old,backend)
        artifact=ROOT/'accepted-images.tar.gz'
        need(artifact.stat().st_size==INNER_BYTES,'COMPLETE_IMAGE_ARCHIVE_REQUIRED')
        configs=verify_archive(artifact,args.archive_sha256,BINDINGS)
        for name in BINDINGS:
            need(configs[name]['config']==old['apps'][name]['candidate_image']['Config'],
                 'ACCEPTED_CANDIDATE_CONFIG_BYTES_CHANGED')
        verify_loaded(m,BINDINGS,configs)
        projected=project_plan(old,ROOT,BINDINGS)
        for entry in projected['apps'].values():
            immutable(m,Path(entry['candidate_file']),model_bytes(entry['model']))
            rendered=json.loads(m.call(['docker','compose','--env-file','/dev/null','--project-name',entry['project'],
                '--project-directory',entry['directory'],'-f',entry['candidate_file'],'config','--format','json']))
            need(rendered==entry['model'],'MANIFEST_MODEL_ROUNDTRIP_CHANGED')
        binding={'schema':'v79-verified-runtime-manifest-binding-v1','original_plan_sha256':PLAN_SHA,
            'original_runner_sha256':ORIGINAL_SHA,'helper_sha256':args.helper_sha256,
            'archive_sha256':args.archive_sha256,'archive_bytes':INNER_BYTES,'bindings':BINDINGS,
            'projected_plan_sha256':transaction.digest(projected)}
        immutable(m,ROOT/'runtime-manifest-binding.json',binding)
        pin=sha(ROOT/'runtime-manifest-binding.json')
        transaction.ComposeBackend(ROOT,projected).check_files();fresh_originals(m,transaction,old,backend)
        return {'status':'PASS_CONFIG_MANIFEST_BINDING_AND_IMAGE_ONLY_PROJECTION',
            'binding_sha256':pin,'original_plan_sha256':PLAN_SHA,'bindings':BINDINGS,
            'application_services_changed':False,'release_decision':'HOLD'}


def bound_validator(m,args):
    transaction,old,_=m.validate_plan(ROOT,PLAN_SHA)
    raw=m.private_file(ROOT/'runtime-manifest-binding.json')
    need(hashlib.sha256(raw).hexdigest()==args.binding_sha256,'BINDING_EXTERNAL_HASH_CHANGED')
    binding=json.loads(raw)
    need(binding.get('schema')=='v79-verified-runtime-manifest-binding-v1'
         and binding['original_plan_sha256']==PLAN_SHA and binding['original_runner_sha256']==ORIGINAL_SHA
         and binding['helper_sha256']==args.helper_sha256 and binding['bindings']==BINDINGS,
         'BINDING_SCOPE_CHANGED')
    configs=verify_archive(ROOT/'accepted-images.tar.gz',binding['archive_sha256'],BINDINGS)
    if not args.server_rollback:verify_loaded(m,BINDINGS,configs)
    for name in BINDINGS:
        need(configs[name]['config']==old['apps'][name]['candidate_image']['Config'],'BOUND_CONFIG_CHANGED')
    plan=project_plan(old,ROOT,BINDINGS)
    need(transaction.digest(plan)==binding['projected_plan_sha256'],'PROJECTED_PLAN_HASH_CHANGED')
    backend=transaction.ComposeBackend(ROOT,plan);backend.check_files()
    return transaction,plan,backend


def executor(m,validator):
    # Reuse the exact original execute bytecode, not a weakened copy. Only the
    # candidate-identity validator is replaced with config+manifest proof above.
    namespace=dict(m.__dict__);namespace['validate_plan']=validator
    return types.FunctionType(m.execute.__code__,namespace,m.execute.__name__,m.execute.__defaults__,m.execute.__closure__)


def server_run(args):
    m,_,_,_=guard(args)
    with m.release_lock():
        try:
            def validator(root,pin):
                need(Path(root)==ROOT and pin==PLAN_SHA,'EXECUTION_PLAN_SCOPE_CHANGED')
                return bound_validator(m,args)
            result=executor(m,validator)(ROOT,PLAN_SHA,manual=args.server_rollback)
            result['config_manifest_bindings']=BINDINGS;result['binding_sha256']=args.binding_sha256
            result['original_plan_sha256']=PLAN_SHA
        except BaseException as error:
            result={'status':'BLOCKED','reason':m.safe_reason(error),'release_decision':'HOLD'}
        if args.server_rollback:
            import secrets
            path=ROOT/('manifest-rollback-outcome-'+secrets.token_hex(6)+'.json')
        else:path=ROOT/'outcome.json'
        m.write_new(path,result);print(json.dumps(result),flush=True)


def launch(args):
    m,transaction,old,backend=guard(args)
    with m.release_lock():
        for marker in ('events.jsonl','outcome.json','progress.log','exit-code','launch-claim.json'):
            need(not (ROOT/marker).exists(),'TRANSACTION_MARKED_DO_NOT_RELAUNCH')
        fresh_originals(m,transaction,old,backend);bound_validator(m,args)
        m.write_new(ROOT/'launch-claim.json',{'original_plan_sha256':PLAN_SHA,'binding_sha256':args.binding_sha256})
        worker=['python3','-B','-u',str(ROOT/'continue-manifest-bound-pair.py'),'--server-execute',
            '--helper-sha256',args.helper_sha256,'--binding-sha256',args.binding_sha256]
        wrapper=("import os,subprocess;p=subprocess.run("+repr(worker)+
            ");f=os.open("+repr(str(ROOT/'exit-code'))+",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
            "os.write(f,str(p.returncode).encode());os.fsync(f);os.close(f)")
        fd=os.open(ROOT/'progress.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as log:subprocess.Popen(['python3','-u','-c',wrapper],
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        return {'status':'LAUNCHED_MANIFEST_BOUND_ORIGINAL_TRANSACTION','binding_sha256':args.binding_sha256}


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
    os.umask(0o077);m=original(ACER_SOURCE)
    pointer=json.loads(m.private_file(ACER_POINTER))
    need(pointer['release_directory']==str(ROOT) and pointer['plan_sha256']==PLAN_SHA
         and pointer['source_sha256']==ORIGINAL_SHA,'ACER_RELEASE_POINTER_CHANGED')
    if args.monitor:return m.monitor(ROOT)
    m.custody(Path.home());archive=Path.home()/'Downloads/hardened-pair-candidate.zip'
    need(not archive.is_symlink() and sha(archive)==OUTER_SHA,'ACCEPTED_OUTER_ARCHIVE_CHANGED')
    with zipfile.ZipFile(archive) as z:
        need(z.getinfo('patched-pair.docker.tar.gz').file_size==INNER_BYTES,'ACCEPTED_INNER_SIZE_CHANGED')
        with z.open('patched-pair.docker.tar.gz') as stream:archive_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    source=Path(__file__).read_text();helper_sha=hashlib.sha256(source.encode()).hexdigest()
    bootstrap=r'''import hashlib,json,os,socket,stat,sys
from pathlib import Path
assert socket.gethostname()=='v79sl' and os.geteuid()!=0
p=json.load(sys.stdin);r=Path(ROOT_VALUE)
s=r.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o700
assert hashlib.sha256((r/'release-hardened-pair.py').read_bytes()).hexdigest()==ORIGINAL_VALUE
assert hashlib.sha256((r/'transaction.json').read_bytes()).hexdigest()==PLAN_VALUE
raw=p['source'].encode();assert len(raw)<100000 and hashlib.sha256(raw).hexdigest()==p['sha256']
path=r/'continue-manifest-bound-pair.py'
if path.exists() or path.is_symlink():
 s=path.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and not s.st_mode&0o077 and path.read_bytes()==raw
else:
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps({'status':'PASS_SEPARATE_MANIFEST_BINDER_INSTALLED'}))
'''.replace('ROOT_VALUE',repr(str(ROOT))).replace('ORIGINAL_VALUE',repr(ORIGINAL_SHA)).replace('PLAN_VALUE',repr(PLAN_SHA))
    rpc('python3 -B -c '+shlex.quote(bootstrap),json.dumps({'source':source,'sha256':helper_sha}).encode())
    base=['python3','-B',str(ROOT/'continue-manifest-bound-pair.py'),'--helper-sha256',helper_sha]
    bound=rpc(shlex.join([*base,'--server-bind','--archive-sha256',archive_sha]))
    need(bound.get('status')=='PASS_CONFIG_MANIFEST_BINDING_AND_IMAGE_ONLY_PROJECTION','BINDING_NOT_VERIFIED')
    binding_sha=bound['binding_sha256'];immutable(m,ACER_POINTER.parent/'manifest-binding-pointer.json',bound)
    print(json.dumps(bound,indent=2),flush=True)
    rollback=shlex.join([*base,'--server-rollback','--binding-sha256',binding_sha])
    print('MANIFEST_AWARE_ROLLBACK_COMMAND='+shlex.join(['ssh','-o','StrictHostKeyChecking=yes',
        'firelion@192.168.100.163',rollback]),flush=True)
    result=rpc(shlex.join([*base,'--server-launch','--binding-sha256',binding_sha]))
    need(result.get('status')=='LAUNCHED_MANIFEST_BOUND_ORIGINAL_TRANSACTION','LAUNCH_NOT_VERIFIED')
    return m.monitor(ROOT)


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    for flag in ('continue','monitor','server-bind','server-launch','server-execute','server-rollback'):
        m.add_argument('--'+flag,action='store_true')
    p.add_argument('--helper-sha256');p.add_argument('--binding-sha256');p.add_argument('--archive-sha256')
    args=p.parse_args();sys.dont_write_bytecode=True
    if args.server_bind:print(json.dumps(prepare_binding(args)),flush=True)
    elif args.server_launch:print(json.dumps(launch(args)),flush=True)
    elif args.server_execute or args.server_rollback:server_run(args)
    else:client(args)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if isinstance(error,SystemExit):raise
        import re
        reason=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z][A-Za-z0-9_:,.]+',str(error)) else 'MANIFEST_CONTINUATION_BLOCKED_REDACTED'
        print(json.dumps({'status':'BLOCKED','reason':reason,'release_decision':'HOLD'}),flush=True)
        raise SystemExit(2)
