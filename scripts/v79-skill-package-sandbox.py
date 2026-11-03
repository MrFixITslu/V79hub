#!/usr/bin/env python3
"""Run an explicitly approved V79 skill ZIP entrypoint in an isolated container.

No Hub process launches this utility. Operator invocation is required.
Hub is only queried for the sealed package record; Docker never mounts the
Hub's data, tokens, working directories, network or docker socket.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

APPROVED_IMAGE = "sha256:54a14b82650cef43dd0e6ccbfd7de357185e8f85681615a624146a2e019f88da"
MAX_ZIP = 1500000
MAX_UNPACKED = 4000000
MAX_ENTRIES = 120
SHA = re.compile(r"^[0-9a-f]{64}$")
PKG_ID = re.compile(r"^pkg-[0-9a-f]{16}$")

# Executes inside Hub only to verify the HMAC sealed package metadata.
# No secrets are returned to this operator helper.
INSPECT = """
import {createPackageStore} from '/app/server/workforce-skill-packages.mjs';
const store=createPackageStore({directory:'/app/data/workforce-skill-packages',
 secret:String(process.env.V79_WORKFORCE_SKILL_REGISTRY_KEY||'')});
const p=store.read(process.argv[1]);
console.log(JSON.stringify({id:p.id,name:p.name,sha256:p.sha256,
 status:p.status,entrypoints:p.entrypoints}));
"""

def run(args, timeout=20, input_data=None):
    return subprocess.run(args, input=input_data, capture_output=True, text=True,
                          timeout=timeout, check=False)

def validate_name(name):
    if not isinstance(name,str) or not name or len(name)>220 or '\\' in name or '\x00' in name or name.startswith('/'):
        raise ValueError("Invalid archive path")
    p=PurePosixPath(name)
    if any(part in ('','.','..') for part in name.rstrip('/').split('/')) or name.startswith('../') or ':' in name:
        raise ValueError("Unsafe archive member")
    if not all(re.fullmatch(r'[A-Za-z0-9_.@-]{1,100}',part) for part in p.parts):
        raise ValueError("Archive member contains invalid characters")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package',required=True)
    parser.add_argument('--entrypoint',required=True)
    parser.add_argument('--approve-sha256',required=True,
                        help='Must exactly match the approved package digest')
    args=parser.parse_args()
    if not PKG_ID.fullmatch(args.package) or not SHA.fullmatch(args.approve_sha256):
        raise ValueError("Invalid package identity")
    validate_name(args.entrypoint)
    if not args.entrypoint.startswith('scripts/') or not args.entrypoint.endswith(('.py','.js','.sh')):
        raise ValueError("Only indexed scripts may be executed")

    identity=run(['docker','exec','v79-hub','node','--input-type=module','-e',INSPECT,args.package],20)
    if identity.returncode or len(identity.stdout)>25000:raise ValueError("Cannot verify approved Hub package")
    package=json.loads(identity.stdout)
    if package.get('id')!=args.package or package.get('status')!='approved' or package.get('sha256')!=args.approve_sha256:
        raise ValueError("Package not approved at pinned digest")
    entry=next((x for x in package.get('entrypoints',[]) if x.get('path')==args.entrypoint),None)
    if entry is None or not SHA.fullmatch(entry.get('sha256','')):raise ValueError("Entry point was not indexed")

    with tempfile.TemporaryDirectory(prefix='v79-sandbox-') as tmp:
        temp=Path(tmp);archive=temp/'input.zip';extracted=temp/'files'
        extracted.mkdir(mode=0o755)
        copy=run(['docker','cp','v79-hub:/app/data/workforce-skill-packages/'+package['sha256']+'.zip',
                  str(archive)],25)
        if copy.returncode or not archive.is_file() or archive.stat().st_size>MAX_ZIP:
            raise ValueError("Cannot retrieve quarantined archive")
        data=archive.read_bytes()
        if hashlib.sha256(data).hexdigest()!=package['sha256']:raise ValueError("ZIP digest changed")
        total=0;seen=set();script=None
        with zipfile.ZipFile(archive) as z:
            infos=z.infolist()
            if len(infos)>MAX_ENTRIES:raise ValueError("Entry count exceeded")
            for item in infos:
                name=item.filename
                validate_name(name)
                key=name.rstrip('/').casefold()
                if key in seen:raise ValueError("Duplicate ZIP member")
                seen.add(key)
                mode=(item.external_attr>>16)&0o170000
                if mode not in (0,stat.S_IFREG,stat.S_IFDIR) or item.flag_bits & 1:
                    raise ValueError("Unsafe ZIP member type")
                total+=item.file_size
                if total>MAX_UNPACKED or item.file_size>1300000:raise ValueError("ZIP expansion limit")
                if item.is_dir():continue
                dest=extracted.joinpath(*PurePosixPath(name).parts)
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as handle:
                    content=handle.read(1300001)
                if len(content)!=item.file_size:raise ValueError("ZIP size mismatch")
                if name==args.entrypoint:
                    if hashlib.sha256(content).hexdigest()!=entry['sha256']:
                        raise ValueError("Entry point digest mismatch")
                    script=dest
                # Files are writable only before entering the immutable sandbox.
                with dest.open('xb') as f:f.write(content)
                dest.chmod(0o444)
        if script is None:raise ValueError("Entry point not found")
        runner={'py':('/usr/bin/python3',['-I','-B']),
                'js':('/usr/local/bin/node',[]),
                'sh':('/bin/sh',[])}[args.entrypoint.rsplit('.',1)[-1]]
        container='v79-skill-run-'+os.urandom(6).hex()
        cmd=[
          'docker','run','--rm','--pull','never','--name',container,
          '--network','none','--read-only','--cap-drop','ALL',
          '--security-opt','no-new-privileges','--pids-limit','24',
          '--cpus','0.5','--memory','128m','--memory-swap','128m',
          '--user','65534:65534','--ulimit','nofile=64:64',
          '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=8m',
          '--mount','type=bind,source='+str(extracted)+',target=/skill,readonly',
          '--workdir','/skill','--env','PYTHONDONTWRITEBYTECODE=1',
          '--entrypoint',runner[0],APPROVED_IMAGE,*runner[1],'/skill/'+args.entrypoint
        ]
        print('SANDBOX_EXECUTION=STARTED',flush=True)
        try:
            result=run(cmd,20)
            stdout=result.stdout[:8000]
            stderr=result.stderr[:8000]
            print('SANDBOX_EXIT='+str(result.returncode))
            if stdout: print('STDOUT_BEGIN\n'+stdout+'\nSTDOUT_END')
            if stderr: print('STDERR_BEGIN\n'+stderr+'\nSTDERR_END')
            if result.returncode:raise SystemExit(result.returncode)
        except subprocess.TimeoutExpired:
            print('SANDBOX_TIMEOUT=BLOCKED')
            raise SystemExit(124)
        finally:
            # Never remove another container: name is private and random.
            run(['docker','rm','-f',container],8)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,zipfile.BadZipFile,json.JSONDecodeError,subprocess.TimeoutExpired) as e:
        print('SANDBOX_STOP='+type(e).__name__+': '+str(e)[:120])
        sys.exit(1)
