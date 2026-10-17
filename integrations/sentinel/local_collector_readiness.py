"""G2.9 local, read-only reported collector readiness probe.

The *only* HTTP target is the owner's loopback NOC readiness address.
No cookies, credentials, headers with identifiers, HTTP redirects or arbitrary
URLs. No writes, monitoring changes, route mounts or signer keys.

Self-reported readiness fields are NOT independent Edge collector attestation.
Only bounded allowlisted labels are printed; raw server bodies and exceptions
are never returned or logged.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

# Confirmed from owner's Acer process-to-port discovery on 2026-10-11:
# enterprise NOC checkout PID 259865 listens on loopback 8788;
# port 8787 belongs to a DIFFERENT legacy Sentinel sentinel.py service.
# Fixed local diagnostic destination, not a configurable proxy URL.
READY_URL = "http://127.0.0.1:8788/readyz"
ALLOWED_COLLECTOR = frozenset((
    "simulated-only", "disabled", "unavailable", "staging", "live", "active"
))
ALLOWED_INTEGRATIONS = frozenset((
    "disabled", "staging", "active", "enabled", "unavailable"
))
MAX_RESPONSE = 4096


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def _label(payload, name, allowlist):
    label = payload.get(name)
    return label if type(label) is str and label in allowlist else "unrecognized"


def classify_noc_readiness(payload: object) -> dict:
    """Sanitize a single local readiness response without asserting trust."""
    if not isinstance(payload, dict):
        return _unavailable()
    collector = _label(payload, "collector", ALLOWED_COLLECTOR)
    integrations = _label(payload, "integrations", ALLOWED_INTEGRATIONS)
    return {
        "schemaVersion": 1,
        "probeStatus": "readiness_report_observed",
        "reportedCollector": collector,
        "reportedIntegrations": integrations,
        "reportedSimulatedOnly": collector == "simulated-only",
        "sourceIdentityVerified": False,
        "independentCollectorVerified": False,
        "actualDevicesVerified": False,
        "readyForExecutiveUse": False,
        "productionReady": False,
        "note": "Self-reported localhost NOC readiness; not independent collection attestation.",
    }


def _unavailable() -> dict:
    return {
        "schemaVersion": 1,
        "probeStatus": "readiness_unavailable",
        "sourceIdentityVerified": False,
        "independentCollectorVerified": False,
        "readyForExecutiveUse": False,
        "productionReady": False,
    }


def check_local_readiness(*, opener=None) -> dict:
    """One bounded unauthenticated GET to fixed loopback /readyz, no redirect."""
    # Explicitly forbid environment HTTP proxies for loopback readiness.
    # No redirects or arbitrary hosts/ports are ever followed.
    opener = opener or build_opener(ProxyHandler({}), _NoRedirect)
    request = Request(
        READY_URL,
        method="GET",
        headers={"Accept": "application/json", "Cache-Control": "no-store"},
    )
    try:
        with opener.open(request, timeout=3) as response:
            if response.status != 200 or response.url != READY_URL:
                return _unavailable()
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                return _unavailable()
            return classify_noc_readiness(json.loads(raw))
    except (HTTPError, URLError, OSError, TimeoutError, ValueError,
            UnicodeError, TypeError, json.JSONDecodeError):
        return _unavailable()


def main() -> int:
    result = check_local_readiness()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["probeStatus"] == "readiness_report_observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
