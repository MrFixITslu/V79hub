#!/usr/bin/env python3
"""Continue the existing exact-pair release using verified runtime manifest IDs.

No transfer/load/rebuild or old-plan rewrite. A separate immutable binding record
links accepted OCI config digests to their exact loaded manifests. The original
transaction code and every remaining guard are reused with that stricter validator.
"""
import argparse
import re
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

ROOT=Path(__file__).resolve().parent
PLAN_SHA=None  # mandatory external exact newly prepared original plan pin
ORIGINAL_SHA=None  # mandatory external original runner source digest
OUTER_SHA='5dccf932e8693fecbe0082dd3a78658f97aadb52b251152b9f3df2fdef7e6586'
INNER_BYTES=204488782
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
        need(row['Id']==binding['manifest'],'LOADED_RUNTIME_MANIFEST_IDENTITY_CHANGED')
        # The older containerd-backed API also uses the target manifest as Id,
        # but may omit Descriptor. When available (including this Dell), require
        # its exact digest/type too; no tag or config-ID fallback is permitted.
        descriptor=row.get('Descriptor')
        if descriptor is not None:
            need(descriptor.get('digest')==binding['manifest'] and
                 descriptor.get('mediaType')=='application/vnd.oci.image.manifest.v1+json',
                 'LOADED_RUNTIME_DESCRIPTOR_CHANGED')
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
    need(Path(__file__).resolve()==ROOT/'manifest-bound-executor.py'
         and sha(Path(__file__))==args.helper_sha256,'BINDING_HELPER_CHECKSUM_CHANGED')
    m=original(ROOT/'release-hardened-pair.py')
    m.CHECKPOINT=args.checkpoint_name
    need(m.server_root()==ROOT,'SEALED_ROOT_CHANGED')
    transaction,old,backend=m.validate_plan(ROOT,PLAN_SHA)
    need(old['backup']['checkpoint']==args.checkpoint_name and
         old['source_sha256']==ORIGINAL_SHA,'ORIGINAL_PLAN_CHECKPOINT_OR_SOURCE_CHANGED')
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
        worker=['python3','-B','-u',str(ROOT/'manifest-bound-executor.py'),'--server-execute',
            '--helper-sha256',args.helper_sha256,'--binding-sha256',args.binding_sha256,
            '--original-plan-sha256',args.original_plan_sha256,
            '--original-runner-sha256',args.original_runner_sha256,
            '--checkpoint-name',args.checkpoint_name]
        wrapper=("import os,subprocess;p=subprocess.run("+repr(worker)+
            ");f=os.open("+repr(str(ROOT/'exit-code'))+",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
            "os.write(f,str(p.returncode).encode());os.fsync(f);os.close(f)")
        fd=os.open(ROOT/'progress.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as log:subprocess.Popen(['python3','-u','-c',wrapper],
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        return {'status':'LAUNCHED_MANIFEST_BOUND_ORIGINAL_TRANSACTION','binding_sha256':args.binding_sha256}



def main():
    global PLAN_SHA,ORIGINAL_SHA
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    for flag in ('server-bind','server-launch','server-execute','server-rollback'):
        m.add_argument('--'+flag,action='store_true')
    p.add_argument('--helper-sha256',required=True)
    p.add_argument('--binding-sha256')
    p.add_argument('--archive-sha256')
    p.add_argument('--original-plan-sha256',required=True)
    p.add_argument('--original-runner-sha256',required=True)
    p.add_argument('--checkpoint-name',required=True)
    args=p.parse_args();sys.dont_write_bytecode=True
    need(re.fullmatch(r'[a-f0-9]{64}',args.helper_sha256 or '') is not None,
         'BOUND_HELPER_SHA256_REQUIRED')
    need(re.fullmatch(r'[a-f0-9]{64}',args.original_plan_sha256 or '') is not None,
         'BOUND_ORIGINAL_PLAN_SHA256_REQUIRED')
    need(re.fullmatch(r'[a-f0-9]{64}',args.original_runner_sha256 or '') is not None,
         'BOUND_ORIGINAL_RUNNER_SHA256_REQUIRED')
    need(re.fullmatch(r'release-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}',args.checkpoint_name or '') is not None,
         'BOUND_CHECKPOINT_NAME_REQUIRED')
    PLAN_SHA=args.original_plan_sha256
    ORIGINAL_SHA=args.original_runner_sha256
    if args.server_bind:print(json.dumps(prepare_binding(args)),flush=True)
    elif args.server_launch:print(json.dumps(launch(args)),flush=True)
    else:server_run(args)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        if isinstance(error,SystemExit):raise
        import re
        reason=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z][A-Za-z0-9_:,.]+',str(error)) else 'MANIFEST_CONTINUATION_BLOCKED_REDACTED'
        print(json.dumps({'status':'BLOCKED','reason':reason,'release_decision':'HOLD'}),flush=True)
        raise SystemExit(2)
