#!/usr/bin/env python3
"""No-write G1.2 backup prerequisites. Reports only allowlisted facts, never secrets.

Preflight does NOT back up, decrypt, start containers, or approve any release.
Designed for the live v79sl host after the exact-image WiPay metadata audit.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

ROOT = Path("/opt/v79/hub")
PIN = ROOT / "releases/wipay-return-585f701.pinned.yml"
EXPECTED_PIN_SHA256 = "8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74"
IMAGES = {
    "v79-hub": "sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30",
    "v79-hub-postgres": "sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
    "v79-business-agent": "sha256:ff64a76651a2b784474f5d7430d0d78515bc7b46b2d0d1f81c51c79958ef417b",
    "v79-tiquet-manager": "sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b",
}

def call(args, timeout=12):
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None

def inspect(name):
    result = call(["docker", "inspect", name])
    if result is None or result.returncode:
        return None
    try:
        return json.loads(result.stdout)[0]
    except (ValueError, IndexError, TypeError):
        return None

def mounts(obj):
    """Destination/volume metadata only; never leak host source paths."""
    return [
        {"type": m.get("Type"), "destination": m.get("Destination"),
         "namedVolume": m.get("Type") == "volume",
         "volumeName": m.get("Name") if m.get("Type") == "volume" else None,
         "writable": bool(m.get("RW"))}
        for m in sorted(obj.get("Mounts") or [], key=lambda x: str(x.get("Destination", "")))
        if str(m.get("Destination", "")).startswith(("/app/", "/var/lib/postgresql", "/run/secrets"))
    ]

def pg_ready(name):
    # Runs ONLY pg_isready, pg_dump --version and pg_restore --version.
    # Never prints or passes POSTGRES_PASSWORD to the host process arguments.
    script = (
        'set -eu; '
        'command -v pg_dump >/dev/null; command -v pg_restore >/dev/null; '
        'pg_isready -q -U "${POSTGRES_USER:-postgres}" '
        '-d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}"'
    )
    result = call(["docker", "exec", name, "sh", "-c", script])
    return result is not None and result.returncode == 0

def containers():
    ps = call(["docker", "ps", "--format", "{{.Names}}"])
    return [] if ps is None or ps.returncode else [s.strip() for s in ps.stdout.splitlines() if s.strip()]

def summarize():
    if socket.gethostname().split(".")[0] != "v79sl":
        raise RuntimeError("STOP: host is not v79sl")
    actual_pin = None
    try:
        if PIN.is_file() and not PIN.is_symlink():
            actual_pin = hashlib.sha256(PIN.read_bytes()).hexdigest()
    except OSError:
        pass
    live = {}
    for name, digest in IMAGES.items():
        meta = inspect(name)
        if not meta:
            live[name] = {"present": False}
            continue
        state = meta.get("State") or {}
        labels = (meta.get("Config") or {}).get("Labels") or {}
        live[name] = {
            "present": True,
            "running": state.get("Status") == "running",
            "healthy": (state.get("Health") or {}).get("Status") == "healthy",
            "imageMatchesPinnedBaseline": meta.get("Image") == digest,
            "composeProject": labels.get("com.docker.compose.project"),
            "mounts": mounts(meta),
        }
    candidates = []
    for name in containers():
        meta = inspect(name)
        if not meta:
            continue
        config = meta.get("Config") or {}
        labels = config.get("Labels") or {}
        project = labels.get("com.docker.compose.project")
        if project != "v79tiquet":
            continue
        service = (labels.get("com.docker.compose.service") or "").lower()
        image = str(config.get("Image") or "").lower()
        if "postgres" not in service and "postgres" not in image:
            continue
        state = meta.get("State") or {}
        candidates.append({
            "container": name,
            "running": state.get("Status") == "running",
            "pgDumpAndPgRestoreAvailable": pg_ready(name),
            "mounts": mounts(meta),
        })
    disk = {}
    for label, path in [("hub", ROOT), ("home", Path("/home/firelion"))]:
        try:
            free = shutil.disk_usage(path)
            disk[label] = {"freeGiB": round(free.free / (1024 ** 3), 1)}
        except OSError:
            disk[label] = {"freeGiB": None}
    tools = {name: shutil.which(name) is not None
             for name in ("age", "gpg", "openssl", "tar", "sha256sum", "docker")}
    hub = live.get("v79-hub", {})
    pg = live.get("v79-hub-postgres", {})
    agent = live.get("v79-business-agent", {})
    tiquet = live.get("v79-tiquet-manager", {})
    checks = {
        "pinnedComposeHashMatched": actual_pin == EXPECTED_PIN_SHA256,
        "fourLiveContainersHealthyAndUnchanged": all(
            item.get("running") and item.get("healthy") and item.get("imageMatchesPinnedBaseline")
            for item in (hub, pg, agent, tiquet)),
        "hubPostgresExportToolsReady": pg_ready("v79-hub-postgres"),
        "exactlyOneHealthyTiquetPostgresIdentified":
            len(candidates) == 1 and candidates[0]["running"] and candidates[0]["pgDumpAndPgRestoreAvailable"],
        "strongEncryptionToolAvailable": tools["age"] or tools["gpg"],
        "hasHashAndArchiveTools": tools["sha256sum"] and tools["tar"],
    }
    return {
        "purpose": "G1.2 READ ONLY ENCRYPTED RECOVERY PREREQUISITES",
        "modifiesState": False,
        "releaseApproved": False,
        "backupWritten": False,
        "restoreVerified": False,
        "pinHashMatches": checks["pinnedComposeHashMatched"],
        "containers": live,
        "tiquetPostgresCandidates": candidates,
        "disk": disk,
        "toolAvailability": tools,
        "checks": checks,
        "prerequisitesReadyForSeparatelyReviewedBackup": all(checks.values()),
        "nextGate": "encrypted full state snapshot plus isolated app/DB/key restore and immutable pinned rollback",
    }

if __name__ == "__main__":
    try:
        print(json.dumps(summarize(), sort_keys=True, indent=2))
    except Exception as exc:
        # Do not emit process stderr or environment values from a failed probe.
        print(json.dumps({"error": type(exc).__name__, "noWrites": True, "releaseApproved": False}))
        sys.exit(2)
    # This program NEVER self-certifies readiness or performs backup/restore.
    sys.exit(3)
