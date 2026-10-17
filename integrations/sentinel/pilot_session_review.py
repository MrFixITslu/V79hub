"""G2.15 OFFLINE review of owner-pasted, bounded TCP pilot evidence.

Validates mathematical consistency and exact limits ONLY; cannot establish
authenticity, packet source, precise 60-second spacing, or unattended health.
No HTTP, sockets, raw traffic, probes, filesystem writes or NOC integration.
Never transforms a manual observation into attested collector telemetry.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

TARGET = "192.168.100.163"
PORT = 443
MAX_SAMPLES = 15
CADENCE = 60
WINDOW = 900
_ALLOWED_OUTCOMES = frozenset(("tcp-open", "refused", "timeout", "connection-failed"))
_SUMMARY_FIELDS = frozenset((
    "schemaVersion", "status", "source", "target", "port", "cadenceSeconds",
    "durationSeconds", "attemptsExecuted", "scheduledSlotsSkipped", "maxAttempts",
    "outcomes", "meanTcpConnectMs", "additionalProbesAuthorized",
    "continuousMonitoringEnabled", "tlsOrHttpVerified",
    "independentlyAuthenticatedCollector", "trustedForExecutiveUse", "productionReady",
))


class InconsistentPilotEvidence(ValueError):
    """Fail closed and keep caller-supplied private fields out of errors."""


def review_owner_pilot(samples: Any, reported_summary: Any) -> dict:
    """Check integrity of owner transcription, NOT independent attestation."""
    if (type(samples) is not list or type(reported_summary) is not dict
        or len(samples) > MAX_SAMPLES
        or set(reported_summary) != _SUMMARY_FIELDS):
        raise InconsistentPilotEvidence("Invalid pilot evidence shape")
    summary = reported_summary
    if (type(summary["schemaVersion"]) is not int or summary["schemaVersion"] != 1
        or summary["status"] != "bounded_one_time_pilot_finished"
        or summary["source"] != "owner_acer_operator_run"
        or summary["target"] != TARGET or type(summary["port"]) is not int
        or summary["port"] != PORT
        or type(summary["cadenceSeconds"]) is not int or summary["cadenceSeconds"] != CADENCE
        or type(summary["durationSeconds"]) is not int or summary["durationSeconds"] != WINDOW
        or type(summary["maxAttempts"]) is not int or summary["maxAttempts"] != MAX_SAMPLES):
        raise InconsistentPilotEvidence("Unexpected pilot scope")
    for name in (
        "additionalProbesAuthorized", "continuousMonitoringEnabled",
        "tlsOrHttpVerified", "independentlyAuthenticatedCollector",
        "trustedForExecutiveUse", "productionReady",
    ):
        if summary[name] is not False:
            raise InconsistentPilotEvidence("Unexpected monitoring trust assertion")
    attempts = summary["attemptsExecuted"]
    skipped = summary["scheduledSlotsSkipped"]
    if (type(attempts) is not int or type(skipped) is not int
        or not 0 <= attempts <= MAX_SAMPLES
        or not 0 <= skipped <= MAX_SAMPLES
        or attempts + skipped != MAX_SAMPLES
        or len(samples) != attempts):
        raise InconsistentPilotEvidence("Inconsistent attempt count")

    outcomes: Counter[str] = Counter()
    observed_ms = []
    last_sample = 0
    for sample in samples:
        if type(sample) is not dict or set(sample) != {
            "sampleNumber", "elapsedMs", "outcome"
        }:
            raise InconsistentPilotEvidence("Unexpected sample fields")
        number = sample["sampleNumber"]
        elapsed = sample["elapsedMs"]
        outcome = sample["outcome"]
        if (type(number) is not int or not last_sample < number <= MAX_SAMPLES
            or type(elapsed) is not int or not 0 <= elapsed <= 5000
            or type(outcome) is not str or outcome not in _ALLOWED_OUTCOMES):
            raise InconsistentPilotEvidence("Invalid sample")
        last_sample = number
        outcomes[outcome] += 1
        observed_ms.append(elapsed)
    if skipped == 0 and [s["sampleNumber"] for s in samples] != list(range(1, MAX_SAMPLES + 1)):
        raise InconsistentPilotEvidence("Unexpected sample sequence")
    reported = summary["outcomes"]
    if (type(reported) is not dict or set(reported) != _ALLOWED_OUTCOMES
        or any(type(v) is not int or v < 0 for v in reported.values())
        or any(reported[name] != outcomes[name] for name in _ALLOWED_OUTCOMES)):
        raise InconsistentPilotEvidence("Outcome totals do not match samples")
    actual_mean = round(sum(observed_ms) / attempts, 1) if attempts else None
    if (type(summary["meanTcpConnectMs"]) not in (float, int)
        if attempts else summary["meanTcpConnectMs"] is not None):
        raise InconsistentPilotEvidence("Invalid reported mean")
    if attempts and abs(summary["meanTcpConnectMs"] - actual_mean) > 0.05:
        raise InconsistentPilotEvidence("Reported mean does not match samples")

    return {
        "schemaVersion": 1,
        "status": "owner_pilot_evidence_consistent",
        "evidenceOrigin": "owner-pasted-terminal",
        "sampleCount": attempts,
        "scheduledSlotsReported": MAX_SAMPLES,
        "slotsSkippedReported": skipped,
        "tcpOpenReported": outcomes["tcp-open"],
        "tcpFailedReported": attempts - outcomes["tcp-open"],
        "meanConnectMsReported": actual_mean,
        "minimumConnectMsReported": min(observed_ms) if attempts else None,
        "maximumConnectMsReported": max(observed_ms) if attempts else None,
        "allObservedConnectionsOpen": attempts == MAX_SAMPLES and outcomes["tcp-open"] == attempts,
        "sampleCadenceIndependentlyVerified": False,
        "serverIdentityVerified": False,
        "httpTlsVerified": False,
        "signedTelemetryVerified": False,
        "collectorActiveVerified": False,
        "furtherProbeAuthorization": False,
        "ongoingMonitoringAuthorized": False,
        "trustedForExecutiveUse": False,
        "productionReady": False,
        "note": "Reported TCP attempts only; no independent timestamps, source attestation, or proof of availability between samples.",
    }
