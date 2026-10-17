#!/usr/bin/env python3
"""R1 Acer isolated FOUR-IMAGE live-data app boot smoke; commercial NO-GO.

Needs companion pinned Git source: p1-r1-acer-disconnected-db-rehearsal.py,
p1-r1-acer-oci-pin-proof.py, and p1-r1-acer-app-mount-preflight.py.

Mutates only local private rootless Podman pod/containers and private RAM-backed
/dev/shm scratch, removing these on all ordinary exit paths. Network none,
no published ports, no image load/pull/tag, no live provider secrets or saved
.env content. Imports no production container credentials. Restores THREE
app data/upload TARs and TWO original database dumps, then starts four original
saved images using TEMPORARY synthetic keys for a bounded health smoke.
Never equate smoke/health with SSO, original-owner access or rollback PASS.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

PD=("podman","--remote=false")
TARGETS={
  ("v79-hub","/app/data"):"hub_data",
  ("v79-tiquet-manager","/app/data"):"tiquet_data",
  ("v79-tiquet-manager","/app/uploads"):"tiquet_uploads",
}
MAX_FILE=64*1024*1024
MAX_TOTAL=512*1024*1024
MAX_MEMBERS=20000

class Stop(Exception):
    pass
def need(b,c):
    if not b: raise Stop(c)
def line(key,value):
    print(key+"="+str(value),flush=True)
def quiet(cmd,stdin=None,timeout=90):
    r=subprocess.run(cmd,input=stdin,stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,timeout=timeout)
    if r.returncode != 0:
        # Never print raw stderr, argv, container output or environment values.
        # Classify only fixed diagnostic categories from the local CLI response.
        error=(r.stderr or b"").decode(errors="replace").lower()
        category="UNCLASSIFIED"
        for label, needles in (
            ("DUPLICATE_MOUNT", ("duplicate mount", "duplicate destination")),
            ("CLI_OPTION_UNSUPPORTED", ("unknown flag", "unknown shorthand flag")),
            ("PERMISSION_DENIED", ("permission denied", "operation not permitted")),
            ("READ_ONLY_FILESYSTEM", ("read-only file system",)),
            ("MEMORY_OR_SPACE", ("cannot allocate memory", "no space left on device")),
        ):
            if any(needle in error for needle in needles):
                category=label
                break
        if category=="DUPLICATE_MOUNT":
            # Only fixed public container paths may be disclosed, never raw text.
            path="UNCLASSIFIED"
            for candidate in ("/var/lib/postgresql/data", "/var/run/postgresql",
                              "/dev/shm", "/var/tmp", "/tmp", "/run"):
                if re.search(r"(?<![\w/])"+re.escape(candidate)+r"(?![\w/])",error):
                    path=candidate
                    break
            line("R1_DUPLICATE_MOUNT_TARGET",path)
        line("R1_LOCAL_COMMAND_ERROR_CATEGORY",category)
        line("R1_LOCAL_COMMAND_EXIT_CODE",r.returncode)
        raise Stop("LOCAL_ROOTLESS_PODMAN_COMMAND_FAILED")
    return r.stdout.decode(errors="replace").strip()
def load_module(name,path):
    need(path.is_file() and not path.is_symlink(),"REQUIRED_REVIEWED_SOURCE_MISSING")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,"SOURCE_IMPORT_UNSUPPORTED")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
def preflight(root):
    need(socket.gethostname()=="firelion-Aspire-A315-51","ACER_HOST_ONLY")
    need(os.geteuid()!=0 and os.getuid()!=0,"ROOT_REFUSED")
    need(not os.environ.get("CONTAINER_HOST") and not os.environ.get("DOCKER_HOST"),
         "REMOTE_PODMAN_CONTEXT_REFUSED")
    need(Path("/dev/shm").is_dir() and not Path("/dev/shm").is_symlink(),
         "RAM_SCRATCH_UNAVAILABLE")
    fs=quiet(["stat","-f","-c","%T","/dev/shm"])
    need(fs=="tmpfs","NO_PLAINTEXT_ON_PERSISTENT_FS")
    sw=subprocess.run(["swapon","--noheadings","--show"],
                      stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
    need(sw.returncode==0 and not sw.stdout.strip(),"ACTIVE_SWAP_REJECTED_FOR_PRIVATE_RECOVERY")
    capacity=shutil.disk_usage("/dev/shm").free
    need(capacity>=1024**3,"RAM_TMPFS_CAPACITY_UNDER_1_GIB")
    root=root.expanduser().absolute()
    need(root.is_dir() and not root.is_symlink() and
         root.stat().st_uid==os.getuid() and not root.stat().st_mode & 0o077,
         "ORIGINAL_BACKUP_DIRECTORY_UNSAFE")
    need(quiet([*PD,"info","--format","{{.Host.Security.Rootless}}"])=="true",
         "ROOTLESS_PODMAN_NOT_VERIFIED")
    module_dir=Path(__file__).resolve().parent
    mount=load_module("r1_mount_policy",
       module_dir/"p1-r1-acer-app-mount-preflight.py")
    db=load_module("r1_db_policy",
       module_dir/"p1-r1-acer-disconnected-db-rehearsal.py")
    # These reread and check encrypted originals, exactly pinned manifests
    # and OCI->local image bits. No source of truth from mutable tag names.
    original, archives, configs=mount.validate_backup(root)
    db.preflight(root)
    print("R1_APP_PREFLIGHT=PASS_ACER_ROOTLESS_RAM_ONLY",flush=True)
    resolved=db.prove_and_resolve_saved_images(root)
    need(set(resolved)==set(db.IMAGES),"FOUR_IMAGE_MAP_INVALID")
    return original,archives,configs,db,mount,resolved
def choose_archives(mounts, manifest):
    d=manifest["appMountDestinations"]
    names={}
    for role,target in TARGETS:
        alias="hub" if role=="v79-hub" else "tiquet"
        index=d[role].index(target)+1
        src=f"{alias}-mount-{index:02}.tar.gpg"
        need(mounts.get(src)==target.lstrip("/"),"TARGET_ARCHIVE_MAPPING_INVALID")
        names[src]=(target.lstrip("/"),TARGETS[(role,target)])
    need(len(names)==3,"THREE_APP_ARCHIVES_REQUIRED")
    return names
def extract_verified(root, selected, scratch):
    # Developer-controlled names, not user-supplied filesystem destinations.
    total=[0]
    for archive,(prefix,folder) in selected.items():
        dest=scratch/folder
        dest.mkdir(mode=0o700)
        src=root/archive
        gp=subprocess.Popen(["gpg","--batch","--quiet","--decrypt",str(src)],
                            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
        count=0
        try:
            with tarfile.open(fileobj=gp.stdout,mode="r|gz") as tar:
                for member in tar:
                    count+=1
                    need(count<=MAX_MEMBERS,"TAR_MEMBER_COUNT_TOO_LARGE")
                    n=member.name.removeprefix("./").rstrip("/")
                    parts=PurePosixPath(n).parts
                    need(bool(n) and not n.startswith("/") and ".." not in parts and
                         "\\" not in n and "\x00" not in n,"TAR_PATH_UNSAFE")
                    need(n==prefix or n.startswith(prefix+"/"),
                         "TAR_MEMBER_OUTSIDE_APPROVED_APP_MOUNT")
                    need(member.isfile() or member.isdir(),
                         "TAR_LINK_OR_SPECIAL_ENTRY_REFUSED")
                    suffix=n[len(prefix):].lstrip("/")
                    if not suffix:
                        need(member.isdir(),"TAR_MOUNT_ROOT_NOT_DIRECTORY")
                        continue
                    relative=PurePosixPath(suffix)
                    need(len(relative.parts)<=14,"TAR_NESTING_TOO_DEEP")
                    base=dest
                    for piece in relative.parts[:-1]:
                        base=base/piece
                        base.mkdir(mode=0o700,exist_ok=True)
                        need(base.is_dir() and not base.is_symlink(),"TAR_PARENT_SYMLINK")
                    target=base/relative.parts[-1]
                    need(not target.is_symlink(),"TAR_TARGET_SYMLINK")
                    if member.isdir():
                        target.mkdir(mode=0o700,exist_ok=True)
                        continue
                    need(0<=member.size<=MAX_FILE,"TAR_FILE_SIZE_LIMIT")
                    total[0]+=member.size
                    need(total[0]<=MAX_TOTAL,"APP_RAM_RECOVERY_SIZE_LIMIT")
                    f=tar.extractfile(member)
                    need(f is not None,"TAR_FILE_STREAM_MISSING")
                    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
                    wrote=0
                    with os.fdopen(fd,"wb") as o:
                        while True:
                            chunk=f.read(131072)
                            if not chunk:break
                            wrote+=len(chunk)
                            need(wrote<=member.size,"TAR_MEMBER_OVERSIZE")
                            o.write(chunk)
                    need(wrote==member.size,"TAR_FILE_TRUNCATED")
            gp.stdout.close()
            need(gp.wait(timeout=60)==0,"APP_ARCHIVE_GPG_FAILURE")
        finally:
            if gp.stdout and not gp.stdout.closed:gp.stdout.close()
            if gp.poll() is None:gp.kill()
            gp.wait()
        line("R1_"+folder.upper()+"_FILESYSTEM_RESTORE","PASS")
    line("R1_REAL_APP_DATA_COPIED_TO_RAM_TMPFS","PASS")
def database_tmpfs():
    # /tmp is supplied exactly once by pod_command for every container.
    return ["--tmpfs=/var/lib/postgresql/data:rw,size=1073741824,mode=0700",
            "--tmpfs=/var/run/postgresql:rw,size=16777216"]
def pod_command(container,image,pod,env,extra=None,commands=None):
    arr=[*PD,"run","--detach","--pull=never",
         "--name",container,"--pod",pod,
         "--read-only","--image-volume=ignore","--log-driver=none",
         "--tmpfs=/tmp:rw,size=67108864,mode=0700",
         "--security-opt=no-new-privileges",
         "--pids-limit=256",
         "--env","NODE_ENV=production"]
    for k,v in env.items():
        arr.extend(["--env",k+"="+v])
    arr.extend(extra or [])
    arr.append(image)
    arr.extend(commands or [])
    return arr
def inspect_no_net(container,allowed=None):
    data=json.loads(quiet([*PD,"inspect","--type=container",container]))
    need(isinstance(data,list) and len(data)==1,"PODMAN_CONTAINER_INSPECT_INVALID")
    host=data[0].get("HostConfig") or {}
    need(not host.get("PortBindings"),"UNEXPECTED_HOST_PORT_BINDING")
    need(host.get("ReadonlyRootfs") is True,
         "CONTAINER_WRITABLE_ROOT_FILESYSTEM_REFUSED")
    config=data[0].get("HostConfig") or {}
    # The run args explicitly set --log-driver=none. If inspect reports a
    # concrete logging driver other than none, fail rather than writing
    # recovered app output into Podman's persistent local storage.
    log_cfg=config.get("LogConfig") or {}
    if isinstance(log_cfg,dict) and log_cfg.get("Type") not in (None,"none"):
        raise Stop("PERSISTENT_RUNTIME_LOG_DRIVER_REFUSED")
    mounts=data[0].get("Mounts") or []
    need(isinstance(mounts,list),"PODMAN_MOUNTS_INVALID")
    for m in mounts:
        if m.get("Type")=="bind":
            need(allowed is not None and m.get("Source") in allowed and
                 m.get("Destination") in ("/app/data","/app/uploads"),
                 "UNREVIEWED_RUNTIME_BIND_MOUNT")
        else:
            need(m.get("Type")=="tmpfs","PERSISTENT_CONTAINER_VOLUME_REFUSED")
def wait_sql(container,port,db):
    for _ in range(100):
        p=subprocess.run([*PD,"exec",container,"psql",
            "-X","-U","postgres","-p",str(port),"-d",db,
            "-t","-A","-c","SELECT 1"],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12)
        if p.returncode==0 and p.stdout.strip()==b"1":return
        time.sleep(.6)
    raise Stop("DISCONNECTED_POSTGRES_SQL_NOT_READY")
def restore_sql(root,archive,container,port,database,dbmod):
    dbmod.decrypted_pipe_to_command(
      root/archive,
      [*PD,"exec","-i",container,"pg_restore",
       "--no-owner","--no-acl","--exit-on-error","--single-transaction",
       "-U","postgres","-p",str(port),"--dbname="+database],
      timeout=900)
    result=quiet([*PD,"exec",container,"psql","-X","-U","postgres",
                  "-p",str(port),"-d",database,"-t","-A","-c",
                  dbmod.TABLES_SQL],timeout=30)
    need(result.isdecimal() and int(result)>0,"RESTORED_DATABASE_USER_TABLES_MISSING")
    return int(result)
def check_service(name,url):
    # The container itself has Node.js; test localhost over pod loopback.
    # Never print application output or response bodies.
    node=(
      "const h=require('http');"
      "const q=h.get(process.argv[1],r=>{"
      "r.resume();r.on('end',()=>process.exit(r.statusCode>=200&&r.statusCode<300?0:2))"
      "});q.on('error',()=>process.exit(3));q.setTimeout(3000,()=>{q.destroy();process.exit(4)})"
    )
    for _ in range(35):
        p=subprocess.run([*PD,"exec",name,"node","-e",node,url],
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if p.returncode==0:return True
        time.sleep(.6)
    return False
def run(root,mounts,db,resolved,selected):
    scratch=Path(tempfile.mkdtemp(prefix="v79-r1-",dir="/dev/shm"))
    os.chmod(scratch,0o700)
    uid=secrets.token_hex(5)
    pod="r1-closed-"+uid
    pg_h="r1-hpg-"+uid
    pg_t="r1-tpg-"+uid
    app_h="r1-hub-"+uid
    app_t="r1-tiquet-"+uid
    try:
        line("R1_PHASE","CREATE_NETWORK_NONE_POD")
        # Reuse an exact already-local image for infra; never resolve/pull pause.
        quiet([*PD,"pod","create","--name",pod,"--network=none",
               "--infra-image",resolved["v79-hub-postgres"],
               "--infra-command","/bin/sleep infinity"],timeout=60)
        infra=quiet([*PD,"pod","inspect",pod,"--format","{{.InfraContainerID}}"])
        need(infra!="","POD_INFRA_NOT_CREATED")
        mode=quiet([*PD,"inspect","--format","{{.HostConfig.NetworkMode}}",infra])
        need(mode=="none","POD_NETWORK_EGRESS_NOT_DISABLED")
        line("R1_POD_NETWORK_NONE_VERIFIED","PASS")
        pass_h=secrets.token_hex(24)
        pass_t=secrets.token_hex(24)
        db_h="r1_hub_restore"
        db_t="r1_tiquet_restore"
        common=database_tmpfs()
        line("R1_PHASE","START_SAVED_PG17_AND_PG16")
        for name,img,db_name,pw,command in [
            (pg_h,resolved["v79-hub-postgres"],db_h,pass_h,None),
            (pg_t,resolved["tiquet-postgres"],db_t,pass_t,
             ["postgres","-c","port=5433"]),
        ]:
            cmd=pod_command(name,img,pod,{"POSTGRES_USER":"postgres",
                                          "POSTGRES_DB":db_name,
                                          "POSTGRES_PASSWORD":pw},
                            extra=common,commands=command)
            line("R1_DATABASE_START_ROLE","HUB_PG17" if name==pg_h else "TIQUET_PG16")
            quiet(cmd,timeout=120)
            inspect_no_net(name)
        wait_sql(pg_h,5432,db_h)
        wait_sql(pg_t,5433,db_t)
        line("R1_EMPTY_DATABASE_STARTUP","PASS_BOTH")
        line("R1_PHASE","RESTORE_THREE_APP_DATA_MOUNTS_TO_RAM")
        extract_verified(root,selected,scratch)
        line("R1_PHASE","RESTORE_TWO_ORIGINAL_DATABASES")
        hub_count=restore_sql(root,"hub-pg.dump.gpg",pg_h,5432,db_h,db)
        tiquet_count=restore_sql(root,"tiquet-pg.dump.gpg",pg_t,5433,db_t,db)
        line("R1_HUB_RESTORED_USER_TABLES",hub_count)
        line("R1_TIQUET_RESTORED_USER_TABLES",tiquet_count)
        line("R1_TWO_DISCONNECTED_DATABASES","PASS")
        shared=secrets.token_hex(32)
        secret_key=secrets.token_hex(32)
        admin_pw=secrets.token_hex(24)
        app_h_env={
            "NODE_ENV":"production","PORT":"3040","DATA_DIR":"/app/data",
            "V79_HUB_STORE_BACKEND":"json",
            "DATABASE_URL":f"postgresql://postgres:{pass_h}@127.0.0.1:5432/{db_h}",
            "V79_HUB_ADMIN_USERNAME":"r1-isolated",
            "V79_HUB_ADMIN_PASSWORD":admin_pw,
            "V79_REQUIRE_ADMIN_MFA":"1",
            "V79_HUB_SECURITY_KEY":secret_key,
            "V79_PLATFORM_SHARED_SECRET":shared,
            "WIPAY_ENABLED":"0","RESEND_API_KEY":"",
            "V79_WORKFORCE_ACTIONS_ENABLED":"0",
            "V79_MARKETING_PRODUCTION_ENABLED":"0",
            "V79_AGENT_INTERNAL_URL":"http://127.0.0.1:9",
            "APP_URL":"http://127.0.0.1:3040",
            "TIQUET_PUBLIC_URL":"http://127.0.0.1:3050",
        }
        app_t_env={
            "NODE_ENV":"production","PORT":"3050",
            "DB_HOST":"127.0.0.1","DB_PORT":"5433",
            "DB_NAME":db_t,"DB_USER":"postgres","DB_PASSWORD":pass_t,
            "DATABASE_PATH":"/app/data/tiquet.db",
            "APP_BASE_URL":"http://127.0.0.1:3050",
            "V79_HUB_INTERNAL_URL":"http://127.0.0.1:3040",
            "V79_HUB_BILLING_URL":"http://127.0.0.1:3040",
            "V79_HUB_PUBLIC_URL":"http://127.0.0.1:3040",
            "V79_PLATFORM_SHARED_SECRET":shared,
            "V79_HUB_MANAGED_BILLING":"1",
            "V79_ALLOW_LEGACY_AUTH":"0",
            "V79_ALLOW_EMAIL_ACCOUNT_LINK":"0",
            "V79_ENTITLEMENT_RECHECK_ENABLED":"1",
            "GOOGLE_CLIENT_ID":"",
        }
        mounts_h=["--volume",str(scratch/"hub_data")+":/app/data:rw"]
        mounts_t=["--volume",str(scratch/"tiquet_data")+":/app/data:rw",
                  "--volume",str(scratch/"tiquet_uploads")+":/app/uploads:rw"]
        line("R1_PHASE","START_SAVED_HUB_AND_TIQUET_APPS")
        quiet(pod_command(app_h,resolved["v79-hub"],pod,app_h_env,extra=mounts_h),timeout=120)
        quiet(pod_command(app_t,resolved["v79-tiquet-manager"],pod,app_t_env,extra=mounts_t),timeout=120)
        allowed={str(scratch/f) for f in ("hub_data","tiquet_data","tiquet_uploads")}
        inspect_no_net(app_h,allowed)
        inspect_no_net(app_t,allowed)
        line("R1_FOUR_PINNED_CONTAINERS_STARTED","PASS")
        line("R1_PHASE","CHECK_BOTH_APP_HEALTH_ENDPOINTS")
        h=check_service(app_h,"http://127.0.0.1:3040/api/health")
        t=check_service(app_t,"http://127.0.0.1:3050/health")
        line("R1_HUB_API_HEALTH","PASS" if h else "FAIL")
        line("R1_TIQUET_HEALTH","PASS" if t else "FAIL")
        need(h and t,"ISOLATED_APP_HEALTH_NOT_PROVEN")
        line("R1_FOUR_IMAGE_RECOVERED_DATA_HEALTH_SMOKE","PASS")
        line("R1_OWNER_MFA_POSITIVE","NOT_TESTED")
        line("R1_SSO_TENANT_ISOLATION","NOT_TESTED")
        line("R1_ROLLBACK_BOOT","NOT_TESTED")
    finally:
        line("R1_PHASE","TEARDOWN_PRIVATE_POD_AND_RAM_DATA")
        subprocess.run([*PD,"pod","rm","-f",pod],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=100)
        left=subprocess.run([*PD,"pod","exists",pod],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        # Zeroize by removing RAM-only scratch recursively; no symlink members
        # can be extracted by source validator; exact scratch path unique.
        # exists returns 1 for absence, 125 for a CLI/runtime error.
        # Retain RAM data and leave swap off if teardown is uncertain.
        need(left.returncode==1,"EPHEMERAL_POD_ABSENCE_NOT_VERIFIED")
        shutil.rmtree(scratch)
        need(not scratch.exists(),
             "EPHEMERAL_RUNTIME_CLEANUP_NOT_VERIFIED")
        line("R1_EPHEMERAL_POD_AND_RAM_SCRATCH_REMOVED","PASS")
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--backup",type=Path,required=True)
    parser.add_argument("--execute",action="store_true")
    a=parser.parse_args()
    os.umask(0o077)
    root,mounts,configs,db,mount,resolved=preflight(a.backup)
    manifest=json.loads((root/"ciphertext-manifest.json").read_text())
    selected=choose_archives(mounts,manifest)
    line("R1_SELECTED_APP_DATA_ARCHIVES",len(selected))
    if not a.execute:
        line("R1_ACTION","READ_ONLY_PREFLIGHT")
        line("R1_FOUR_IMAGE_APP_BOOT","NOT_PERFORMED")
    else:
        run(root,mounts,db,resolved,selected)
    line("R1_CUSTOMER_RELEASE","NO_GO")
if __name__=="__main__":
    try:main()
    except (Stop,RuntimeError,OSError,ValueError,KeyError,IndexError,
            tarfile.TarError,subprocess.TimeoutExpired) as exc:
        line("STOP",str(exc) if isinstance(exc,Stop)
             else "R1_ISOLATED_RECOVERY_FAILED_REDACTED")
        line("R1_CUSTOMER_RELEASE","NO_GO")
        sys.exit(1)
