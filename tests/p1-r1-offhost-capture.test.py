"""Offline negative tests: never contact SSH, Docker, production or GPG keys."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "p1-r1-offhost-capture.py"
spec = importlib.util.spec_from_file_location("p1_r1_offhost", SCRIPT)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def fixture():
    return {
        "images": copy.deepcopy(capture.IMAGE_IDS),
        "rollback": capture.ROLLBACK_HUB,
        "sourceRevision": capture.SOURCE_REVISION,
        "configs": {
            "hub": {"files": ["/opt/v79/hub/file-%d.yml" % i for i in range(13)] +
                    ["/opt/v79/hub/.env"],
                    "digests": [x if x is not None else "e" * 64 for x in capture.HUB_COMPOSE_HASHES] + ["a" * 64],
                    "composeCount": 13},
            "tiquet": {"files": ["/opt/tiquet/docker-compose.yml", "/opt/tiquet/.env"],
                       "digests": ["b" * 64, "c" * 64], "composeCount": 1}
        },
        "mounts": {"v79-hub": ["/app/data", *capture.HUB_SECRET_DESTINATIONS],
                   "v79-tiquet-manager": ["/app/data", "/app/uploads"]}
    }


class OffhostTests(unittest.TestCase):
    def test_remote_probe_compiles(self):
        compile(capture.REMOTE_PROBE, "remote-stdin-probe", "exec")
        capture.self_test()

    def test_current_plan_and_all_streams(self):
        plan = fixture()
        capture.validate_plan(plan)
        streams = capture.streams_for(plan)
        self.assertEqual(len(streams), 12)
        self.assertEqual([a for a, _, _ in streams][:4],
                         ["hub-pg.dump.gpg", "tiquet-pg.dump.gpg",
                          "hub-config.tar.gpg", "tiquet-config.tar.gpg"])
        self.assertEqual(streams[-1][0], "exact-images-and-rollback.tar.gpg")
        self.assertIn(capture.ROLLBACK_HUB, streams[-1][1])
        self.assertTrue(all(str(s).startswith("/") for s in plan["mounts"]["v79-hub"]))
        self.assertNotIn("WIPAY_", json.dumps(streams))

    def test_invalid_plans_fail_closed(self):
        changes = (
            lambda p: p["images"].update({"v79-hub": capture.ROLLBACK_HUB}),
            lambda p: p["configs"]["hub"]["digests"].pop(),
            lambda p: p["configs"]["hub"]["digests"].__setitem__(0, "f" * 64),
            lambda p: p["configs"]["hub"].update({"composeCount": 9}),
            lambda p: p["mounts"]["v79-hub"].append("/app/../../etc"),
            lambda p: p["mounts"]["v79-hub"].append("/run/secrets/unreviewed-token"),
            lambda p: p["mounts"]["v79-tiquet-manager"].append("/run/secrets/v79-agent-token"),
            lambda p: p["mounts"]["v79-tiquet-manager"].remove("/app/uploads"),
            lambda p: p["mounts"]["v79-hub"].append("/app/data"),
            lambda p: p["configs"]["tiquet"]["digests"].pop(),
        )
        for change in changes:
            with self.subTest(change=str(change)):
                sample = fixture()
                change(sample)
                with self.assertRaises(capture.Abort):
                    capture.validate_plan(sample)

    def test_secret_file_mounts_are_explicit_and_regular_file_gated(self):
        plan = fixture()
        streams = capture.streams_for(plan)
        secret_reader_commands = [
            args for name, args, kind in streams
            if kind == "tgz" and any(secret in args for secret in capture.HUB_SECRET_DESTINATIONS)
        ]
        self.assertEqual(len(secret_reader_commands), 3)
        for args in secret_reader_commands:
            self.assertEqual(args[:6], ["docker", "exec", "-u", "0", "v79-hub", "sh"])
            self.assertIn('test -f "$1"', args)
            self.assertIn('test ! -L "$1"', args)
            self.assertIn('exec tar', args)
        self.assertNotIn("v79-agent-token", json.dumps([name for name, _, _ in streams]))
        self.assertNotIn("V79_WORKFORCE_TOKEN_FILE_HOST", json.dumps(streams))

    def test_missing_history_layer_six_requires_explicit_acknowledgment(self):
        self.assertIsNone(capture.HUB_COMPOSE_HASHES[5])
        plan = fixture()
        capture.validate_plan(plan)
        self.assertRegex(plan["configs"]["hub"]["digests"][5], r"^[0-9a-f]{64}$")
        self.assertNotEqual(plan["configs"]["hub"]["digests"][5], plan["configs"]["hub"]["digests"][4])

    def test_command_quotes_remote_script_args(self):
        command = capture.ssh_command(["python3", "-B", "-", "a'$(echo danger)"])
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("BatchMode=yes", command)
        self.assertIn("'\"'\"'", command[-1])

    def test_capture_creates_encrypted_acer_only_set_and_private_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            os.chmod(base, 0o700)
            plan = fixture()
            def fake_encrypt(_command, outfile):
                outfile.write_bytes(b"FAKE ENCRYPTED CIPHERTEXT, NOT REAL USER DATA")
                os.chmod(outfile, 0o600)
            with mock.patch.object(capture, "key_ready"), \
                 mock.patch.object(capture, "safe_base", return_value=base), \
                 mock.patch.object(capture, "encrypt_stream", side_effect=fake_encrypt), \
                 mock.patch.object(capture, "probe", return_value=plan):
                with contextlib.redirect_stdout(io.StringIO()):
                    capture.run_capture(plan, base)
            dirs = list(base.glob("p1-r1-current-release-*"))
            self.assertEqual(len(dirs), 1)
            root = dirs[0]
            self.assertFalse((root / "CAPTURE_INCOMPLETE").exists())
            receipt = root / "ciphertext-manifest.json"
            self.assertEqual(receipt.stat().st_mode & 0o077, 0)
            data = json.loads(receipt.read_text())
            self.assertEqual(data["status"], "CAPTURED_NOT_RESTORED")
            self.assertFalse(data["fullAppRestoreVerified"])
            self.assertFalse(data["customerBetaAuthorized"])
            self.assertEqual(len(data["files"]), 12)
            for entry in data["files"]:
                f = root / entry["name"]
                self.assertEqual(f.stat().st_mode & 0o077, 0)
                self.assertEqual(entry["sha256"], capture.sha_file(f))
            with mock.patch.object(capture, "verify_one") as checker, \
                 contextlib.redirect_stdout(io.StringIO()):
                capture.verify_set(root)
            self.assertEqual(checker.call_count, 12)
            original_manifest = receipt.read_text()
            incomplete = json.loads(original_manifest)
            incomplete["files"] = [x for x in incomplete["files"]
                                   if x["name"] != "tiquet-pg.dump.gpg"]
            receipt.write_text(json.dumps(incomplete))
            with self.assertRaisesRegex(capture.Abort, "MANIFEST_COMPONENT_COUNT_MISMATCH"):
                capture.verify_set(root)
            receipt.write_text(original_manifest)
            # Tamper and confirm the archive hash gate prevents any further processing.
            (root / data["files"][0]["name"]).write_bytes(b"CORRUPTED")
            with self.assertRaisesRegex(capture.Abort, "CIPHERTEXT_HASH"):
                capture.verify_set(root)

    def test_failed_stream_preserves_incomplete_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            os.chmod(base, 0o700)
            with mock.patch.object(capture, "key_ready"), \
                 mock.patch.object(capture, "safe_base", return_value=base), \
                 mock.patch.object(capture, "encrypt_stream",
                                   side_effect=capture.Abort("SIMULATED_SSH_FAIL")), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(capture.Abort):
                    capture.run_capture(fixture(), base)
            root = next(base.glob("p1-r1-current-release-*"))
            self.assertTrue((root / "CAPTURE_INCOMPLETE").exists())
            self.assertFalse((root / "ciphertext-manifest.json").exists())
            with self.assertRaisesRegex(capture.Abort, "CAPTURE_MARKED_INCOMPLETE"):
                capture.verify_set(root)

    def test_source_drift_during_capture_preserves_incomplete_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            os.chmod(base, 0o700)
            plan = fixture()
            changed = fixture()
            changed["configs"]["tiquet"]["digests"][0] = "f" * 64
            def fake_encrypt(_command, outfile):
                outfile.write_bytes(b"ENCRYPTED MOCK CIPHERTEXT")
                os.chmod(outfile, 0o600)
            with mock.patch.object(capture, "key_ready"), \
                 mock.patch.object(capture, "safe_base", return_value=base), \
                 mock.patch.object(capture, "encrypt_stream", side_effect=fake_encrypt), \
                 mock.patch.object(capture, "probe", return_value=changed), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(capture.Abort, "CHANGED_DURING_BACKUP"):
                    capture.run_capture(plan, base)
            root = next(base.glob("p1-r1-current-release-*"))
            self.assertTrue((root / "CAPTURE_INCOMPLETE").exists())

    def test_no_acceptance_claim_without_decrypt_or_restore(self):
        text = SCRIPT.read_text()
        self.assertIn("CAPTURED_NOT_RESTORED", text)
        self.assertIn("RELEASE_GATE=NO_GO", text)
        self.assertNotIn("docker compose up", text)
        self.assertNotIn("docker rm", text)
        self.assertNotIn("docker load", text)


if __name__ == "__main__":
    unittest.main()
