#!/usr/bin/env python3
"""Read-only post-switch identity and exposure check. No environment secrets emitted."""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys

HUB = "sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
PREVIOUS = "sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
TIQUET = "sha256:b1ff48fcef3336ac6750dbdfae9df1aa85db0d3ed800804a88acc98519f1485f"
SOURCE = "114841271d4f8b9c4b63df6aedfd55bde2e82f40"
NAMES = ("v79-hub", "v79-tiquet-manager", "v79-hub-postgres", "tiquet-postgres",
         "v79sl_DOMAIN", "portainer", "pgadmin", "v79-sentinel-dell-noc")
FLAGS = ("V79_REQUIRE_ADMIN_MFA", "V79_SELF_SERVICE_SIGNUP", "WIPAY_ENV", "WIPAY_ENABLED")

def run(*args):
    try:
        p = subprocess.run(["docker", *args], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, check=False, timeout=15)
        if p.returncode or len(p.stdout) > 4_000_000:
            raise ValueError("DOCKER_READ_FAILED")
        return json.loads(p.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeDecodeError):
        raise ValueError("DOCKER_READ_FAILED") from None

def classified_flags(env):
    rows = dict(entry.split("=", 1) for entry in env if "=" in entry and entry.split("=", 1)[0] in FLAGS)
    def yesno(key):
        value = rows.get(key, "").lower()
        return "enabled" if value in ("1", "true") else "disabled" if value in ("0", "false") else "unverified"
    return {
        "admin_mfa": yesno("V79_REQUIRE_ADMIN_MFA"),
        "self_service_signup": yesno("V79_SELF_SERVICE_SIGNUP"),
        "wipay_enabled": yesno("WIPAY_ENABLED"),
        "wipay_mode": rows.get("WIPAY_ENV") if rows.get("WIPAY_ENV") in ("sandbox", "live") else "unverified",
    }

def bindings(row):
    out = []
    for private_port, entries in sorted((row.get("HostConfig") or {}).get("PortBindings", {}).items()):
        for entry in entries or []:
            address, port = entry.get("HostIp"), entry.get("HostPort")
            if address in ("", "0.0.0.0", "::"):
                scope = "all_interfaces"
            elif address in ("127.0.0.1", "::1"):
                scope = "loopback"
            else:
                scope = "specific_address_review"
            out.append({"container_port": private_port, "host_port": port, "bind_scope": scope})
    return out

def main():
    if socket.gethostname().split(".")[0] != "v79sl" or os.getenv("DOCKER_HOST") or os.getenv("DOCKER_CONTEXT"):
        raise ValueError("HOST_OR_CONTEXT_REFUSED")
    context = run("context", "inspect")
    if len(context) != 1 or context[0].get("Endpoints", {}).get("docker", {}).get("Host") not in (
            "unix:///var/run/docker.sock", "unix:///run/docker.sock"):
        raise ValueError("NONLOCAL_DOCKER")
    rows = run("inspect", "--type", "container", *NAMES)
    by_name = {row["Name"].lstrip("/"): row for row in rows}
    if set(by_name) != set(NAMES):
        raise ValueError("CONTAINER_SET_MISMATCH")
    hub = by_name["v79-hub"]
    image = run("image", "inspect", HUB)[0]
    revision = (image.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.revision")
    expected = {"v79-hub": HUB, "v79-tiquet-manager": TIQUET}
    core = {name: {"image_matches": by_name[name]["Image"] == sha,
                   "running": by_name[name]["State"]["Status"] == "running",
                   "healthy": by_name[name]["State"].get("Health", {}).get("Status") == "healthy"}
            for name, sha in expected.items()}
    for name in ("v79-hub-postgres", "tiquet-postgres"):
        core[name] = {"running": by_name[name]["State"]["Status"] == "running",
                      "healthy": by_name[name]["State"].get("Health", {}).get("Status") == "healthy"}
    try:
        previous_present = run("image", "inspect", PREVIOUS)[0]["Id"] == PREVIOUS
    except ValueError:
        previous_present = False
    compose_label = (hub.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project.config_files", "")
    result = {
        "schema": "v79-hub-postswitch-readonly-20261027",
        "core": core,
        "approved_source_revision_matches": revision == SOURCE,
        "hub_container_created_utc": hub.get("Created"),
        "hub_restart_count": hub.get("RestartCount"),
        "hub_runtime_flags": classified_flags(hub.get("Config", {}).get("Env") or []),
        "hub_compose_chain_fingerprint": hashlib.sha256(compose_label.encode()).hexdigest(),
        "prior_hub_image_locally_available": previous_present,
        "published_bindings": {name: bindings(by_name[name]) for name in NAMES[4:]},
        "firewall_effectiveness": "unverified",
        "mfa_and_sso_browser_acceptance": "unverified",
        "production_changes": "NONE",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({"production_changes": "NONE", "status": "HOLD", "reason": "READ_ONLY_CHECK_FAILED_REDACTED"}))
        sys.exit(2)
