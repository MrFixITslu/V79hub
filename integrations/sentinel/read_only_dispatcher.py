"""G2 source-side GET authorization prototype. NOT an installed NOC route.

This is a pure request policy/dispatch object, NOT a network listener.
An eventual host must enforce transport TLS/mTLS/Tailscale identity, caller
provisioning and server-side organization binding. In-memory replay protection
is SINGLE-PROCESS ONLY and insufficient for a distributed production service.

Unlike the existing NOC's operator-cookie routes, it NEVER accepts browser
cookies/CSRF as machine authorization or exposes POST/write operations.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, Mapping, Any

from source_signer import (
    SentinelContractError, TrustedSourceSigner,
    aggregate_mission_snapshot, sign_aggregate_for_challenge,
)

READ_PATH = "/internal/sentinel/g2/mission-aggregate"
READ_DOMAIN = b"V79-SENTINEL-G2-GET-v1\n"
REQUIRED = frozenset((
    "X-V79-Read-Organization", "X-V79-Read-Key-Id",
    "X-V79-Read-Request-Id", "X-V79-Read-Issued-At",
    "X-V79-Read-Signature",
))
UUID_V4 = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$")
ISSUED_AT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


@dataclass(frozen=True)
class TrustedReadCaller:
    organization_id: str
    key_id: str
    shared_secret: bytes

    def __post_init__(self):
        if (not isinstance(self.organization_id, str) or
            not isinstance(self.key_id, str) or
            not isinstance(self.shared_secret, bytes) or
            len(self.shared_secret) < 32):
            raise SentinelContractError("Invalid trusted machine caller")


def read_mac_input(organization_id: str, key_id: str, request_id: str, issued_at: str) -> bytes:
    """Exact, domain-separated ASCII request signing material for GET only."""
    return READ_DOMAIN + "\n".join((
        "GET", READ_PATH, organization_id, key_id, request_id, issued_at,
    )).encode("ascii")


class IsolatedReadOnlySentinelDispatcher:
    """Authenticated read policy for one founder/org and a bounded replay map.

    The signer key, read caller secret and snapshot loader must be injected
    from an independently reviewed/trusted source, NEVER from client JSON.
    A caller-authenticated request is still not proof that Sentinel actually
    monitored any device: simulated-only readiness remains a separate gate.
    """
    def __init__(self, caller: TrustedReadCaller, signer: TrustedSourceSigner,
                 snapshot_loader: Callable[[], Mapping[str, Any]],
                 *, clock: Callable[[], datetime] | None = None):
        if caller.organization_id != signer.organization_id or caller.key_id != signer.key_id:
            raise SentinelContractError("Signer and read caller scope mismatch")
        self._caller = caller
        self._signer = signer
        self._snapshot_loader = snapshot_loader
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._used: dict[str, datetime] = {}
        self._mutex = Lock()

    def get(self, method: str, path: str, headers: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
        """Returns status and sanitized JSON; no cookies, no writes, no URLs."""
        if method != "GET" or path != READ_PATH:
            return 404, {"error": "Not found"}
        if not isinstance(headers, Mapping) or frozenset(headers) != REQUIRED:
            return 401, {"error": "Unauthorized"}
        org = headers["X-V79-Read-Organization"]
        key_id = headers["X-V79-Read-Key-Id"]
        req = headers["X-V79-Read-Request-Id"]
        time_text = headers["X-V79-Read-Issued-At"]
        mac = headers["X-V79-Read-Signature"]
        if (org != self._caller.organization_id or key_id != self._caller.key_id
            or not isinstance(req, str) or not UUID_V4.fullmatch(req)
            or not isinstance(time_text, str) or not ISSUED_AT.fullmatch(time_text)
            or not isinstance(mac, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", mac)):
            return 401, {"error": "Unauthorized"}
        try:
            issued = datetime.fromisoformat(time_text.replace("Z", "+00:00"))
            if issued.isoformat(timespec="milliseconds").replace("+00:00", "Z") != time_text:
                return 401, {"error": "Unauthorized"}
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() != timedelta(0):
                return 503, {"error": "Read temporarily unavailable"}
            if not -30 <= (now - issued).total_seconds() <= 60:
                return 401, {"error": "Unauthorized"}
            expected = hmac.new(
                self._caller.shared_secret,
                read_mac_input(org, key_id, req, time_text),
                hashlib.sha256,
            ).digest()
            presented = base64.urlsafe_b64decode(mac + "=")
            if not hmac.compare_digest(expected, presented):
                return 401, {"error": "Unauthorized"}
        except (ValueError, UnicodeError, TypeError, OverflowError):
            return 401, {"error": "Unauthorized"}

        # Atomic in-process replay check; distributed persistence required later.
        with self._mutex:
            self._used = {
                k: seen for k, seen in self._used.items()
                if (now - seen).total_seconds() <= 90
            }
            if req in self._used or len(self._used) >= 128:
                return 409, {"error": "Duplicate or busy"}
            self._used[req] = now

        try:
            # The loader must point to a reviewed LOCAL projection; never
            # fetch an arbitrary URL or a model-provided data source.
            raw = self._snapshot_loader()
            aggregate = aggregate_mission_snapshot(raw, now=now)
            envelope = sign_aggregate_for_challenge(aggregate, {
                "requestId": req,
                "organizationId": org,
                "keyId": key_id,
            }, self._signer, now=now)
            return 200, envelope
        except (SentinelContractError, ValueError, TypeError, OSError, TimeoutError):
            return 503, {"error": "Read temporarily unavailable"}
