"""Synthetic, NO-NETWORK tests for fixed scope 15-minute Acer TCP 443 pilot."""
from __future__ import annotations

import errno
import json
import stat
import tempfile
import unittest
from pathlib import Path

from supervised_v79_tcp_pilot import (
    APPROVED_ACER_HOSTNAME, CADENCE_SECONDS, DURATION_SECONDS,
    GUARD_FILE_NAME, MAX_ATTEMPTS, PORT, TARGET, PilotGuardError,
    claim_one_pilot, classify_connect_result, execute_supervised_pilot,
)


class FakeClock:
    def __init__(self, t=100.0):
        self.t = float(t)
        self.sleeps = []
    def now(self):
        return self.t
    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


class BoundedSupervisedPilotTests(unittest.TestCase):
    def test_exact_server_and_cadence_are_fixed(self):
        self.assertEqual(TARGET, "192.168.100.163")
        self.assertEqual(PORT, 443)
        self.assertEqual(APPROVED_ACER_HOSTNAME, "firelion-Aspire-A315-51")
        self.assertEqual(CADENCE_SECONDS, 60)
        self.assertEqual(DURATION_SECONDS, 900)
        self.assertEqual(MAX_ATTEMPTS, 15)

    def test_exactly_fifteen_attempts_at_sixty_second_cadence(self):
        fake = FakeClock()
        attempts = []
        output = []
        def connect():
            attempts.append(fake.now())
            fake.t += 0.004
            return 0
        report = execute_supervised_pilot(
            connect=connect, clock=fake.now, sleep=fake.sleep, emit=output.append,
        )
        self.assertEqual(len(attempts), 15)
        self.assertEqual(report["attemptsExecuted"], 15)
        self.assertEqual(report["outcomes"]["tcp-open"], 15)
        self.assertEqual([round(t - attempts[0]) for t in attempts], list(range(0, 900, 60)))
        self.assertAlmostEqual(fake.now(), 1000.0)
        self.assertEqual(report["durationSeconds"], 900)
        self.assertEqual(output[-1], report)
        self.assertFalse(report["continuousMonitoringEnabled"])
        self.assertFalse(report["independentlyAuthenticatedCollector"])
        self.assertFalse(report["trustedForExecutiveUse"])
        self.assertFalse(report["productionReady"])

    def test_connection_failure_does_not_trigger_retry(self):
        fake = FakeClock()
        attempted = []
        def failing():
            attempted.append(fake.now())
            return errno.ETIMEDOUT
        report = execute_supervised_pilot(
            connect=failing, clock=fake.now, sleep=fake.sleep, emit=lambda *_: None,
        )
        self.assertEqual(len(attempted), 15)
        self.assertEqual(report["outcomes"]["timeout"], 15)
        self.assertEqual(report["outcomes"]["tcp-open"], 0)
        self.assertFalse(report["tlsOrHttpVerified"])

    def test_drift_skips_slots_instead_of_bursting(self):
        fake = FakeClock()
        attempted = []
        def delayed_sleep(n):
            fake.sleep(n)
            if len(fake.sleeps) == 1:
                fake.t += 120
        def connect():
            attempted.append(fake.now())
            return 0
        result = execute_supervised_pilot(
            connect=connect, clock=fake.now, sleep=delayed_sleep, emit=lambda *_: None,
        )
        self.assertEqual(result["scheduledSlotsSkipped"], 2)
        self.assertEqual(len(attempted), 13)
        self.assertEqual(result["attemptsExecuted"], 13)
        self.assertEqual(result["maxAttempts"], 15)
        self.assertEqual(fake.now(), 1000.0)

    def test_expired_window_makes_zero_attempts(self):
        fake = FakeClock()
        calls = []
        def sleep_after_deadline(n):
            fake.t += 901
        report = execute_supervised_pilot(
            connect=lambda: calls.append("network"), clock=fake.now,
            sleep=sleep_after_deadline, emit=lambda *_: None,
        )
        # First slot is due immediately: one allowed attempt; on sleep for the
        # next slot the deadline is over. No further network attempts occur.
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["attemptsExecuted"], 1)
        self.assertEqual(report["scheduledSlotsSkipped"], 14)

    def test_exception_from_attempt_is_counted_but_not_retried(self):
        fake = FakeClock()
        attempts = []
        def failing():
            attempts.append(fake.now())
            raise OSError("No route")
        result = execute_supervised_pilot(
            connect=failing, clock=fake.now, sleep=fake.sleep, emit=lambda *_: None,
        )
        self.assertEqual(len(attempts), 15)
        self.assertEqual(result["outcomes"]["connection-failed"], 15)
        self.assertEqual(fake.now(), 1000.0)

    def test_failure_codes_are_sanitized(self):
        self.assertEqual(classify_connect_result(0), "tcp-open")
        self.assertEqual(classify_connect_result(errno.ECONNREFUSED), "refused")
        self.assertEqual(classify_connect_result(errno.ETIMEDOUT), "timeout")
        self.assertEqual(classify_connect_result(53), "connection-failed")
        self.assertEqual(classify_connect_result(True), "connection-failed")
        self.assertEqual(classify_connect_result("192.168.100.163"), "connection-failed")

    def test_guard_consumes_one_approval_and_prevents_rerun(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            marker = claim_one_pilot(host=APPROVED_ACER_HOSTNAME, home=home)
            self.assertEqual(marker.name, GUARD_FILE_NAME)
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(marker.parent.stat().st_mode), 0o700)
            with self.assertRaisesRegex(PilotGuardError, "already claimed"):
                claim_one_pilot(host=APPROVED_ACER_HOSTNAME, home=home)

    def test_wrong_vantage_does_not_consume_approval(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            with self.assertRaisesRegex(PilotGuardError, "approved Acer"):
                claim_one_pilot(host="v79sl", home=home)
            self.assertFalse((home / ".local" / "state").exists())

    def test_symlink_guard_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / ".local" / "state").mkdir(parents=True)
            (home / ".local" / "state" / "v79-sentinel").symlink_to(home)
            with self.assertRaises(PilotGuardError):
                claim_one_pilot(host=APPROVED_ACER_HOSTNAME, home=home)

    def test_summary_keeps_scope_narrow_and_untrusted(self):
        fake = FakeClock()
        events = []
        report = execute_supervised_pilot(
            connect=lambda: 0, clock=fake.now, sleep=fake.sleep, emit=events.append,
        )
        self.assertEqual((report["target"], report["port"]), (TARGET, PORT))
        self.assertEqual(len(events), 16)
        self.assertFalse(report["additionalProbesAuthorized"])
        self.assertFalse(report["continuousMonitoringEnabled"])
        self.assertFalse(report["tlsOrHttpVerified"])

    def test_no_subprocess_packet_capture_scheduler_or_other_target(self):
        source = Path(__file__).with_name("supervised_v79_tcp_pilot.py").read_text()
        for forbidden in (
            "subprocess", "dumpcap", "tshark", "pcapng", "scapy",
            "getaddrinfo(", "socket.gethostbyname(", "requests.",
            "urllib.request", "cron", "systemctl", "nmap",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("socket.AF_INET, socket.SOCK_STREAM", source)
        self.assertIn("sock.connect_ex((TARGET, PORT))", source)


if __name__ == "__main__":
    unittest.main()
