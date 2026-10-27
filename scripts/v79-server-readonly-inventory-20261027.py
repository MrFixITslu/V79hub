#!/usr/bin/env python3
"""Bounded, read-only Dell inventory; never prints secrets or customer data.

Run on v79sl with Docker read permission. Backup metadata is not restore proof.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

HOST = "v79sl"
BACKUP_ROOTS = (
    Path("/home/firelion/ServerBackups/v79sl"),
    Path("/home/firelion/.v79-v3-encrypted-checkpoints"),
)
UNITS = ("ufw.service", "tailscaled.service", "fail2ban.service",
         "unattended-upgrades.service", "docker.service")
MAX_CONTAINERS = 100

class Stop(Exception):
    pass

def invoke(argv, timeout=15):
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("READ_ONLY_COMMAND_UNAVAILABLE") from None
    if len(result.stdout) > 4_000_000:
        raise Stop("READ_ONLY_OUTPUT_LIMIT")
    return result

def docker_json(*argv):
    result = invoke(["docker", *argv])
    if result.returncode:
        raise Stop("DOCKER_READ_UNAVAILABLE")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        raise Stop("DOCKER_RESPONSE_INVALID") from None

def backup_metadata(root):
    if not root.is_dir() or root.is_symlink():
        return {"present": False, "valid_backup": False}
    newest = None
    files = 0
    try:
        # Bounded metadata walk. No archive content or path is returned.
        for directory, subdirs, names in os.walk(root, followlinks=False):
            depth = len(Path(directory).relative_to(root).parts)
            subdirs[:] = sorted(x for x in subdirs if not (Path(directory) / x).is_symlink())[:30] if depth < 3 else []
            for name in sorted(names)[:100]:
                entry = Path(directory) / name
                if entry.is_symlink() or not entry.is_file():
                    continue
                stat = entry.stat()
                files += 1
                newest = max(newest or 0, stat.st_mtime)
                if files >= 1000:
                    break
            if files >= 1000:
                break
    except OSError:
        return {"present": True, "metadata": "unavailable", "valid_backup": False}
    return {"present": True, "files_sampled": files,
            "newest_file_utc": dt.datetime.fromtimestamp(newest, dt.timezone.utc).isoformat() if newest else None,
            "coverage": "unverified", "integrity": "unverified", "restore": "unverified",
            "valid_backup": False}

def container_summary(row):
    name = str(row.get("Name", "")).lstrip("/")
    state = row.get("State") or {}
    host = row.get("HostConfig") or {}
    config = row.get("Config") or {}
    ports = host.get("PortBindings") or {}
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}", name):
        raise Stop("CONTAINER_NAME_INVALID")
    image = row.get("Image")
    if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise Stop("CONTAINER_IMAGE_INVALID")
    return {
        "name": name, "image_id": image, "state": state.get("Status"),
        "health": (state.get("Health") or {}).get("Status", "not_configured"),
        "restarts": row.get("RestartCount"), "oom_killed": state.get("OOMKilled"),
        "privileged": bool(host.get("Privileged")), "read_only_root": bool(host.get("ReadonlyRootfs")),
        "no_new_privileges": "no-new-privileges:true" in (host.get("SecurityOpt") or []),
        "runtime_user_configured": bool(config.get("User")),
        "published_ports": sorted(str(p) for p, binding in ports.items() if binding),
        "persistent_mount_destinations": sorted(str(m.get("Destination")) for m in row.get("Mounts") or []
                                                if m.get("Type") in ("bind", "volume")),
    }

def collect():
    if socket.gethostname().split(".")[0] != HOST:
        raise Stop("WRONG_HOST")
    if os.getenv("DOCKER_HOST") or os.getenv("DOCKER_CONTEXT"):
        raise Stop("REMOTE_DOCKER_CONTEXT_REFUSED")
    endpoint = docker_json("context", "inspect")
    if not isinstance(endpoint, list) or len(endpoint) != 1 or (
        endpoint[0].get("Endpoints", {}).get("docker", {}).get("Host")
        not in ("unix:///var/run/docker.sock", "unix:///run/docker.sock")
    ):
        raise Stop("NONLOCAL_DOCKER_DAEMON")
    names = invoke(["docker", "ps", "-a", "--format", "{{.Names}}"])
    if names.returncode:
        raise Stop("DOCKER_READ_UNAVAILABLE")
    selected = names.stdout.decode("utf-8").splitlines()
    if len(selected) > MAX_CONTAINERS or len(selected) != len(set(selected)):
        raise Stop("CONTAINER_INVENTORY_BOUND")
    containers = [container_summary(docker_json("inspect", "--type", "container", name)[0])
                  for name in selected]
    services = {}
    for unit in UNITS:
        value = invoke(["systemctl", "is-active", unit]).stdout.decode("utf-8", "replace").strip()
        services[unit] = value if value in {"active", "inactive", "failed", "activating", "unknown"} else "unverified"
    timers = []
    timer_sources = {}
    for scope, prefix in (("system", []), ("user", ["--user"])):
        timer_result = invoke(["systemctl", *prefix, "list-timers", "--all", "--no-legend", "--no-pager"])
        timer_sources[scope] = "available" if timer_result.returncode == 0 else "unavailable"
        if timer_result.returncode == 0:
            for line in timer_result.stdout.decode("utf-8", "replace").splitlines():
                for token in line.split():
                    if token.endswith(".timer") and re.search(r"backup|checkpoint|v79", token, re.I):
                        timers.append({"scope": scope, "unit": token})
    disk = os.statvfs("/")
    return {
        "schema": "v79-server-readonly-inventory-20261027",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "host": HOST, "container_count": len(containers), "containers": containers,
        "host_units": services, "timer_sources": timer_sources,
        "relevant_timer_names": sorted(timers, key=lambda item: (item["scope"], item["unit"])),
        "backup_locations": [backup_metadata(p) for p in BACKUP_ROOTS],
        "root_disk_free_bytes": disk.f_bavail * disk.f_frsize,
        "whole_server_backup_coverage": "UNVERIFIED",
        "restore_and_security_acceptance": "UNVERIFIED",
        "production_changes": "NONE",
    }

class SafetyTests(unittest.TestCase):
    def test_wrong_host_stops_before_commands(self):
        with patch("socket.gethostname", return_value="other"), patch(__name__ + ".invoke") as call:
            with self.assertRaises(Stop):
                collect()
            call.assert_not_called()
    def test_no_secrets_or_mount_sources(self):
        row = {"Name": "/v79-hub", "Image": "sha256:" + "a" * 64,
               "State": {"Status": "running", "Health": {"Status": "healthy", "Log": ["secret"]}},
               "Config": {"Env": ["API_KEY=secret"], "User": "appuser"},
               "HostConfig": {"PortBindings": {"3040/tcp": [{"HostIp": "127.0.0.1"}]},
                              "Binds": ["/private/secret:/app/data"]},
               "Mounts": [{"Type": "bind", "Source": "/private/secret", "Destination": "/app/data"}]}
        result = json.dumps(container_summary(row))
        self.assertNotIn("secret", result)
        self.assertNotIn("API_KEY", result)
        self.assertIn("/app/data", result)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--run", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        outcome = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(SafetyTests))
        return 0 if outcome.wasSuccessful() else 1
    try:
        print(json.dumps(collect(), indent=2, sort_keys=True))
        return 0
    except Stop as exc:
        print(json.dumps({"production_changes": "NONE", "status": "HOLD", "reason": str(exc)}))
        return 2
    except Exception:
        print(json.dumps({"production_changes": "NONE", "status": "HOLD", "reason": "AUDIT_FAILED_REDACTED"}))
        return 2

if __name__ == "__main__":
    sys.exit(main())
