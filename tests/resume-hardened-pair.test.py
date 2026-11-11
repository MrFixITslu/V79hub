#!/usr/bin/env python3
"""Exact partial-transfer regression and integrity/refusal boundary tests."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('resume',Path(__file__).parents[1]/'scripts/resume-hardened-pair.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ResumeTests(unittest.TestCase):
    def test_exact_production_size_regression_resumes_only_the_missing_tail(self):
        offset=203423744;missing=m.INNER_BYTES-offset
        self.assertEqual(missing,1065038)
        self.assertGreater(m.INNER_BYTES,203470115)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'accepted-images.tar.gz'
            with path.open('wb') as f:f.truncate(offset)
            path.chmod(0o600)
            prefix=m.sha(path);tail=b'x'*missing
            h=hashlib.sha256()
            with path.open('rb') as f:
                for block in iter(lambda:f.read(1024**2),b''):h.update(block)
            h.update(tail)
            count=m.complete_transfer(path,io.BytesIO(tail),expected_size=m.INNER_BYTES,
                expected_sha256=h.hexdigest(),offset=offset,prefix_sha256=prefix)
            self.assertEqual(count,1065038)
            self.assertEqual(path.stat().st_size,m.INNER_BYTES)
            self.assertEqual(m.sha(path),h.hexdigest())

    def fixture(self,root):
        path=root/'partial';path.write_bytes(b'accepted-prefix');path.chmod(0o600)
        full=b'accepted-prefix-and-tail'
        return path,full,{'expected_size':len(full),'expected_sha256':hashlib.sha256(full).hexdigest(),
                          'offset':len(b'accepted-prefix'),'prefix_sha256':m.sha(path)}

    def test_mismatched_prefix_never_appends_or_truncates(self):
        with tempfile.TemporaryDirectory() as temp:
            p,full,args=self.fixture(Path(temp));args['prefix_sha256']='0'*64
            with self.assertRaisesRegex(m.Refused,'PREFIX_HASH_MISMATCH'):
                m.complete_transfer(p,io.BytesIO(b'-and-tail'),**args)
            self.assertEqual(p.read_bytes(),b'accepted-prefix')

    def test_short_transfer_keeps_verified_progress_without_accepting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            p,full,args=self.fixture(Path(temp))
            with self.assertRaisesRegex(m.Refused,'STREAM_ENDED_EARLY'):
                m.complete_transfer(p,io.BytesIO(b'-and'),**args)
            self.assertEqual(p.read_bytes(),b'accepted-prefix-and')

    def test_extra_bytes_never_extend_the_file_past_the_expected_size(self):
        with tempfile.TemporaryDirectory() as temp:
            p,full,args=self.fixture(Path(temp))
            with self.assertRaisesRegex(m.Refused,'STREAM_EXCEEDS'):
                m.complete_transfer(p,io.BytesIO(b'-and-tail-extra'),**args)
            self.assertEqual(p.read_bytes(),full)

    def test_wrong_final_hash_does_not_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            p,full,args=self.fixture(Path(temp));args['expected_sha256']='f'*64
            with self.assertRaisesRegex(m.Refused,'COMPLETE_ARCHIVE_HASH_MISMATCH'):
                m.complete_transfer(p,io.BytesIO(b'-and-tail'),**args)

    def test_completed_archive_can_be_verified_without_retransmission(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'full';p.write_bytes(b'already complete');p.chmod(0o600)
            n=m.complete_transfer(p,io.BytesIO(),expected_size=p.stat().st_size,
                expected_sha256=m.sha(p),offset=p.stat().st_size,prefix_sha256=m.sha(p))
            self.assertEqual(n,0)

    def test_shared_hardlinked_or_symlink_artifacts_are_rejected(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p,full,args=self.fixture(root)
            p.chmod(0o644)
            with self.assertRaisesRegex(m.Refused,'ARTIFACT_CHANGED'):m.complete_transfer(p,io.BytesIO(),**args)
            p.chmod(0o600);link=root/'link';link.symlink_to(p)
            with self.assertRaises(OSError):m.complete_transfer(link,io.BytesIO(),**args)
            os.link(p,root/'hard')
            with self.assertRaisesRegex(m.Refused,'ARTIFACT_CHANGED'):m.complete_transfer(p,io.BytesIO(),**args)

    def test_server_host_guard_precedes_original_code_import(self):
        with patch.object(m.socket,'gethostname',return_value='not-v79sl'),patch.object(m,'original') as original:
            with self.assertRaisesRegex(m.Refused,'V79SL_ONLY'):m.guard(types.SimpleNamespace(helper_sha256='x'))
            original.assert_not_called()

    def test_original_runner_and_existing_plan_pins_cannot_drift(self):
        original=Path(m.__file__).with_name('release-hardened-pair.py')
        self.assertEqual(m.sha(original),m.ORIGINAL_SHA)
        self.assertEqual(m.PLAN_SHA,'4ca27746c1296d359c550eb0351105d98cfc6f8d8d021970ba026062719e89c5')

    def test_loader_error_is_classified_without_exposing_stderr(self):
        p=types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'no space left synthetic-secret')
        with patch.object(m.subprocess,'run',return_value=p):
            with self.assertRaisesRegex(m.Refused,'DOCKER_LOAD_DISK_FULL') as error:m.load_archive(Path('/synthetic'))
        self.assertNotIn('synthetic-secret',str(error.exception))


if __name__=='__main__':unittest.main()
