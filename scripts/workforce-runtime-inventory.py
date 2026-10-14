#!/usr/bin/env python3
"""Read-only G2 deployment inventory. No exec, source sync, keys or data capture."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys


def main():
    if socket.gethostname() != "v79sl":
        sys.exit("STOP: this inventory is only for v79sl")
    if not shutil.which("docker"):
        sys.exit("STOP: Docker is unavailable; nothing changed")
    names = ["v79-hub", "v79-business-agent", "v79-hub-postgres", "v79-tiquet-manager", "tiquet-postgres"]
    output = {"mode": "read-only", "deployment_performed": False, "containers": {}, "compose_files": []}
    files = set()
    for name in names:
        result = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=20, check=False)
        if result.returncode:
            output["containers"][name] = {"available": False}
            continue
        info = json.loads(result.stdout)[0]
        labels = info.get("Config", {}).get("Labels", {})
        listed = labels.get("com.docker.compose.project.config_files", "")
        for raw in listed.split(","):
            if raw:
                files.add(raw)
        output["containers"][name] = {
            "image_id": info.get("Image"),
            "running": info.get("State", {}).get("Running") is True,
            "health": info.get("State", {}).get("Health", {}).get("Status", "not_configured"),
            "project": labels.get("com.docker.compose.project"),
            "service": labels.get("com.docker.compose.service"),
            "compose_files": listed,
            "source_commit_label": labels.get("org.opencontainers.image.revision"),
            "workforce_enabled": "V79_WORKFORCE_ACTIONS_ENABLED=1" in info.get("Config", {}).get("Env", []),
        }
    for raw in sorted(files):
        p = Path(raw)
        if not p.is_absolute() or not str(p).startswith(("/opt/v79/", "/home/firelion/")) or p.suffix not in (".yml", ".yaml"):
            output["compose_files"].append({"path": raw, "inspected": False})
            continue
        if p.is_symlink() or not p.is_file():
            output["compose_files"].append({"path": raw, "inspected": False})
            continue
        st = p.stat()
        if st.st_size > 2 * 1024 * 1024:
            output["compose_files"].append({"path": raw, "inspected": False})
            continue
        output["compose_files"].append({"path": raw, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                       "mode": oct(st.st_mode & 0o777), "inspected": True})
    output["free_bytes"] = shutil.disk_usage("/opt/v79" if os.path.isdir("/opt/v79") else "/").free
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
