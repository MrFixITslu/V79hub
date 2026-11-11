#!/usr/bin/env python3
"""Real GPG pipeline tests in a disposable local keyring. No Docker or SSH."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('checkpoint',
    Path(__file__).parents[1]/'scripts/capture-release-checkpoint.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)


class RealEncryption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.keyring=cls.root/'keys';cls.keyring.mkdir(mode=0o700)
        subprocess.run(['gpg','--homedir',str(cls.keyring),'--batch','--pinentry-mode',
            'loopback','--passphrase','','--quick-generate-key',
            'V79 disposable checkpoint test <synthetic@example.invalid>',
            'rsa2048','encr','1d'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        raw=subprocess.check_output(['gpg','--homedir',str(cls.keyring),
            '--batch','--with-colons','--fingerprint'],stderr=subprocess.DEVNULL).decode()
        cls.fingerprint=next(line.split(':')[9] for line in raw.splitlines() if line.startswith('fpr:'))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['gpgconf','--homedir',str(cls.keyring),'--kill','gpg-agent'],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.temp.cleanup()

    def test_real_stream_encrypts_and_offhost_decrypts_without_plaintext_file(self):
        target=self.root/'stream.gpg'
        with patch.object(m,'RECIPIENT',self.fingerprint),patch.dict(os.environ,{'GNUPGHOME':str(self.keyring)}):
            m.encrypted_stream([sys.executable,'-c','import sys;sys.stdout.buffer.write(b"synthetic-only"*1000)'],
                               target,self.keyring,30)
            proof=m.decrypt_validate(target)
        self.assertEqual(proof['plaintext_bytes'],14000)
        self.assertNotIn(b'synthetic-only',target.read_bytes())
        self.assertEqual(target.stat().st_mode&0o777,0o600)

    def test_tampered_ciphertext_never_passes_custody(self):
        target=self.root/'tampered.gpg'
        with patch.object(m,'RECIPIENT',self.fingerprint),patch.dict(os.environ,{'GNUPGHOME':str(self.keyring)}):
            m.encrypted_bytes(b'synthetic-secret',target,self.keyring,30)
            raw=bytearray(target.read_bytes());raw[-8]^=1;target.write_bytes(raw)
            with self.assertRaises(m.Halt):m.decrypt_validate(target)

    def test_failed_dump_producer_is_rejected_even_if_gpg_succeeds(self):
        with patch.object(m,'RECIPIENT',self.fingerprint):
            with self.assertRaisesRegex(m.Halt,'CAPTURE_PRODUCER_FAILED'):
                m.encrypted_stream([sys.executable,'-c',
                    'import sys;sys.stdout.buffer.write(b"partial");sys.exit(2)'],
                    self.root/'failed-producer.gpg',self.keyring,30)

    def test_release_namespace_excludes_original_recovery_destinations(self):
        import re
        self.assertEqual(m.RECIPIENT,'484CF39CE37A02884497AD9C41A17102D2842ECE')
        self.assertNotEqual(m.ROOT,Path('/home/firelion/.v79-step2-checkpoints'))
        self.assertIsNone(re.fullmatch(m.REMOTE_RE,
            '/home/firelion/.v79-step2-checkpoints/s2-20261022T182118Z-4fc56843'))
        self.assertIn('firelion@192.168.100.163',m.SSH)


if __name__=='__main__':unittest.main()
