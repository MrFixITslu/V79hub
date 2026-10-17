"""Persistent same-host replay tests. Uses ONLY disposable temp SQLite files."""
from __future__ import annotations

import base64
import hashlib
import hmac
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from read_only_dispatcher import (
    READ_PATH, IsolatedReadOnlySentinelDispatcher, TrustedReadCaller, read_mac_input,
)
from source_signer import TrustedSourceSigner
from sqlite_replay_guard import ReplayStoreUnavailable, SqliteNonceReplayGuard

NOW_MS = 1_791_675_600_000
NOW = datetime.fromtimestamp(NOW_MS / 1000, timezone.utc)
READ_SECRET = b"synthetic-read-hmac-test-secret-32-bytes-only"
ORG = "v79founder"
KEY = "sentinel-g2-test"


def _worker_claim(db_path: str, nonce: str, now_ms: int, queue) -> None:
    try:
        result = SqliteNonceReplayGuard(db_path).claim(nonce, now_ms)
        queue.put(("ok", result))
    except Exception as exc:
        queue.put(("error", type(exc).__name__))


def _raw():
    return {
        "source": "local-mission-control", "monitorMode": "staging",
        "lastCheck": NOW.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "services": [{"name": "Customer-hidden", "state": "up",
                      "http": 200, "latencyMs": 5}],
        "qa": {"results": [{"name": "private@example.invalid"}]},
    }


def _request(nonce: str) -> dict[str, str]:
    issued = NOW.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    mac = hmac.new(READ_SECRET, read_mac_input(ORG, KEY, nonce, issued), hashlib.sha256).digest()
    return {
        "X-V79-Read-Organization": ORG, "X-V79-Read-Key-Id": KEY,
        "X-V79-Read-Request-Id": nonce, "X-V79-Read-Issued-At": issued,
        "X-V79-Read-Signature": base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii"),
    }


class PersistentNonceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "g2-replay.sqlite3"

    def tearDown(self):
        self.dir.cleanup()

    def _api(self):
        return IsolatedReadOnlySentinelDispatcher(
            TrustedReadCaller(ORG, KEY, READ_SECRET),
            TrustedSourceSigner(KEY, ORG, Ed25519PrivateKey.generate()),
            _raw, clock=lambda: NOW,
            replay_guard=SqliteNonceReplayGuard(self.path),
        )

    def test_single_use_claim_survives_new_object_and_restart(self):
        request = str(uuid4())
        a = SqliteNonceReplayGuard(self.path)
        self.assertTrue(a.claim(request, NOW_MS))
        b = SqliteNonceReplayGuard(self.path)
        self.assertFalse(b.claim(request, NOW_MS))
        self.assertTrue(b.claim(str(uuid4()), NOW_MS))
        self.assertEqual(os.stat(self.path).st_mode & 0o077, 0)

    def test_two_independent_dispatchers_share_replay_state(self):
        headers = _request(str(uuid4()))
        api_a = self._api()
        api_b = self._api()
        first_status, first = api_a.get("GET", READ_PATH, headers)
        self.assertEqual(first_status, 200)
        self.assertNotIn("Customer-hidden", str(first))
        self.assertEqual(api_b.get("GET", READ_PATH, headers)[0], 409)

    def test_stale_rows_expire_without_unbounded_growth(self):
        nonce = str(uuid4())
        guard = SqliteNonceReplayGuard(self.path)
        self.assertTrue(guard.claim(nonce, NOW_MS))
        self.assertFalse(guard.claim(nonce, NOW_MS + 89_999))
        self.assertTrue(guard.claim(nonce, NOW_MS + 90_000))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM used_requests").fetchone()[0], 1)

    def test_bounded_capacity_fails_closed(self):
        guard = SqliteNonceReplayGuard(self.path)
        for _ in range(128):
            self.assertTrue(guard.claim(str(uuid4()), NOW_MS))
        self.assertFalse(guard.claim(str(uuid4()), NOW_MS))
        self.assertFalse(guard.claim(str(uuid4()), NOW_MS - 10_000))

    def test_untrusted_nonce_types_cannot_be_stored(self):
        guard = SqliteNonceReplayGuard(self.path)
        for candidate in ("not-uuid", "a" * 1000, "../sentinel", "", 12, None):
            self.assertFalse(guard.claim(candidate, NOW_MS))
        self.assertFalse(guard.claim(str(uuid4()), True))
        self.assertFalse(guard.claim(str(uuid4()), -1))

    def test_symlink_and_world_readable_database_refused(self):
        target = Path(self.dir.name) / "target"
        target.write_text("not a database", encoding="utf8")
        self.path.symlink_to(target)
        with self.assertRaises(ReplayStoreUnavailable):
            SqliteNonceReplayGuard(self.path)
        self.path.unlink()
        self.path.write_bytes(b"")
        self.path.chmod(0o644)
        with self.assertRaises(ReplayStoreUnavailable):
            SqliteNonceReplayGuard(self.path)

    def test_missing_private_directory_refused_without_creation(self):
        bad = Path(self.dir.name) / "nonexistent" / "noncestore.sqlite3"
        with self.assertRaises(ReplayStoreUnavailable):
            SqliteNonceReplayGuard(bad)
        self.assertFalse(bad.parent.exists())

    def test_four_simultaneous_processes_exactly_one_claim_wins(self):
        guard = SqliteNonceReplayGuard(self.path)
        self.assertIsNotNone(guard)
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        nonce = str(uuid4())
        workers = [
            ctx.Process(target=_worker_claim, args=(str(self.path), nonce, NOW_MS, queue))
            for _ in range(4)
        ]
        for worker in workers:
            worker.start()
        outcomes = []
        try:
            for worker in workers:
                worker.join(timeout=10)
                self.assertFalse(worker.is_alive(), "Worker must not remain blocked")
                self.assertEqual(worker.exitcode, 0)
            outcomes = [queue.get(timeout=2) for _ in workers]
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=2)
            queue.close()
        self.assertEqual(sorted(outcomes), sorted([
            ("ok", True), ("ok", False), ("ok", False), ("ok", False),
        ]))

    def test_unauthorized_request_cannot_allocate_nonce(self):
        api = self._api()
        headers = _request(str(uuid4()))
        forged = {**headers, "X-V79-Read-Signature": "A" * 43}
        self.assertEqual(api.get("GET", READ_PATH, forged)[0], 401)
        # Since spoofed caller did not consume it, genuine request succeeds.
        self.assertEqual(api.get("GET", READ_PATH, headers)[0], 200)

    def test_fail_closed_when_database_becomes_unavailable(self):
        api = self._api()
        # Invalidate the dedicated staging-only SQLite file after setup.
        self.path.unlink()
        self.assertEqual(api.get("GET", READ_PATH, _request(str(uuid4())))[0], 503)


if __name__ == "__main__":
    unittest.main()
