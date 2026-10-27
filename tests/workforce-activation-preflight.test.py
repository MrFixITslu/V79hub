import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'scripts/workforce-activation-preflight-20261027.py'
spec = importlib.util.spec_from_file_location('preflight', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PreflightTests(unittest.TestCase):
    def test_wrong_host_never_executes_any_command(self):
        with patch.object(m.socket, 'gethostname', return_value='synthetic-host'), patch.object(m, 'run') as run:
            with self.assertRaises(SystemExit):
                m.main()
            run.assert_not_called()

    def test_inspect_projects_no_environment_secrets_or_source_paths(self):
        info = {'Id': 'a'*64, 'Image': 'sha256:'+'b'*64, 'Config': {'Env': ['DATABASE_URL=never-emit-this', 'V79_WORKFORCE_ACTIONS_ENABLED=1']},
                'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                'Mounts': [{'Source': '/private/never-emit-this', 'Destination': '/run/secrets/v79-workforce-token', 'RW': False}]}
        calls = []
        def fake(args, **kwargs):
            calls.append(args)
            return json.dumps([info])
        with patch.object(m, 'run', side_effect=fake):
            result = m.inspect_containers()
        self.assertNotIn('never-emit-this', json.dumps(result))
        self.assertTrue(result['v79-hub']['worker_token_mount_readonly'])
        self.assertEqual(result['v79-hub']['flags']['V79_WORKFORCE_ACTIONS_ENABLED'], 'enabled')
        self.assertTrue(all(cmd[:2] == ['docker', 'inspect'] for cmd in calls))

    def test_symlink_latch_blocks_even_if_target_is_missing_and_status_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / '.local/share/v79-approved-task-worker'
            root.mkdir(parents=True)
            (root/'uncertain.json').symlink_to(root/'missing')
            (root/'status.json').write_text(json.dumps({'state':'succeeded','operation':'create_work_item','approvedDigest':'do-not-emit'}))
            (root/'status.json').chmod(0o600)
            result = m.worker_status(home)
            self.assertTrue(result['uncertainty_latch'])
            self.assertEqual(result['last_result'], 'succeeded')
            self.assertNotIn('do-not-emit', json.dumps(result))

    def test_embedded_node_audit_parses(self):
        self.assertEqual(subprocess.run(['node','--input-type=module','--check'],input=m.NODE_AUDIT,text=True,capture_output=True).returncode,0)

if __name__ == '__main__':
    unittest.main()
