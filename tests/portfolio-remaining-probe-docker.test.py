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
        # Regression: recreate the precise reviewed Gaming Studio J Dockerfile,
        # including its Node file capability and non-root launch, not a toy image.
        # This remains CI-only, disconnected at probe execution, and synthetic.
        game=good+'-pinned-games'
        source=root/'pinned-games'
        source.mkdir()
        call('git','init','-q',str(source))
        commit='17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'
        call('git','-C',str(source),'fetch','--depth','1','--no-tags',
             'https://github.com/MrFixITslu/Gaming-Studio-J.git',commit)
        assert call('git','-C',str(source),'rev-parse','FETCH_HEAD').decode().strip()==commit
        call('git','-C',str(source),'checkout','--detach','-q',commit)
        call('docker','build','--pull=false','-t',game,str(source))
        pinned=r.inspect(game,image=True)
        print('PINNED_GAMES_IMAGE_BUILD=PASS',flush=True)
        try:
            s.probe_image(r,run,'gaming-studio-j',pinned['Id'],old)
        except (s.Stop,r.Stop):
            print('PINNED_GAMES_NODE_ENTRY_PROBE=REPRODUCED_FAILURE',flush=True)
        else:
            raise AssertionError('Pinned Games failure was not reproduced')
        # Controlled ablation: same fully built image, remove only the Node
        # file capability; retain the non-root user and isolation flags.
        nocap=root/'no-filecap';nocap.mkdir()
        (nocap/'Dockerfile').write_text('FROM '+game+'\\nUSER root\\nRUN setcap -r "$(readlink -f "$(which node)")"\\nUSER node\\n')
        game_nocap=game+'-nocap'
        call('docker','build','--pull=false','-t',game_nocap,str(nocap))
        s.probe_image(r,run,'gaming-studio-j',r.inspect(game_nocap,image=True)['Id'],old)
        print('PINNED_GAMES_SAME_IMAGE_WITHOUT_FILECAP=PASS',flush=True)
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
    subprocess.run(['docker','image','rm',academy,bad,good,good+'-pinned-games',good+'-pinned-games-nocap'],capture_output=True)
