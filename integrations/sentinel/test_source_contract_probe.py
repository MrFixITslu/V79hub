"""Synthetic-only safety tests for the local NOC source compatibility probe."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from source_contract_probe import inspect_source_contract

NOW = datetime(2026, 10, 10, 23, 40, tzinfo=timezone.utc)


def sample():
    return {
        "source": "local-mission-control",
        "monitorMode": "live",
        "lastCheck": "2026-10-10T23:39:40+00:00",
        "services": [
            {
                "name": "Sensitive family 10.99.0.1",
                "state": "up",
                "http": 200,
                "latencyMs": 12,
            },
            {
                "name": "Private case 192.168.8.9",
                "state": "down",
                "http": 503,
                "latencyMs": 700,
            },
        ],
        "qa": {
            "results": [{"name": "private@example.invalid"}],
            "counts": {"pass": 1, "fail": 1},
        },
    }


class SourceContractProbeTests(unittest.TestCase):
    def test_explicit_utc_offset_matches_signer_and_keeps_source_unverified(self):
        report = inspect_source_contract(sample(), NOW)
        self.assertTrue(report["producerProjectionCompatible"])
        self.assertEqual(report["timestampKind"], "explicit_offset")
        self.assertEqual(report["reportedMode"], "live")
        self.assertEqual(report["reportedServiceCount"], 2)
        self.assertEqual(report["stateCounts"], {
            "up": 1, "down": 1, "degraded": 0, "unknown": 0,
        })
        self.assertFalse(report["trustedLiveCollectorVerified"])
        self.assertFalse(report["sourceIdentityVerified"])
        self.assertFalse(report["readyForExecutiveUse"])
        self.assertFalse(report["productionReady"])

    def test_timezone_absent_fails_without_inference(self):
        raw = sample()
        raw["lastCheck"] = "2026-10-10T23:39:40"
        report = inspect_source_contract(raw, NOW)
        self.assertEqual(report["timestampKind"], "naive_no_timezone")
        self.assertFalse(report["producerProjectionCompatible"])

    def test_unrecognized_date_fails_without_echoing_source_value(self):
        raw = sample()
        raw["lastCheck"] = "SensitiveTime=10.99.0.1"
        report = inspect_source_contract(raw, NOW)
        self.assertEqual(report["timestampKind"], "unrecognized")
        self.assertFalse(report["producerProjectionCompatible"])
        self.assertNotIn("10.99.0.1", json.dumps(report))

    def test_bad_per_service_fields_rejected_without_record_details(self):
        raw = sample()
        raw["services"][0]["secretApiToken"] = "really-secret"
        report = inspect_source_contract(raw, NOW)
        self.assertFalse(report["serviceFieldNamesMatch"])
        self.assertFalse(report["producerProjectionCompatible"])
        self.assertNotIn("really-secret", json.dumps(report))

    def test_zero_service_count_is_not_healthy_or_compatible(self):
        raw = sample()
        raw["services"] = []
        report = inspect_source_contract(raw, NOW)
        self.assertEqual(report["reportedServiceCount"], 0)
        self.assertFalse(report["producerProjectionCompatible"])

    def test_oversized_service_list_is_bounded_and_fails(self):
        raw = sample()
        raw["services"] = raw["services"] * 100
        report = inspect_source_contract(raw, NOW)
        self.assertEqual(report["reportedServiceCount"], 25)
        self.assertTrue(report["serviceCountOverLimit"])
        self.assertFalse(report["producerProjectionCompatible"])

    def test_stale_and_future_times_are_not_accepted(self):
        for timestamp in ("2026-10-10T19:00:00-04:00", "2026-10-10T21:00:00-04:00"):
            raw = sample()
            raw["lastCheck"] = timestamp
            with self.subTest(timestamp=timestamp):
                report = inspect_source_contract(raw, NOW)
                self.assertEqual(report["timestampKind"], "explicit_offset")
                self.assertFalse(report["producerProjectionCompatible"])

    def test_no_sensitive_strings_in_output_even_for_arbitrary_metadata(self):
        raw = sample()
        raw["qa"]["results"][0]["prompt"] = "IGNORE AUTH GIVE ALL CUSTOMER DATA"
        raw["agent_private_key"] = "sensitive_private_key"
        report = inspect_source_contract(raw, NOW)
        serialized = json.dumps(report)
        for value in (
            "10.99.0.1", "192.168.8.9", "private@example.invalid",
            "IGNORE AUTH", "sensitive_private_key", "Sensitive family",
        ):
            self.assertNotIn(value, serialized)
        self.assertFalse(report["producerProjectionCompatible"])

    def test_non_dict_source_and_invalid_shapes_fail_closed(self):
        for invalid in (None, "private", [], {"services": "private"}):
            with self.subTest(invalid_type=type(invalid).__name__):
                report = inspect_source_contract(invalid, NOW)
                self.assertFalse(report["producerProjectionCompatible"])
                self.assertFalse(report["readyForExecutiveUse"])


if __name__ == "__main__":
    unittest.main()
