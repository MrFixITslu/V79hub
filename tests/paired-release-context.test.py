#!/usr/bin/env python3
"""Failure-boundary tests with synthetic secrets; no Docker or network."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('context',
    Path(__file__).parents[1] / 'scripts/paired-release-context.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    apps = {}
    for name, old in m.contract().CURRENT.items():
        before = {'services': {name: {'image': old, 'environment': {
            'PRICE': '$12\n${literal}$$', 'SECRET': 'synthetic-test-only'}}}}
        candidate = copy.deepcopy(before)
        candidate['services'][name]['image'] = m.contract().CANDIDATE[name]
        apps[name] = {'before': before, 'candidate': candidate,
                      'rollback': copy.deepcopy(before),
                      'interpolation': {'FROZEN_PRICE': '$12\n${literal}$$'},
                      'ordered_inputs': [{'path': '/synthetic/source.yaml',
                        'content': 'synthetic\n',
                        'sha256': hashlib.sha256(b'synthetic\n').hexdigest()}]}
    return {'schema': m.SCHEMA, 'apps': apps}


class DurableContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.data = fixture()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        return m.save(self.path, 'release.json', self.data)

    def test_rollback_survives_absent_live_sources_and_exact_dollars(self):
        digest = self.save()
        self.assertFalse(Path('/synthetic/source.yaml').exists())
        self.assertEqual(m.load(self.path, 'release.json', digest), self.data)
        self.assertEqual((self.path / 'release.json').stat().st_mode & 0o777, 0o600)

    def test_existing_context_cannot_be_overwritten(self):
        digest = self.save()
        with self.assertRaises(FileExistsError):
            self.save()
        self.assertEqual(m.load(self.path, 'release.json', digest), self.data)

    def test_tampered_valid_json_rejected_by_external_digest(self):
        digest = self.save()
        p = self.path / 'release.json'
        p.write_bytes(p.read_bytes().replace(b'synthetic-test-only', b'changed-test-secret'))
        with self.assertRaisesRegex(m.Refused, 'EXTERNAL_DIGEST_MISMATCH'):
            m.load(self.path, 'release.json', digest)

    def test_unpinned_digest_rejected(self):
        self.save()
        with self.assertRaisesRegex(m.Refused, 'EXTERNAL_DIGEST_REQUIRED'):
            m.load(self.path, 'release.json', '')

    def test_model_security_drift_refused_before_write(self):
        self.data['apps']['v79-hub']['candidate']['services']['v79-hub']['privileged'] = True
        with self.assertRaisesRegex(m.Refused, 'MODEL_CONTRACT_FAILED'):
            self.save()
        self.assertEqual(list(self.path.iterdir()), [])

    def test_changed_source_bytes_rejected(self):
        self.data['apps']['v79-hub']['ordered_inputs'][0]['content'] += 'changed'
        with self.assertRaisesRegex(m.Refused, 'INPUT_INTEGRITY_FAILED'):
            self.save()

    def test_shared_permissions_rejected(self):
        digest = self.save()
        (self.path / 'release.json').chmod(0o644)
        with self.assertRaisesRegex(m.Refused, 'NOT_PRIVATE_REGULAR'):
            m.load(self.path, 'release.json', digest)

    def test_symlink_and_hardlink_context_rejected(self):
        digest = self.save()
        os.symlink(self.path / 'release.json', self.path / 'link.json')
        with self.assertRaises(OSError):
            m.load(self.path, 'link.json', digest)
        os.link(self.path / 'release.json', self.path / 'hard.json')
        with self.assertRaisesRegex(m.Refused, 'NOT_PRIVATE_REGULAR'):
            m.load(self.path, 'hard.json', digest)

    def test_directory_symlink_and_shared_directory_rejected(self):
        child = self.path / 'private'
        child.mkdir(mode=0o700)
        (self.path / 'link').symlink_to(child)
        with self.assertRaises(OSError):
            m.save(self.path / 'link', 'release.json', self.data)
        child.chmod(0o755)
        with self.assertRaisesRegex(m.Refused, 'DIRECTORY_NOT_PRIVATE'):
            m.save(child, 'release.json', self.data)

    def test_pipe_cannot_block_reader(self):
        os.mkfifo(self.path / 'pipe.json', 0o600)
        with self.assertRaisesRegex(m.Refused, 'NOT_PRIVATE_REGULAR'):
            m.load(self.path, 'pipe.json', '0' * 64)

    def test_scope_and_path_traversal_rejected(self):
        for name in ('../release.json', '/release.json', 'x/y.json'):
            with self.assertRaisesRegex(m.Refused, 'FILENAME_INVALID'):
                m.save(self.path, name, self.data)
        self.data['apps']['other'] = {}
        with self.assertRaisesRegex(m.Refused, 'SCOPE_INVALID'):
            self.save()


if __name__ == '__main__':
    unittest.main()
