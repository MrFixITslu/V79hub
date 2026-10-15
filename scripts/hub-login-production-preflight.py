#!/usr/bin/env python3
"""V79 Hub login-only production READ-ONLY runtime inventory.

No writes, deploys, network requests, container exec, build, pull, restarts,
environment-value disclosure, recovery mutation, or secret access.
Run on v79sl only; this output alone NEVER authorizes deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

EXPECTED_STACK = (
    "/opt/v79/hub/docker-compose.yml",
    "/opt/v79/hub/releases/wipay-return-585f701.pinned.yml",
)
SERVICES = ("v79-hub", "v79-hub-postgres", "v79-business-agent", "v79-tiquet-manager")
LOGIN_DESIGN_SEED_SHA = "21e19d3efc6584e32ba482dc51a902f2f6e16846"
RELEASE_BRANCH = "release/hub-login-only-20261015"


def safe_hash(path: str) -> str | None:
    f = Path(path)
    if not f.is_file() or f.is_symlink():
        return None
    # Only the known, non-secret pinned Docker Compose override is hashed.
    return hashlib.sha256(f.read_bytes()).hexdigest()


def docker_inspect(name: str) -> dict | None:
    r = subprocess.run(["docker", "inspect", "--type", "container", name], check=False,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12)
    if r.returncode:
        return None
    rows = json.loads(r.stdout)
    return rows[0] if isinstance(rows, list) and len(rows) == 1 else None


def service_entry(meta: dict | None) -> dict:
    if not meta:
        return {"present": False}
    cfg = meta.get("Config", {})
    labels = cfg.get("Labels") or {}
    state = meta.get("State") or {}
    health = state.get("Health") or {}
    # Avoid Config.Env, Mounts[].Source, HostConfig.Binds,
    # secrets, and the full Docker metadata; hashes of secrets are not useful here.
    return {
        "present": True,
        "image_id": meta.get("Image"),
        "status": state.get("Status"),
        "health": health.get("Status", "not_configured"),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "compose_files": labels.get("com.docker.compose.project.config_files"),
        "revision": labels.get("org.opencontainers.image.revision", ""),
        "mount_destinations": sorted(
            x.get("Destination", "") for x in meta.get("Mounts") or []
        ),
        "network_names": sorted((meta.get("NetworkSettings") or {}).get("Networks") or {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable safe output")
    a = parser.parse_args()

    checks = {}
    host_ok = socket.gethostname().split(".")[0] == "v79sl"
    checks["expected_host"] = host_ok
    if not host_ok:
        print("NO_GO: wrong host; no Docker inspection or files read", file=sys.stderr)
        return 3

    try:
        services = {name: service_entry(docker_inspect(name)) for name in SERVICES}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        print("NO_GO: Docker inventory unavailable; no changes made", file=sys.stderr)
        return 3

    hub = services["v79-hub"]
    db = services["v79-hub-postgres"]
    tiquet = services["v79-tiquet-manager"]
    agent = services["v79-business-agent"]
    current_stack = hub.get("compose_files") or ""
    checks["hub_running_healthy"] = hub.get("status") == "running" and hub.get("health") == "healthy"
    checks["hub_compose_project_preserved"] = hub.get("compose_project") == "v79-hub" and hub.get("compose_service") == "v79-hub"
    checks["exact_known_pinned_stack"] = current_stack == ",".join(EXPECTED_STACK)
    checks["pinned_override_present"] = bool(safe_hash(EXPECTED_STACK[1]))
    checks["hub_data_mount_present"] = "/app/data" in hub.get("mount_destinations", [])
    checks["database_running_healthy"] = db.get("status") == "running" and db.get("health") == "healthy"
    checks["agent_running_healthy"] = agent.get("status") == "running" and agent.get("health") == "healthy"
    checks["tiquet_running_healthy"] = tiquet.get("status") == "running" and tiquet.get("health") == "healthy"
    checks["tiquet_compose_separate"] = tiquet.get("compose_project") == "v79tiquet"
    checks["network_proxy_preserved"] = "proxy_network" in hub.get("network_names", [])
    checks["hub_internal_database_network_preserved"] = "hub_data_network" in hub.get("network_names", [])

    result = {
        "task": "hub_login_only_readonly_runtime_inventory",
        "login_design_seed_sha": LOGIN_DESIGN_SEED_SHA,
        "candidate_branch": RELEASE_BRANCH,
        "release_candidate_image_sha_must_be_verified_separately": True,
        "hostname": "v79sl",
        "service_fingerprints": services,
        "expected_pinned_override_sha256": safe_hash(EXPECTED_STACK[1]),
        "checks": checks,
        "all_inventory_checks_passed": all(checks.values()),
        "offhost_decryption_verified_here": False,
        "candidate_image_built_here": False,
        "restore_rehearsal_verified_here": False,
        "production_deployed_here": False,
        "release_gate": "NO_GO_PENDING_INDEPENDENT_RECOVERY_AND_IMAGE_EVIDENCE",
    }
    if a.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key, ok in checks.items():
            print(key + "=" + ("PASS" if ok else "NO_GO"))
        print("HUB_CURRENT_IMAGE_ID=" + str(hub.get("image_id") or "UNAVAILABLE"))
        print("HUB_PINNED_COMPOSE_SHA256=" + str(result["expected_pinned_override_sha256"] or "UNAVAILABLE"))
        print("RELEASE_GATE=" + result["release_gate"])
        print("NO PRODUCTION CHANGES PERFORMED")
    return 0 if all(checks.values()) else 3


if __name__ == "__main__":
    raise SystemExit(main())
