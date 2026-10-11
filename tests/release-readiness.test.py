import contextlib
import importlib.util
import io
import json
import hashlib
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_readiness', ROOT/'scripts/release-readiness.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class AuditTests(unittest.TestCase):
    def test_unavailable_docker_fails_closed_and_redacts_diagnostics(self):
        with patch.object(mod, 'run', return_value=None):
            report = mod.audit({})
        self.assertEqual(report['production'], 'NO-GO')
        self.assertEqual(report['apps']['hub']['inspection'], 'UNAVAILABLE')
        self.assertFalse(report['live_restore_test_performed'])
        self.assertEqual(report['database_containers']['tiquet-postgres']['inspection'],'UNAVAILABLE')

    def test_capture_never_returns_failure_output_or_credentials(self):
        result = type('Result', (), {'returncode':1, 'stdout':'secret-credential', 'stderr':'postgres://private'})()
        with patch.object(mod.subprocess, 'run', return_value=result):
            self.assertIsNone(mod.run(['docker','inspect','v79-hub']))

    def test_env_command_labels_health_logs_and_customer_data_do_not_leak(self):
        secret = 'DO_NOT_DISCLOSE_PRIVATE_VALUE'
        container = {'Id':'a'*64, 'Image':'sha256:'+'b'*64,
          'Config':{'Image':'reviewed-image:tag','Env':['JWT_SECRET='+secret,'DATABASE_URL='+secret,
            'V79_REQUIRE_ADMIN_MFA=1'], 'Cmd':['node',secret], 'User':'1000',
            'Labels':{'unsafe-label':secret}}, 'HostConfig':{}, 'Mounts':[],
          'State':{'Status':'running','Health':{'Status':'healthy','Log':[{'Output':secret}]}},
          'NetworkSettings':{'Networks':{'proxy_network':{}}}}
        calls = []
        def fake(args, input_text=None, timeout=25):
            calls.append(args)
            if args[:2] == ['docker','inspect']:
                return json.dumps([container])
            if args[:3] == ['docker','image','inspect']:
                return json.dumps([{'Id':container['Image'],'RepoDigests':[], 'Config':{'Labels':{'secret':secret}}}])
            if args[:2] == ['docker','exec'] and mod.SOURCE_HELPER in args:
                return json.dumps({'source':{},'dist_files':0,'dist_sha256':'x','markers':{}})
            if args[:2] == ['docker','exec'] and input_text is None:
                self.assertIn('http://127.0.0.1:', args[-1])
                self.assertNotIn('r.text()', args[-1])
                self.assertNotIn('r.json()', args[-1])
                return json.dumps({'http_status':200,'ok':True})
            if args[:2] == ['docker','exec']:
                self.assertEqual(input_text, mod.DB_HELPER)
                return json.dumps({'transaction_read_only':'on','customer_rows_read':0,'migration_applied':'UNVERIFIED'})
            return None
        with patch.object(mod, 'run', side_effect=fake):
            report = mod.audit({})
        self.assertNotIn(secret, json.dumps(report))
        self.assertEqual(report['apps']['hub']['flags_at_container_creation']['V79_REQUIRE_ADMIN_MFA'], 'ON')
        self.assertFalse(report['apps']['hub']['application_dotenv_overlay_verified'])
        self.assertFalse(report['database_containers']['v79-hub-postgres']['application_mapping_verified'])
        for args in calls:
            self.assertTrue(args[0] in ('docker','git'))
            if args[0] == 'docker':
                self.assertIn(args[1], ('inspect','image','exec','ps'))

    def test_complete_manifest_reports_missing_different_and_extra_files(self):
        result = mod.compare({'server.ts':{'git':'changed'},'server/new.mjs':{'git':'new'}},
                             {'server.ts':'expected','server/auth.mjs':'preserve'})
        self.assertEqual(result['different'], ['server.ts'])
        self.assertEqual(result['missing'], ['server/auth.mjs'])
        self.assertEqual(result['extra_runtime_source'], ['server/new.mjs'])
        self.assertFalse(result['build_attestation_verified'])

    def test_tiquet_packaging_does_not_call_unshipped_frontend_source_a_regression(self):
        result = mod.compare({'server/index.js':{'git':'ok'}},
                             {'server/index.js':'ok','src/App.tsx':'built-in-dist'},True)
        self.assertEqual(result['missing'], [])
        self.assertEqual(result['matching'], 1)

    def test_database_probe_avoids_application_initialization_and_is_read_only(self):
        self.assertIn("await client.query('BEGIN READ ONLY')", mod.DB_HELPER)
        self.assertIn('default_transaction_read_only=on', mod.DB_HELPER)
        self.assertNotIn("import './server", mod.DB_HELPER)
        self.assertNotIn("from './db", mod.DB_HELPER)
        self.assertIn("migration_applied:'UNVERIFIED'", mod.DB_HELPER)

    def test_apply_mode_is_rejected_before_any_command(self):
        with patch.object(mod, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): mod.main(['apply'])
        run.assert_not_called()

    def test_repo_status_does_not_read_untracked_files_or_refresh_git_index(self):
        responses = ['a'*40+'\n','100644 blob '+'b'*40+'\tserver.ts\0','','c'*40+'\n']
        with patch.object(mod, 'run', side_effect=responses) as run:
            report = mod.repo_evidence(Path('/synthetic/repo'))
        self.assertEqual(report['files']['server.ts'], 'b'*40)
        self.assertIn('--untracked-files=no', run.call_args_list[2].args[0])

    def test_source_probe_excludes_secrets_data_and_symlink_targets(self):
        self.assertIn("n.startsWith('.env')", mod.SOURCE_HELPER)
        self.assertIn("'data','uploads','logs','backups','.git'", mod.SOURCE_HELPER)
        self.assertIn('st.isSymbolicLink()', mod.SOURCE_HELPER)
        self.assertNotIn('readFileSync(secret', mod.SOURCE_HELPER)

    def test_real_hash_probe_on_synthetic_files_does_not_read_env_data_or_symlinks(self):
        with tempfile.TemporaryDirectory(prefix='v79-audit-fixture-') as directory:
            root = Path(directory)
            (root/'server').mkdir()
            (root/'data').mkdir()
            content = b'// reviewed synthetic auth source\n'
            (root/'server/auth.mjs').write_bytes(content)
            (root/'server/.env').write_text('PRIVATE_VALUE=never-read-this')
            (root/'data/customer.json').write_text('never-read-customer-data')
            outside = root/'private-source.mjs'
            outside.write_text('never-read-symlink-target')
            (root/'server/link.mjs').symlink_to(outside)
            payload = mod.SOURCE_HELPER.replace("'/app'", json.dumps(str(root)))
            result = subprocess.run(['node','-e',payload],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(list(data['source']),['server/auth.mjs'])
            expected = hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
            self.assertEqual(data['source']['server/auth.mjs']['git'],expected)
            self.assertEqual(data['symlinks'],['server/link.mjs'])
            for forbidden in ('never-read-this','never-read-customer-data','never-read-symlink-target'):
                self.assertNotIn(forbidden,result.stdout)

if __name__ == '__main__': unittest.main()
