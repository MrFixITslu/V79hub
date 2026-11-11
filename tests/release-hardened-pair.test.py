#!/usr/bin/env python3
"""Self-contained export, custody/freshness and production-scope refusal tests."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('release',Path(__file__).parents[1]/'scripts/release-hardened-pair.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ReleaseTests(unittest.TestCase):
    def test_remote_refusal_keeps_exact_stage_without_raw_output(self):
        result=types.SimpleNamespace(returncode=2,stdout=b'{"status":"BLOCKED","reason":"SEALED_MODEL_ROUNDTRIP_CHANGED"}',
                                     stderr=b'synthetic-secret-must-not-print')
        with patch.object(m.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(m.Refused,'REMOTE_SEALED_MODEL_ROUNDTRIP_CHANGED'):m.call(['synthetic'])
        result.stdout=b'{"status":"BLOCKED","reason":"secret=synthetic-only"}'
        with patch.object(m.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(m.Refused,'COMMAND_FAILED_REDACTED'):m.call(['synthetic'])

    def test_exported_sources_are_byte_identical(self):
        self.assertEqual(len(m.SOURCES),5)
        for filename,source in m.SOURCES.items():
            self.assertEqual(source,Path(m.__file__).with_name(filename).read_text())

    def test_checkpoint_window_rejects_expired_or_future_capture(self):
        now=datetime.datetime.now(datetime.timezone.utc)
        for hours in (-1,5):
            created=now-datetime.timedelta(hours=hours)
            with self.assertRaisesRegex(m.Refused,'FOUR_HOUR_RELEASE_WINDOW'):
                m.fresh({'created_at':created.isoformat(),'verified_at':now.isoformat()})

    def test_server_hostname_guard_precedes_any_docker_call(self):
        with patch.object(m.socket,'gethostname',return_value='unrelated-host'),patch.object(m,'call') as call:
            with self.assertRaises(m.Refused):m.server_root()
            call.assert_not_called()

    def test_remote_directory_rejects_recovery_and_traversal(self):
        for value in ('/tmp/pair-test','/home/firelion/.v79-step2-checkpoints/s2-test',
            '/home/firelion/.v79-hardened-pair-releases/../pair-20261025T000000Z-aaaaaaaaaaaa'):
            with self.assertRaises(m.Refused):m.remote_directory(value)

    def test_reports_never_forward_unknown_exception_or_secret_value(self):
        self.assertEqual(m.safe_reason(ValueError('synthetic-secret')), 'RELEASE_BLOCKED_REDACTED')
        self.assertEqual(m.safe_reason(m.Refused('bad secret=value')), 'RELEASE_BLOCKED_REDACTED')
        self.assertEqual(m.safe_reason(m.Refused('HOST_FIELDS_CHANGED:Memory')), 'HOST_FIELDS_CHANGED:Memory')

    def fixture(self,home):
        root=home/'V79-Portfolio-Checkpoints'/m.CHECKPOINT;root.mkdir(parents=True)
        names={'protected-images.tar.gpg','runtime-and-config.tar.gpg','private-host-state.tar.gpg',
               'tiquet-postgres.dump.gpg','v79-hub-postgres.dump.gpg'}
        names.update(n+'-mount-'+str(i)+'.tar.gpg' for n,count in
            [('v79-hub',7),('v79-tiquet-manager',2),('v79-business-agent',1)] for i in range(count))
        now=datetime.datetime.now(datetime.timezone.utc).isoformat()
        manifest={'audit':'V79_RELEASE_WINDOW_CHECKPOINT_V1','apps_resumed_same_ids':True,
            'recipient_fingerprint':'484CF39CE37A02884497AD9C41A17102D2842ECE',
            'created_at':now,'images':{},'files':[]}
        for name in names:
            m.write_new(root/name,b'ciphertext fixture')
            manifest['files'].append({'name':name,'bytes':18,'sha256':'a'*64})
        m.write_new(root/'manifest.json',manifest)
        receipt={'audit':'V79_RELEASE_WINDOW_OFFHOST_CUSTODY_V1',
            'manifest_sha256':m.sha(root/'manifest.json'),'verified_at':now,
            'files':[{'name':name,'plaintext_bytes':10,'plaintext_sha256':'b'*64} for name in names]}
        m.write_new(root/'offhost-verified-test.json',receipt)
        return root,receipt

    def test_complete_custody_receipt_is_required_and_bound_to_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);root,receipt=self.fixture(home)
            backup=m.custody(home)
            self.assertEqual(backup['manifest_sha256'],m.sha(root/'manifest.json'))
            receipt['files'].pop()
            (root/'offhost-verified-test.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(m.Refused,'CUSTODY_INCOMPLETE'):m.custody(home)

    def test_changed_or_missing_checkpoint_artifact_stops_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);root,_=self.fixture(home)
            (root/'runtime-and-config.tar.gpg').write_bytes(b'changed length')
            with self.assertRaisesRegex(m.Refused,'ARTIFACT_UNAVAILABLE'):m.custody(home)

    def test_ambiguous_duplicate_custody_receipts_are_not_silently_selected(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);root,receipt=self.fixture(home)
            m.write_new(root/'offhost-verified-second.json',receipt)
            with self.assertRaisesRegex(m.Refused,'EXACT_CUSTODY_RECEIPT_REQUIRED'):m.custody(home)


if __name__=='__main__':unittest.main()
