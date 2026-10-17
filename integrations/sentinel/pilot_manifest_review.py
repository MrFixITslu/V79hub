"""G2.12 offline V79-owned pilot target manifest validation.

A valid manifest is a proposal only, NEVER authority to probe a device.
Only explicit owner-proposed RFC1918 IPv4 endpoints are accepted for review.
No network connections, pings, DNS, service discovery, packet capture,
secret storage, automatic device extraction, file writes or trust elevation.
IP addresses, host labels and device descriptions are never printed.
"""
from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path

MAX_INPUT_BYTES = 12_288
MAX_TARGETS = 3
_ALLOWED_RFC1918 = tuple(
    ipaddress.IPv4Network(net)
    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_ID = re.compile(r"^[a-z][a-z0-9-]{2,31}$")
_SCOPE = "v79-internal-pilot-review-only"
_PURPOSES = frozenset(("gateway-availability", "service-availability"))


class InvalidPilotManifest(ValueError):
    """Untrusted manifest input is never expanded into an active target."""


def _private_ipv4(value: object) -> str:
    if type(value) is not str or len(value) > 15:
        raise InvalidPilotManifest("Expected explicitly chosen private IPv4")
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise InvalidPilotManifest("Invalid target IPv4") from exc
    if (not isinstance(parsed, ipaddress.IPv4Address)
        or str(parsed) != value
        or not any(parsed in network for network in _ALLOWED_RFC1918)
        or parsed.is_multicast or parsed.is_loopback or parsed.is_unspecified):
        raise InvalidPilotManifest("Disallowed target IPv4")
    return value


def validate_pilot_manifest(manifest: object) -> dict:
    """Validate proposal shape and return NO addresses or authorization."""
    if type(manifest) is not dict or set(manifest) != {
        "schemaVersion", "scope", "collectionMode", "targets"
    }:
        raise InvalidPilotManifest("Unrecognized manifest schema")
    if (type(manifest["schemaVersion"]) is not int
        or manifest["schemaVersion"] != 1
        or manifest["scope"] != _SCOPE
        or manifest["collectionMode"] != "review-only"):
        raise InvalidPilotManifest("Unapproved manifest mode")
    targets = manifest["targets"]
    if type(targets) is not list or len(targets) > MAX_TARGETS:
        raise InvalidPilotManifest("Too many pilot targets")

    target_ids = set()
    endpoints = set()
    for entry in targets:
        if type(entry) is not dict or set(entry) != {
            "targetId", "ipv4", "tcpPort", "purpose"
        }:
            raise InvalidPilotManifest("Unexpected proposed target fields")
        target_id = entry["targetId"]
        if type(target_id) is not str or not _ID.fullmatch(target_id):
            raise InvalidPilotManifest("Invalid proposed target ID")
        address = _private_ipv4(entry["ipv4"])
        port = entry["tcpPort"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise InvalidPilotManifest("Invalid proposed TCP port")
        if type(entry["purpose"]) is not str or entry["purpose"] not in _PURPOSES:
            raise InvalidPilotManifest("Unexpected monitoring purpose")
        if target_id in target_ids or (address, port) in endpoints:
            raise InvalidPilotManifest("Duplicate pilot target")
        target_ids.add(target_id)
        endpoints.add((address, port))

    return {
        "schemaVersion": 1,
        "status": "pilot_manifest_reviewable" if targets else "pilot_manifest_empty",
        "scope": _SCOPE,
        "collectionMode": "review-only",
        "proposedTargets": len(targets),
        "approvedMonitoringTargets": 0,
        "ownershipIndependentlyVerified": False,
        "targetReachabilityVerified": False,
        "activeProbingAuthorized": False,
        "collectorEnabled": False,
        "trustedForExecutiveUse": False,
        "productionReady": False,
        "note": "Schema check only. V79 owner must independently attest ownership and approve exact targets before separate supervised tests.",
    }


def review_manifest_path(path: Path) -> dict:
    """Explicit local file only; never return raw data even on parse errors."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            raise InvalidPilotManifest("Invalid local review file")
        data = path.read_bytes()
        if len(data) > MAX_INPUT_BYTES:
            raise InvalidPilotManifest("Manifest too large")
        return validate_pilot_manifest(json.loads(data))
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as exc:
        raise InvalidPilotManifest("Pilot review unavailable") from exc


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise InvalidPilotManifest("One explicit local manifest path required")
        report = review_manifest_path(Path(sys.argv[1]).absolute())
        status = 0
    except Exception:
        report = {
            "schemaVersion": 1,
            "status": "pilot_manifest_invalid",
            "proposedTargets": 0,
            "approvedMonitoringTargets": 0,
            "activeProbingAuthorized": False,
            "collectorEnabled": False,
            "trustedForExecutiveUse": False,
            "productionReady": False,
        }
        status = 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
