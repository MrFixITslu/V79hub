"""G2.6 read-only Acer staging/source preflight.

NO network, listeners, secrets, sudo, process manipulation or file writes.
Never equate an isolated test success with a deployable Sentinel read service.
Outputs bounded non-sensitive facts only, not source code or credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SENTINEL_SOURCE_RELATIVE = ("noc/server.py", "noc/sentinel_mission_bridge.py")
PROTOCOL_PATHS = (
    "integrations/sentinel/source_signer.py",
    "integrations/sentinel/read_only_dispatcher.py",
    "integrations/sentinel/loopback_http_fixture.py",
)
PROHIBITED_LIVE_ASSUMPTIONS = (
    "machine_key_provisioned",
    "private_transport_verified",
    "durable_replay_store_verified",
    "source_collector_verified",
    "tenant_mapping_verified",
    "actual_noc_route_mounted",
    "independent_security_reviewed",
)


def _git_head(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=4, check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and len(value) == 40 and all(
        ch in "0123456789abcdef" for ch in value
    ) else None


def _inside(source: Path, parent: Path) -> bool:
    try:
        source.relative_to(parent)
        return True
    except ValueError:
        return False


def assess(staging: Path, sentinel: Path, expected_staging_head: str) -> dict:
    staging = staging.resolve()
    sentinel = sentinel.resolve()
    head = _git_head(staging)
    head_matches = head == expected_staging_head and len(expected_staging_head) == 40
    sentinel_head = _git_head(sentinel)
    separate = staging != sentinel and not _inside(staging, sentinel) and not _inside(sentinel, staging)
    staging_source = all((staging / p).is_file() for p in PROTOCOL_PATHS)
    sentinel_source = all((sentinel / p).is_file() for p in SENTINEL_SOURCE_RELATIVE)
    # This preflight never queries running processes, collects network/device
    # data, or claims that the actual NOC runtime matches these source files.
    checked = bool(head_matches and sentinel_head and separate and staging_source and sentinel_source)
    return {
        "schemaVersion": 1,
        "result": "source_layout_verified" if checked else "needs_attention",
        "stagingHead": head[:12] if head else None,
        "stagingHeadMatchesExpected": head_matches,
        "sentinelHead": sentinel_head[:12] if sentinel_head else None,
        "sourceTreesSeparate": separate,
        "stagingProtocolFilesPresent": staging_source,
        "sentinelNocSourcePresent": sentinel_source,
        "isolatedStagingReadyForReview": checked,
        "trustedLiveCollectorVerified": False,
        "productionReady": False,
        "liveDeploymentAuthorized": False,
        "unverifiedLiveGates": list(PROHIBITED_LIVE_ASSUMPTIONS),
        "notes": "Read-only filesystem metadata, no runtime/network checks or source promotions.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only G2.6 source preflight")
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--sentinel", required=True, type=Path)
    parser.add_argument("--expected-staging-head", required=True)
    args = parser.parse_args()
    result = assess(args.staging, args.sentinel, args.expected_staging_head)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["isolatedStagingReadyForReview"] else 2


if __name__ == "__main__":
    sys.exit(main())
