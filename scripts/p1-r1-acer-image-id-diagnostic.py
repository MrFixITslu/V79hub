#!/usr/bin/env python3
"""Read-only diagnosis of Docker-saved image IDs vs Acer rootless Podman cache.

No containers, image imports/tags/pulls, network, archive writes or plaintext
files. Streams the encrypted saved-image TAR through memory, reads ONLY its
bounded manifest.json, drains GPG to EOF, then compares config IDs with the
local rootless image inventory. Prints only known image role/status, never
image tags, archived configs, secret metadata or credentials.
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

IMAGES = {
    "HUB_APP": "d0dfba263dbfec8a08e6c46995c2172daf234206fe8d0f6484bb98b938cd3c65",
    "TIQUET_APP": "5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42",
    "HUB_POSTGRES": "b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "TIQUET_POSTGRES": "cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
    "HUB_ROLLBACK": "4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698",
}
FILE = "exact-images-and-rollback.tar.gpg"
INSPECT_FILE = "runtime-inspect.json.gpg"
PODMAN = ("podman", "--remote=false")
HEX = re.compile(r"[0-9a-f]{64}\Z")

class Stop(Exception):
    pass

def require(ok, code):
    if not ok:
        raise Stop(code)

def normalize_id(raw):
    if not isinstance(raw, str):
        return ""
    value = raw.removeprefix("sha256:").lower()
    return value if HEX.fullmatch(value) else ""

def docker_manifest_config_ids(body):
    require(isinstance(body, list) and 1 <= len(body) <= 50,
            "DOCKER_ARCHIVE_MANIFEST_INVALID")
    found = set()
    for entry in body:
        require(isinstance(entry, dict) and isinstance(entry.get("Config"), str),
                "DOCKER_ARCHIVE_CONFIG_ENTRY_INVALID")
        config = PurePosixPath(entry["Config"]).name
        digest = normalize_id(config.removesuffix(".json"))
        require(digest, "DOCKER_ARCHIVE_CONFIG_DIGEST_INVALID")
        found.add(digest)
    return found

def podman_image_ids(items):
    require(isinstance(items, list), "PODMAN_IMAGES_FORMAT_INVALID")
    found = set()
    for item in items:
        require(isinstance(item, dict), "PODMAN_IMAGE_ENTRY_INVALID")
        imageid = item.get("Id", item.get("ID", item.get("id")))
        digest = normalize_id(imageid)
        if digest:
            found.add(digest)
    return found

def read_archive_configs(archive):
    decrypt = subprocess.Popen(
        ["gpg", "--batch", "--quiet", "--decrypt", str(archive)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    parsed = None
    try:
        # r| is truly streaming and never extracts archive members to disk.
        with tarfile.open(fileobj=decrypt.stdout, mode="r|") as tar:
            for member in tar:
                if member.name.removeprefix("./") == "manifest.json":
                    require(parsed is None and member.isfile()
                            and 0 < member.size <= 2 * 1024 * 1024,
                            "DOCKER_ARCHIVE_MANIFEST_INVALID")
                    stream = tar.extractfile(member)
                    require(stream is not None, "DOCKER_ARCHIVE_MANIFEST_UNREADABLE")
                    parsed = docker_manifest_config_ids(json.load(stream))
            # Iterate through EOF even if manifest was encountered early.
            # It ensures GPG's return code is meaningful, never SIGPIPE.
        decrypt.stdout.close()
        require(decrypt.wait(timeout=90) == 0, "ARCHIVE_GPG_DECRYPT_FAILED")
        require(parsed is not None, "DOCKER_ARCHIVE_MANIFEST_NOT_FOUND")
        return parsed
    finally:
        if decrypt.stdout and not decrypt.stdout.closed:
            decrypt.stdout.close()
        if decrypt.poll() is None:
            decrypt.kill()
        decrypt.wait()

def saved_runtime_image_ids(body):
    # Source backup writer captures docker inspect of the FOUR live
    # image objects, not containers; rollback image is archive-only.
    require(isinstance(body, list) and len(body) == 4,
            "SAVED_IMAGE_INSPECT_COUNT_INVALID")
    ids = set()
    for item in body:
        require(isinstance(item, dict), "SAVED_IMAGE_INSPECT_ROW_INVALID")
        digest = normalize_id(item.get("Id"))
        require(bool(digest) and digest not in ids, "SAVED_IMAGE_INSPECT_ID_INVALID")
        ids.add(digest)
    return ids

def verify_ciphertext(root, filename):
    manifest_path = root / "ciphertext-manifest.json"
    require(manifest_path.is_file() and not manifest_path.is_symlink(),
            "CIPHERTEXT_MANIFEST_MISSING")
    doc = json.loads(manifest_path.read_text())
    entries = doc.get("files")
    require(isinstance(entries, list), "CIPHERTEXT_MANIFEST_INVALID")
    matches = [e for e in entries if isinstance(e, dict) and e.get("name") == filename]
    require(len(matches) == 1, "CIPHERTEXT_MANIFEST_ENTRY_INVALID")
    entry = matches[0]
    path = root / filename
    require(path.is_file() and not path.is_symlink(),
            "CIPHERTEXT_COMPONENT_MISSING")
    require(path.stat().st_size == entry.get("bytes")
            and (path.stat().st_mode & 0o077) == 0,
            "CIPHERTEXT_COMPONENT_SIZE_OR_PERMISSIONS_INVALID")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    require(h.hexdigest() == entry.get("sha256"),
            "CIPHERTEXT_COMPONENT_HASH_MISMATCH")
    return path

def read_saved_image_inspect(path):
    # GPG stdout carries sensitive original Docker metadata! Keep it
    # strictly in memory; never print or write its content.
    proc = subprocess.Popen(
        ["gpg", "--batch", "--quiet", "--decrypt", str(path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    chunks = []
    total = 0
    try:
        while True:
            block = proc.stdout.read(131072)
            if not block:
                break
            total += len(block)
            require(total <= 8 * 1024 * 1024,
                    "SAVED_INSPECT_JSON_EXCEEDS_PRIVATE_MEMORY_LIMIT")
            chunks.append(block)
        proc.stdout.close()
        require(proc.wait(timeout=60) == 0, "SAVED_INSPECT_DECRYPT_FAILED")
        return saved_runtime_image_ids(json.loads(b"".join(chunks)))
    finally:
        if proc.stdout and not proc.stdout.closed:
            proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()

def check_rootless_local_machine():
    require(socket.gethostname() == "firelion-Aspire-A315-51", "RUN_ONLY_ON_ACER")
    require(os.geteuid() != 0, "NO_ROOT_PODMAN")
    require(not os.environ.get("CONTAINER_HOST") and
            not os.environ.get("DOCKER_HOST"), "REMOTE_CONTAINER_CONTEXT_REFUSED")
    require(shutil.which("podman") is not None and shutil.which("gpg") is not None,
            "PODMAN_OR_GPG_NOT_PRESENT")
    r = subprocess.run([*PODMAN, "info", "--format",
                        "{{.Host.Security.Rootless}}"],
                       capture_output=True, text=True, timeout=30)
    require(r.returncode == 0 and r.stdout.strip() == "true",
            "ACER_ROOTLESS_PODMAN_NOT_VERIFIED")

def run_inventory():
    result = subprocess.run(
        [*PODMAN, "images", "--all", "--no-trunc", "--format", "json"],
        capture_output=True, timeout=60)
    require(result.returncode == 0, "PODMAN_LOCAL_INVENTORY_FAILED")
    return podman_image_ids(json.loads(result.stdout))

def pin_lookup(pin):
    r = subprocess.run([*PODMAN, "image", "exists", "sha256:" + pin],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30)
    return r.returncode == 0

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--backup", type=Path, required=True)
    args = cli.parse_args()
    check_rootless_local_machine()
    root = args.backup.expanduser().absolute()
    require(root.is_dir() and not root.is_symlink(),
            "VERIFIED_BACKUP_DIRECTORY_MISSING")
    require((root.stat().st_mode & 0o077) == 0,
            "BACKUP_DIRECTORY_PERMISSIONS_INVALID")
    require(not (root / "CAPTURE_INCOMPLETE").exists(),
            "INCOMPLETE_BACKUP_SET")
    receipt = root / "ciphertext-manifest.json"
    require(receipt.is_file() and not receipt.is_symlink(),
            "BACKUP_MANIFEST_MISSING")
    data = json.loads(receipt.read_text())
    expected = dict(zip(
        ("v79-hub", "v79-tiquet-manager", "v79-hub-postgres", "tiquet-postgres"),
        ("sha256:" + pin for pin in list(IMAGES.values())[:4])))
    require(data.get("schema") == 1
            and data.get("status") == "CAPTURED_NOT_RESTORED"
            and data.get("images") == expected
            and data.get("rollbackHub") == "sha256:" + IMAGES["HUB_ROLLBACK"]
            and isinstance(data.get("files"), list)
            and len(data["files"]) == 14,
            "ORIGINAL_BACKUP_SET_PROVENANCE_NOT_MATCHED")
    source = verify_ciphertext(root, FILE)
    saved_inspect = verify_ciphertext(root, INSPECT_FILE)
    print("R1_DIAGNOSTIC=READ_ONLY_ACER_LOCAL", flush=True)
    local_ids = run_inventory()
    archive_ids = read_archive_configs(source)
    runtime_ids = read_saved_image_inspect(saved_inspect)
    matched_archive = 0
    matched_local = 0
    matched_lookup = 0
    for label, pin in IMAGES.items():
        in_archive = pin in archive_ids
        in_local = pin in local_ids
        addressable = pin_lookup(pin)
        matched_archive += in_archive
        matched_local += in_local
        matched_lookup += addressable
        print("R1_" + label + "|ARCHIVE_CONFIG=" + ("YES" if in_archive else "NO") +
              "|PODMAN_CONFIG=" + ("YES" if in_local else "NO") +
              "|PIN_LOOKUP=" + ("YES" if addressable else "NO"), flush=True)
    print("R1_ARCHIVE_CONFIG_IDS_MATCH=%d/5" % matched_archive)
    print("R1_ARCHIVE_UNIQUE_CONFIG_IDS=%d" % len(archive_ids))
    print("R1_SAVED_RUNTIME_INSPECT_IDS_MATCH=%d/4" %
          len(set(list(IMAGES.values())[:4]) & runtime_ids))
    print("R1_ARCHIVE_VS_RUNTIME_INSPECT_SHARED=%d" %
          len(archive_ids & runtime_ids))
    print("R1_ARCHIVE_VS_LOCAL_SHARED_CONFIG_IDS=%d" %
          len(archive_ids & local_ids))
    print("R1_LOCAL_CONFIG_IDS_MATCH=%d/5" % matched_local)
    print("R1_SHA_PIN_LOOKUPS=%d/5" % matched_lookup)
    print("R1_LOCAL_IMAGE_RECORDS=%d" % len(local_ids))
    print("R1_DATABASE_RESTORE=NOT_RUN")
    print("R1_IMAGES_IMPORTED=NO_NEW_IMPORT")
    print("R1_PRODUCTION_CONNECTION=NONE")
    print("R1_RELEASE_GATE=NO_GO")

if __name__ == "__main__":
    try:
        main()
    except (Stop, OSError, ValueError, json.JSONDecodeError, tarfile.TarError,
            subprocess.TimeoutExpired) as exc:
        print("STOP=" + str(exc) if isinstance(exc, Stop)
              else "STOP=LOCAL_IMAGE_DIAGNOSTIC_FAILED_REDACTED")
        print("R1_RELEASE_GATE=NO_GO")
        sys.exit(1)
