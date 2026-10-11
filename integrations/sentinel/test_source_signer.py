"""G2 fixture-only Python producer unit tests; no NOC service/network accessed."""
from __future__ import annotations
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from source_signer import (
    TrustedSourceSigner, SentinelContractError,
    aggregate_mission_snapshot, sign_aggregate_for_challenge,
)

NOW = datetime(2026, 10, 10, 23, 40, tzinfo=timezone.utc)
REQUEST = {
    "organizationId": "v79founder",
    "keyId": "sentinel-g2-fixture",
    "requestId": "d2a562cb-1515-4e3e-8bd7-024e6c66ce51",
}


def sample():
    return {
        "source": "local-mission-control",
        "monitorMode": "staging",
        "lastCheck": "2026-10-10T23:39:40Z",
        "services": [
            {"name": "Secret 192.168.1.5", "state": "up", "http": 200, "latencyMs": 34},
            {"name": "ACME private customer", "state": "down", "http": 503, "latencyMs": None},
            {"name": "internal vpn", "state": "degraded", "http": None, "latencyMs": 555},
        ],
        "qa": {"results": [{"name": "customer@example.invalid", "state": "fail"}]},
    }


class SourceSignerTests(unittest.TestCase):
    def setUp(self):
        self.signer = TrustedSourceSigner(
            key_id="sentinel-g2-fixture",
            organization_id="v79founder",
            private_key=Ed25519PrivateKey.generate(),
        )

    def signed(self, raw=None, challenge=None):
        agg = aggregate_mission_snapshot(raw if raw is not None else sample(), now=NOW)
        return sign_aggregate_for_challenge(
            agg, challenge if challenge is not None else REQUEST,
            self.signer, now=NOW,
        )

    def test_raw_names_never_cross_signed_boundary(self):
        envelope = self.signed()
        self.assertEqual(len(envelope["signature"]), 86)
        self.assertEqual(envelope["organizationId"], "v79founder")
        for word in ["ACME", "Secret", "192.168", "customer@example", "services\": [", "qa"]:
            self.assertNotIn(word, envelope["payloadJson"])
        import json
        obj = json.loads(envelope["payloadJson"])
        self.assertEqual(obj["counts"], {
            "servicesObserved": 3, "up": 1, "down": 1, "degraded": 1, "unknown": 0,
        })
        self.assertEqual(obj["observedAt"], "2026-10-10T23:39:40.000Z")

    def test_wrong_tenant_and_key_forbidden(self):
        for altered in [
            {**REQUEST, "organizationId": "customer_123"},
            {**REQUEST, "keyId": "attacker-key"},
            {**REQUEST, "requestId": "not-a-uuid"},
            {**REQUEST, "unexpected": "ignored"},
        ]:
            with self.subTest(altered=altered), self.assertRaises(SentinelContractError):
                self.signed(challenge=altered)

    def test_unbounded_or_malformed_raw_observations_rejected(self):
        bad = [
            {**sample(), "services": []},
            {**sample(), "services": sample()["services"] * 9},
            {**sample(), "services": [{**sample()["services"][0], "packet": "secret"}]},
            {**sample(), "services": [{**sample()["services"][0], "state": "unsure"}]},
            {**sample(), "services": [{**sample()["services"][0], "latencyMs": True}]},
            {**sample(), "qa": "invalid"},
            {**sample(), "unexpected": "private"},
            {**sample(), "source": "remote-arbitrary-source"},
            {**sample(), "lastCheck": "2026-10-10T23:00:00Z"},
            {**sample(), "lastCheck": "2026-10-11T01:00:00Z"},
            {**sample(), "lastCheck": "2026-02-30T00:00:00Z"},
        ]
        for row in bad:
            with self.subTest(case=str(row)[:55]), self.assertRaises(SentinelContractError):
                aggregate_mission_snapshot(row, now=NOW)

    def test_extra_signed_fields_or_inconsistent_counts_forbidden(self):
        agg = aggregate_mission_snapshot(sample(), now=NOW)
        for changed in [
            {**agg, "qa": {"results": []}},
            {**agg, "counts": {**agg["counts"], "servicesObserved": 5}},
            {**agg, "counts": {**agg["counts"], "up": True}},
            {**agg, "counts": {**agg["counts"], "incidentText": "classified"}},
            {**agg, "observedAt": "2026-10-10T23:00:00.000Z"},
        ]:
            with self.subTest(changed=str(changed)[:65]), self.assertRaises(SentinelContractError):
                sign_aggregate_for_challenge(changed, REQUEST, self.signer, now=NOW)

    def test_no_operator_browser_cookies_or_granted_privileges(self):
        envelope = self.signed()
        self.assertEqual(set(envelope), {
            "schemaVersion", "keyId", "organizationId", "requestId",
            "issuedAt", "expiresAt", "payloadJson", "signature",
        })
        for forbidden in ("cookie", "csrf", "agent", "role", "permission", "approved"):
            self.assertNotIn(forbidden, str(envelope).lower())

    def test_no_untrusted_signer_configuration(self):
        key = Ed25519PrivateKey.generate()
        with self.assertRaises(SentinelContractError):
            TrustedSourceSigner("bad key id", "v79founder", key)
        with self.assertRaises(SentinelContractError):
            TrustedSourceSigner("valid", "bad", key)

    def test_issued_and_expiry_windows_exact(self):
        envelope = self.signed()
        self.assertEqual(envelope["issuedAt"], "2026-10-10T23:40:00.000Z")
        self.assertEqual(envelope["expiresAt"], "2026-10-10T23:40:30.000Z")
        late = NOW + timedelta(minutes=16)
        agg = aggregate_mission_snapshot(sample(), now=NOW)
        with self.assertRaises(SentinelContractError):
            sign_aggregate_for_challenge(agg, REQUEST, self.signer, now=late)


if __name__ == "__main__":
    unittest.main()
