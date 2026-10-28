"""Source/build sequencing checks; no Docker, GitHub or production access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('builder', Path(__file__).parents[1] /
    'scripts/build-website-lead-candidates.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuilderTest(unittest.TestCase):
    def exercise(self, fail_fetch=False):
        calls = []
        with tempfile.TemporaryDirectory(prefix='builder-unit-') as directory:
            output = io.StringIO()

            def fake_run(args, **kwargs):
                calls.append(args)
                stdout = b''
                if args[:2] == ['docker','inspect']:
                    stdout = json.dumps([{'Name':'/v79-hub','Id':'hub-live','Image':'hub-old'},
                        {'Name':'/V79website','Id':'website-live','Image':'website-old'}]).encode()
                elif args[:2] == ['git','init']:
                    Path(args[2]).mkdir()
                elif args[0] == 'git' and 'fetch' in args and fail_fetch:
                    raise subprocess.CalledProcessError(128,args)
                elif args[0] == 'git' and 'rev-parse' in args:
                    stdout = (builder.HUB if Path(args[2]).name == 'hub' else builder.WEBSITE).encode()
                elif args[:3] == ['docker','image','inspect']:
                    stdout = b'sha256:test-candidate'
                return subprocess.CompletedProcess(args,0,stdout=stdout)

            with patch.object(builder.tempfile,'mkdtemp',return_value=directory), \
                 patch.object(builder.subprocess,'run',side_effect=fake_run), \
                 contextlib.redirect_stdout(output):
                if fail_fetch:
                    with self.assertRaises(SystemExit): builder.main()
                else:
                    builder.main()
                    receipt = json.loads((Path(directory)/'receipt.json').read_text())
                    self.assertFalse(receipt['deployed'])
                    self.assertTrue(receipt['live_identities_unchanged'])
            for command in calls:
                if command[0] == 'git' and '-C' in command:
                    self.assertTrue(Path(command[2]).is_relative_to(Path(directory)))
                self.assertNotIn('/opt/v79/hub',command)
                self.assertNotIn('worktree',command)
            return calls, output.getvalue()

    def test_fresh_sources_and_only_two_candidate_tests(self):
        calls, _ = self.exercise()
        self.assertEqual(sum(c[:2] == ['docker','build'] for c in calls),2)
        tests = [c for c in calls if c[:2] == ['docker','run']]
        self.assertEqual(len(tests),2)
        self.assertTrue(all('--read-only' in c and '--test' in c for c in tests))
        self.assertTrue(all(c[c.index('--network')+1] == 'none' for c in tests))

    def test_failed_source_fetch_stops_before_any_image_build(self):
        calls, output = self.exercise(fail_fetch=True)
        self.assertFalse(any(c[:2] == ['docker','build'] for c in calls))
        self.assertIn('"stage": "hub_source"',output)
        self.assertIn('"deployed": false',output)


if __name__ == '__main__':
    unittest.main()
