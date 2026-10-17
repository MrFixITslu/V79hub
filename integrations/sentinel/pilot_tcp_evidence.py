"""G2.13 offline evidence classifier for an owner-witnessed ONE-SHOT TCP test.

This module NEVER opens sockets, reuses permission for another probe,
spawns processes, starts collectors, adds NOC routes or sends a Hub report.
A log submitted by a person is not independently authenticated telemetry.
The approved target scope must be supplied SEPARATELY, never taken as
authorization from client-supplied observation fields.

Only sanitized status + one-attempt timing are returned. Endpoint IPs,
identifiers, command output and secrets never appear in the summary.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Any


class PilotEvidenceError(ValueError):
    """Generic, safe rejection of untrusted pilot observation evidence."""


@dataclass(frozen=True)
class ApprovedOneShotScope:
    """Operator-granted one attempt; representation does not grant execution."""

    target_ipv4: str
    target_port: int
    vantage_id: str

    def __post_init__(self):
        if type(self.target_ipv4) is not str:
            raise PilotEvidenceError("Invalid pilot target")
        try:
            address = ipaddress.IPv4Address(self.target_ipv4)
        except ipaddress.AddressValueError as exc:
            raise PilotEvidenceError("Invalid pilot target") from exc
        if (str(address) != self.target_ipv4
            or not (address in ipaddress.IPv4Network("10.0.0.0/8")
                    or address in ipaddress.IPv4Network("172.16.0.0/12")
                    or address in ipaddress.IPv4Network("192.168.0.0/16"))
            or type(self.target_port) is not int
            or not 1 <= self.target_port <= 65535
            or type(self.vantage_id) is not str
            or self.vantage_id not in ("owner-acer",)):
            raise PilotEvidenceError("Unrecognized approved scope")


def classify_owner_tcp_report(report: Any, approval: ApprovedOneShotScope) -> dict:
    """Review a previously witnessed result; NO active target testing."""
    if type(approval) is not ApprovedOneShotScope:
        raise PilotEvidenceError("Separate approved scope required")
    if type(report) is not dict or set(report) != {
        "targetIPv4", "tcpPort", "vantageId", "attempts", "outcome",
        "elapsedMs", "observationChannel"
    }:
        raise PilotEvidenceError("Invalid observation fields")
    if (report["targetIPv4"] != approval.target_ipv4
        or report["tcpPort"] != approval.target_port
        or report["vantageId"] != approval.vantage_id
        or type(report["attempts"]) is not int
        or report["attempts"] != 1
        or report["observationChannel"] != "owner-pasted-terminal"
        or report["outcome"] not in ("tcp-open", "refused", "timeout", "failed")
        or type(report["elapsedMs"]) is not int
        or not 0 <= report["elapsedMs"] <= 3000):
        raise PilotEvidenceError("Report does not match one-shot approved scope")
    return {
        "schemaVersion": 1,
        "status": "owner_witnessed_one_time_tcp_result",
        "observationChannel": "owner-pasted-terminal",
        "attemptsReported": 1,
        "outcomeReported": report["outcome"],
        "elapsedMsReported": report["elapsedMs"],
        "servicePortReachableReported": report["outcome"] == "tcp-open",
        "targetMatchesSuppliedScope": True,
        "independentlyAuthenticated": False,
        "cryptographicallyAttested": False,
        "tlsOrHttpHealthVerified": False,
        "collectorActiveVerified": False,
        "networkInventoryVerified": False,
        "approvedForAdditionalChecks": False,
        "continuousMonitoringAuthorized": False,
        "trustedForExecutiveUse": False,
        "productionReady": False,
        "note": "Manual one-shot TCP result, not authenticated recurring Sentinel device evidence.",
    }


def classify_noc_collector_readiness(readiness: Any) -> dict:
    """Always prevent source self-labels from conferring collector trust."""
    if type(readiness) is not dict or set(readiness) != {
        "ready", "collector", "integrations"
    }:
        status = "unrecognized_readiness"
    elif readiness["ready"] is True and readiness["collector"] == "simulated-only":
        status = "simulation_confirmed"
    elif readiness["ready"] is True and readiness["collector"] in ("live", "active"):
        status = "collector_claim_unattested"
    else:
        status = "not_verified"
    return {
        "schemaVersion": 1,
        "status": status,
        "independentlyAuthenticated": False,
        "collectorActiveVerified": False,
        "trustedForExecutiveUse": False,
        "productionReady": False,
        "note": "Readiness self-report does not attest a live monitored device or collector.",
    }
