"""Isolated G2 Sentinel aggregate producer prototype; NOT wired into NOC.

Requires cryptography. The owning NOC must enforce separate service identity,
tenant authorization and TLS before invoking sign_aggregate_for_challenge.
Never reuse browser operator cookies or the existing approval-check service.
No HTTP listener, background job, key provisioning or live Sentinel accesses.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SIGNING_DOMAIN = b"V79-SENTINEL-READ-G2-v1\n"
SOURCE = "local-mission-control"
SERVICE_STATES = ("up", "down", "degraded", "unknown")
RAW_FIELDS = frozenset(("source", "monitorMode", "lastCheck", "services", "qa"))
SERVICE_FIELDS = frozenset(("name", "state", "http", "latencyMs"))
AGGREGATE_FIELDS = frozenset(("schemaVersion", "source", "observedAt", "monitorMode", "counts"))
COUNT_FIELDS = frozenset(("servicesObserved", "up", "down", "degraded", "unknown"))
CHALLENGE_FIELDS = frozenset(("requestId", "organizationId", "keyId"))
MAX_SOURCE_CHARS = 32_000
TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$")
UUID_V4 = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


class SentinelContractError(ValueError):
    """Generic non-sensitive failure of an untrusted source/response."""


@dataclass(frozen=True)
class TrustedSourceSigner:
    key_id: str
    organization_id: str
    private_key: Ed25519PrivateKey

    def __post_init__(self) -> None:
        if (not isinstance(self.key_id, str) or not 1 <= len(self.key_id) <= 64
            or not IDENTIFIER.fullmatch(self.key_id)
            or not isinstance(self.organization_id, str)
            or not 6 <= len(self.organization_id) <= 96
            or not IDENTIFIER.fullmatch(self.organization_id)
            or not isinstance(self.private_key, Ed25519PrivateKey)):
            raise SentinelContractError("Invalid trusted signer configuration")


def _utc_ms(dt: datetime) -> str:
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise SentinelContractError("UTC timestamp required")
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 40 or not TIMESTAMP.fullmatch(value):
        raise SentinelContractError("Invalid monitoring timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise SentinelContractError("Invalid monitoring timestamp") from exc
    return dt


def aggregate_mission_snapshot(raw: object, *, now: datetime | None = None) -> dict[str, Any]:
    """Reduce actual NOC Mission Control bridge fields to bounded totals.

    SOURCE observation time is preserved; a local aggregate is NOT proof of
    real collection, publisher identity or a verified customer network.
    Service names, IPs, QA results and raw incident details are never copied.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(raw, dict) or frozenset(raw) != RAW_FIELDS:
        raise SentinelContractError("Malformed monitoring summary")
    if raw["source"] != SOURCE or raw["monitorMode"] not in ("live", "staging"):
        raise SentinelContractError("Unapproved monitoring source")
    services = raw["services"]
    if not isinstance(services, list) or not 1 <= len(services) <= 24:
        raise SentinelContractError("No bounded monitoring services available")
    if not isinstance(raw["qa"], dict):
        raise SentinelContractError("Malformed QA summary")
    try:
        raw_bytes = json.dumps(raw, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8")
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise SentinelContractError("Invalid monitoring summary") from exc
    if len(raw_bytes) > MAX_SOURCE_CHARS:
        raise SentinelContractError("Oversized monitoring summary")

    observed = _parse_utc(raw["lastCheck"])
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise SentinelContractError("Trusted UTC time required")
    age = (now - observed).total_seconds()
    if age > 900 or age < -120:
        raise SentinelContractError("Monitoring source is stale or future-dated")
    totals = {state: 0 for state in SERVICE_STATES}
    for service in services:
        if not isinstance(service, dict) or frozenset(service) != SERVICE_FIELDS:
            raise SentinelContractError("Unexpected raw service shape")
        name = service["name"]
        state = service["state"]
        code = service["http"]
        latency = service["latencyMs"]
        if (not isinstance(name, str) or len(name) > 65 or state not in SERVICE_STATES
            or (code is not None and (type(code) is not int or not 100 <= code <= 599))
            or (latency is not None and (type(latency) is not int or not 0 <= latency <= 120_000))):
            raise SentinelContractError("Invalid service observation")
        totals[state] += 1
    return {
        "schemaVersion": 1,
        "source": SOURCE,
        "observedAt": _utc_ms(observed),
        "monitorMode": raw["monitorMode"],
        "counts": {"servicesObserved": len(services), **totals},
    }


def sign_aggregate_for_challenge(
    aggregate: Mapping[str, Any],
    challenge: object,
    signer: TrustedSourceSigner,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Sign pre-aggregated service health for a service-authorized challenge.

    Caller MUST authenticate and tenant-bind machine requests first. This
    function does not perform that authorization or persistent replay tracking.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise SentinelContractError("Trusted UTC time required")
    if not isinstance(challenge, dict) or frozenset(challenge) != CHALLENGE_FIELDS:
        raise SentinelContractError("Invalid service challenge")
    if (challenge["organizationId"] != signer.organization_id
        or challenge["keyId"] != signer.key_id
        or not isinstance(challenge["requestId"], str)
        or not UUID_V4.fullmatch(challenge["requestId"])):
        raise SentinelContractError("Untrusted service challenge")

    if not isinstance(aggregate, dict) or frozenset(aggregate) != AGGREGATE_FIELDS:
        raise SentinelContractError("Unexpected aggregate keys")
    counts = aggregate["counts"]
    if (aggregate["schemaVersion"] != 1 or aggregate["source"] != SOURCE
        or aggregate["monitorMode"] not in ("live", "staging")
        or not isinstance(counts, dict) or frozenset(counts) != COUNT_FIELDS):
        raise SentinelContractError("Invalid aggregate contents")
    if not all(type(counts[k]) is int and 0 <= counts[k] <= 24 for k in COUNT_FIELDS):
        raise SentinelContractError("Invalid aggregate counts")
    if (counts["servicesObserved"] < 1
        or counts["servicesObserved"] != sum(counts[state] for state in SERVICE_STATES)):
        raise SentinelContractError("Inconsistent aggregate counts")
    observed = _parse_utc(aggregate["observedAt"])
    age = (now - observed).total_seconds()
    if age > 900 or age < -120:
        raise SentinelContractError("Aggregate no longer fresh")

    payload_json = json.dumps(aggregate, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(payload_json.encode("utf8")) > 32_000:
        raise SentinelContractError("Aggregate payload too large")

    issued_at = _utc_ms(now)
    expires_at = _utc_ms(now + timedelta(seconds=30))
    fields = [
        1, signer.key_id, signer.organization_id, challenge["requestId"],
        issued_at, expires_at, payload_json,
    ]
    signing_input = SIGNING_DOMAIN + json.dumps(fields, separators=(",", ":"), ensure_ascii=False).encode("utf8")
    signature = base64.urlsafe_b64encode(signer.private_key.sign(signing_input)).rstrip(b"=").decode("ascii")
    return {
        "schemaVersion": 1,
        "keyId": signer.key_id,
        "organizationId": signer.organization_id,
        "requestId": challenge["requestId"],
        "issuedAt": issued_at,
        "expiresAt": expires_at,
        "payloadJson": payload_json,
        "signature": signature,
    }
