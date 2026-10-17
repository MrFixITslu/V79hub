#!/usr/bin/env python3
"""V79 P1 R1 Acer-only read-only inventory of encrypted app mounts/configs.

Print counts and classification ONLY, never unpack or print payloads,
filenames within TAR, secrets, environment values, sensitive metadata,
customer records or absolute host mount sources. Cannot start any container,
connect to production, rewrite backup, or authorize commercial release.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import sys
import tarfile

ROOT_IMAGE_IDS = {
    "v79-hub":"sha256:d0dfba263dbfec8a08e6c46995c2172daf234206fe8d0f6484bb98b938cd3c65",
    "v79-tiquet-manager":"sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42",
    "v79-hub-postgres":"sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "tiquet-postgres":"sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
}
ROLLBACK = "sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698"
SECRET_DESTS = {
    "/run/secrets/v79-agent-token",
    "/run/secrets/v79-workforce-token",
    "/run/secrets/v79-readonly-platform-token",
    "/run/secrets/v79-coo-github-token",
}
REPORT_DEST = "/run/v79-workforce-reports"

class Stop(Exception):
    pass

def need(cond, code):
    if not cond:
        raise Stop(code)

def safe_relative(member):
    # Tar names are untrusted and might include special filesystem files.
    if not isinstance(member.name,str):
        return False
    n = member.name.removeprefix("./")
    p = PurePosixPath(n)
    return bool(n) and not n.startswith("/") and not n.startswith("../") and ".." not in p.parts and "\x00" not in n and "\\" not in n

def expected_mounts(manifest):
    mounts = manifest.get("appMountDestinations")
    need(isinstance(mounts,dict) and
         set(mounts)=={"v79-hub","v79-tiquet-manager"},
         "BACKUP_MOUNT_MANIFEST_INVALID")
    expected={}
    for component, arr in mounts.items():
        need(isinstance(arr,list) and len(arr)<=20 and
             len(arr)==len(set(arr)) and "/app/data" in arr and
             (component!="v79-tiquet-manager" or "/app/uploads" in arr),
             "BACKUP_MOUNT_LIST_INVALID")
        alias="hub" if component=="v79-hub" else "tiquet"
        for i,target in enumerate(arr,1):
            need(isinstance(target,str) and target.startswith("/") and
                 (target.startswith("/app/") or
                  component=="v79-hub" and
                  target in (SECRET_DESTS|{REPORT_DEST})) and
                 ".." not in PurePosixPath(target).parts and
                 not target.endswith("/"),"BACKUP_MOUNT_DESTINATION_INVALID")
            expected[f"{alias}-mount-{i:02}.tar.gpg"]=target.lstrip("/")
    need(len(expected)==8 and len(mounts["v79-hub"])==6 and
         len(mounts["v79-tiquet-manager"])==2,
         "EXACT_CURRENT_APP_MOUNT_COUNT_CHANGED")
    return expected

def validate_backup(root):
    need(socket.gethostname()=="firelion-Aspire-A315-51",
         "RUN_ONLY_ON_ACER")
    need(os.getuid()!=0 and os.geteuid()!=0,"ROOT_EXECUTION_REFUSED")
    need(not os.environ.get("DOCKER_HOST") and not os.environ.get("CONTAINER_HOST"),
         "REMOTE_RUNTIME_CONTEXT_REFUSED")
    need(shutil.which("gpg") is not None,"GPG_CLIENT_MISSING")
    root=root.expanduser().absolute()
    need(root.is_dir() and not root.is_symlink() and
         root.stat().st_uid==os.getuid() and
         not root.stat().st_mode & 0o077,
         "OFFHOST_BACKUP_DIRECTORY_UNSAFE")
    need(not (root/"CAPTURE_INCOMPLETE").exists(),
         "CAPTURE_INCOMPLETE")
    f=root/"ciphertext-manifest.json"
    need(f.is_file() and not f.is_symlink() and not f.stat().st_mode & 0o077,
         "BACKUP_MANIFEST_UNSAFE")
    doc=json.loads(f.read_text())
    need(doc.get("schema")==1 and
         doc.get("status")=="CAPTURED_NOT_RESTORED" and
         doc.get("images")==ROOT_IMAGE_IDS and
         doc.get("rollbackHub")==ROLLBACK and
         doc.get("fullAppRestoreVerified") is False and
         doc.get("customerBetaAuthorized") is False,
         "BACKUP_ORIGINAL_IDENTITY_INVALID")
    mounts=expected_mounts(doc)
    cfgs={"hub-config.tar.gpg":"hub","tiquet-config.tar.gpg":"tiquet"}
    required={**{k:"tgz" for k in mounts},**{k:"tgz" for k in cfgs}}
    files=doc.get("files")
    need(isinstance(files,list) and len(files)==14,"EXPECTED_14_STREAMS")
    entries={e.get("name"):e for e in files if isinstance(e,dict)}
    need(len(entries)==14 and required.keys()<=entries.keys(),
         "BACKUP_COMPONENT_SET_INCOMPLETE")
    for filename in required:
        entry=entries[filename]
        path=root/filename
        need(entry.get("type")==required[filename] and
             path.is_file() and not path.is_symlink() and
             not path.stat().st_mode & 0o077 and
             path.stat().st_size==entry.get("bytes"),
             "BACKUP_COMPONENT_STAT_CHANGED")
        h=hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda:stream.read(1024*1024),b""):
                h.update(block)
        need(h.hexdigest()==entry.get("sha256"),
             "BACKUP_COMPONENT_CIPHERTEXT_HASH_CHANGED")
    return root,mounts,cfgs

def scan_encrypted_tar(path,expected_prefix=None):
    p=subprocess.Popen(["gpg","--batch","--quiet","--decrypt",str(path)],
                       stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL)
    stats={"files":0,"dirs":0,"links":0,"special":0,"unsafe":0,
           "out_of_prefix":0,"members":0,"logical_size":0}
    try:
        with tarfile.open(fileobj=p.stdout,mode="r|gz") as t:
            for member in t:
                stats["members"]+=1
                need(stats["members"]<=200_000,"ARCHIVE_MEMBER_LIMIT")
                stats["logical_size"]+=member.size
                need(stats["logical_size"]<=64*1024**3,
                     "ARCHIVE_LOGICAL_SIZE_LIMIT")
                path_ok=safe_relative(member)
                if not path_ok:
                    stats["unsafe"]+=1
                if path_ok and expected_prefix is not None:
                    n=member.name.removeprefix("./").rstrip("/")
                    if n!=expected_prefix and not n.startswith(expected_prefix+"/"):
                        stats["out_of_prefix"]+=1
                if member.isfile():
                    stats["files"]+=1
                elif member.isdir():
                    stats["dirs"]+=1
                elif member.issym() or member.islnk():
                    stats["links"]+=1
                else:
                    stats["special"]+=1
        p.stdout.close()
        need(p.wait(timeout=90)==0,"ARCHIVE_GPG_STREAM_FAILURE")
    finally:
        if p.stdout and not p.stdout.closed:
            p.stdout.close()
        if p.poll() is None:
            p.kill()
        p.wait()
    need(stats["members"]>0,"EMPTY_ARCHIVE_COMPONENT")
    return stats

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--backup",type=Path,required=True)
    args=parser.parse_args()
    root,mounts,cfgs=validate_backup(args.backup)
    print("R1_APP_MOUNT_PREFLIGHT=READ_ONLY",flush=True)
    print("R1_BACKUP_CIPHERTEXT_CHECKED=10_TAR_STREAMS",flush=True)
    print("R1_EXPECTED_HUB_APP_MOUNTS=6")
    print("R1_EXPECTED_TIQUET_APP_MOUNTS=2")
    print("R1_HUB_CREDENTIAL_FILE_MOUNTS=4")
    clean=True
    for archive,target in [*sorted(mounts.items()),*
                           sorted((name,None) for name in cfgs)]:
        s=scan_encrypted_tar(root/archive,target)
        label=archive.removesuffix(".tar.gpg").replace("-","_").upper()
        ok=s["unsafe"]==s["special"]==s["out_of_prefix"]==0
        clean=clean and ok
        print(f"R1_{label}|FILES={s['files']}|DIRS={s['dirs']}|"
              f"LINKS={s['links']}|SPECIAL={s['special']}|"
              f"UNSAFE={s['unsafe']}|OUTSIDE_MOUNT={s['out_of_prefix']}|"
              f"INVENTORY={'PASS' if ok else 'REVIEW'}",flush=True)
    print("R1_APP_ARCHIVE_INVENTORY_STATUS="+
          ("PASS_STRUCTURE_ONLY" if clean else "REVIEW_REQUIRED"))
    print("R1_APP_MOUNT_RESTORE=NOT_PERFORMED")
    print("R1_APPLICATION_BOOT=NOT_PERFORMED")
    print("R1_RELEASE_GATE=NO_GO")
    need(clean,"UNSAFE_OR_UNEXPECTED_APP_ARCHIVE_MEMBERS")

if __name__=="__main__":
    try:
        main()
    except (Stop,ValueError,KeyError,OSError,tarfile.TarError,
            subprocess.TimeoutExpired) as e:
        print("STOP="+str(e) if isinstance(e,Stop)
              else "STOP=APP_MOUNT_PREFLIGHT_FAILED_REDACTED")
        print("R1_RELEASE_GATE=NO_GO")
        sys.exit(1)
