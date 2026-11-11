#!/usr/bin/env python3
"""Read-only reviewed Hub/Tiquet code hashes and receipt/runtime reconciliation.

No Docker mutation, database query, provider request or raw logs/environment.
Source sampling is not complete-image attestation or security acceptance.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

EXPECTED = {"v79-hub": {"server.ts": "d3e24b7291541f70c1c16b2592e9bb41611fb6fae4525c6b60d5346f35755fd0", "server/organization-access.mjs": "8f8a2eb850fca8c8c249edfc38e9427068a345d6bfee1d19c454a5a6835dde0b", "server/owner-coo-workboard.mjs": "1b67fcaf5e4a72d47670c2c8d446483fed8e354713214ea1cd71924dd6c80fec", "server/security-contract.mjs": "a64d5093c4951ea9c9cba3d796fc9369c4b4726132e6236f40a16e14f65f1f12", "server/tiquet-provisioning.mjs": "babf68d1b3a0a9ec0b4372777183edd90295bff92aebb21fd78e9134d9d55c43", "server/workforce-briefing-route.mjs": "3fd5e5640fe6fe19953eb66daedc1701916fb245a812000165f378cc046db9b4", "server/workforce-briefings.mjs": "41c318713d6f82c53ff3fb2bff3d4213926ee5e339a92e209d915163fe20cbfb", "server/workforce-python-report-reader.mjs": "de1f31c7bc8e91ef8320dc12febc5550ce21b422b9dad6129c5d801deec92402"}, "v79-tiquet-manager": {"server/hubAwareAuthentication.js": "059b44d3c1d37677802dc6217b7d3485dc5afad8ce666c1b0999883fad184a92", "server/index.js": "ecf8c323a8c50ee51d6ee9f5ecc85219d8888c2b514cc71ef7e69c440a75fcdb", "server/security.js": "145174e865d8a37064e0516ce1efaee04eb4170e4bba6da16ffe3dd06fbea5b8", "server/tiquetPortalSocketAccess.js": "7685efa991cec3ab09c399c501f253d5cdf985b4b5140c9c429565fa2b7f7d16", "server/tiquetSocketAccess.js": "f249c1c103cd3513f253c78900d3a1429b012ef5ffa940957eff784fe296260f", "server/tiquetSocketHeartbeatGuard.js": "45f4d601306ef9f219bff27c1f64433df56d8c47ceebc45d7f24d0c0a0857060", "server/tokenRevocation.js": "7aac55803e6ed57e2cdcbb3686d4e1eb5ebba479318aa18159cabcbb408d711b"}}
RECIPIENT_RUN=Path('/home/firelion/v79-portfolio-rollout.6kvFDd5e')
CORE_BLOB='6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
NAMES=('v79-hub','v79-tiquet-manager')
NODE_HASH="const fs=require('fs'),c=require('crypto');const out={};for(const p of JSON.parse(process.argv[1])){try{out[p]=c.createHash('sha256').update(fs.readFileSync('/app/'+p)).digest('hex')}catch{out[p]=null}}process.stdout.write(JSON.stringify(out))"

class Stop(Exception):pass
def need(value,code):
    if not value:raise Stop(code)
def emit(key,value):
    need(re.fullmatch(r'[A-Z0-9_]+',key) and value in ('PASS','MISMATCH','UNCHANGED','ENABLED','DISABLED','UNSET','INVALID','NO_GO','NONE'),'OUTPUT_NOT_SAFE')
    print(key+'='+value,flush=True)
def call(args,timeout=30,data=None,result=False):
    env={k:v for k,v in os.environ.items() if not k.startswith(('DOCKER_','COMPOSE_','GIT_'))}
    try:p=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout,env=env)
    except subprocess.TimeoutExpired:raise Stop('READ_ONLY_COMMAND_TIMEOUT') from None
    if result:return p
    need(p.returncode==0,'READ_ONLY_COMMAND_FAILED')
    return p.stdout
def docker(args):return call(['docker','--host','unix:///var/run/docker.sock',*args])
def inspect(name):
    rows=json.loads(docker(['container','inspect',name]));need(len(rows)==1,'INSPECT_INVALID')
    row=rows[0];need(re.fullmatch(r'[0-9a-f]{64}',row.get('Id','')),'CONTAINER_ID_INVALID')
    return row
def private(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid() and path.stat().st_mode&0o077==0,'PRIVATE_SOURCE_UNSAFE')
    return path.read_bytes()
def audit():
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'SERVER_NONROOT_REQUIRED')
    raw=private(RECIPIENT_RUN/'rollout.py')
    need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==CORE_BLOB,'CORE_SOURCE_CHANGED')
    spec=importlib.util.spec_from_file_location('trusted_p1_reader',RECIPIENT_RUN/'rollout.py')
    core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
    receipt=json.loads(private(RECIPIENT_RUN/'release-receipt.json'))
    before={name:inspect(name) for name in NAMES}
    for name,row in before.items():
        need(row.get('Image')==receipt['images'][name],'ACCEPTED_APP_IMAGE_CHANGED')
        need(row['State'].get('Running') is True and row['State'].get('Health',{}).get('Status')=='healthy','APP_HEALTH_NOT_PROVEN')
    result={}
    try:
        for name,row in before.items():
            paths=list(EXPECTED[name])
            actual=json.loads(docker(['exec',row['Id'],'node','-e',NODE_HASH,json.dumps(paths)]))
            result[name]=actual==EXPECTED[name]
            emit('HUB_REVIEWED_SOURCE' if name=='v79-hub' else 'TIQUET_REVIEWED_SOURCE','PASS' if result[name] else 'MISMATCH')
        env=before['v79-tiquet-manager']['Config'].get('Env') or []
        values=[item.split('=',1)[1] for item in env if item.startswith('V79_ENTITLEMENT_RECHECK_ENABLED=')]
        flag='UNSET' if not values else 'ENABLED' if values==['1'] else 'DISABLED' if values==['0'] else 'INVALID'
        emit('TIQUET_CONFIG_ENTITLEMENT_RECHECK',flag)
    finally:
        for name,old in before.items():
            now=inspect(name)
            need(now['Id']==old['Id'] and now['Image']==old['Image'] and core.fingerprint(now)==core.fingerprint(old)
                 and now['State'].get('Running') is True and now['State'].get('Health',{}).get('Status')=='healthy','PROTECTED_APP_CHANGED')
        emit('PROTECTED_PAIR_RUNTIME','UNCHANGED')
        emit('DEPLOYMENT','NONE');emit('R1_CUSTOMER_RELEASE','NO_GO')
    need(all(result.values()),'REVIEWED_SOURCE_MISMATCH')
def self_test():
    need(set(EXPECTED)==set(NAMES),'EXPECTED_SCOPE_INVALID')
    need(sum(map(len,EXPECTED.values()))==15,'EXPECTED_FILE_COUNT_INVALID')
    for paths in EXPECTED.values():
        for path,digest in paths.items():
            need(re.fullmatch(r'(server\.ts|server/[A-Za-z0-9_-]+\.(?:js|mjs))',path) and re.fullmatch(r'[0-9a-f]{64}',digest),'EXPECTED_SOURCE_INVALID')
    emit('SELF_TEST','PASS')
def main():
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');p.add_argument('--server',action='store_true');args=p.parse_args()
    if args.self_test:return self_test()
    if args.server:return audit()
    need(socket.gethostname()!='v79sl' and os.getuid()!=0,'ACER_NONROOT_REQUIRED')
    response=call(['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','firelion@v79sl','python3 -B - --server'],timeout=220,data=Path(__file__).read_bytes(),result=True)
    for line in response.stdout.decode().splitlines():
        need(re.fullmatch(r'[A-Z0-9_]+=(PASS|MISMATCH|UNCHANGED|ENABLED|DISABLED|UNSET|INVALID|NO_GO|NONE)',line) or re.fullmatch(r'STOP=[A-Z0-9_]+',line),'REMOTE_OUTPUT_NOT_SAFE')
        print(line,flush=True)
    need(response.returncode==0,'REMOTE_READ_ONLY_AUDIT_FAILED')
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if isinstance(error,Stop) and re.fullmatch(r'[A-Z0-9_]+',str(error)) else 'READ_ONLY_AUDIT_ERROR'
        print('STOP='+code,flush=True);print('R1_CUSTOMER_RELEASE=NO_GO',flush=True);sys.exit(1)
