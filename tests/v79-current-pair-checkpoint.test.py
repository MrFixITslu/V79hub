import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).parent.parent / "scripts/v79-current-pair-checkpoint.py"
if not SOURCE.exists():  # local draft layout
    SOURCE = Path(__file__).with_name("v79_current_pair_checkpoint.py")
spec = importlib.util.spec_from_file_location("capture", SOURCE)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

class CheckpointSafety(unittest.TestCase):
    def test_wrong_host_stops_before_docker_inspection(self):
        with patch.object(capture.socket, "gethostname", return_value="not-v79sl"), \
             patch.object(capture, "inspect") as inspect:
            with self.assertRaisesRegex(capture.Stop, "WRONG_HOST_OR_ROOT_USER"):
                capture.preflight()
            inspect.assert_not_called()

    def test_partial_unpause_attempts_both_apps(self):
        state = {"v79-hub": True, "v79-tiquet-manager": True}
        def inspect(name): return {"State": {"Paused": state[name]}}
        def call(args, timeout=30):
            if args[2] == "v79-hub": raise capture.Stop("synthetic Docker failure")
            state[args[2]] = False
        with patch.object(capture, "inspect", side_effect=inspect), \
             patch.object(capture, "call", side_effect=call):
            with self.assertRaisesRegex(capture.Stop, "UNPAUSE_FAILED_WATCHDOG_ARMED"):
                capture.resume_apps()
        self.assertFalse(state["v79-tiquet-manager"])

    def test_stream_promotion_requires_both_processes_to_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_gpg = root / "gpg"
            fake_gpg.write_text("#!/bin/sh\nexec cat\n")
            fake_gpg.chmod(0o700)
            data = b"synthetic database bytes\x00secret-marker"
            output = root / "archive.gpg"
            with patch.dict(os.environ, {"PATH": str(root) + os.pathsep + os.environ["PATH"]}):
                result = capture.encrypt_stream([sys.executable, "-c",
                    "import sys;sys.stdout.buffer.write(" + repr(data) + ")"], output, root, 30)
                self.assertEqual(result["sha256"], capture.digest(output))
                self.assertEqual(output.read_bytes(), data)  # synthetic pipeline only
                with self.assertRaisesRegex(capture.Stop, "ENCRYPTED_STREAM_FAILED"):
                    capture.encrypt_stream([sys.executable, "-c", "raise SystemExit(7)"],
                                           root / "failed.gpg", root, 30)
                self.assertFalse((root / "failed.gpg").exists())

if __name__ == "__main__": unittest.main()
