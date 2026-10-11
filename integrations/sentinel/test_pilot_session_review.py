"""No-network synthetic tests for G2.15 witnessed session evidence checks."""
from __future__ import annotations

import ast
import copy
import json
import unittest
from pathlib import Path

from pilot_session_review import InconsistentPilotEvidence, review_owner_pilot

OBSERVED_MS = [3, 7, 6, 4, 5, 6, 5, 6, 6, 4, 6, 8, 5, 2, 3]


def samples():
    return [
        {"elapsedMs": ms, "outcome": "tcp-open", "sampleNumber": n}
        for n, ms in enumerate(OBSERVED_MS, start=1)
    ]


def summary():
    return {
        "additionalProbesAuthorized": False, "attemptsExecuted": 15,
        "cadenceSeconds": 60, "continuousMonitoringEnabled": False,
        "durationSeconds": 900, "independentlyAuthenticatedCollector": False,
        "maxAttempts": 15, "meanTcpConnectMs": 5.1,
        "outcomes": {"connection-failed": 0, "refused": 0,
                     "tcp-open": 15, "timeout": 0},
        "port": 443, "productionReady": False,
        "scheduledSlotsSkipped": 0, "schemaVersion": 1,
        "source": "owner_acer_operator_run",
        "status": "bounded_one_time_pilot_finished",
        "target": "192.168.100.163", "tlsOrHttpVerified": False,
        "trustedForExecutiveUse": False,
    }


class OwnerCompletedSessionReviewTests(unittest.TestCase):
    def test_actual_report_shape_and_math_are_consistent(self):
        result = review_owner_pilot(samples(), summary())
        self.assertEqual(result["status"], "owner_pilot_evidence_consistent")
        self.assertEqual(result["tcpOpenReported"], 15)
        self.assertEqual(result["tcpFailedReported"], 0)
        self.assertEqual(result["meanConnectMsReported"], 5.1)
        self.assertEqual(result["minimumConnectMsReported"], 2)
        self.assertEqual(result["maximumConnectMsReported"], 8)
        self.assertTrue(result["allObservedConnectionsOpen"])
        for key in ("sampleCadenceIndependentlyVerified", "serverIdentityVerified",
                    "httpTlsVerified", "signedTelemetryVerified",
                    "collectorActiveVerified", "furtherProbeAuthorization",
                    "ongoingMonitoringAuthorized", "trustedForExecutiveUse",
                    "productionReady"):
            self.assertFalse(result[key])

    def test_no_private_target_or_vantage_in_aggregate(self):
        result = review_owner_pilot(samples(), summary())
        serialized = json.dumps(result)
        for sensitive in ("192.168.100.163", "owner_acer", "firelion", "v79sl", "private-host"):
            self.assertNotIn(sensitive, serialized)

    def test_refuse_any_changed_pilot_scope(self):
        for field, value in (
            ("target", "192.168.100.162"), ("port", 80),
            ("port", "443"), ("port", True), ("cadenceSeconds", 30),
            ("durationSeconds", 1800), ("maxAttempts", 30),
            ("source", "authenticated-collector"), ("status", "monitoring-enabled"),
            ("schemaVersion", True),
        ):
            changed = summary()
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(InconsistentPilotEvidence):
                review_owner_pilot(samples(), changed)

    def test_rejects_false_trust_or_more_authorization(self):
        for name in ("additionalProbesAuthorized", "continuousMonitoringEnabled",
                     "tlsOrHttpVerified", "independentlyAuthenticatedCollector",
                     "trustedForExecutiveUse", "productionReady"):
            changed = summary()
            changed[name] = True
            with self.subTest(field=name), self.assertRaises(InconsistentPilotEvidence):
                review_owner_pilot(samples(), changed)

    def test_refuse_missing_duplicate_extra_reordered_and_injected_samples(self):
        cases = [
            samples()[:-1], samples() + samples()[-1:],
            samples()[::-1], samples()[:14] + [samples()[13]],
            samples()[:14] + [{**samples()[14], "secret": "private"}],
            samples()[:14] + [{**samples()[14], "elapsedMs": True}],
            samples()[:14] + [{**samples()[14], "outcome": "live-monitoring"}],
        ]
        for records in cases:
            with self.subTest(length=len(records)), self.assertRaises(InconsistentPilotEvidence):
                review_owner_pilot(records, summary())

    def test_refuse_wrong_summary_or_false_math(self):
        changed = [
            {"attemptsExecuted": 14}, {"scheduledSlotsSkipped": 1},
            {"meanTcpConnectMs": 6.5},
            {"meanTcpConnectMs": True},
            {"outcomes": {"tcp-open": 15}},
            {"outcomes": {"connection-failed": 0, "refused": 0,
                          "tcp-open": 14, "timeout": 0}},
            {"collectorEnabled": True},
        ]
        for patch in changed:
            altered = {**summary(), **patch}
            with self.subTest(patch=str(patch)[:30]), self.assertRaises(InconsistentPilotEvidence):
                review_owner_pilot(samples(), altered)

    def test_one_failed_connection_is_reported_not_transformed_into_up(self):
        items = samples()
        items[7]["outcome"] = "timeout"
        report = summary()
        report["outcomes"] = {**report["outcomes"], "tcp-open": 14, "timeout": 1}
        outcome = review_owner_pilot(items, report)
        self.assertEqual(outcome["tcpFailedReported"], 1)
        self.assertFalse(outcome["allObservedConnectionsOpen"])
        self.assertFalse(outcome["trustedForExecutiveUse"])

    def test_strictly_no_network_or_mutating_procedures(self):
        text = Path(__file__).with_name("pilot_session_review.py").read_text()
        module = ast.parse(text)
        imports = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                imports.update(x.name for x in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        for banned in ("socket", "requests", "urllib", "subprocess", "asyncio", "scapy"):
            self.assertNotIn(banned, imports)
        for forbidden in ("connect_ex(", "getaddrinfo(", "write_text(", "write_bytes(", "Popen(", "dumpcap", "tshark"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
