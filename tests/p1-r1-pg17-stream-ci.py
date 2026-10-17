#!/usr/bin/env python3
"""CI-ONLY real PostgreSQL 17 GPG streaming validator.

Only synthetic rows and a disposable Docker PG17 container. Never connects to
v79sl, reads Acer backups, installs anything on an owner host or restores data.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "p1-r1-offhost-capture.py"
NAME = "v79-r1-ci-pg17"
PASSPHRASE = "CI-SYNTHETIC-ONLY-NO-REAL-RECOVERY-KEY-20261017"


def run(command, **kw):
    return subprocess.run(command, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, **kw)


class PostgreSQL17EncryptedStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("GITHUB_ACTIONS") != "true" or \
                os.environ.get("V79_PG17_STREAM_TEST") != "1":
            raise unittest.SkipTest("refuse execution outside isolated GitHub CI")
        spec = importlib.util.spec_from_file_location("r1_capture_under_test", SOURCE)
        cls.impl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.impl)
        cls.tmp = tempfile.TemporaryDirectory(prefix="v79-r1-ci-pg17-")
        cls.root = Path(cls.tmp.name)
        for executable in ("docker", "gpg"):
            if not shutil.which(executable):
                raise unittest.SkipTest(executable + " missing in isolated CI")
        run(["docker", "run", "--rm", "-d", "--network", "none", "--name", NAME,
             "-e", "POSTGRES_PASSWORD=ci_fixture_only", "-e",
             "POSTGRES_DB=ci_fixture", "postgres:17"])
        cls.container_started = True
        # pg_isready can see Postgres' bootstrap server before initdb's
        # requested POSTGRES_DB exists. Wait for a real SQL response from that
        # database, not merely for an accepting socket.
        for _ in range(80):
            p = subprocess.run(["docker", "exec", NAME, "psql", "-U", "postgres",
                                "-d", "ci_fixture", "-X", "-t", "-A", "-c", "SELECT 1"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if p.returncode == 0 and p.stdout.strip() == b"1":
                break
            import time
            time.sleep(0.25)
        else:
            raise RuntimeError("CI_SYNTHETIC_PG17_DATABASE_NOT_READY")
        run(["docker", "exec", NAME, "psql", "-U", "postgres", "-d", "ci_fixture",
             "-v", "ON_ERROR_STOP=1", "-c",
             "CREATE TABLE synth_archive_check (n integer PRIMARY KEY);"
             " INSERT INTO synth_archive_check VALUES (7);"])
        archive = run(["docker", "exec", NAME, "pg_dump", "-U",
                       "postgres", "-d", "ci_fixture", "-Fc"]).stdout
        if not archive.startswith(b"PGDMP"):
            raise RuntimeError("CI_SYNTHETIC_PG17_DUMP_INVALID")
        cls.archive = cls.root / "synthetic-pg17.dump"
        cls.archive.write_bytes(archive)
        cls.encrypted = cls.root / "synthetic-pg17.dump.gpg"
        run(["gpg", "--batch", "--yes", "--pinentry-mode", "loopback",
             "--passphrase", PASSPHRASE, "--symmetric", "--cipher-algo", "AES256",
             "--output", str(cls.encrypted), str(cls.archive)])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "container_started", False):
            subprocess.run(["docker", "rm", "-f", NAME], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def decrypt_command(self, encrypted):
        return ["gpg", "--batch", "--quiet", "--pinentry-mode", "loopback",
                "--passphrase", PASSPHRASE, "--decrypt", str(encrypted)]

    def test_real_pg17_dump_and_pg17_restore_list_after_full_decrypt(self):
        self.impl.drain_and_validate(self.decrypt_command(self.encrypted),
                                     ["docker", "exec", "-i", NAME, "pg_restore", "--list"])
        print("CI_SYNTHETIC_PG17_GPG_TOC=PASS")

    def test_validator_can_exit_early_while_gpg_is_fully_drained(self):
        self.impl.drain_and_validate(self.decrypt_command(self.encrypted),
                                     ["python3", "-c",
                                      "import sys; assert sys.stdin.buffer.read(5)==b'PGDMP'"])
        print("CI_SYNTHETIC_EARLY_TO_C_END_OF_GPG=PASS")

    def test_corrupted_ciphertext_must_not_become_pass(self):
        corrupted = self.root / "corrupted.dump.gpg"
        bytes_ = bytearray(self.encrypted.read_bytes())
        bytes_[-8] ^= 0x80
        corrupted.write_bytes(bytes_)
        with self.assertRaises(self.impl.Abort):
            self.impl.drain_and_validate(self.decrypt_command(corrupted),
                                         ["docker", "exec", "-i", NAME, "pg_restore", "--list"])
        print("CI_SYNTHETIC_TAMPER_DENIED=PASS")

    def test_truncated_ciphertext_must_not_become_pass(self):
        truncated = self.root / "truncated.dump.gpg"
        truncated.write_bytes(self.encrypted.read_bytes()[:-16])
        with self.assertRaises(self.impl.Abort):
            self.impl.drain_and_validate(self.decrypt_command(truncated),
                                         ["docker", "exec", "-i", NAME, "pg_restore", "--list"])
        print("CI_SYNTHETIC_TRUNCATION_DENIED=PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
