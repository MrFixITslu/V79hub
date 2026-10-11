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
recovery_spec = importlib.util.spec_from_file_location('recovery_preflight', ROOT/'scripts/recovery-preflight.py')
recovery = importlib.util.module_from_spec(recovery_spec)
recovery_spec.loader.exec_module(recovery)

class AuditTests(unittest.TestCase):
    def test_recovery_mapping_requires_named_container_address_database_port_and_read_only(self):
        app={'addr':'192.0.2.1','db':'synthetic','port':5432,'version':'17','ro':'on'}
        target={k:v for k,v in app.items() if k!='addr'}
        container={'NetworkSettings':{'Networks':{'isolated':{'IPAddress':'192.0.2.1'}}}}
        self.assertTrue(recovery.mapping_matches(app,target,container))
        for key,value in [('addr','192.0.2.2'),('db','wrong'),('port',5433),('version','16'),('ro','off')]:
            self.assertFalse(recovery.mapping_matches({**app,key:value},target,container))
        self.assertFalse(recovery.mapping_matches(None,target,container))
        self.assertFalse(recovery.mapping_matches({k:v for k,v in app.items() if k!='db'},
            {k:v for k,v in target.items() if k!='db'},container))

    def test_recovery_database_probe_quotes_synthetic_credentials_and_uses_read_only_sql(self):
        import os
        with tempfile.TemporaryDirectory(prefix='v79-recovery-shell-') as directory:
            stub=Path(directory)/'psql'
            stub.write_text('''#!/usr/bin/env python3
import os,sys,json
assert os.environ['PGPASSWORD']==os.environ['SYNTHETIC_EXPECTED']
assert sys.argv[sys.argv.index('-U')+1]=='fixture role'
assert sys.argv[sys.argv.index('-d')+1]=='fixture db'
sql=sys.argv[sys.argv.index('-c')+1]
assert sql.startswith('BEGIN READ ONLY;') and sql.endswith('ROLLBACK;')
print(json.dumps({'fixture_passed':True}))
''')
            stub.chmod(0o700)
            synthetic='synthetic $ ; " space credential'
            result=subprocess.run(['sh','-s'],input=recovery.DB_PROBE,text=True,capture_output=True,
                timeout=5,env={**os.environ,'PATH':directory+':'+os.environ['PATH'],
                'POSTGRES_USER':'fixture role','POSTGRES_DB':'fixture db',
                'POSTGRES_PASSWORD':synthetic,'SYNTHETIC_EXPECTED':synthetic})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['fixture_passed'])
            self.assertNotIn(synthetic,result.stdout+result.stderr)

    def test_recovery_resource_thresholds_fail_closed(self):
        good=recovery.resource_checks(2*1024**3,10*1024**3,[1024**3],['gpg'])
        self.assertTrue(all(good[k] for k in ('memory_ok','disk_ok','encryption_tool_available')))
        bad=recovery.resource_checks(1024**3,4*1024**3,[1024**3],[])
        self.assertFalse(any(bad[k] for k in ('memory_ok','disk_ok','encryption_tool_available')))

    def test_recovery_mapping_diagnostics_distinguish_unavailable_from_mismatch_without_values(self):
        app={'addr':'192.0.2.1','db':'PRIVATE_DATABASE_NAME','port':5432,'version':'17','ro':'on'}
        target={**app,'db':'PRIVATE_OTHER_DATABASE'}
        container={'NetworkSettings':{'Networks':{'isolated':{'IPAddress':app['addr']}}}}
        mismatch=recovery.mapping_checks(app,target,container)
        self.assertTrue(mismatch['app_metadata_probe_available'])
        self.assertTrue(mismatch['named_database_probe_available'])
        self.assertFalse(mismatch['database_name_matches'])
        self.assertTrue(mismatch['server_address_matches_named_container'])
        unavailable=recovery.mapping_checks(app,None,container)
        self.assertFalse(unavailable['named_database_probe_available'])
        for forbidden in (app['db'],target['db'],app['addr']):
            self.assertNotIn(forbidden,json.dumps(mismatch)+json.dumps(unavailable))

    def test_recovery_incomplete_database_size_is_explicit_and_does_not_pass(self):
        with patch.object(recovery,'capture',return_value=None), contextlib.redirect_stdout(io.StringIO()) as out:
            recovery.main()
        report=json.loads(out.getvalue())
        self.assertFalse(report['resources'].get('database_size_based_requirement_complete',False))
        self.assertFalse(report['preflight_checks_passed'])

    def test_recovery_unavailable_preflight_never_creates_resources_or_leaks_diagnostics(self):
        with patch.object(recovery,'capture',return_value=None) as call, contextlib.redirect_stdout(io.StringIO()) as out:
            recovery.main()
        report=json.loads(out.getvalue())
        self.assertFalse(report['preflight_checks_passed'])
        self.assertFalse(report['backup_created']);self.assertFalse(report['restore_performed'])
        for args in call.call_args_list:
            self.assertEqual(args.args[0][:2],['docker','inspect'])
        self.assertNotIn('customer',recovery.DB_PROBE)
        self.assertIn('BEGIN READ ONLY',recovery.APP_PROBE)
        self.assertIn('BEGIN READ ONLY',recovery.DB_PROBE)
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

    def test_database_identity_checks_execute_against_exact_schema_column_names(self):
        # Exercise the actual helper using catalog fixtures, never a live DB.
        for linked in (True, False):
            cols = [{'table_name':t,'column_name':'id'} for t in ('accounts','users','jobs')]
            if linked:
                cols += [{'table_name':'accounts','column_name':'hub_organization_id'},
                         {'table_name':'users','column_name':'hub_user_id'}]
            stub = '''const catalog = CATALOG;
const pg = {Client: class {
 async connect() {} async end() {}
 async query(sql) {
  if(sql === 'BEGIN READ ONLY' || sql === 'ROLLBACK') return {rows:[]};
  if(sql === 'SHOW server_version') return {rows:[{server_version:'fixture'}]};
  if(sql === 'SHOW transaction_read_only') return {rows:[{transaction_read_only:'on'}]};
  if(sql.includes('FROM information_schema.columns')) return {rows:catalog};
  if(sql.includes('FROM pg_indexes')) return {rows:[]};
  throw new Error('Noncatalog query rejected');
 }
}};'''.replace('CATALOG',json.dumps(cols))
            code = mod.DB_HELPER.replace("import pg from 'pg';",stub)
            result = subprocess.run(['node','--input-type=module','-'],input=code,
                capture_output=True,text=True,timeout=10,env={'PATH':__import__('os').environ['PATH'],
                'V79_AUDIT_APP':'tiquet'})
            self.assertEqual(result.returncode,0,result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['checks']['hub_account_link'],linked)
            self.assertEqual(report['checks']['hub_user_link'],linked)
            self.assertEqual(report['migration_applied'],'UNVERIFIED')
            self.assertEqual(report['customer_rows_read'],0)

    def test_pinned_release_reference_does_not_checkout_fetch_or_relabel_working_tree(self):
        ref = 'd'*40
        responses = [ref+'\n','100644 blob '+'b'*40+'\tserver.ts\0','c'*40+'\n']
        with patch.object(mod,'run',side_effect=responses) as run:
            report = mod.repo_evidence(Path('/synthetic/repo'),ref)
        self.assertEqual(report['commit'],ref)
        self.assertIsNone(report['tracked_status_entries'])
        self.assertEqual(run.call_args_list[0].args[0][-1],ref+'^{commit}')
        for call in run.call_args_list:
            self.assertNotIn('checkout',call.args[0]);self.assertNotIn('fetch',call.args[0])
        with patch.object(mod,'run') as run:
            self.assertFalse(mod.repo_evidence(Path('/synthetic/repo'),'invalid')['repository'])
        run.assert_not_called()

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
            css = b'/* public synthetic style */\n'
            (root/'server/style.css').write_bytes(css)
            (root/'server/.env').write_text('PRIVATE_VALUE=never-read-this')
            (root/'data/customer.json').write_text('never-read-customer-data')
            outside = root/'private-source.mjs'
            outside.write_text('never-read-symlink-target')
            (root/'server/link.mjs').symlink_to(outside)
            payload = mod.SOURCE_HELPER.replace("'/app'", json.dumps(str(root)))
            result = subprocess.run(['node','-e',payload],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(list(data['source']),['server/auth.mjs','server/style.css'])
            expected = hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
            self.assertEqual(data['source']['server/auth.mjs']['git'],expected)
            css_blob = hashlib.sha1(b'blob '+str(len(css)).encode()+b'\0'+css).hexdigest()
            self.assertEqual(data['source']['server/style.css']['git'],css_blob)
            self.assertEqual(data['symlinks'],['server/link.mjs'])
            for forbidden in ('never-read-this','never-read-customer-data','never-read-symlink-target'):
                self.assertNotIn(forbidden,result.stdout)

if __name__ == '__main__': unittest.main()
