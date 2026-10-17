#!/usr/bin/env python3
"""R1: one-pass, Acer-only, ROOTLESS Podman isolated PostgreSQL restore smoke.

Uses a cryptographically proven Docker29 OCI-index -> config-ID map against
already-imported images in the Acer rootless Podman cache; DOES NOT import.
Restores Hub PG17 and Tiquet PG16 dumps into disposable --network=none
PostgreSQL containers with tmpfs databases, counts restored user tables,
and ALWAYS destroys all disposable DB containers (including on failure).
Never reads or connects to the v79sl production host or starts Hub/Tiquet apps.
No decrypted files are written to disk. Does NOT authorize a release.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time

IMAGES = {
    "v79-hub": "sha256:d0dfba263dbfec8a08e6c46995c2172daf234206fe8d0f6484bb98b938cd3c65",
    "v79-tiquet-manager": "sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42",
    "v79-hub-postgres": "sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "tiquet-postgres": "sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
}
ROLLBACK = "sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698"
PODMAN = ("podman", "--remote=false")
REQUIRED = {
    "hub-pg.dump.gpg": "pg",
    "tiquet-pg.dump.gpg": "pg",
    "exact-images-and-rollback.tar.gpg": "tar",
}
TABLES_SQL = (
    "SELECT count(*) FROM pg_catalog.pg_class c "
    "JOIN pg_catalog.pg_namespace n ON c.relnamespace=n.oid "
    "WHERE c.relkind IN ('r','p') "
    "AND n.nspname NOT IN ('pg_catalog','information_schema') "
    "AND n.nspname NOT LIKE 'pg_toast%';"
)

class Stop(Exception):
    pass

def ensure(ok, reason):
    if not ok:
        raise Stop(reason)

def private_file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def validate_manifest(root):
    root = root.expanduser().absolute()
    ensure(root.is_dir() and not root.is_symlink(), "ARCHIVE_DIRECTORY_INVALID")
    ensure(root.stat().st_uid == os.getuid()
           and (root.stat().st_mode & 0o077) == 0,
           "ARCHIVE_DIRECTORY_PERMISSIONS")
    receipt = root / "ciphertext-manifest.json"
    ensure(receipt.is_file() and not receipt.is_symlink(), "ARCHIVE_MANIFEST_MISSING")
    ensure(not (root / "CAPTURE_INCOMPLETE").exists(), "INCOMPLETE_BACKUP_SET")
    data = json.loads(receipt.read_text())
    ensure(data.get("schema") == 1 and data.get("status") == "CAPTURED_NOT_RESTORED"
           and data.get("images") == IMAGES and data.get("rollbackHub") == ROLLBACK,
           "BACKUP_PROVENANCE_NOT_PINNED")
    files = data.get("files")
    ensure(isinstance(files, list) and len(files) == 14, "NOT_THE_VERIFIED_14_STREAM_SET")
    entries = {e["name"]: e for e in files if isinstance(e, dict) and isinstance(e.get("name"), str)}
    ensure(len(entries) == len(files), "DUPLICATE_BACKUP_COMPONENT")
    for name, kind in REQUIRED.items():
        e = entries.get(name)
        ensure(e is not None and e.get("type") == kind,
               "BACKUP_REQUIRED_COMPONENT_MISSING")
        p = root / name
        ensure(p.is_file() and not p.is_symlink() and (p.stat().st_mode & 0o077) == 0
               and e.get("bytes") == p.stat().st_size
               and isinstance(e.get("sha256"), str)
               and re.fullmatch(r"[0-9a-f]{64}", e["sha256"])
               and private_file_hash(p) == e["sha256"],
               "BACKUP_REQUIRED_COMPONENT_INTEGRITY_FAILURE")
    return root

def preflight(root):
    ensure(socket.gethostname() == "firelion-Aspire-A315-51",
           "RUN_ONLY_ON_ACER")
    ensure(os.getuid() != 0 and os.geteuid() != 0, "ROOT_EXECUTION_REFUSED")
    ensure(not os.environ.get("CONTAINER_HOST") and not os.environ.get("DOCKER_HOST"),
           "REMOTE_CONTAINER_CONTEXT_REFUSED")
    ensure(shutil.which("podman") and shutil.which("gpg"),
           "PODMAN_OR_GPG_MISSING")
    root = validate_manifest(root)
    info = subprocess.run([*PODMAN, "info", "--format", "{{.Host.Security.Rootless}}"],
                          capture_output=True, text=True, timeout=30)
    ensure(info.returncode == 0 and info.stdout.strip() == "true",
           "LOCAL_ROOTLESS_PODMAN_REQUIRED")
    ensure(shutil.disk_usage(Path.home()).free >= 8 * 1024**3,
           "INSUFFICIENT_ACER_DISK_SPACE")
    print("R1_ACER_ROOTLESS_ISOLATION_PREFLIGHT=PASS", flush=True)
    print("R1_VERIFIED_INPUT_COMPONENTS=3_OF_14_RECHECKED", flush=True)
    return root

def db_run_args(name, image, database):
    # No --publish, --volume or --network=host. All PostgreSQL data in tmpfs
    # disappears on podman rm -f; no decrypted copy survives in named volumes.
    return [
        *PODMAN, "run", "--rm", "--detach", "--pull=never",
        "--name", name, "--network=none",
        "--security-opt=no-new-privileges", "--pids-limit=160",
        "--tmpfs=/var/lib/postgresql/data:rw,size=1073741824,mode=0700",
        "--tmpfs=/var/run/postgresql:rw,size=16777216",
        "--tmpfs=/tmp:rw,size=67108864",
        "--env", "POSTGRES_PASSWORD=" + secrets.token_hex(24),
        "--env", "POSTGRES_USER=postgres",
        "--env", "POSTGRES_DB=" + database,
        image
    ]

def silent_run(args, timeout=60):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       timeout=timeout)
    ensure(p.returncode == 0, "ISOLATED_CONTAINER_OPERATION_FAILED")
    return p.stdout.decode(errors="replace").strip()

def decrypted_pipe_to_command(archive, consumer, timeout=1800):
    # Two explicit exit codes: no falsely successful downstream consumer if
    # GPG failed auth/decryption or an early close caused SIGPIPE.
    gpg = subprocess.Popen(["gpg", "--batch", "--quiet", "--decrypt", str(archive)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
    receiver = None
    try:
        receiver = subprocess.Popen(consumer, stdin=gpg.stdout, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        gpg.stdout.close()
        receiver_rc = receiver.wait(timeout=timeout)
        gpg_rc = gpg.wait(timeout=60)
        ensure(receiver_rc == 0 and gpg_rc == 0,
               "GPG_OR_ISOLATED_RESTORE_STREAM_FAILED")
    finally:
        if receiver is not None:
            if receiver.poll() is None:
                receiver.kill()
            receiver.wait()
        if gpg.poll() is None:
            gpg.kill()
        gpg.wait()

def local_image_exists(image):
    p = subprocess.run([*PODMAN, "image", "exists", image], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)
    return p.returncode == 0

def prove_and_resolve_saved_images(root):
    # Import no images and NEVER choose by mutable image tag/repository name.
    # Identity mapping must be independently rebuilt from the original 14-
    # stream encrypted archive, not a user-entered alternate image digest.
    source = Path(__file__).with_name("p1-r1-acer-oci-pin-proof.py")
    ensure(source.is_file() and not source.is_symlink(),
           "PINNED_OCI_PROOF_SCRIPT_MISSING")
    spec = importlib.util.spec_from_file_location("r1_saved_oci_proof", source)
    ensure(spec is not None and spec.loader is not None,
           "OCI_PROOF_SCRIPT_IMPORT_NOT_AVAILABLE")
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    archive = proof.prep(root)
    result = proof.stream_proof(archive, return_mapping=True)
    ensure(isinstance(result, dict) and
           set(result) == {x.removeprefix("sha256:") for x in [*IMAGES.values(), ROLLBACK]} and
           len(set(result.values())) == 5,
           "OCI_INDEX_TO_CONFIG_MAPPING_UNVERIFIED")
    # Read-only local rootless image inventory: exact CONFIG digest, not OCI
    # manifest/index reference. Never print the IDs or tags.
    inventory = json.loads(silent_run(
        [*PODMAN, "images", "--all", "--no-trunc", "--format", "json"], timeout=40))
    ensure(isinstance(inventory, list), "PODMAN_IMAGE_INVENTORY_INVALID")
    local = set()
    for row in inventory:
        ensure(isinstance(row, dict), "PODMAN_IMAGE_INVENTORY_ROW_INVALID")
        value = row.get("Id", row.get("ID", row.get("id", "")))
        if isinstance(value, str):
            clean = value.removeprefix("sha256:")
            if re.fullmatch(r"[0-9a-f]{64}", clean):
                local.add(clean)
    ensure(set(result.values()).issubset(local),
           "PINNED_CONFIG_IMAGES_NOT_PRESENT_LOCAL_NO_IMPORT")
    for config in result.values():
        ensure(local_image_exists("sha256:" + config),
               "PODMAN_EXACT_CONFIG_ID_NOT_ADDRESSABLE")
    print("R1_ORIGINAL_OCI_PIN_TO_LOCAL_CONFIG_IDS=PASS_5_OF_5", flush=True)
    print("R1_IMAGE_IMPORT=NONE_ALREADY_CACHED", flush=True)
    return {name: "sha256:" + result[pin.removeprefix("sha256:")]
            for name, pin in IMAGES.items()}

def wait_for_sql(name, database):
    # Do not trust pg_isready during the image's transient initdb server.
    for _ in range(90):
        p = subprocess.run([*PODMAN, "exec", name, "psql", "-X", "-U", "postgres",
                            "-d", database, "-t", "-A", "-c", "SELECT 1"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
        if p.returncode == 0 and p.stdout.strip() == b"1":
            return
        time.sleep(0.5)
    raise Stop("ISOLATED_DATABASE_SQL_NOT_READY")

def assert_disconnected_tmpfs_container(name):
    # Read full inspect only in memory: it contains a synthetic password.
    # Never print or write inspect JSON or synthetic credentials.
    raw = silent_run([*PODMAN, "inspect", "--type=container", name], timeout=20)
    rows = json.loads(raw)
    ensure(isinstance(rows, list) and len(rows) == 1,
           "RESTORE_CONTAINER_INSPECT_INVALID")
    record = rows[0]
    host = record.get("HostConfig") or {}
    ensure(host.get("NetworkMode") == "none",
           "ISOLATION_NETWORK_POLICY_NOT_ENFORCED")
    ensure(not host.get("PortBindings"),
           "RESTORE_CONTAINER_PORT_PUBLISHED")
    mounts = record.get("Mounts") or []
    ensure(isinstance(mounts, list) and all(
        isinstance(m, dict) and m.get("Type") == "tmpfs"
        for m in mounts), "UNEXPECTED_PERSISTENT_DATABASE_MOUNT")
    tmpfs = host.get("Tmpfs") or {}
    ensure(isinstance(tmpfs, dict) and
           "/var/lib/postgresql/data" in tmpfs,
           "DATABASE_NOT_ON_DISPOSABLE_TMPFS")

def restore_one(root, prefix, image, dump, database):
    name = "v79-r1-" + prefix + "-" + secrets.token_hex(4)
    # Register name for unconditional container removal even when run fails.
    print("R1_" + prefix.upper() + "_RESTORE=START", flush=True)
    try:
        silent_run(db_run_args(name, image, database), timeout=90)
        assert_disconnected_tmpfs_container(name)
        wait_for_sql(name, database)
        decrypted_pipe_to_command(
            root / dump,
            [*PODMAN, "exec", "-i", name, "pg_restore", "-U", "postgres",
             "--no-owner", "--no-acl", "--single-transaction", "--exit-on-error",
             "--dbname=" + database], timeout=900)
        rows = silent_run([*PODMAN, "exec", name, "psql", "-X", "-U", "postgres",
                           "-d", database, "-t", "-A", "-c", TABLES_SQL])
        ensure(rows.isdecimal() and int(rows) > 0, "NO_RESTORED_USER_TABLES")
        print("R1_" + prefix.upper() + "_RESTORE=PASS", flush=True)
        print("R1_" + prefix.upper() + "_USER_TABLES=" + rows, flush=True)
    finally:
        # On success and failure: no live, dormant or persistent plaintext DB.
        subprocess.run([*PODMAN, "rm", "-f", name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=45, check=False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly allow networkless DB restore from pinned pre-cached images")
    args = parser.parse_args()
    os.umask(0o077)
    root = preflight(args.backup)
    if not args.execute:
        print("R1_ACTION=READ_ONLY_PREFLIGHT", flush=True)
    else:
        offline = prove_and_resolve_saved_images(root)
        restore_one(root, "hub", offline["v79-hub-postgres"],
                    "hub-pg.dump.gpg", "r1_hub_restore")
        restore_one(root, "tiquet", offline["tiquet-postgres"],
                    "tiquet-pg.dump.gpg", "r1_tiquet_restore")
        print("R1_BOTH_DATABASES_RESTORED_OFFLINE=PASS", flush=True)
        print("R1_DISPOSABLE_DATABASE_CONTAINERS=REMOVED", flush=True)
    print("R1_APP_BOOT=NOT_YET_TESTED", flush=True)
    print("R1_CUSTOMER_RELEASE=NO_GO", flush=True)

if __name__ == "__main__":
    try:
        main()
    except (Stop, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
        print("STOP=" + str(e) if isinstance(e, Stop) else "STOP=LOCAL_REHEARSAL_FAILED_REDACTED")
        print("R1_CUSTOMER_RELEASE=NO_GO")
        sys.exit(1)
