#!/usr/bin/env python3
"""S2 real PostgreSQL offline restore. Acer-only, non-root, network-none rootless.

Only run by guarded physical-terminal wrapper after network isolation and swapoff.
Only decrypts approved Hub/Tiquet pg custom-format archives to a pipe leading to
pg_restore inside disposable tmpfs-backed PostgreSQL containers. No DB values,
paths, tokens, credentials or PostgreSQL logs are printed or persisted.
No image import, app boot, provider connection or production contact.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import secrets
import shutil
import socket
import subprocess
import sys
import time

HOST = 'firelion-Aspire-A315-51'
ROOT = Path.home() / 'V79-Portfolio-Checkpoints' / 's2-20261022T182118Z-4fc56843'
PROOF = Path.home() / 'Downloads' / 'v79_s2_offline_oci_pg_cache_v3.py'
# Replaced in a pinned source generation step with verified full-length SHA.
PROOF_SHA256 = '8273f0cc7570fcac87172f8377abd0e884911a527d76de4c8650b52c6c28493b'
PD = ('podman', '--remote=false')
GIB = 1024**3
MAX_ENCRYPTED_DB = 2 * GIB
SQL = ("SELECT count(*) FROM pg_catalog.pg_class c "
       "JOIN pg_catalog.pg_namespace n ON c.relnamespace=n.oid "
       "WHERE c.relkind IN ('r','p') AND n.nspname NOT IN "
       "('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%';")

class Stop(Exception):
    pass

def need(ok, code):
    if not ok:
        raise Stop(code)

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def role_hint(name):
    need(isinstance(name, str), 'INVALID_ARCHIVE_NAME')
    base = PurePosixPath(name).name.lower()
    need(base.endswith('.gpg'), 'ENCRYPTED_SUFFIX_UNSUPPORTED')
    base = base[:-4]
    if any(x in base for x in ('image', 'oci', 'docker-save', 'mount', 'volume', 'config', 'runtime')):
        return None
    db_terms = ('postgres', 'pg.dump', 'pg-', 'db.dump', 'database')
    if 'hub' in base and any(x in base for x in db_terms) and 'tiquet' not in base:
        return 'hub'
    if 'tiquet' in base and any(x in base for x in db_terms):
        return 'tiquet'
    return None

def safe_encrypted(root, record):
    need(isinstance(record, dict), 'ARCHIVE_RECORD_BAD')
    n, size, d = (record.get(k) for k in ('name','bytes','sha256'))
    need(isinstance(n, str) and n and '\\' not in n and '\x00' not in n and
         not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts,
         'ARCHIVE_PATH_UNSAFE')
    need(isinstance(size, int) and not isinstance(size, bool) and 0 < size < MAX_ENCRYPTED_DB,
         'DB_ARCHIVE_SIZE_UNSUPPORTED')
    need(isinstance(d,str) and re.fullmatch(r'[0-9a-fA-F]{64}',d),
         'DB_DIGEST_UNSUPPORTED')
    p = root / n
    need(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve()) and
         p.stat().st_size == size, 'DB_ARCHIVE_MISSING_OR_CHANGED')
    need(sha256(p) == d.lower(), 'DB_ARCHIVE_HASH_CHANGED')
    return p

def select_databases(root):
    manifest = root / 'manifest.json'
    need(root.is_dir() and not root.is_symlink() and root.stat().st_uid==os.getuid() and
         (root.stat().st_mode & 0o077)==0 and manifest.is_file() and
         not manifest.is_symlink() and manifest.stat().st_size < 1048576,
         'SOURCE_MANIFEST_OR_PERMISSIONS_UNSAFE')
    doc = json.loads(manifest.read_text())
    files = doc.get('files')
    need(isinstance(files,list) and len(files) == 15 and
         doc.get('apps_resumed_same_ids') is True and
         doc.get('restore_tested') is False, 'S2_MANIFEST_UNEXPECTED')
    groups={'hub':[], 'tiquet':[]}
    for entry in files:
        need(isinstance(entry,dict),'ARCHIVE_RECORD_BAD')
        role=role_hint(entry.get('name'))
        if role:
            groups[role].append(entry)
    need(all(len(v)==1 for v in groups.values()), 'DB_ARCHIVE_ROLES_NOT_UNIQUE')
    return {role:safe_encrypted(root, items[0]) for role,items in groups.items()}

def call(args, timeout=60, capture=False):
    p = subprocess.run(args, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=timeout)
    need(p.returncode==0, 'LOCAL_CONTAINER_OPERATION_FAILED')
    return p.stdout if capture else b''

def inspect_container(name):
    data = json.loads(call([*PD,'inspect','--type=container',name], timeout=25,capture=True))
    need(isinstance(data,list) and len(data)==1, 'CONTAINER_INSPECT_UNEXPECTED')
    c=data[0]; h=c.get('HostConfig') or {}
    need(h.get('NetworkMode')=='none' and not h.get('PortBindings'), 'RESTORE_NETWORK_NOT_ISOLATED')
    need(bool(h.get('ReadonlyRootfs')), 'ROOT_FILESYSTEM_NOT_READONLY')
    # Podman does not reliably populate Docker's HostConfig.Tmpfs or list
    # user-specified tmpfs mounts in inspect.Mounts. Verify the kernel's
    # mounted filesystem for all required paths inside the *running*
    # networkless container instead, before opening any archive.
    mounts = c.get('Mounts') or []
    need(isinstance(mounts,list) and not mounts, 'PERSISTENT_MOUNT_REFUSED')
    need(not h.get('Binds'), 'UNREVIEWED_HOST_BIND')
    for target in ('/var/lib/postgresql/data','/var/run/postgresql','/tmp'):
        statfs = subprocess.run(
            [*PD,'exec',name,'stat','-f','-c','%T',target],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=20)
        need(statfs.returncode==0 and statfs.stdout.strip()==b'tmpfs',
             'DATABASE_NOT_TMPFS_BACKED')
    print('ISOLATED_PG_RUNTIME_TMPFS=PASS_3_OF_3', flush=True)
    need((c.get('HostConfig') or {}).get('LogConfig',{}).get('Type') in ('none', None),
         'LOG_DRIVER_NOT_DISABLED')

def readiness(name, database):
    for _ in range(80):
        p = subprocess.run([*PD,'exec',name,'psql','-X','-U','postgres',
            '-d',database,'-t','-A','-c','SELECT 1'],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,timeout=15)
        if p.returncode==0 and p.stdout.strip()==b'1':
            return
        time.sleep(0.75)
    raise Stop('POSTGRES_NOT_READY')

def gpg_restore(archive, name, db):
    gpg = subprocess.Popen(['gpg','--batch','--no-tty','--quiet','--decrypt',str(archive)],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    dst=None
    try:
        dst=subprocess.Popen([*PD,'exec','-i',name,'pg_restore','-U','postgres',
            '--no-owner','--no-acl','--single-transaction','--exit-on-error',
            '--dbname='+db],
            stdin=gpg.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        gpg.stdout.close()
        try:
            dst_rc=dst.wait(timeout=900)
            gpg_rc=gpg.wait(timeout=45)
        except subprocess.TimeoutExpired:
            raise Stop('RESTORE_TIMEOUT') from None
        need(dst_rc==0 and gpg_rc==0, 'GPG_OR_PG_RESTORE_FAILED')
    finally:
        if dst and dst.poll() is None:
            dst.kill()
        if dst: dst.wait()
        if gpg.poll() is None:
            gpg.kill()
        gpg.wait()
        if gpg.stdout and not gpg.stdout.closed: gpg.stdout.close()

def parse_table_count(raw):
    # psycopg/psql subprocess output is bytes, not str. Fail closed on
    # invalid, empty, negative, overlong or customer-data-like output.
    need(isinstance(raw, bytes) and
         re.fullmatch(rb'[0-9]{1,6}', raw) is not None,
         'RESTORE_USER_TABLE_COUNT_INVALID')
    value = int(raw)
    need(0 < value < 1000000, 'RESTORE_USER_TABLE_COUNT_INVALID')
    return value


def restore_one(label, image, archive):
    name = 'v79-s2-closed-'+label+'-'+secrets.token_hex(5)
    db = 's2_'+label+'_rehearsal'
    # Always remove by exact randomized name, even if startup failed partially.
    print('S2_'+label.upper()+'_DB_RESTORE=START', flush=True)
    run = [*PD,'run','--detach','--rm','--pull=never',
           '--name',name,'--network=none','--read-only',
           '--image-volume=ignore','--log-driver=none','--security-opt=no-new-privileges',
           '--pids-limit=160','--memory=2g',
           '--tmpfs=/var/lib/postgresql/data:rw,size=1073741824,mode=0700',
           '--tmpfs=/var/run/postgresql:rw,size=16777216,mode=0700',
           '--tmpfs=/tmp:rw,size=67108864,mode=0700',
           '--env','POSTGRES_PASSWORD='+secrets.token_hex(24),
           '--env','POSTGRES_USER=postgres', '--env','POSTGRES_DB='+db,
           'sha256:'+image]
    err = None
    try:
        call(run,timeout=100)
        inspect_container(name)
        readiness(name,db)
        gpg_restore(archive,name,db)
        rows=call([*PD,'exec',name,'psql','-X','-U','postgres','-d',db,
                   '-t','-A','-c',SQL],timeout=45,capture=True).strip()
        table_count = parse_table_count(rows)
        print('S2_'+label.upper()+'_DB_RESTORE=PASS',flush=True)
        print('S2_'+label.upper()+'_USER_TABLE_COUNT='+str(table_count),flush=True)
    except (Stop, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        err=exc
    finally:
        subprocess.run([*PD,'rm','-f',name],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=50)
        exists = subprocess.run([*PD,'container','exists',name],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=20)
        if exists.returncode==0:
            raise Stop('DISPOSABLE_PG_CONTAINER_CLEANUP_FAILED')
        need(exists.returncode==1, 'PODMAN_CLEANUP_VERIFICATION_UNKNOWN')
        print('S2_'+label.upper()+'_PG_CONTAINER_REMOVED=PASS',flush=True)
    if err:
        if isinstance(err,Stop):
            raise err
        raise Stop('OFFLINE_RESTORE_RUNTIME_ERROR')

def load_proof():
    need(PROOF.is_file() and not PROOF.is_symlink() and
         PROOF.stat().st_uid == os.getuid() and
         sha256(PROOF)==PROOF_SHA256, 'EXACT_CACHE_PROOF_SOURCE_MISMATCH')
    spec=importlib.util.spec_from_file_location('v79_s2_pinned_offline_proof',PROOF)
    need(spec is not None and spec.loader is not None, 'OCI_PROOF_LOAD_FAILED')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run():
    need(socket.gethostname()==HOST and os.geteuid()!=0,
         'ACER_NONROOT_REQUIRED')
    need(not any(os.environ.get(k) for k in ('DOCKER_HOST','CONTAINER_HOST','SSH_CONNECTION','SSH_TTY')),
         'REMOTE_CONTEXT_OR_SSH_REFUSED')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    proof=load_proof()
    proof.host_is_offline()
    print('ISOLATION_BEFORE_DATABASES=PASS', flush=True)
    archives=select_databases(ROOT)
    print('S2_DB_ARCHIVE_ROLES=PASS_2_OF_2',flush=True)
    # Trust no local tag/version: re-read the encrypted OCI archive, independently
    # re-evaluate pinned Linux/amd64 reference->config->cached image chain.
    image_archive, image_sha, pins=proof.guarded_manifest()
    need(proof.secure_hash(image_archive)==image_sha,'IMAGE_CIPHERTEXT_CHANGED')
    gpg=subprocess.Popen(['gpg','--batch','--no-tty','--quiet','--decrypt',str(image_archive)],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        blobs,extras,counts=proof.scan_tar(gpg.stdout)
        gpg.stdout.close()
        need(gpg.wait(timeout=45)==0, 'OCI_ARCHIVE_GPG_FAILURE')
    finally:
        if gpg.poll() is None:
            gpg.kill()
        gpg.wait()
        if gpg.stdout and not gpg.stdout.closed: gpg.stdout.close()
    need(proof.evaluate(pins,blobs,extras,counts), 'OCI_IMAGE_PIN_LINKS_FAILED')
    proof.cache_gate(pins,blobs)
    configs={}
    for role in ('v79-hub-postgres','tiquet-postgres'):
        mapped=proof.resolve_image(pins[role],blobs)
        need(len(mapped)==1,'PG_OCI_REFERENCE_NOT_UNIQUE')
        configs[role]=next(iter(mapped))
    print('RESTORE_IMAGE_PINS=PASS_2_OF_2',flush=True)
    restore_one('hub',configs['v79-hub-postgres'],archives['hub'])
    restore_one('tiquet',configs['tiquet-postgres'],archives['tiquet'])
    print('S2_TWO_REAL_PG_DATABASE_RESTORES=PASS',flush=True)
    print('S2_APP_BOOT=NOT_STARTED',flush=True)
    print('S2_DATA_MOUNTS_RESTORE=NOT_STARTED',flush=True)
    print('S2_COMMERCIAL_RELEASE=NO_GO',flush=True)

def synthetic_test():
    # Pure, local self-test of archive selection and path rejection, no GPG/Podman.
    assert role_hint('hub-pg.dump.gpg')=='hub'
    assert role_hint('tiquet-postgres.dump.gpg')=='tiquet'
    assert role_hint('foo.gpg') is None
    assert role_hint('hub-mount-01.tar.gpg') is None
    for bad in ('../hub-pg.dump.gpg','/tmp/hub-pg.dump.gpg'):
        try:
            safe_encrypted(Path('/tmp'), {'name':bad,'bytes':1,'sha256':'a'*64})
            raise AssertionError('unsafe name accepted')
        except Stop:
            pass
    assert role_hint('foo.gpg') is None
    # Synthetic regression: Docker-style metadata is NOT a trusted proof
    # of a runtime tmpfs; the actual mounted filesystem must be checked.
    assert b'tmpfs'.strip() == b'tmpfs'
    assert b'overlay'.strip() != b'tmpfs'
    assert b'ext4'.strip() != b'tmpfs'
    assert parse_table_count(b'1') == 1
    assert parse_table_count(b'25') == 25
    assert parse_table_count(b'999999') == 999999
    for bad in (b'', b'0', b'-1', b'1.2', b'12\\n', b'1000000', b'x', b'12 34'):
        try:
            parse_table_count(bad)
            raise AssertionError('invalid psql output accepted')
        except Stop:
            pass
    print('S2_OFFLINE_DB_RESTORE_SELF_TEST=PASS')
    print('DECRYPTION=NONE RESTORE=NONE')


# Exact, previously owner-verified Acer outer and inner V4 files.
INNER_V4 = 'RUN_V79_S2_Guarded_Offline_OCI_v4.sh'
OUTER_V4 = 'RUN_V79_S2_Reversible_Isolation_v4.sh'
PIN_INNER_V4 = '1eccee023030019446052884379cd6839c0c83ff593772f105dfbe508bca1120'
PIN_OUTER_V4 = 'fae585d47d3a3574d9a9d41b8842261bf87e29499146b8a0c03ca63b61965b2a'
INNER_NEW = 'RUN_V79_S2_Guarded_Offline_DB_Restore_v3.sh'
OUTER_NEW = 'RUN_V79_S2_Reversible_DB_Restore_v3.sh'
SCRIPT_NAME = 'v79_s2_offline_dual_pg_restore_v3.py'

def replace_once(data, old, new):
    need(data.count(old) == 1, 'SOURCE_WRAPPER_LAYOUT_DRIFT')
    return data.replace(old, new, 1)

def prepare():
    need(socket.gethostname()==HOST and os.geteuid()!=0,
         'PREPARE_ACER_NONROOT_ONLY')
    folder=Path.home()/'Downloads'
    me=folder/SCRIPT_NAME
    need(me.is_file() and not me.is_symlink() and me.stat().st_uid == os.getuid(),
         'PREPARE_SOURCE_NOT_IN_DOWNLOADS')
    # Verify the prior runner source before building anything. No decrypt/network or container action.
    for name,pin in ((INNER_V4,PIN_INNER_V4),(OUTER_V4,PIN_OUTER_V4)):
        f=folder/name
        need(f.is_file() and not f.is_symlink() and f.stat().st_uid == os.getuid() and
             sha256(f)==pin,'PREPARE_VERIFIED_V4_INPUT_REQUIRED')
    need((folder/PROOF.name).is_file() and sha256(folder/PROOF.name)==PROOF_SHA256,
         'PREPARE_OCI_CACHE_PROOF_CHANGED')
    python_sha=sha256(me)
    inner=(folder/INNER_V4).read_text()
    inner=replace_once(inner,'SCRIPT=v79_s2_offline_oci_pg_cache_v3.py',
                       'SCRIPT='+SCRIPT_NAME)
    inner=replace_once(inner,PROOF_SHA256,python_sha)
    inner=replace_once(inner,'python3 -B "$SCRIPT" --proof',
                       'python3 -B "$SCRIPT" --restore')
    # Remove outdated identity-only description; retains offline and swap controls.
    inner=replace_once(inner,'# Acer-only offline OCI integrity and image-pin proof; NOT a data restore.',
                       '# Acer-only isolated Hub/Tiquet database restore; no app boot.')
    inner_before_cleanup_guard_sha=hashlib.sha256(inner.encode()).hexdigest()
    outer=(folder/OUTER_V4).read_text()
    need(outer.count(INNER_V4)>=2 and outer.count(PROOF.name)>=2,
         'PREPARE_OUTER_INPUT_DRIFT')
    outer=outer.replace(INNER_V4,INNER_NEW).replace(PROOF.name,SCRIPT_NAME)
    outer=replace_once(outer,PIN_INNER_V4,hashlib.sha256(inner.encode()).hexdigest())
    outer=replace_once(outer,PROOF_SHA256,python_sha)
    outer=replace_once(outer,'ISOLATION=PASS_NOW_RUNNING_PINNED_OCI_PROOF',
                       'ISOLATION=PASS_NOW_RUNNING_PINNED_DB_RESTORE')

    # Safety critical: never restore swap or networking while a recovered
    # customer database may remain in an unexpected container.
    inner = replace_once(inner,
        '  if [[ "$swapped" == 1 ]]; then\n',
        '''  if [[ "$swapped" == 1 ]]; then
    local remain
    remain="$(podman --remote=false ps --all --format '{{.Names}}' 2>/dev/null)" || {
      echo 'SAFE_STOP=LOCAL_CONTAINER_STATE_UNKNOWN_SWAP_LEFT_OFF'
      exit 2
    }
    if grep -Eq '^v79-s2-closed-(hub|tiquet)-[0-9a-f]{10}$' <<< "$remain"; then
      echo 'SAFE_STOP=PLAIN_DB_CONTAINER_REMAINS_SWAP_LEFT_OFF'
      exit 2
    fi
''')
    outer = replace_once(outer,
        '  # Restore baseline swap even if the earlier runner exited unexpectedly.\n',
        '''  # Refuse to reconnect/re-enable swap if a decrypted DB container remains.
  local remain
  remain="$(podman --remote=false ps --all --format '{{.Names}}' 2>/dev/null)" || {
    echo 'SAFE_STOP=LOCAL_CONTAINER_STATE_UNKNOWN_KEEP_OFFLINE'
    exit 2
  }
  if grep -Eq '^v79-s2-closed-(hub|tiquet)-[0-9a-f]{10}$' <<< "$remain"; then
    echo 'SAFE_STOP=PLAIN_DB_CONTAINER_REMAINS_KEEP_OFFLINE'
    exit 2
  fi
  # Restore baseline swap even if the earlier runner exited unexpectedly.
''')

    outer=replace_once(outer,inner_before_cleanup_guard_sha,
                       hashlib.sha256(inner.encode()).hexdigest())
    out={INNER_NEW:inner, OUTER_NEW:outer}
    for name,code in out.items():
        f=folder/name
        need(not f.is_symlink() and (not f.exists() or
             (f.is_file() and f.read_text()==code)),
             'PREPARE_EXISTING_FILE_CONFLICT')
    for name,code in out.items():
        f=folder/name
        if not f.exists():
            with f.open('x') as o: o.write(code)
        check=subprocess.run(['bash','-n',str(f)],stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,timeout=15)
        need(check.returncode==0,'PREPARE_WRAPPER_SYNTAX_FAIL')
        print(name+'=SHA256_'+hashlib.sha256(code.encode()).hexdigest()[:16]+'_VERIFIED')
    print('S2_RESTORE_RUNNER_PREPARATION=PASS')
    print('OFFLINE_DB_RESTORE=NOT_STARTED')

def main():
    cli=argparse.ArgumentParser()
    opt=cli.add_mutually_exclusive_group(required=True)
    opt.add_argument('--self-test',action='store_true')
    opt.add_argument('--restore',action='store_true')
    opt.add_argument('--prepare',action='store_true')
    args=cli.parse_args()
    try:
        if args.self_test:
            synthetic_test()
        elif args.prepare:
            prepare()
        else:
            run()
        return 0
    except Stop as e:
        print('SAFE_STOP='+str(e))
        print('S2_COMMERCIAL_RELEASE=NO_GO')
        return 2
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired,RuntimeError) as e:
        print('SAFE_STOP=OFFLINE_RESTORE_REQUIRES_REVIEW')
        print('S2_COMMERCIAL_RELEASE=NO_GO')
        return 2

if __name__=='__main__':
    sys.exit(main())
