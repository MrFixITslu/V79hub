import importlib.util
import hashlib
import io
import subprocess
import tarfile
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


    def test_pinned_host_mount_tar_preserves_data_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "app-data"
            (source / "nested").mkdir(parents=True)
            (source / "nested" / "item.txt").write_bytes(b"disposable-test-bytes")
            (source / "shortcut").symlink_to("nested/item.txt")
            name, dest = "v79-hub", "/app/data"
            digest = hashlib.sha256(str(source).encode()).hexdigest()[:12]
            mount = {"Type": "bind", "RW": True,
                     "Source": str(source), "Destination": dest}
            with patch.dict(capture.MOUNTS, {(name, dest): digest}):
                command = capture.host_app_archive_args(name, mount)
                self.assertEqual(command[0], "tar")
                self.assertNotIn("docker", command)
                output = subprocess.check_output(command, stderr=subprocess.DEVNULL)
            with tarfile.open(fileobj=io.BytesIO(output), mode="r:") as tar:
                self.assertEqual(tar.extractfile("./nested/item.txt").read(),
                                 b"disposable-test-bytes")
                link = tar.getmember("./shortcut")
                self.assertTrue(link.issym())
                self.assertEqual(link.linkname, "nested/item.txt")

    def test_host_archive_fails_closed_for_database_and_unpinned_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = root / "approved"
            substitute = root / "substitute"
            approved.mkdir()
            substitute.mkdir()
            name, dest = "v79-hub", "/app/data"
            digest = hashlib.sha256(str(approved).encode()).hexdigest()[:12]
            mount = {"Type": "bind", "RW": True,
                     "Source": str(substitute), "Destination": dest}
            with patch.dict(capture.MOUNTS, {(name, dest): digest}):
                with self.assertRaisesRegex(capture.Stop, "HOST_ARCHIVE_SOURCE_DRIFT"):
                    capture.host_app_archive_args(name, mount)
                with self.assertRaisesRegex(capture.Stop, "HOST_ARCHIVE_SCOPE"):
                    capture.host_app_archive_args("v79-hub-postgres", {
                        "Type": "volume", "RW": True, "Source": str(approved),
                        "Destination": "/var/lib/postgresql/data"})

    def test_host_archive_rejects_source_symlink_and_non_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            symlink = root / "link"
            symlink.symlink_to(real, target_is_directory=True)
            file = root / "file"
            file.write_text("not a directory")
            name, dest = "v79-hub", "/app/data"
            for bad in (symlink, file):
                mount = {"Type": "bind", "RW": True,
                         "Source": str(bad), "Destination": dest}
                digest = hashlib.sha256(str(bad).encode()).hexdigest()[:12]
                with patch.dict(capture.MOUNTS, {(name, dest): digest}):
                    with self.assertRaisesRegex(capture.Stop, "HOST_ARCHIVE_SOURCE_INVALID"):
                        capture.host_app_archive_args(name, mount)

if __name__ == "__main__": unittest.main()
