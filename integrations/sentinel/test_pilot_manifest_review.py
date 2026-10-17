"""Isolated no-network tests for G2.12 offline proposed target review."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pilot_manifest_review import (
    InvalidPilotManifest, validate_pilot_manifest, review_manifest_path,
)


def sample(targets=None):
    return {
        "schemaVersion": 1,
        "scope": "v79-internal-pilot-review-only",
        "collectionMode": "review-only",
        "targets": list(targets or []),
    }


def target(name="v79-router", address="192.168.100.1", port=443,
           purpose="gateway-availability"):
    return {"targetId": name, "ipv4": address, "tcpPort": port, "purpose": purpose}


class PilotTargetReviewTests(unittest.TestCase):
    def test_empty_template_remains_unapproved(self):
        result = validate_pilot_manifest(sample())
        self.assertEqual(result["status"], "pilot_manifest_empty")
        self.assertEqual(result["proposedTargets"], 0)
        self.assertEqual(result["approvedMonitoringTargets"], 0)
        self.assertFalse(result["activeProbingAuthorized"])

    def test_three_private_proposals_are_not_authorized(self):
        rows = [
            target(),
            target("v79-server", "10.1.2.3", 80, "service-availability"),
            target("v79-workstation", "172.16.2.10", 8443, "service-availability"),
        ]
        result = validate_pilot_manifest(sample(rows))
        self.assertEqual(result["proposedTargets"], 3)
        self.assertEqual(result["approvedMonitoringTargets"], 0)
        for key in ("ownershipIndependentlyVerified", "targetReachabilityVerified",
                    "activeProbingAuthorized", "collectorEnabled",
                    "trustedForExecutiveUse", "productionReady"):
            self.assertFalse(result[key])
        text = json.dumps(result)
        for address in ("192.168.100.1", "10.1.2.3", "172.16.2.10"):
            self.assertNotIn(address, text)
        for name in ("v79-router", "v79-server", "v79-workstation"):
            self.assertNotIn(name, text)

    def test_rejects_wrong_network_scopes(self):
        addresses = (
            "8.8.8.8", "1.1.1.1", "127.0.0.1", "169.254.0.1",
            "0.0.0.0", "255.255.255.255", "2001:db8::1",
            "192.0.2.22", "198.51.100.5", "224.0.0.1",
            "192.168.100.1/24", "192.168.100.001", "",
            "192.168.100.1; curl example.com",
        )
        for address in addresses:
            with self.subTest(address=address), self.assertRaises(InvalidPilotManifest):
                validate_pilot_manifest(sample([target(address=address)]))

    def test_cannot_inject_urls_secrets_or_monitor_write_privileges(self):
        bad = (
            {**sample([target()]), "enablePolling": True},
            {**sample([target()]), "accessToken": "SECRET"},
            sample([{**target(), "credential": "SECRET"}]),
            sample([{**target(), "tcpPort": "443"}]),
            sample([{**target(), "tcpPort": True}]),
            sample([{**target(), "purpose": "packet-capture"}]),
            {**sample([target()]), "collectionMode": "active"},
            {**sample([target()]), "scope": "arbitrary-customer-network"},
        )
        for value in bad:
            with self.subTest(value=str(value)[:30]), self.assertRaises(InvalidPilotManifest):
                validate_pilot_manifest(value)

    def test_denies_duplicate_ids_and_endpoint_pairs(self):
        bad = (
            [target(), target("v79-router", "192.168.100.2", 443)],
            [target(), target("v79-second", "192.168.100.1", 443)],
        )
        for rows in bad:
            with self.assertRaises(InvalidPilotManifest):
                validate_pilot_manifest(sample(rows))

    def test_limits_to_three_and_checks_strict_identifiers(self):
        with self.assertRaises(InvalidPilotManifest):
            validate_pilot_manifest(sample([
                target(f"host-{n}", f"10.0.0.{n+1}") for n in range(4)
            ]))
        for name in ("a", "bad name", "../device", "💾", "UPPER", "device-" * 10):
            with self.subTest(name=name), self.assertRaises(InvalidPilotManifest):
                validate_pilot_manifest(sample([target(name=name)]))

    def test_requires_exact_schema_and_field_types(self):
        for invalid in (
            None, [], "private", {"schemaVersion": 1},
            {**sample(), "schemaVersion": True},
            {**sample(), "schemaVersion": "1"},
            {**sample(), "targets": None},
            sample([{"targetId": "missing-fields"}]),
        ):
            with self.subTest(value=str(invalid)[:30]), self.assertRaises(InvalidPilotManifest):
                validate_pilot_manifest(invalid)

    def test_reads_only_explicit_local_json_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pilot-proposed.json"
            p.write_text(json.dumps(sample([target()])), encoding="utf-8")
            result = review_manifest_path(p)
            self.assertEqual(result["proposedTargets"], 1)
            self.assertFalse(result["activeProbingAuthorized"])

    def test_symlink_large_and_invalid_json_never_print_sensitive_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pilot-proposed.json"
            link = Path(td) / "linked.json"
            path.write_text('{"private":"secret.example"}', encoding="utf-8")
            link.symlink_to(path)
            with self.assertRaisesRegex(InvalidPilotManifest, "^Pilot review unavailable$"):
                review_manifest_path(link)
            with self.assertRaises(InvalidPilotManifest):
                review_manifest_path(path)
            path.write_bytes(b"X" * 13000)
            with self.assertRaises(InvalidPilotManifest):
                review_manifest_path(path)

    def test_does_not_probe_or_promote_targets_in_source(self):
        source = Path(__file__).with_name("pilot_manifest_review.py").read_text()
        import ast
        module = ast.parse(source)
        imports = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        for forbidden in ("socket", "requests", "urllib", "subprocess", "scapy", "asyncio"):
            self.assertNotIn(forbidden, imports)
        self.assertNotIn("create_connection(", source)
        self.assertNotIn("connect(", source)
        self.assertNotIn("write_text(", source)
        self.assertNotIn("write_bytes(", source)


if __name__ == "__main__":
    unittest.main()
