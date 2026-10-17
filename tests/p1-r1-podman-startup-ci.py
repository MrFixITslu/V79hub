"""Real rootless Podman startup with PUBLIC synthetic PG17/16 images only."""
import importlib.util
from pathlib import Path
import secrets
import subprocess
import os
import tempfile

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
ref='docker.io/library/node:22-alpine'
subprocess.run([*m.PD,'pull',ref],check=True,stdout=subprocess.DEVNULL)
infra=m.quiet([*m.PD,'image','inspect',ref,'--format','{{.Id}}'])
pod='r1-ci-'+secrets.token_hex(5)
scratch=None
observer=None
try:
    m.create_closed_pod(pod,infra)
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
    # Verify rootless :U on private synthetic RAM copies as a non-root Node user.
    scratch=Path(tempfile.mkdtemp(prefix="r1-ci-",dir="/dev/shm"))
    data=scratch/"data"; data.mkdir(mode=0o700)
    (data/"private").write_text("SYNTHETIC_ONLY")
    os.chmod(data/"private",0o600)
    app=pod+"-node"
    code=("const fs=require('fs'),http=require('http');"
          "fs.readFileSync('/app/data/private');"
          "fs.writeFileSync('/app/data/new','synthetic');"
          "fs.writeFileSync('/app/logs/test','synthetic');"
          "http.createServer((q,r)=>{r.end('ok')}).listen(3060)")
    observer=m.start_app(m.pod_command(app,infra,pod,{},
        extra=["--user=1000:1000","--volume",str(data)+":/app/data:rw,U",
               "--tmpfs=/app/logs:rw,size=16777216,mode=0700,uid=1000,gid=1000"],
        commands=["node","-e",code]))
    m.inspect_no_net(app,{str(data)})
    assert m.check_service(app,"http://127.0.0.1:3060/health")
    print("SYNTHETIC_NONROOT_PRIVATE_MOUNTS_AND_HEALTH=PASS",flush=True)
finally:
    subprocess.run([*m.PD,'pod','rm','-f',pod],check=True,stdout=subprocess.DEVNULL)
    result=subprocess.run([*m.PD,'pod','exists',pod])
    assert result.returncode==1
    if observer:
        observer[0].wait(timeout=15)
        observer[1].join(timeout=2)
        observer[0].stdout.close()
    if scratch:
        m.quiet([*m.PD,"unshare","rm","-rf","--",str(scratch)])
        assert not scratch.exists()
    print('SYNTHETIC_PODMAN_CLEANUP=PASS',flush=True)
