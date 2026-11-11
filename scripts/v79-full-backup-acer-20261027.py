#!/usr/bin/env python3
"""Acer-side encrypted offhost capture of the exact Dell source inventory.

No plaintext customer data is saved on Acer. This is not a restore certificate:
file-backed apps and Redis may change during a live copy.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import unittest

HOST = "firelion-Aspire-A315-51"
SERVER = "firelion@192.168.100.163"
RECIPIENT = "484CF39CE37A02884497AD9C41A17102D2842ECE"
RESERVE = 100 * 1024**3
DESTINATION = Path.home() / "V79-Full-Recovery"

class Stop(Exception):
    pass

def local(args, *, data=None, timeout=120):
    try:
        return subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("LOCAL_OR_SSH_COMMAND_FAILED") from None

def remote(source, mode, baseline=None):
    inner = "python3 - " + mode
    if baseline:
        inner += " --expected-baseline " + shlex.quote(baseline)
    command = "sg docker -c " + shlex.quote(inner)
    p = local(["ssh", "-o", "StrictHostKeyChecking=yes", SERVER, command],
              data=source.read_bytes(), timeout=90)
    if p.returncode or len(p.stdout) > 2_000_000:
        raise Stop("REMOTE_PLAN_UNAVAILABLE")
    return p.stdout

def free_bytes(path):
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize

def safe_file(item):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,150}", item):
        raise Stop("ITEM_NAME_INVALID")
    return item.replace(":", "__") + ".gpg"

def key_check():
    if local(["gpg", "--batch", "--list-secret-keys", RECIPIENT]).returncode:
        raise Stop("RECOVERY_PRIVATE_KEY_NOT_AVAILABLE")
    # Verify the key can actually decrypt before transferring any customer data.
    with tempfile.TemporaryDirectory(prefix="v79-keycheck-") as temporary:
        encrypted = Path(temporary) / "probe.gpg"
        probe = subprocess.run(["gpg", "--batch", "--quiet", "--trust-model", "always",
                                "--recipient", RECIPIENT, "--encrypt", "--output", str(encrypted)],
                               input=b"V79 recovery key check\n", stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=False)
        if probe.returncode:
            raise Stop("RECOVERY_PUBLIC_KEY_UNAVAILABLE")
        result = local(["gpg", "--batch", "--quiet", "--decrypt", str(encrypted)])
        if result.returncode or result.stdout != b"V79 recovery key check\n":
            raise Stop("RECOVERY_DECRYPTION_NOT_AVAILABLE")

def encrypt_item(source, baseline, item, output):
    inner = "python3 - --stream " + shlex.quote(item) + " --expected-baseline " + shlex.quote(baseline)
    command = "sg docker -c " + shlex.quote(inner)
    partial = output.with_name(output.name + ".partial")
    try:
        with source.open("rb") as script:
            producer = subprocess.Popen(["ssh", "-o", "StrictHostKeyChecking=yes", SERVER, command],
                                        stdin=script, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                consumer = subprocess.Popen(
                    ["gpg", "--batch", "--quiet", "--trust-model", "always", "--recipient", RECIPIENT,
                     "--encrypt", "--output", str(partial)],
                    stdin=producer.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                producer.stdout.close()
                consumer_status = consumer.wait(timeout=25200)
                producer_status = producer.wait(timeout=25200)
                source_error = producer.stderr.read(4096)
            except (OSError, subprocess.TimeoutExpired):
                producer.kill()
                producer.wait()
                if "consumer" in locals() and consumer.poll() is None:
                    consumer.kill()
                    consumer.wait()
                raise Stop("STREAM_TIMEOUT") from None
        if producer_status or consumer_status or not partial.is_file() or partial.stat().st_size == 0:
            code = re.search(rb"STOP=([A-Z_]+)", source_error)
            if producer_status and code:
                raise Stop("SOURCE_" + code.group(1).decode("ascii"))
            raise Stop("STREAM_OR_ENCRYPTION_FAILED")
        partial.rename(output)
    finally:
        partial.unlink(missing_ok=True)
    digest = hashlib.sha256()
    with output.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "bytes": output.stat().st_size}

def verify_item(item, path):
    if item == "runtime-inspect":
        result = local(["gpg", "--batch", "--quiet", "--decrypt", str(path)], timeout=120)
        if result.returncode or not isinstance(json.loads(result.stdout), dict):
            raise Stop("RUNTIME_INSPECT_DECRYPT_FAILED")
        return
    if item.startswith("pg-globals:"):
        result = local(["gpg", "--batch", "--quiet", "--decrypt", str(path)], timeout=120)
        if result.returncode or not result.stdout:
            raise Stop("PG_GLOBALS_DECRYPT_FAILED")
        return
    if item.startswith("pg-db:"):
        decrypt = subprocess.Popen(["gpg", "--batch", "--quiet", "--decrypt", str(path)],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            prefix = decrypt.stdout.read(5)
            for _ in iter(lambda: decrypt.stdout.read(1024 * 1024), b""):
                pass
            if prefix != b"PGDMP" or decrypt.wait(timeout=120) != 0:
                raise Stop("PG_DUMP_DECRYPT_FAILED")
        finally:
            decrypt.stdout.close()
        return
    decrypt = subprocess.Popen(["gpg", "--batch", "--quiet", "--decrypt", str(path)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    validate = subprocess.run(["tar", "-tf", "-"], stdin=decrypt.stdout, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=21600, check=False)
    decrypt.stdout.close()
    if validate.returncode or decrypt.wait(timeout=120) != 0:
        raise Stop("TAR_DECRYPT_OR_STRUCTURE_FAILED")

def capture(source):
    os.umask(0o077)
    if socket.gethostname().split(".")[0] != HOST:
        raise Stop("ACER_HOST_REQUIRED")
    if not source.is_file() or source.is_symlink():
        raise Stop("SOURCE_SCRIPT_INVALID")
    if not DESTINATION.exists():
        DESTINATION.mkdir(mode=0o700)
    if DESTINATION.is_symlink() or DESTINATION.stat().st_mode & 0o077:
        raise Stop("DESTINATION_PERMISSIONS")
    if free_bytes(DESTINATION) < RESERVE + 40 * 1024**3:
        raise Stop("OFFHOST_SPACE_BELOW_START_THRESHOLD")
    key_check()
    try:
        plan = json.loads(remote(source, "--plan"))
    except (ValueError, UnicodeDecodeError):
        raise Stop("PLAN_INVALID") from None
    items = plan.get("items")
    baseline = plan.get("baseline_sha256")
    if not isinstance(items, list) or len(items) < 30 or len(items) > 400 or (
            not isinstance(baseline, str) or not re.fullmatch(r"[a-f0-9]{64}", baseline)):
        raise Stop("PLAN_SHAPE_INVALID")
    if len(set(items)) != len(items) or len({safe_file(item) for item in items}) != len(items):
        raise Stop("PLAN_ITEM_DUPLICATE")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = Path(tempfile.mkdtemp(prefix="full-" + stamp + "-", dir=DESTINATION))
    os.chmod(directory, 0o700)
    (directory / "STATUS").write_text("IN_PROGRESS\n")
    receipt = {"schema": "v79-full-offhost-capture-20261027",
               "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "baseline_sha256": baseline, "plan": plan, "encrypted_items": {},
               "production_changes": "ONLY_TEMPORARY_READ_ONLY_DOCKER_HELPERS",
               "live_file_consistency": "UNVERIFIED", "restore_verified": False}
    print("BACKUP_DIRECTORY=" + str(directory), flush=True)
    try:
        for number, item in enumerate(items, 1):
            if free_bytes(directory) < RESERVE:
                raise Stop("OFFHOST_SPACE_RESERVE_REACHED")
            output = directory / safe_file(item)
            info = encrypt_item(source, baseline, item, output)
            verify_item(item, output)
            receipt["encrypted_items"][item] = info
            print(f"ENCRYPTED_AND_DECRYPTED={number}/{len(items)}:{item}", flush=True)
        # Final static identity check; use plan rather than another customer-data read.
        after = json.loads(remote(source, "--plan"))
        if after.get("baseline_sha256") != baseline:
            raise Stop("SOURCE_BASELINE_CHANGED_DURING_CAPTURE")
        with (directory / "receipt.json").open("x") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
        (directory / "STATUS").write_text("OFFHOST_CIPHERTEXT_VERIFIED_RESTORE_NOT_PROVEN\n")
        print("OFFHOST_BACKUP=PASS_ENCRYPTED_ITEMS_" + str(len(items)), flush=True)
        print("RESTORE_VERIFIED=NO", flush=True)
    except Exception:
        (directory / "STATUS").write_text("INCOMPLETE_DO_NOT_RESTORE\n")
        raise

class SafetyTests(unittest.TestCase):
    def test_item_rejects_path_or_shell(self):
        for name in ("../config", "x;touch /tmp/a", "a/b"):
            with self.assertRaises(Stop):
                safe_file(name)
    def test_item_name_deterministic(self):
        self.assertEqual(safe_file("pg-db:v79-hub-postgres:0"), "pg-db__v79-hub-postgres__0.gpg")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-script", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--backup", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(SafetyTests))
        return 0 if result.wasSuccessful() else 1
    try:
        capture(args.source_script)
        return 0
    except Stop as exc:
        print("STOP=" + str(exc))
        return 2
    except Exception:
        print("STOP=REDACTED_BACKUP_FAILURE")
        return 2

if __name__ == "__main__":
    sys.exit(main())
