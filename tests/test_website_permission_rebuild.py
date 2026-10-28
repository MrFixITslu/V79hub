import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('rebuild', Path(__file__).parents[1] / 'scripts/rebuild-website-runtime-permissions.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class RebuildTests(unittest.TestCase):
    def test_access_check_uses_image_user_without_network_or_writable_filesystem(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return b'{"mode":"600","readable":false,"error":"EACCES"}'
        self.assertFalse(r.access(run, r.OLD_IMAGE)['readable'])
        args = calls[0]
        self.assertEqual(args[args.index('--network') + 1], 'none')
        self.assertEqual(args[args.index('--workdir') + 1], '/')
        self.assertIn('--read-only', args)
        self.assertNotIn('--user', args)
        self.assertNotIn('--mount', args)

    def test_unconfirmed_package_defect_stops_before_source_fetch_or_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lead-release-state.json').write_text('{"phase":"ROLLED_BACK"}')
            rows = [{'Name': name, 'Id': name, 'Image': 'old',
                     'State': {'Running': True, 'StartedAt': 'same', 'Health': {'Status': 'healthy'}}}
                    for name in ('v79-hub', 'V79website')]
            stdout = io.StringIO()
            with patch.object(r, 'ROOT', root), \
                 patch.object(r.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(rows).encode())) as run, \
                 patch.object(r, 'access', return_value={'readable': True}), contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    r.main()
            self.assertEqual(run.call_count, 1)
            self.assertIn('PACKAGE_ACCESS_CAUSE_NOT_CONFIRMED_NO_BUILD', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
