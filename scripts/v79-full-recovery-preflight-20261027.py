#!/usr/bin/env python3
"""Read-only source inventory for a whole-server recovery plan.

No backup, restore, container creation, customer-data read or secret output.
Run on v79sl as the normal Docker-authorised operator.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

MAX_CONTAINERS = 100
MAX_VOLUMES = 300
DATABASE_NAMES = ("v79-hub-postgres", "tiquet-postgres", "fire-finance-db",
                  "v79-pos-db", "v79_academy_postgres")
RECOVERY_KEY = Path("/home/firelion/.v79-g12-recovery-public.asc")

class Stop(Exception):
    pass

def invoke(args, timeout=20):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("READ_COMMAND_UNAVAILABLE_OR_TIMEOUT") from None
    if len(result.stdout) > 8_000_000:
        raise Stop("READ_OUTPUT_LIMIT")
    return result

def docker_json(*args):
    result = invoke(["docker", *args])
    if result.returncode:
        raise Stop("DOCKER_READ_UNAVAILABLE")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        raise Stop("DOCKER_JSON_INVALID") from None

def mount_summary(row):
    mounts = row.get("Mounts") or []
    result = []
    for mount in mounts:
        kind = mount.get("Type")
        dest = mount.get("Destination")
        if kind not in ("bind", "volume", "tmpfs") or not isinstance(dest, str) or not dest.startswith("/"):
            raise Stop("UNSUPPORTED_MOUNT_SHAPE")
        source = mount.get("Source") or ""
        # Stable within this inventory only. The encrypted recovery manifest must
        # carry the actual source path; do not expose it in this shared output.
        result.append({"type": kind, "destination": dest, "read_only": not bool(mount.get("RW")),
                       "source_sha256": hashlib.sha256(source.encode()).hexdigest() if source else None,
                       "volume_name": mount.get("Name") if kind == "volume" else None})
    return sorted(result, key=lambda item: (item["type"], item["destination"]))

def collect():
    if socket.gethostname().split(".")[0] != "v79sl":
        raise Stop("WRONG_HOST")
    if os.getenv("DOCKER_HOST") or os.getenv("DOCKER_CONTEXT"):
        raise Stop("REMOTE_DOCKER_CONTEXT_REFUSED")
    contexts = docker_json("context", "inspect")
    if len(contexts) != 1 or contexts[0].get("Endpoints", {}).get("docker", {}).get("Host") not in (
            "unix:///var/run/docker.sock", "unix:///run/docker.sock"):
        raise Stop("NONLOCAL_DOCKER")
    names_result = invoke(["docker", "ps", "-a", "--format", "{{.Names}}"])
    if names_result.returncode:
        raise Stop("CONTAINER_LIST_UNAVAILABLE")
    names = names_result.stdout.decode().splitlines()
    if len(names) > MAX_CONTAINERS or len(names) != len(set(names)):
        raise Stop("CONTAINER_INVENTORY_BOUND")
    rows = docker_json("inspect", "--type", "container", *names) if names else []
    containers = {}
    for row in rows:
        name = row.get("Name", "").lstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name):
            raise Stop("CONTAINER_NAME_INVALID")
        containers[name] = {
            "running": row.get("State", {}).get("Status") == "running",
            "image_id": row.get("Image"),
            "mounts": mount_summary(row),
            "compose_project_present": bool((row.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project")),
        }
    if set(containers) != set(names):
        raise Stop("CONTAINER_SET_MISMATCH")
    volume_names = invoke(["docker", "volume", "ls", "--format", "{{.Name}}"])
    if volume_names.returncode:
        raise Stop("VOLUME_LIST_UNAVAILABLE")
    volumes = volume_names.stdout.decode().splitlines()
    if len(volumes) > MAX_VOLUMES or len(volumes) != len(set(volumes)):
        raise Stop("VOLUME_INVENTORY_BOUND")
    volume_rows = docker_json("volume", "inspect", *volumes) if volumes else []
    drivers = sorted(set(str(v.get("Driver", "")) for v in volume_rows))
    if len(volume_rows) != len(volumes):
        raise Stop("VOLUME_SET_MISMATCH")
    current = {m["volume_name"] for c in containers.values() if c["running"]
               for m in c["mounts"] if m["type"] == "volume"}
    binds = {m["source_sha256"] for c in containers.values() if c["running"]
             for m in c["mounts"] if m["type"] == "bind"}
    running = [name for name, row in containers.items() if row["running"]]
    fs = os.statvfs("/")
    key = RECOVERY_KEY.is_file() and not RECOVERY_KEY.is_symlink()
    return {
        "schema": "v79-full-recovery-preflight-20261027",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "host": "v79sl",
        "running_container_count": len(running),
        "all_container_count": len(containers),
        "containers": containers,
        "docker_volume_count": len(volumes),
        "docker_volume_drivers": drivers,
        "volumes_mounted_by_running_containers": len(current),
        "bind_sources_mounted_by_running_containers": len(binds),
        "unattached_volume_count": len(set(volumes) - current),
        "expected_database_containers": {name: containers.get(name, {}).get("running", False)
                                         for name in DATABASE_NAMES},
        "recovery_public_key_present": key,
        "root_filesystem_free_bytes": fs.f_bavail * fs.f_frsize,
        "backup_destination_capacity": "MUST_CHECK_OFFHOST",
        "live_database_volume_tar_safe": False,
        "whole_server_backup_complete": False,
        "production_changes": "NONE",
    }

class SafetyTests(unittest.TestCase):
    def test_wrong_host_never_inspects(self):
        with patch("socket.gethostname", return_value="wrong"), patch(__name__ + ".invoke") as call:
            with self.assertRaises(Stop):
                collect()
            call.assert_not_called()
    def test_mount_source_not_disclosed(self):
        row = {"Mounts": [{"Type": "bind", "Source": "/private/merchant-secret",
                           "Destination": "/run/secrets/merchant", "RW": False}]}
        result = json.dumps(mount_summary(row))
        self.assertNotIn("/private/merchant-secret", result)
        self.assertIn("/run/secrets/merchant", result)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(SafetyTests))
        return 0 if result.wasSuccessful() else 1
    try:
        print(json.dumps(collect(), sort_keys=True, indent=2))
        return 0
    except Stop as exc:
        print(json.dumps({"production_changes": "NONE", "status": "HOLD", "reason": str(exc)}))
        return 2
    except Exception:
        print(json.dumps({"production_changes": "NONE", "status": "HOLD", "reason": "PREFLIGHT_FAILED_REDACTED"}))
        return 2

if __name__ == "__main__":
    sys.exit(main())
