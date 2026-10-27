#!/usr/bin/env python3
"""Stream exact current V79 recovery sources over SSH. No plaintext files.

The Acer driver encrypts stdout immediately. This helper makes temporary,
networkless, read-only Docker helper containers to read local volume/host data.
No live container is stopped, paused, changed or restarted. File-backed stores
can still change during capture; the receipt must not claim app consistency.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

MAX_CONTAINERS = 100
MAX_VOLUMES = 300
PG_NAMES = ("v79-hub-postgres", "tiquet-postgres", "fire-finance-db",
            "v79-pos-db", "v79_academy_postgres")
TAR_IMAGE_FROM = "v79-hub-postgres"
BLOCKED_PREFIXES = ("/proc", "/sys", "/dev", "/var/lib/docker")

class Stop(Exception):
    pass

def command(args, *, json_result=False, timeout=60):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("SOURCE_READ_UNAVAILABLE") from None
    if p.returncode or len(p.stdout) > 12_000_000:
        raise Stop("SOURCE_READ_FAILED")
    if not json_result:
        return p.stdout
    try:
        return json.loads(p.stdout)
    except (ValueError, UnicodeDecodeError):
        raise Stop("SOURCE_JSON_INVALID") from None

def inventory():
    if socket.gethostname().split(".")[0] != "v79sl":
        raise Stop("WRONG_HOST")
    if os.getenv("DOCKER_HOST") or os.getenv("DOCKER_CONTEXT"):
        raise Stop("REMOTE_DOCKER_REFUSED")
    contexts = command(["docker", "context", "inspect"], json_result=True)
    if len(contexts) != 1 or contexts[0].get("Endpoints", {}).get("docker", {}).get("Host") not in (
            "unix:///var/run/docker.sock", "unix:///run/docker.sock"):
        raise Stop("NONLOCAL_DOCKER")
    names = command(["docker", "ps", "-a", "--format", "{{.Names}}"]).decode().splitlines()
    if not names or len(names) > MAX_CONTAINERS or len(names) != len(set(names)):
        raise Stop("CONTAINER_BOUND")
    rows = command(["docker", "inspect", "--type", "container", *names], json_result=True)
    if len(rows) != len(names):
        raise Stop("CONTAINER_SET_CHANGED")
    by_name = {r.get("Name", "").lstrip("/"): r for r in rows}
    if set(by_name) != set(names):
        raise Stop("CONTAINER_SET_CHANGED")
    for name in PG_NAMES:
        row = by_name.get(name)
        if not row or row.get("State", {}).get("Status") != "running":
            raise Stop("POSTGRES_NOT_RUNNING")
    volumes = command(["docker", "volume", "ls", "--format", "{{.Name}}"]).decode().splitlines()
    if len(volumes) > MAX_VOLUMES or len(volumes) != len(set(volumes)):
        raise Stop("VOLUME_BOUND")
    volume_rows = command(["docker", "volume", "inspect", *volumes], json_result=True)
    if len(volume_rows) != len(volumes) or any(v.get("Driver") != "local" for v in volume_rows):
        raise Stop("VOLUME_DRIVER_OR_SET_CHANGED")
    active_pg_volumes = set()
    bind_sources = set()
    for name, row in by_name.items():
        for mount in row.get("Mounts") or []:
            source = mount.get("Source")
            if mount.get("Type") == "bind" and isinstance(source, str) and source.startswith("/"):
                if row.get("State", {}).get("Status") == "running" and not any(
                        source == p or source.startswith(p + "/") for p in BLOCKED_PREFIXES):
                    try:
                        if not Path(source).is_socket():
                            bind_sources.add(source)
                    except OSError:
                        raise Stop("BIND_SOURCE_UNAVAILABLE") from None
            if name in PG_NAMES and mount.get("Destination") == "/var/lib/postgresql/data":
                if mount.get("Type") != "volume" or mount.get("Name") not in volumes:
                    raise Stop("POSTGRES_STORAGE_UNEXPECTED")
                active_pg_volumes.add(mount["Name"])
    tar_image = by_name[TAR_IMAGE_FROM]["Image"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", tar_image):
        raise Stop("HELPER_IMAGE_INVALID")
    images = sorted(set(r["Image"] for r in rows))
    if any(not re.fullmatch(r"sha256:[0-9a-f]{64}", image) for image in images):
        raise Stop("IMAGE_ID_INVALID")
    dbs = {}
    for name in PG_NAMES:
        script = ('exec psql -U "${POSTGRES_USER:-postgres}" '
                  '-d "${POSTGRES_DB:-postgres}" -At -c '
                  '"SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate ORDER BY datname"')
        entries = command(["docker", "exec", name, "sh", "-ec", script]).decode().splitlines()
        if not entries or len(entries) > 30 or len(entries) != len(set(entries)) or any(
                not x or "\n" in x or "\r" in x for x in entries):
            raise Stop("DATABASE_LIST_INVALID")
        dbs[name] = entries
    identity = {
        "containers": sorted((name, r["Id"], r["Image"],
                              [(m.get("Type"), m.get("Source"), m.get("Name"), m.get("Destination"))
                               for m in r.get("Mounts") or []]) for name, r in by_name.items()),
        "volumes": sorted(volumes), "databases": dbs,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return by_name, volumes, active_pg_volumes, bind_sources, images, dbs, tar_image, digest

def items(volumes, active_pg_volumes, dbs):
    out = ["runtime-inspect", "host-files", "images"]
    for name in PG_NAMES:
        out.append("pg-globals:" + name)
        for index in range(len(dbs[name])):
            out.append("pg-db:" + name + ":" + str(index))
    out += ["volume:" + name for name in volumes if name not in active_pg_volumes]
    return out

def host_paths(bind_sources):
    roots = ["/etc", "/home", "/opt", "/root", "/boot", "/usr/local",
             "/var/spool/cron", "/var/lib/tailscale", "/var/lib/NetworkManager"]
    paths = [x for x in roots if Path(x).exists()]
    for source in sorted(bind_sources):
        if not any(source == root or source.startswith(root + "/") for root in roots):
            paths.append(source)
    # Avoid recursive mounts, sockets and sensitive virtual filesystems.
    result = []
    for path in paths:
        if any(path == p or path.startswith(p + "/") for p in BLOCKED_PREFIXES):
            continue
        if Path(path).is_socket():
            continue
        result.append(path.lstrip("/"))
    return sorted(set(result))

def helper(tar_image, mounts, paths):
    args = ["docker", "run", "--rm", "--pull", "never", "--network", "none",
            "--read-only", "--cap-drop", "ALL", "--cap-add", "DAC_READ_SEARCH",
            "--security-opt", "no-new-privileges", "--user", "0:0",
            "--pids-limit", "64", "--memory", "256m", "--cpus", "1"]
    for mount in mounts:
        args += ["--mount", mount]
    args += ["--entrypoint", "/bin/tar", tar_image, "-C", paths[0], "-cf", "-", *paths[1:]]
    return args

def stream(args):
    try:
        p = subprocess.run(args, stdout=sys.stdout.buffer, stderr=subprocess.DEVNULL,
                           timeout=3600, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("STREAM_UNAVAILABLE_OR_TIMEOUT") from None
    if p.returncode:
        raise Stop("STREAM_FAILED")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--stream", metavar="ITEM")
    parser.add_argument("--expected-baseline")
    args = parser.parse_args()
    if args.stream and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,150}", args.stream):
        raise Stop("ITEM_INVALID")
    by_name, volumes, pg_volumes, binds, images, dbs, tar_image, baseline = inventory()
    sources = items(volumes, pg_volumes, dbs)
    if args.plan:
        print(json.dumps({"schema": "v79-full-backup-source-20261027",
            "baseline_sha256": baseline, "items": sources,
            "containers": len(by_name), "volumes": len(volumes),
            "postgres_clusters": len(PG_NAMES),
            "active_postgres_data_volumes_excluded_from_raw_tar": len(pg_volumes),
            "host_bind_sources": len(binds), "production_changes": "NONE",
            "app_file_consistency": "NOT_PROVEN_BY_LIVE_COPY"}, sort_keys=True))
        return 0
    if args.expected_baseline != baseline or args.stream not in sources:
        raise Stop("BASELINE_OR_ITEM_CHANGED")
    item = args.stream
    if item == "runtime-inspect":
        payload = {"containers": list(by_name.values()),
                   "volumes": command(["docker", "volume", "inspect", *volumes], json_result=True),
                   "baseline_sha256": baseline}
        sys.stdout.buffer.write(json.dumps(payload, sort_keys=True).encode())
    elif item == "host-files":
        paths = host_paths(binds)
        if not paths:
            raise Stop("HOST_SOURCE_EMPTY")
        stream(helper(tar_image, ["type=bind,source=/,target=/host,readonly"],
                      ["/host", *paths]))
    elif item == "images":
        stream(["docker", "image", "save", *images])
    elif item.startswith("pg-globals:"):
        name = item.split(":", 1)[1]
        stream(["docker", "exec", name, "sh", "-ec",
                'exec pg_dumpall -U "${POSTGRES_USER:-postgres}" --globals-only'])
    elif item.startswith("pg-db:"):
        _, name, index = item.split(":")
        dbname = dbs[name][int(index)]
        stream(["docker", "exec", name, "sh", "-ec",
                'exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "$1" -Fc --no-owner --no-acl',
                "sh", dbname])
    elif item.startswith("volume:"):
        name = item.split(":", 1)[1]
        stream(helper(tar_image, ["type=volume,source=" + name + ",target=/source,readonly"],
                      ["/source", "."]))
    else:
        raise Stop("ITEM_UNSUPPORTED")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as exc:
        print("STOP=" + str(exc), file=sys.stderr)
        sys.exit(2)
    except Exception:
        print("STOP=REDACTED_SOURCE_FAILURE", file=sys.stderr)
        sys.exit(2)
