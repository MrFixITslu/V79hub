"""Read-only G2 NOC contract compatibility probe; no source values exposed.

Pure inspect_source_contract(...) accepts only an already obtained local
Mission Control snapshot. Optional CLI imports the actual owner's NOC bridge
from a separately configured PYTHONPATH and invokes snapshot() once. Never
logs services, IPs, raw times, exceptions or QA contents. Does NOT prove
monitor mode or actual Edge/collector operation.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from source_signer import aggregate_mission_snapshot, SentinelContractError

_CANONICAL_STATES = ("up", "down", "degraded", "unknown")
_SOURCE_FIELDS = frozenset(("source", "monitorMode", "lastCheck", "services", "qa"))
_SERVICE_FIELDS = frozenset(("name", "state", "http", "latencyMs"))
_AWARE_OFFSET = re.compile(
    r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?[+-]\d\d:\d\d$"
)
_NAIVE_DATE = re.compile(
    r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?$"
)


def inspect_source_contract(raw: Any, now: datetime | None = None) -> dict[str, Any]:
    """Return only bounded counts/booleans; never reproduce input strings."""
    now = now or datetime.now(timezone.utc)
    fields_ok = isinstance(raw, dict) and frozenset(raw) == _SOURCE_FIELDS
    services = raw.get("services") if isinstance(raw, dict) else None
    services_ok = isinstance(services, list)
    count = len(services) if services_ok else 0
    bounded_count = min(count, 25)  # 25 is an overflow sentinel, not a device ID
    shape_ok = services_ok and all(
        isinstance(s, dict) and frozenset(s) == _SERVICE_FIELDS
        for s in services[:25]
    ) and count <= 24
    label = raw.get("monitorMode") if isinstance(raw, dict) else None
    mode = label if label in ("live", "staging") else "unrecognized"
    ts = raw.get("lastCheck") if isinstance(raw, dict) else None
    if not isinstance(ts, str):
        timestamp_kind = "non_string"
    elif ts.endswith("Z"):
        timestamp_kind = "zulu_suffix"
    elif _AWARE_OFFSET.fullmatch(ts):
        timestamp_kind = "explicit_offset"
    elif _NAIVE_DATE.fullmatch(ts):
        timestamp_kind = "naive_no_timezone"
    else:
        timestamp_kind = "unrecognized"
    counts = {key: 0 for key in _CANONICAL_STATES}
    if services_ok and count <= 24:
        for item in services:
            if not isinstance(item, dict):
                continue
            state = item.get("state")
            if state in _CANONICAL_STATES:
                counts[state] += 1
    compatible = False
    try:
        compatible = aggregate_mission_snapshot(raw, now=now)["schemaVersion"] == 1
    except (SentinelContractError, TypeError, ValueError, OverflowError):
        pass
    return {
        "schemaVersion": 1,
        "reportedMode": mode,
        "reportedServiceCount": bounded_count,
        "serviceCountOverLimit": count > 24,
        "stateCounts": counts,
        "timestampKind": timestamp_kind,
        "sourceFieldNamesMatch": fields_ok,
        "serviceFieldNamesMatch": bool(shape_ok),
        "qaShapePresent": isinstance(raw.get("qa"), dict) if isinstance(raw, dict) else False,
        "producerProjectionCompatible": compatible,
        "trustedLiveCollectorVerified": False,
        "sourceIdentityVerified": False,
        "readyForExecutiveUse": False,
        "productionReady": False,
        "note": "Unverified local NOC source shape only. No secrets or raw records printed.",
    }


def main() -> int:
    # Import actual NOC bridge only when explicitly invoked by an operator
    # with a separately configured PYTHONPATH. No server/service is started.
    try:
        from sentinel_mission_bridge import snapshot
        report = inspect_source_contract(snapshot())
    except Exception:
        # No tracebacks: source exceptions may embed site identifiers.
        report = {
            "schemaVersion": 1,
            "probeStatus": "source_unavailable",
            "readyForExecutiveUse": False,
            "productionReady": False,
        }
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report.get("producerProjectionCompatible", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())
