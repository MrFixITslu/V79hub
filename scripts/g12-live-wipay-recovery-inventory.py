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
GITHUB_REFERENCE_SHA = "7f84d276a90b8d426c0a2fe33ca652321aee8d88"
REFERENCE_BLOBS = {
    "server/sentinel-qa-routes.mjs": "96476be32773799b473220cfd51bea54c2b4e9ed",
    "server/sentinel-qa-cleanup.mjs": "ef4a648dc410dd84b8a32b99faec960e0b4863ae",
    "server/sentinel-write-fence.mjs": "b60bb6a1ad381074c7faf85734b3febe4f1b5795",
    "server/sentinel-audit-retention.mjs": "624e9ec7e28311f0a1e122169ba6208565d1e6ea",
    "server/agent-approval-ledger.mjs": "87961e5fcd925495b0d9474e3b3d287677147e59",
    "server/agent-evidence-attestation.mjs": "907f4da5edee6a1d0377245023f7190a7c244afa",
    "server/agent-proposal-inbox.mjs": "914620fded08002ff85e260df81c6ab034c11e69",
    "server/agent-reviewed-handoff.mjs": "5ba448e7b1256a07175c73e30dd15b28c744a37d",
    "server/agent-supervised-tiquet.mjs": "0eec3d1e9f2219d91bd390c7728aeb3e7a2dc2e6",
    "server/agent-supervised-marketing.mjs": "31ff2a72fe3519a6d31ff08750778038505d585d",
    "server/agent-approval-audit-chain.mjs": "62db000a5ffbc6ee7138adc4f0d0bcdbc71fe95a",
    "server/tiquet-signed-source-reader.mjs": "32e369e4c2bac83c33a3bb8add69ee35a522895e",
    "server.ts": "b69c46637970bd7dc95f3cf45f8a29fee5a10e3a",
    "src/index.ts": "638f43658812e8fb5b97f2575bc23faba6064d28",
    "src/evidence.ts": "a60bedd824bea173b1f4d10485189ed1c993c494",
    "src/workforce.ts": "e2fb6123a3bb9c3c4facfedadfea0ecb124448e6",
    "src/executive-workforce.ts": "5c0a4a4ed3cfeaa85f416157bd3f9392a566b8e9",
    "src/executive-handoff.ts": "b10ec2b3a4a117fbd54b14d56764e30d17c348fa",
    "src/executive-cycle.ts": "4af563d121d95e0affb14a51482ffd4fdc6c2616",
    "src/ollama-executive.ts": "04636f6b529e3edab02f6b351cfe4cf803ec5690",
}

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
        observed = json.loads(proc.stdout)
        for filepath in paths:
            entry = observed.get(filepath)
            if not isinstance(entry, dict):
                entry = {"state": "missing_or_unreadable"}
                observed[filepath] = entry
            expected = REFERENCE_BLOBS.get(filepath)
            entry["expected_git_blob_sha1"] = expected
            digest = entry.get("git_blob_sha1")
            entry["comparison"] = (
                "MATCH_REFERENCE" if digest == expected else
                "DIFFERENT_FROM_REFERENCE" if isinstance(digest, str) else
                "MISSING_OR_UNREADABLE"
            )
        return observed
    except (ValueError, TypeError, AttributeError):
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
        "github_comparison_sha": GITHUB_REFERENCE_SHA,
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
