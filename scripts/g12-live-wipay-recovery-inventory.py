#!/usr/bin/env python3
"""Read-only V79 release evidence inventory. Never emits env values or secret contents.

Purpose: determine whether the pinned WiPay release could be overwritten,
identify the protected runtime code fingerprints, and locate recovery evidence.
A successful inspection is NOT authorization to deploy or proof of restorability.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path("/opt/v79/hub")
PIN = ROOT / "releases/wipay-return-585f701.pinned.yml"
EXPECTED_PIN_SHA256 = "8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74"
SERVICES = ("v79-hub", "v79-hub-postgres", "v79-business-agent", "v79-tiquet-manager")
ALLOWED_CODE = (
    "server/sentinel-qa-routes.mjs",
    "server/sentinel-qa-cleanup.mjs",
    "server/sentinel-write-fence.mjs",
    "server/sentinel-audit-retention.mjs",
    "server/agent-approval-ledger.mjs",
    "server/agent-evidence-attestation.mjs",
    "server/agent-proposal-inbox.mjs",
    "server/agent-reviewed-handoff.mjs",
    "server/agent-supervised-tiquet.mjs",
    "server/agent-supervised-marketing.mjs",
    "server/agent-approval-audit-chain.mjs",
    "server/tiquet-signed-source-reader.mjs",
    "server.ts",
)
AGENT_CODE = (
    "src/index.ts",
    "src/evidence.ts",
    "src/workforce.ts",
    "src/executive-workforce.ts",
    "src/executive-handoff.ts",
    "src/executive-cycle.ts",
    "src/ollama-executive.ts",
)



def run(args, *, timeout=20, cwd=None):
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout,
                              cwd=cwd, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            h.update(block)
    return h.hexdigest()

def image_metadata(name):
    proc = run(["docker", "inspect", name])
    if proc is None or proc.returncode:
        return {"present": False}
    try:
        item = json.loads(proc.stdout)[0]
    except (ValueError, IndexError, TypeError):
        return {"present": False}
    state = item.get("State") or {}
    config = item.get("Config") or {}
    host = item.get("HostConfig") or {}
    labels = config.get("Labels") or {}
    return {
        "present": True,
        "state": state.get("Status"),
        "health": (state.get("Health") or {}).get("Status", "not_configured"),
        "image_id": item.get("Image"),
        "image_name": config.get("Image"),
        "runtime_user": config.get("User") or "image_default",
        "read_only_root": host.get("ReadonlyRootfs"),
        "privileged": host.get("Privileged"),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_files": labels.get("com.docker.compose.project.config_files"),
        "network_names": sorted((item.get("NetworkSettings") or {}).get("Networks") or {}),
    }

def code_fingerprints(name, paths=ALLOWED_CODE):
    # Allowlisted application code files only; no secrets, DBs or user records.
    # Returns Git-compatible SHA1 blob IDs (not plain SHA1 file hashes).
    script = """
const fs=require('node:fs'), crypto=require('node:crypto');
const paths=JSON.parse(process.argv[1]); const out={};
for(const path of paths){
 try {
  const bytes=fs.readFileSync('/app/'+path);
  const blob=Buffer.concat([Buffer.from('blob '+bytes.length+'\\0'),bytes]);
  out[path]={state:'present',git_blob_sha1:crypto.createHash('sha1').update(blob).digest('hex')};
 } catch { out[path]={state:'missing_or_unreadable'}; }
}
process.stdout.write(JSON.stringify(out));
"""
    proc = run(["docker", "exec", name, "node", "-e", script, json.dumps(paths)])
    if proc is None or proc.returncode:
        return {"status": "unavailable"}
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {"status": "unavailable"}

def compose_shape():
    # docker compose config may contain resolved credentials in stdout.
    # Parse in memory; never print raw output or stderr.
    args = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"),
            "-f", str(PIN), "config", "--format", "json"]
    proc = run(args, cwd=ROOT, timeout=40)
    if proc is None or proc.returncode:
        return {"status": "unverified"}
    try:
        conf = json.loads(proc.stdout)
        services = conf.get("services") or {}
        hub = services.get("v79-hub") or {}
        agent = services.get("v79-business-agent") or {}
        return {
            "status": "parsed",
            "service_names": sorted(services),
            "hub_uses_image": isinstance(hub.get("image"), str),
            "hub_uses_build": bool(hub.get("build")),
            "agent_uses_image": isinstance(agent.get("image"), str),
            "agent_uses_build": bool(agent.get("build")),
        }
    except (ValueError, AttributeError, TypeError):
        return {"status": "unverified"}

def backup_metadata(directory):
    # Metadata only. Does not read archives, decrypt, prove integrity, or test restores.
    if not directory.is_dir():
        return {"directory_present": False}
    files = 0
    candidate_encrypted = 0
    candidate_plain = 0
    newest = None
    try:
        # Two levels only, bounded traversal; no names or contents emitted.
        for child in list(directory.iterdir())[:200]:
            walk = list(child.iterdir())[:200] if child.is_dir() else [child]
            for item in walk:
                if not item.is_file():
                    continue
                files += 1
                if item.suffix.lower() in (".age", ".gpg", ".enc"):
                    candidate_encrypted += 1
                elif item.suffix.lower() in (".gz", ".tar", ".zip", ".dump"):
                    candidate_plain += 1
                newest = max(newest or 0, item.stat().st_mtime)
    except (OSError, PermissionError):
        return {"directory_present": True, "readable": False}
    return {
        "directory_present": True,
        "metadata_readable": True,
        "files_sampled": files,
        "encrypted_extension_candidates": candidate_encrypted,
        "unencrypted_or_unknown_archive_extensions": candidate_plain,
        "newest_file_utc": dt.datetime.fromtimestamp(newest, dt.timezone.utc).isoformat() if newest else None,
        "restore_tested": False,
    }

def main():
    if socket.gethostname().split(".")[0] != "v79sl":
        sys.exit("STOP: only run on the v79sl server")
    out = {
        "purpose": "G1.2 LIVE RELEASE EVIDENCE INVENTORY / READ ONLY",
        "release_ready": False,
        "no_resources_modified": True,
        "containers": {name: image_metadata(name) for name in SERVICES},
        "running_hub_code_blobs": code_fingerprints("v79-hub"),
        "running_business_agent_code_blobs": code_fingerprints("v79-business-agent", AGENT_CODE),
        "pilot_business_agent_code_blobs": code_fingerprints("v79-g12-agent-pilot", AGENT_CODE),
        "pin": {
            "exists": PIN.is_file() and not PIN.is_symlink(),
            "expected_sha256": EXPECTED_PIN_SHA256,
        },
        "compose": compose_shape(),
        "backups": {
            "focused_launch_checkpoint": backup_metadata(Path("/home/firelion/v79-backups/focused-launch-checkpoint-20261010")),
            "release_128_archive_dir": backup_metadata(Path("/home/firelion/.v79-release-128-backups")),
        },
        "release_gates": {
            "full_encrypted_restore": "unverified",
            "wipay_preserving_cutover_and_rollback": "unverified",
            "independent_security_acceptance": "unverified",
            "exact_account_cleanup_targets": "unverified",
        },
    }
    if out["pin"]["exists"]:
        try:
            observed = sha256_file(PIN)
            out["pin"]["observed_sha256"] = observed
            out["pin"]["matches_preflight"] = observed == EXPECTED_PIN_SHA256
        except OSError:
            out["pin"]["matches_preflight"] = False
    else:
        out["pin"]["matches_preflight"] = False
    print(json.dumps(out, indent=2, sort_keys=True))
    if not out["pin"]["matches_preflight"]:
        return 2
    if any(not c["present"] or c["state"] != "running" or c["health"] != "healthy"
           for c in out["containers"].values()):
        return 2
    if out["compose"]["status"] != "parsed":
        return 2
    if any(out[key].get("status") == "unavailable" for key in
           ("running_hub_code_blobs", "running_business_agent_code_blobs")):
        return 2
    return 0  # Inspection succeeded; release_ready is always false.

if __name__ == "__main__":
    sys.exit(main())
