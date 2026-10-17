"""Disposable real Docker candidate probe lifecycle. CI only."""
import importlib.util
import json
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time

assert socket.gethostname()!='v79sl','CI fixture must never run on production'
ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
s=module('remaining','scripts/portfolio-remaining-rollout.py')
r=module('verified_rollout','scripts/portfolio-pinned-rollout.py')
def call(*args):return subprocess.run(args,check=True,capture_output=True).stdout
identity=secrets.token_hex(6)
good='v79-remaining-probe-fixture:'+identity
bad=good+'-bad'
academy=good+'-academy'
redis='v79-remaining-redis-fixture-'+identity
try:
    call('docker','pull','node:22-alpine')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);run=root/'v79-remaining-rollout.ABC12345';run.mkdir()
        (root/'server.js').write_text('console.log("fixture")')
        (root/'package.json').write_text('{}')
        (root/'Dockerfile').write_text('FROM node:22-alpine\nWORKDIR /app\nCOPY server.js package.json /app/\nRUN chmod 644 /app/server.js /app/package.json\nUSER node\n')
        call('docker','build','-t',good,str(root))
        old={'Config':{'User':'node','WorkingDir':'/app','Cmd':['node','server.js'],'Entrypoint':['docker-entrypoint.sh']}}
        s.probe_image(r,run,'gaming-studio-j',r.inspect(good,image=True)['Id'],old)
        (root/'Dockerfile').write_text('FROM '+good+'\nUSER root\nRUN chmod 600 /app/server.js\nUSER node\n')
        call('docker','build','--pull=false','--network=none','-t',bad,str(root))
        try:s.probe_image(r,run,'gaming-studio-j',r.inspect(bad,image=True)['Id'],old)
        except (s.Stop,r.Stop):pass
        else:raise AssertionError('Unreadable candidate was not rejected')
        call('docker','pull','node:20-alpine')
        (root/'dist').mkdir();(root/'dist/server.cjs').write_text('console.log("public fixture")')
        (root/'package.json').write_text('{"type":"module"}')
        (root/'Dockerfile').write_text('FROM node:20-alpine\nWORKDIR /app\nCOPY package.json /app/\nCOPY dist /app/dist\nHEALTHCHECK --interval=1s CMD sleep 300\nCMD ["node","dist/server.cjs"]\n')
        call('docker','build','-t',academy,str(root))
        academy_old={'Config':{'User':'','WorkingDir':'/app','Cmd':['node','dist/server.cjs'],'Entrypoint':['docker-entrypoint.sh']}}
        metadata=s.probe_metadata
        def checked_metadata(*args):
            result=metadata(*args)
            assert result['Config']['Healthcheck']['Test']==['NONE'],'Inherited healthcheck was not disabled'
            return result
        s.probe_metadata=checked_metadata
        try:s.probe_image(r,run,'v79_course_builder',r.inspect(academy,image=True)['Id'],academy_old)
        finally:s.probe_metadata=metadata
        remaining=call('docker','container','ls','--all','--quiet','--filter','label=v79.remaining-release-probe=ABC12345')
        assert not remaining.strip(),'Probe resource leaked'
    call('docker','pull','redis:7-alpine')
    call('docker','run','-d','--name',redis,'--network','none','--memory','128m','--memory-swap','128m','--tmpfs','/data:rw,nosuid,nodev,size=32m','redis:7-alpine')
    for _ in range(30):
        ready=subprocess.run(['docker','exec',redis,'redis-cli','ping'],capture_output=True)
        if ready.returncode==0 and ready.stdout.strip()==b'PONG':break
        time.sleep(0.2)
    else:raise AssertionError('Synthetic Redis did not start')
    call('docker','exec',redis,'redis-cli','SET','public-fixture','synthetic-value')
    snapshot=call('docker','exec',redis,'redis-cli','--rdb','-')
    assert snapshot.startswith(b'REDIS') and len(snapshot)>64,'RDB stdout snapshot invalid'
    print('ACTUAL_DOCKER_RELEASE_PROBE_SUCCESS_FAILURE_CLEANUP_AND_REDIS_STDOUT=PASS')
finally:
    subprocess.run(['docker','rm','-fv',redis],capture_output=True)
    subprocess.run(['docker','image','rm',academy,bad,good],capture_output=True)
