#!/usr/bin/env python3
"""P1-R1 evidence-only runtime contract; no backups, secret output or mutations.

Run on v79sl before authorizing an encrypted recovery snapshot. This program
does NOT establish a restorable backup, security signoff or customer beta GO.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
CORE = ("v79-hub", "v79-tiquet-manager", "v79-hub-postgres", "tiquet-postgres")
HUB_MFA = "V79_REQUIRE_ADMIN_MFA"
TIQUET_CHECK = "V79_ENTITLEMENT_RECHECK_ENABLED"
TIQUET_LEGACY = "V79_ALLOW_LEGACY_AUTH"


def docker_json(*args):
    result = subprocess.run(
        ["docker", *args], capture_output=True, check=False, timeout=25,
    )
    if result.returncode:
        raise RuntimeError("DOCKER_INSPECTION_FAILED")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("DOCKER_JSON_UNAVAILABLE") from None


def flags_from_env(rows):
    # Never return or print other environment variables.
    out = {}
    for value in rows:
        name, separator, setting = value.partition("=")
        if separator and name in (HUB_MFA, TIQUET_CHECK, TIQUET_LEGACY):
            out[name] = setting.lower()
    return out


def checked_files(csv_files, read_bytes):
    entries = csv_files.split(",") if csv_files else []
    if not entries or len(entries) > 40 or len(set(entries)) != len(entries):
        raise RuntimeError("COMPOSE_CHAIN_MISSING_DUPLICATE_OR_TOO_LONG")
    receipt = []
    for i, filename in enumerate(entries, 1):
        if not filename.startswith("/") or ".." in Path(filename).parts:
            raise RuntimeError("COMPOSE_PATH_NOT_ABSOLUTE")
        if os.path.islink(filename):
            raise RuntimeError("COMPOSE_SYMLINK_NOT_ALLOWED")
        try:
            file_stat = os.stat(filename, follow_symlinks=False)
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > 2_000_000:
                raise RuntimeError("COMPOSE_FILE_TYPE_OR_SIZE")
            digest = hashlib.sha256(read_bytes(filename)).hexdigest()
        except OSError:
            raise RuntimeError("COMPOSE_FILE_UNAVAILABLE") from None
        receipt.append({"index": i, "name": Path(filename).name, "sha256": digest})
    return receipt


def evaluate(rows, expected, image_present, read_bytes):
    if len(rows) != len(CORE):
        raise RuntimeError("CORE_CONTAINER_COUNT_MISMATCH")
    by_name = {str(c.get("Name", "")).lstrip("/"): c for c in rows}
    if set(by_name) != set(CORE):
        raise RuntimeError("CORE_CONTAINER_IDENTITY_MISMATCH")
    checks = {}
    for name in CORE:
        row = by_name[name]
        image = row.get("Image")
        state = row.get("State") or {}
        if not SHA.fullmatch(str(image)) or state.get("Status") != "running":
            raise RuntimeError("CORE_IMAGE_OR_RUNNING_STATUS_FAIL")
        health = (state.get("Health") or {}).get("Status")
        if health != "healthy":
            raise RuntimeError("CORE_HEALTH_NOT_VERIFIED")
        checks[name] = {"image": image, "health": health}
    for name in ("v79-hub", "v79-tiquet-manager"):
        if checks[name]["image"] != expected[name]:
            raise RuntimeError("LIVE_IMAGE_DRIFT_" + name.replace("-", "_").upper())
    hub = by_name["v79-hub"]
    tiquet = by_name["v79-tiquet-manager"]
    hf = flags_from_env((hub.get("Config") or {}).get("Env") or [])
    tf = flags_from_env((tiquet.get("Config") or {}).get("Env") or [])
    if hf.get(HUB_MFA) not in ("1", "true"):
        raise RuntimeError("HUB_MFA_NOT_ENABLED")
    if tf.get(TIQUET_CHECK) not in ("1", "true"):
        raise RuntimeError("TIQUET_ENTITLEMENT_RECHECK_NOT_ENABLED")
    if tf.get(TIQUET_LEGACY) not in ("0", "false"):
        raise RuntimeError("TIQUET_LEGACY_AUTH_NOT_DISABLED")
    labels = (hub.get("Config") or {}).get("Labels") or {}
    compose = checked_files(
        labels.get("com.docker.compose.project.config_files", ""), read_bytes
    )
    if not image_present(expected["v79-hub"]) or not image_present(expected["v79-tiquet-manager"]):
        raise RuntimeError("CURRENT_RELEASE_IMAGE_MISSING")
    # Absence of an app-data mount must be investigated; presence isn't proof of backup.
    mount_kinds = {}
    for name in ("v79-hub", "v79-tiquet-manager"):
        mount_kinds[name] = sorted(set(
            str(m.get("Type", "UNKNOWN")) + ":" + str(m.get("Destination", "UNKNOWN"))
            for m in (by_name[name].get("Mounts") or [])
        ))
    return {
        "audit": "V79_P1_R1_CURRENT_RELEASE_CONTRACT_V1",
        "mode": "READ_ONLY",
        "result": "PASS_CURRENT_RUNTIME_CONTRACT_ONLY",
        "core": checks,
        "compose_count": len(compose),
        "compose_ordered_sha256": compose,
        "app_mount_types_and_destinations": mount_kinds,
        "mfa": "ENABLED",
        "tiquet_entitlement_recheck": "ENABLED",
        "tiquet_legacy_auth": "DISABLED",
        "restore_verified": False,
        "offhost_recovery_verified": False,
        "customer_release_authorized": False,
        "production_mutations": "NONE",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expect-hub", required=True)
    p.add_argument("--expect-tiquet", required=True)
    opts = p.parse_args(argv)
    expected = {"v79-hub": opts.expect_hub, "v79-tiquet-manager": opts.expect_tiquet}
    if not all(SHA.fullmatch(value) for value in expected.values()):
        raise RuntimeError("EXPECTED_IMAGE_SHA_REQUIRED")
    if os.uname().nodename != "v79sl":
        raise RuntimeError("EXPECTED_V79SL_SERVER_ONLY")
    rows = docker_json("inspect", *CORE)
    result = evaluate(
        rows, expected,
        lambda image: bool(docker_json("image", "inspect", image)),
        lambda filename: Path(filename).read_bytes(),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        # Only allow controlled diagnostic codes, never raw Docker exceptions.
        msg = str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+", msg):
            msg = "AUDIT_FAILED_REDACTED"
        print("STOP=" + msg)
        sys.exit(1)
