"""Actual Docker cp/save format with owned synthetic images; no live data."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit',ROOT/'scripts/p1-current-offhost-archive-audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def call(cmd):return subprocess.check_output(cmd,stderr=subprocess.DEVNULL,timeout=60).decode().strip()
images=[];containers=[]
try:
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);(root/'fixture').write_text('synthetic no secret')
        for i in range(4):
            (root/'Dockerfile').write_text(f'FROM scratch\nCOPY fixture /app/data/fixture\nCOPY fixture /run/secrets/v79-agent-token\nLABEL p1.synthetic={i}\n')
            images.append(call(['docker','build','--network=none','--quiet',str(root)]))
        cid=call(['docker','create','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',images[0],'/never-start'])
        containers.append(cid)
        for dest in ('/app/data','/run/secrets/v79-agent-token'):
            raw=subprocess.check_output(['docker','cp',cid+':'+dest,'-'],stderr=subprocess.DEVNULL,timeout=30)
            a.mount_archive(io.BytesIO(raw),dest)
        child=subprocess.Popen(['docker','save',*images],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            a.images(child.stdout,set(images));child.stdout.close();assert child.wait(timeout=30)==0
        finally:
            if child.poll() is None:child.kill()
            child.wait()
    print('ACTUAL_DOCKER_CP_AND_SAVE_FORMAT=PASS')
finally:
    for cid in containers:subprocess.run(['docker','rm',cid],check=True,stdout=subprocess.DEVNULL,timeout=30)
    for image in images:subprocess.run(['docker','image','rm',image],check=True,stdout=subprocess.DEVNULL,timeout=30)
