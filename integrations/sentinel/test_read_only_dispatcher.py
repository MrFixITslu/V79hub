"""Pure isolated service authentication tests; no HTTP server or external network."""
from __future__ import annotations
import base64
import hashlib
import hmac
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from read_only_dispatcher import (
    READ_PATH, IsolatedReadOnlySentinelDispatcher, TrustedReadCaller,
    read_mac_input,
)
from source_signer import TrustedSourceSigner

NOW = datetime(2026, 10, 10, 23, 40, tzinfo=timezone.utc)
SECRET = b"synthetic-only-ephemeral-32-byte-auth-secret-v79"


def synthetic_snapshot():
    return {
        "source": "local-mission-control",
        "monitorMode": "staging",
        "lastCheck": "2026-10-10T23:39:45Z",
        "services": [
            {"name": "private island customer", "state": "down", "http": 500, "latencyMs": 21},
            {"name": "10.10.20.30", "state": "up", "http": 200, "latencyMs": 30},
        ],
        "qa": {"results": [{"name": "customer@example.invalid"}]},
    }


def signed_headers(req_id=None, organization="v79founder", key_id="sentinel-g2-test",
                   issued_at="2026-10-10T23:40:00.000Z"):
    req = req_id or str(uuid4())
    signature = hmac.new(SECRET,
                         read_mac_input(organization, key_id, req, issued_at),
                         hashlib.sha256).digest()
    return {
        "X-V79-Read-Organization": organization,
        "X-V79-Read-Key-Id": key_id,
        "X-V79-Read-Request-Id": req,
        "X-V79-Read-Issued-At": issued_at,
        "X-V79-Read-Signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
    }


class ReadOnlyGateTests(unittest.TestCase):
    def setUp(self):
        self.calls = 0
        def loader():
            self.calls += 1
            return synthetic_snapshot()
        self.api = IsolatedReadOnlySentinelDispatcher(
            TrustedReadCaller("v79founder", "sentinel-g2-test", SECRET),
            TrustedSourceSigner("sentinel-g2-test", "v79founder", Ed25519PrivateKey.generate()),
            loader, clock=lambda: NOW, allow_in_memory_for_tests=True,
        )

    def test_authenticated_get_returns_only_aggregate_signed_payload(self):
        status, result = self.api.get("GET", READ_PATH, signed_headers())
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, 1)
        import json
        data = json.loads(result["payloadJson"])
        self.assertEqual(data["counts"], {
            "servicesObserved": 2, "up": 1, "down": 1, "degraded": 0, "unknown": 0,
        })
        output = json.dumps(result)
        for secret in ("private island", "10.10.20.30", "customer@example.invalid", "services\": [", "qa"):
            self.assertNotIn(secret, output)
        self.assertEqual(len(result["signature"]), 86)

    def test_no_method_or_path_change_and_no_browser_cookie_authorization(self):
        for method, path in [
            ("POST", READ_PATH), ("PUT", READ_PATH), ("DELETE", READ_PATH),
            ("GET", READ_PATH + "?url=https://evil.example"),
            ("GET", "/api/v1/incidents/ack"),
        ]:
            with self.subTest(method=method, path=path):
                status, _ = self.api.get(method, path, signed_headers())
                self.assertEqual(status, 404)
        bad_headers = signed_headers()
        bad_headers["Cookie"] = "not-an-approved-service-identity"
        self.assertEqual(self.api.get("GET", READ_PATH, bad_headers)[0], 401)
        self.assertEqual(self.calls, 0)

    def test_wrong_tenant_key_or_changed_signature_refused_without_source_read(self):
        for headers in [
            signed_headers(organization="other_tenant"),
            signed_headers(key_id="different_signer"),
            {**signed_headers(), "X-V79-Read-Signature": "A" * 43},
            {**signed_headers(), "X-V79-Read-Request-Id": "invalid"},
            {**signed_headers(), "X-V79-Read-Issued-At": "2026-10-10T22:40:00.000Z"},
            {**signed_headers(), "X-V79-Read-Issued-At": "2026-10-11T22:40:00.000Z"},
        ]:
            with self.subTest(headers=str(headers.keys())):
                self.assertEqual(self.api.get("GET", READ_PATH, headers)[0], 401)
        self.assertEqual(self.calls, 0)

    def test_one_use_nonce_consumed_and_duplicate_cannot_requery_source(self):
        headers = signed_headers()
        self.assertEqual(self.api.get("GET", READ_PATH, headers)[0], 200)
        self.assertEqual(self.api.get("GET", READ_PATH, headers)[0], 409)
        self.assertEqual(self.calls, 1)

    def test_upstream_failure_never_releases_partial_or_private_data(self):
        def fail():
            raise TimeoutError("Private service IP 10.55.66.77")
        api = IsolatedReadOnlySentinelDispatcher(
            TrustedReadCaller("v79founder", "sentinel-g2-test", SECRET),
            TrustedSourceSigner("sentinel-g2-test", "v79founder", Ed25519PrivateKey.generate()),
            fail, clock=lambda: NOW, allow_in_memory_for_tests=True,
        )
        result = api.get("GET", READ_PATH, signed_headers())
        self.assertEqual(result[0], 503)
        self.assertNotIn("10.55.66.77", str(result))

    def test_old_timestamp_rejected_and_nothing_collected(self):
        h = signed_headers(issued_at="2026-10-10T23:38:00.000Z")
        self.assertEqual(self.api.get("GET", READ_PATH, h)[0], 401)
        self.assertEqual(self.calls, 0)

    def test_missing_persistent_replay_guard_denied_by_default(self):
        with self.assertRaises(ValueError):
            IsolatedReadOnlySentinelDispatcher(
                TrustedReadCaller("v79founder", "sentinel-g2-test", SECRET),
                TrustedSourceSigner("sentinel-g2-test", "v79founder", Ed25519PrivateKey.generate()),
                synthetic_snapshot, clock=lambda: NOW,
            )

    def test_reader_and_signer_must_be_bound_to_same_trusted_org(self):
        with self.assertRaises(ValueError):
            IsolatedReadOnlySentinelDispatcher(
                TrustedReadCaller("tenant_other", "sentinel-g2-test", SECRET),
                TrustedSourceSigner("sentinel-g2-test", "v79founder", Ed25519PrivateKey.generate()),
                synthetic_snapshot, clock=lambda: NOW, allow_in_memory_for_tests=True,
            )


if __name__ == "__main__":
    unittest.main()
