"""Real rootless Podman startup with PUBLIC synthetic PG17/16 images only."""
import importlib.util
from pathlib import Path
import secrets
import subprocess
import os

spec=importlib.util.spec_from_file_location('boot',Path(__file__).resolve().parents[1]/'scripts/p1-r1-acer-four-image-boot.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert os.getuid()!=0
assert m.quiet([*m.PD,'info','--format','{{.Host.Security.Rootless}}'])=='true'
# CI may pull PUBLIC test fixtures; production recovery never pulls.
images=[]
for version in ('17','16'):
    ref='docker.io/library/postgres:'+version+'-alpine'
    subprocess.run([*m.PD,'pull',ref],check=True,stdout=subprocess.DEVNULL)
    images.append(m.quiet([*m.PD,'image','inspect',ref,'--format','{{.Id}}']))
pod='r1-ci-'+secrets.token_hex(5)
try:
    m.quiet([*m.PD,'pod','create','--name',pod,'--network=none',
             '--infra-image',images[0],'--infra-command','/bin/sleep infinity'])
    for version,image,port in zip(('17','16'),images,(5432,5433)):
        name=pod+'-pg'+version
        args=m.pod_command(name,image,pod,{
            'POSTGRES_USER':'postgres','POSTGRES_PASSWORD':secrets.token_hex(24),
            'POSTGRES_DB':'synthetic'},extra=m.database_tmpfs(),
            commands=None if port==5432 else ['postgres','-c','port=5433'])
        m.quiet(args)
        m.inspect_no_net(name)
        m.wait_sql(name,port,'synthetic')
        print('SYNTHETIC_PODMAN_PG'+version+'_STARTUP=PASS',flush=True)
finally:
    subprocess.run([*m.PD,'pod','rm','-f',pod],check=True,stdout=subprocess.DEVNULL)
    result=subprocess.run([*m.PD,'pod','exists',pod])
    assert result.returncode==1
    print('SYNTHETIC_PODMAN_CLEANUP=PASS',flush=True)
