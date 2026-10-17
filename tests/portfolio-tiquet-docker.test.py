"""Disposable Docker integration fixture; CI only, never run against production."""
import importlib.util
from pathlib import Path
import secrets
import subprocess
import tempfile

spec=importlib.util.spec_from_file_location('diag', Path(__file__).resolve().parents[1]/'scripts/portfolio-tiquet-startup-diagnostic.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

def command(*args):
    return subprocess.run(args, check=True, capture_output=True).stdout

identity=secrets.token_hex(6)
network='v79-tqdiag-'+identity
name=network+'-metadata'
app=network+'-app'
tag=repaired=None
try:
    command('docker','pull','node:20-alpine')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); stage=root/'V79Tiquet'; stage.mkdir(); (stage/'server').mkdir()
        (stage/'server/index.js').write_text('console.log("PUBLIC_FIXTURE_OK")')
        (stage/'package.json').write_text('{}')
        (stage/'package-lock.json').write_text('{}')
        command('git','init','-q',str(stage))
        command('git','-C',str(stage),'add','.')
        command('git','-C',str(stage),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Public fixture')
        d.REVISION=command('git','-C',str(stage),'rev-parse','HEAD').decode().strip()
        d.RUN=root
        tag='v79-portfolio/v79tiquet:'+d.REVISION
        repaired=tag+'-public-modes-v1'
        (root/'Dockerfile').write_text('FROM node:20-alpine\nWORKDIR /app\nCOPY V79Tiquet/package*.json /app/\nCOPY V79Tiquet/server /app/server\nRUN chmod 700 /app/server && chmod 600 /app/server/index.js /app/package*.json\nUSER node\nCMD ["node","-e","eval(require(\'fs\').readFileSync(\'/app/server/index.js\',\'utf8\'))"]\n')
        command('docker','build','--network=none','-t',tag,str(root))
        failed=subprocess.run(['docker','run','--rm','--network=none',tag], capture_output=True)
        assert failed.returncode != 0 and b'EACCES' in failed.stderr, 'Fixture did not reproduce non-root permission failure: '+failed.stderr.decode()
        base=d.inspect(tag,image=True)['Id']
        fixed=d.repair_public_modes(base,{'paths':{'/app/package.json':{'readable':False}}})
        assert b'PUBLIC_FIXTURE_OK' in command('docker','run','--rm','--network=none',fixed)
        # Guard proves full runtime Config equality inside repair_public_modes.
        assert d.inspect(tag,image=True)['Id']==base, 'Original cached image changed'
    command('docker','network','create','--internal','--label',d.LABEL+'='+identity,network)
    for container in (name,app):
        command('docker','create','--name',container,'--label',d.LABEL+'='+identity,'--network',network,
                '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',tag)
    command('docker','start',app)
    command('docker','wait',app)
    # Exercise real Docker stopped/created container, null/absence and network semantics.
    d.reap_previous()
    assert d.inspect(name,optional=True) is None and d.inspect(app,optional=True) is None
    print('DOCKER_PUBLIC_MODE_REPAIR_AND_ORPHAN_CLEANUP=PASS')
finally:
    subprocess.run(['docker','rm','-fv',name,app],capture_output=True)
    subprocess.run(['docker','network','rm',network],capture_output=True)
    if tag:
        subprocess.run(['docker','image','rm',repaired,tag],capture_output=True)
