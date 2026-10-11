"""G2.9 readonly local NOC-to-aggregate projection; NO signing or transport.

Operator-invoked only. Uses an already reviewable local Python NOC module
through PYTHONPATH, invokes snapshot() once, never modifies the NOC, opens
no network listeners, provisions no machine identity and writes no files.
Report contains bounded counts and trust *denials*, never individual service
names, IPs, customer metadata, raw timestamps, QA/packet data or exceptions.

The returned "reportedMode" is a LABEL, not proof of a live Edge collector.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from source_signer import aggregate_mission_snapshot, SentinelContractError

_STATES = ("up", "down", "degraded", "unknown")


def project_local_snapshot(raw: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Accept only the strict local source shape; return sanitized metadata."""
    aggregate = aggregate_mission_snapshot(
        raw,
        now=now if now is not None else datetime.now(timezone.utc),
    )
    counts = aggregate["counts"]
    return {
        "schemaVersion": 1,
        "status": "local_projection_valid",
        "reportedMode": aggregate["monitorMode"],
        "reportedSourceType": aggregate["source"],
        "counts": {
            "servicesObserved": counts["servicesObserved"],
            **{state: counts[state] for state in _STATES},
        },
        "utcObservationNormalized": aggregate["observedAt"].endswith("Z"),
        "sourceAuthenticated": False,
        "collectorVerified": False,
        "edgeDevicesVerified": False,
        "trustedForExecutiveUse": False,
        "productionReady": False,
        "note": "Read-only projection of unverified NOC observations; no private records exposed.",
    }


def main() -> int:
    try:
        # No browser session, HTTP proxy, DB connection, service startup,
        # signer key or file rewrite. Owner has separately reviewed the bridge.
        from sentinel_mission_bridge import snapshot
        report = project_local_snapshot(snapshot())
        ok = True
    except Exception:
        # Do not emit tracebacks/exceptions containing sensitive NOC details.
        report = {
            "schemaVersion": 1,
            "status": "local_projection_unavailable",
            "sourceAuthenticated": False,
            "collectorVerified": False,
            "trustedForExecutiveUse": False,
            "productionReady": False,
        }
        ok = False
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
