"""CI-only real Docker storage lifecycle fixture; NOT cached Academy acceptance."""
import importlib.util
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time

assert socket.gethostname()!='v79sl'
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runner',ROOT/'scripts/portfolio-isolated-academy-startup.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
token=secrets.token_hex(7);tag='academy-contract-fixture:'+token
probe='v79-isolated-academy-'+token;cid=None
try:
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'dist').mkdir()
        (root/'dist/server.cjs').write_text("const fs=require('fs');fs.writeFileSync('/app/data/synthetic','fixture');require('http').createServer((q,s)=>{if(q.url==='/healthz'){s.setHeader('Content-Type','application/json');s.end(JSON.stringify({status:'ok'}))}else{s.statusCode=401;s.end()}}).listen(18081,'127.0.0.1')")
        (root/'Dockerfile').write_text('FROM node:20-alpine\nWORKDIR /app\nENV NODE_ENV=production PORT=3030\nCOPY dist /app/dist\nEXPOSE 3030\nHEALTHCHECK CMD sleep 300\nCMD ["node","dist/server.cjs"]\n')
        subprocess.run(['docker','build','-q','-t',tag,str(root)],check=True,capture_output=True,timeout=120)
    img=r.inspect('image',tag);image=img['Id'];r.PUBLIC_ENV=r.image_environment(img)
    r.EXPECTED_CONFIG={k:img['Config'].get(k) for k in ('Cmd','Entrypoint','WorkingDir')}
    created=r.command(r.create_args(image,token));assert created.returncode==0
    cid=created.stdout.decode().strip()
    before=r.inspect('container',cid);assert r.isolated(before,image,token),'Created contract failed'
    assert r.command(['docker','start',cid]).returncode==0
    running=r.inspect('container',cid)
    print('RUNNING_CONTRACT_CODE='+r.validate(running,image,token,r.PUBLIC_ENV),flush=True)
    print('FIXTURE_STATE='+running['State']['Status'],flush=True)
    print('FIXTURE_REALIZED_MOUNTS='+str(len(running.get('Mounts') or [])),flush=True)
    assert r.isolated(running,image,token),'Running contract failed'
    for _ in range(30):
        result=r.command(['docker','exec',cid,'sh','-c',r.synthetic_health()])
        if result.returncode==0:break
        time.sleep(.2)
    else:raise AssertionError('Fixture health failed')
    assert r.command(['docker','exec',cid,'node','-e',r.unsigned_denial()]).returncode==0
    assert r.cleanup(probe,token,image,cid);cid=None
    print('DOCKER_CREATED_RUNNING_HTTP_DENIAL_CLEANUP_FIXTURE=PASS')
finally:
    if cid:subprocess.run(['docker','rm','-f',cid],capture_output=True,timeout=120)
    subprocess.run(['docker','image','rm',tag],capture_output=True,timeout=30)
