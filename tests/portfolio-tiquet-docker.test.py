"""Disposable Docker integration fixture; CI only, never run against production."""
import hashlib
import importlib.util
import json
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
tag='v79-mode-fixture:'+identity
repaired=tag+'-fixed'
try:
    command('docker','pull','node:20-alpine')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/'index.js').write_text('console.log("PUBLIC_FIXTURE_OK")')
        content=(root/'index.js').read_bytes()
        blob=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
        (root/'manifest.json').write_text(json.dumps([{'path':'server/index.js','mode':420,'blob':blob}]))
        (root/'repair.js').write_text(d.MODE_REPAIR_JS)
        (root/'Dockerfile').write_text('FROM node:20-alpine\nWORKDIR /app\nCOPY index.js /app/server/index.js\nRUN chmod 700 /app/server && chmod 600 /app/server/index.js\nUSER node\nCMD ["node","server/index.js"]\n')
        command('docker','build','--network=none','-t',tag,str(root))
        failed=subprocess.run(['docker','run','--rm','--network=none',tag], capture_output=True)
        assert failed.returncode != 0 and b'EACCES' in failed.stderr, 'Fixture did not reproduce non-root permission failure'
        (root/'Dockerfile').write_text('FROM '+tag+'\nUSER root\nCOPY manifest.json /tmp/v79-public-modes.json\nCOPY repair.js /tmp/v79-public-mode-repair.js\nRUN node /tmp/v79-public-mode-repair.js\nUSER node\n')
        command('docker','build','--pull=false','--network=none','-t',repaired,str(root))
        assert b'PUBLIC_FIXTURE_OK' in command('docker','run','--rm','--network=none',repaired)
    command('docker','network','create','--internal','--label',d.LABEL+'='+identity,network)
    command('docker','create','--name',name,'--label',d.LABEL+'='+identity,'--network',network,
            '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',tag)
    # Exercise real Docker inspect/null/absence semantics, not mocks.
    d.reap_previous()
    assert d.inspect(name,optional=True) is None
    print('DOCKER_PUBLIC_MODE_REPAIR_AND_ORPHAN_CLEANUP=PASS')
finally:
    subprocess.run(['docker','rm','-fv',name],capture_output=True)
    subprocess.run(['docker','network','rm',network],capture_output=True)
    subprocess.run(['docker','image','rm',repaired,tag],capture_output=True)
