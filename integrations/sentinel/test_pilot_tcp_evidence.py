"""G2.13 no-network one-shot TCP evidence and simulated-source trust tests."""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from pilot_tcp_evidence import (
    ApprovedOneShotScope, PilotEvidenceError,
    classify_owner_tcp_report, classify_noc_collector_readiness,
)


def valid_report():
    return {
        "targetIPv4": "192.168.100.163", "tcpPort": 443,
        "vantageId": "owner-acer", "attempts": 1,
        "outcome": "tcp-open", "elapsedMs": 4,
        "observationChannel": "owner-pasted-terminal",
    }


SCOPE = ApprovedOneShotScope("192.168.100.163", 443, "owner-acer")


class WitnessEvidenceTests(unittest.TestCase):
    def test_exact_approved_one_shot_tcp_open_is_observation_only(self):
        result = classify_owner_tcp_report(valid_report(), SCOPE)
        self.assertEqual(result["outcomeReported"], "tcp-open")
        self.assertEqual(result["attemptsReported"], 1)
        self.assertEqual(result["elapsedMsReported"], 4)
        self.assertTrue(result["servicePortReachableReported"])
        self.assertTrue(result["targetMatchedPreviouslyApprovedScope"])
        for key in (
            "independentlyAuthenticated", "cryptographicallyAttested",
            "tlsOrHttpHealthVerified", "collectorActiveVerified",
            "networkInventoryVerified", "approvedForAdditionalChecks",
            "continuousMonitoringAuthorized", "trustedForExecutiveUse",
            "productionReady",
        ):
            self.assertFalse(result[key])

    def test_private_identifiers_not_exposed(self):
        output = json.dumps(classify_owner_tcp_report(valid_report(), SCOPE))
        for secret in ("192.168.100", "v79sl", "owner-acer", "443", "api_key", "private"):
            self.assertNotIn(secret, output)

    def test_changed_scope_never_authorizes_another_target_or_port(self):
        for patch in (
            {"targetIPv4": "192.168.100.162"},
            {"targetIPv4": "10.0.0.2"},
            {"tcpPort": 80},
            {"vantageId": "other"},
            {"attempts": 2},
            {"attempts": 0},
            {"attempts": True},
            {"observationChannel": "automated-collector"},
        ):
            report = {**valid_report(), **patch}
            with self.subTest(patch=patch), self.assertRaises(PilotEvidenceError):
                classify_owner_tcp_report(report, SCOPE)

    def test_rejects_unapproved_roles_and_public_hosts(self):
        for values in (
            ("8.8.8.8", 443, "owner-acer"),
            ("192.168.100.163", 0, "owner-acer"),
            ("192.168.100.163", 443, "customer-browser"),
            ("127.0.0.1", 443, "owner-acer"),
            ("192.168.100.163", True, "owner-acer"),
            ("192.168.100.163", 443, "owner-acer; command"),
        ):
            with self.subTest(values=values), self.assertRaises(PilotEvidenceError):
                ApprovedOneShotScope(*values)

    def test_rejects_extra_injected_authorization_fields(self):
        for patch in (
            {"approved": True}, {"collectorActive": True},
            {"enabled": True}, {"secret": "x"},
            {"continuousMonitoringAuthorized": True},
            {"targetIPv4": "https://example.net"},
            {"outcome": "network-fully-secure"},
            {"elapsedMs": 5000},
            {"elapsedMs": False},
            {"tcpPort": "443"},
        ):
            report = {**valid_report(), **patch}
            with self.subTest(patch=patch), self.assertRaises(PilotEvidenceError):
                classify_owner_tcp_report(report, SCOPE)

    def test_non_open_result_does_not_claim_reachable(self):
        for status in ("refused", "timeout", "failed"):
            report = {**valid_report(), "outcome": status}
            result = classify_owner_tcp_report(report, SCOPE)
            self.assertFalse(result["servicePortReachableReported"])
            self.assertFalse(result["collectorActiveVerified"])

    def test_all_readiness_variants_remain_unattested(self):
        reports = (
            ({"ready": True, "collector": "simulated-only", "integrations": "disabled"}, "simulation_confirmed"),
            ({"ready": True, "collector": "live", "integrations": "active"}, "collector_claim_unattested"),
            ({"ready": True, "collector": "active", "integrations": "enabled"}, "collector_claim_unattested"),
            ({"ready": False, "collector": "simulated-only", "integrations": "disabled"}, "not_verified"),
            ({"ready": True, "collector": "staging", "integrations": "disabled"}, "not_verified"),
            ({"ready": True, "collector": "live", "integrations": "active", "secret": "private"}, "unrecognized_readiness"),
            (None, "unrecognized_readiness"),
        )
        for original, expected in reports:
            with self.subTest(expected=expected):
                result = classify_noc_collector_readiness(original)
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["collectorActiveVerified"])
                self.assertFalse(result["trustedForExecutiveUse"])
                self.assertFalse(result["productionReady"])
                self.assertNotIn("private", json.dumps(result))

    def test_missing_scope_and_bad_payload_are_denied(self):
        for value in (None, "secret", [], {"targetIPv4": "192.168.100.163"}):
            with self.assertRaises(PilotEvidenceError):
                classify_owner_tcp_report(value, SCOPE)
        with self.assertRaises(PilotEvidenceError):
            classify_owner_tcp_report(valid_report(), valid_report())

    def test_source_cannot_actively_probe_or_persist_observations(self):
        code = Path(__file__).with_name("pilot_tcp_evidence.py").read_text()
        tree = ast.parse(code)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        for banned in ("socket", "subprocess", "urllib", "requests", "scapy", "asyncio"):
            self.assertNotIn(banned, imports)
        for banned in ("connect(", "getaddrinfo(", "write_text(", "write_bytes(", "dumpcap", "tshark"):
            self.assertNotIn(banned, code)


if __name__ == "__main__":
    unittest.main()
