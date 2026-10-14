"""Synthetic Docker failures and scope checks; never contacts the live server."""
import copy
import datetime
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]/'scripts/marketing-production-cutover-disabled.py'

def load():
    spec = importlib.util.spec_from_file_location('cutover', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class CutoverTest(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def test_full_configuration_scope_rejects_billing_credentials_mounts_and_other_services(self):
        m = self.m
        for name in m.SPECS:
            service = m.SPECS[name][1]
            before = {'services': {service: {'image': 'old', 'environment': {'BILLING': 'preserved'},
                'volumes': [{'source': 'original-data', 'target': '/app/data'}]},
                'unrelated': {'image': 'original'}}}
            additions = {'image': 'new', 'environment': {'V79_MARKETING_PRODUCTION_ENABLED': '0'}}
            after = copy.deepcopy(before)
            after['services'][service]['image'] = 'new'
            after['services'][service]['environment'].update(additions['environment'])
            if name == 'v79marketing-app':
                after['services'][service].update(mem_limit='805306368', cpus=1.0)
            m.configuration_parity(name, before, after, additions)
            for change in ('billing', 'socket', 'other-image', 'enabled'):
                bad = copy.deepcopy(after)
                if change == 'billing': bad['services'][service]['environment']['BILLING'] = 'changed'
                if change == 'socket': bad['services'][service]['volumes'].append({'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'})
                if change == 'other-image': bad['services']['unrelated']['image'] = 'changed'
                if change == 'enabled': bad['services'][service]['environment']['V79_MARKETING_PRODUCTION_ENABLED'] = '1'
                with self.assertRaises(RuntimeError): m.configuration_parity(name, before, bad, additions)

    def test_memory_normalization_does_not_allow_changed_or_unbounded_limits(self):
        m = self.m
        for good in (805306368, '805306368', '805306368b', '768m', '768MB', '768mib'):
            self.assertEqual(m.normalize_approved_memory({'services': {'x': {'mem_limit': good}}}, 'x')['services']['x']['mem_limit'], 805306368)
        for bad in (None, True, 0, 1073741824, '768', '1g', '805306368.0', '0'):
            with self.assertRaises(RuntimeError): m.normalize_approved_memory({'services': {'x': {'mem_limit': bad}}}, 'x')

    def test_health_probe_log_changes_do_not_hide_runtime_drift(self):
        m = self.m
        a = {'Id': 'id', 'Image': 'image', 'Config': {}, 'HostConfig': {}, 'Mounts': [],
             'State': {'StartedAt': 'fixed', 'Health': {'Log': ['old']}}, 'NetworkSettings': {'Networks': {'private': {}}}}
        b = copy.deepcopy(a); b['State']['Health']['Log'] = ['new']
        self.assertEqual(m.stable_runtime(a), m.stable_runtime(b))
        b['HostConfig']['Privileged'] = True
        self.assertNotEqual(m.stable_runtime(a), m.stable_runtime(b))

    def test_protected_file_rejects_symlink_and_world_readable_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'key'; path.write_text('synthetic'); path.chmod(0o600)
            self.m.file_hash(path, True)
            link = Path(directory)/'link'; link.symlink_to(path)
            with self.assertRaises(RuntimeError): self.m.file_hash(link, True)
            path.chmod(0o644)
            with self.assertRaises(RuntimeError): self.m.file_hash(path, True)

    def test_checkpoint_rejects_tampered_backup_keys_stale_or_missing_rehearsal(self):
        m = self.m
        with tempfile.TemporaryDirectory() as directory:
            m.RECOVERY = Path(directory)
            configuration = {path: m.FILES.get(path, 'f'*64) for path in
                m.HUB_FILES+m.MARKETING_FILES+['/opt/v79/hub/.env', '/home/firelion/V79Marketing/.env']}
            for name in m.BACKUPS|m.PREPARED:
                (m.RECOVERY/name).write_bytes(b'synthetic-private-checkpoint')
                (m.RECOVERY/name).chmod(0o600)
            receipt = {'candidateImage': m.CANDIDATE, 'candidateCommit': m.SHA,
                'marketingCandidateImage': m.MARKETING_CANDIDATE, 'marketingCandidateCommit': m.MARKETING_SHA,
                'runtimeImages': m.BASELINES, 'liveDeploymentPerformed': False,
                'capturedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'configurationHashes': configuration,
                'encryptedBackups': {name: m.file_hash(m.RECOVERY/name, True) for name in m.BACKUPS},
                'preparedOverlayHashes': {name: m.file_hash(m.RECOVERY/name, True) for name in m.PREPARED}}
            for flag in ('snapshotRestoreVerified', 'isolatedStartupRollbackVerified', 'copiedIdentityBillingPreserved',
                'scratchCleanupVerified', 'liveContainerIdsUnchanged', 'marketingOnlineBackupRestored',
                'marketingOriginalAndCandidateStartupVerified', 'marketingRollbackWithCopiedG3SchemaVerified',
                'pairedG3SignatureReplayAndPublishDisabledVerified', 'copiedG2AcceptedWorkItemPreserved'):
                receipt[flag] = True
            path = m.RECOVERY/'rehearsal-receipt.json'
            path.write_text(json.dumps(receipt)); path.chmod(0o600)
            (m.RECOVERY/'STATUS').write_text('ISOLATED_REHEARSAL_PASS_LIVE_DEPLOYMENT_NOT_PERFORMED\n')
            actual_hash = m.file_hash
            def hash_with_original_config(filename, private=False):
                if str(filename) in configuration: return configuration[str(filename)]
                return actual_hash(filename, private)
            with patch.object(m, 'file_hash', hash_with_original_config):
                m.verify_checkpoint()
                for name in ('hub-pg.dump.gpg', 'g3-protected-keys.json'):
                    target = m.RECOVERY/name; saved = target.read_bytes(); target.write_bytes(b'tampered')
                    with self.assertRaises(RuntimeError): m.verify_checkpoint()
                    target.write_bytes(saved)
                bad = copy.deepcopy(receipt)
                bad['capturedAt'] = (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=2)).isoformat()
                path.write_text(json.dumps(bad))
                with self.assertRaises(RuntimeError): m.verify_checkpoint()
                bad = copy.deepcopy(receipt); bad['pairedG3SignatureReplayAndPublishDisabledVerified'] = False
                path.write_text(json.dumps(bad))
                with self.assertRaises(RuntimeError): m.verify_checkpoint()

    def test_raw_docker_error_and_secret_arguments_are_withheld(self):
        m = self.m
        output = io.StringIO()
        result = types.SimpleNamespace(returncode=1, stderr=b'synthetic-secret-should-never-print', stdout=b'')
        with patch.object(m.subprocess, 'run', return_value=result), redirect_stdout(output):
            with self.assertRaises(RuntimeError) as failure: m.run(['docker', 'synthetic-secret-should-never-print'])
        self.assertNotIn('synthetic-secret', str(failure.exception)+output.getvalue())

    def simulate(self, fail_service=None, data_drift=False):
        m = self.m
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); m.WORK = root/'cutover'; m.RECOVERY = root/'recovery'; m.RECOVERY.mkdir()
        m.BUILD_RECEIPT = root/'build.json'
        (m.RECOVERY/'rehearsal-receipt.json').write_text('{}')
        old, original, overlays, image_metadata = {}, {}, {}, {}
        image_env = ['NODE_ENV=production', 'NODE_VERSION=22.synthetic', 'PATH=/usr/local/bin']
        for name, digest in m.BASELINES.items():
            old[name] = {'Id': 'old-'+name, 'Image': digest, 'State': {'Running': True, 'StartedAt': 'fixed', 'Health': {'Status': 'healthy'}},
                'Config': {'Labels': {}, 'Env': image_env}, 'HostConfig': {'Memory': 0, 'NanoCpus': 0},
                'Mounts': [{'Type': 'volume', 'Name': name+'-data', 'Source': '/data/'+name, 'Destination': '/app/data', 'RW': True}],
                'NetworkSettings': {'Networks': {'private': {}}}}
            image_metadata[digest] = {'Id': digest, 'Config': {'Env': image_env}}
        for name, (project, service, working, files, filename, image, commit) in m.SPECS.items():
            old[name]['Config']['Labels'] = {'com.docker.compose.project': project, 'com.docker.compose.service': service,
                'com.docker.compose.project.working_dir': working, 'com.docker.compose.project.config_files': ','.join(files)}
            environment = {}
            if name == 'v79-hub':
                environment = {'V79_WORKFORCE_ACTIONS_ENABLED': '1', 'V79_WORKFORCE_AUDIT_KEY': 'a'*64,
                               'V79_WORKFORCE_TOKEN_FILE': '/run/secrets/v79-workforce-token'}
            old[name]['Config']['Env'] = image_env+[k+'='+v for k, v in environment.items()]
            original[name] = {'services': {service: {'image': m.BASELINES[name], 'environment': environment}}}
            overlays[name] = {'image': image, 'environment': {'V79_MARKETING_PRODUCTION_ENABLED': '0',
                'V79_MARKETING_PRODUCTION_SHARED_SECRET': 'b'*64}}
            if name == 'v79marketing-app':
                overlays[name].update(mem_limit=805306368, cpus=1.0)
                overlays[name]['environment']['V79_MARKETING_PRODUCTION_PUBLISH_ENABLED'] = '0'
            image_metadata[image] = {'Id': image, 'Config': {'Env': image_env, 'Labels': {'org.opencontainers.image.revision': commit}}}
        live = copy.deepcopy(old)
        desired = copy.deepcopy(original)
        for name, overlay in overlays.items():
            service = m.SPECS[name][1]
            desired[name]['services'][service]['image'] = overlay['image']
            desired[name]['services'][service]['environment'].update(overlay['environment'])
            if name == 'v79marketing-app': desired[name]['services'][service].update(mem_limit='805306368', cpus=1.0)
        build = {'live_identity_unchanged': True, 'deployment_performed': False,
            'live_containers': {name: {'id': meta['Id'], 'started_at': 'fixed'} for name, meta in old.items()},
            'candidates': {repo: {'image': m.SPECS[name][5], 'commit': m.SPECS[name][6]}
                for name, repo in [('v79-hub', 'V79hub'), ('v79marketing-app', 'V79Marketing')]}}
        m.BUILD_RECEIPT.write_text(json.dumps(build))
        marketing_state = {'digest': 'unchanged', 'productionLedgerDigest': None,
            'founderLinks': [{'businessId': m.OWNER_ORG, 'organizationId': m.OWNER_ORG, 'scopedHubUserId': m.OWNER_SCOPED_ID}],
            'ownerConnectedPlatforms': [{'platform': 'youtube', 'connected': 1, 'tokenRecords': 1}]}
        receipt = {'configurationHashes': {}, 'preparedOverlayHashes': {}, 'ownerConnectedPlatforms': marketing_state['ownerConnectedPlatforms']}
        calls = []
        def fake_run(args, data=None, timeout=60, **_kw):
            if args[:3] == ['docker', 'image', 'inspect']:
                return json.dumps([image_metadata[args[3]]]).encode()
            if args[:3] == ['docker', 'image', 'tag']: return b''
            self.assertEqual(args[:2], ['docker', 'compose'])
            name = next(name for name, spec in m.SPECS.items() if spec[1] == args[-1])
            marker = m.WORK/('switch-attempted-'+name+'.json')
            self.assertTrue(marker.is_file(), 'Attempt marker must be durable before mutation')
            self.assertNotIn('--build', args); self.assertIn('--no-deps', args); self.assertIn('--no-build', args)
            self.assertEqual(args[args.index('--pull')+1], 'never')
            calls.append(name)
            if fail_service == name: raise RuntimeError('Synthetic Docker failure')
            meta = live[name]; meta['Id'] = 'new-'+name; meta['Image'] = m.SPECS[name][5]
            meta['Config']['Env'] += [k+'='+v for k, v in overlays[name]['environment'].items()]
            meta['Config']['Labels']['com.docker.compose.project.config_files'] += ','+str(m.RECOVERY/m.SPECS[name][4])
            if name == 'v79marketing-app': meta['HostConfig'].update(Memory=805306368, NanoCpus=1000000000)
            return b''
        def sqlite(_name):
            value = copy.deepcopy(marketing_state)
            if data_drift and calls: value['digest'] = 'changed-during-rollout'
            return value
        error = None
        with ExitStack() as stack:
            for target, replacement in [
                ('socket.gethostname', lambda: 'v79sl'), ('pwd.getpwuid', lambda _uid: types.SimpleNamespace(pw_name='firelion')),
                ('os.getuid', lambda: 1000), ('shutil.which', lambda _command: '/synthetic/docker'),
                ('verify_checkpoint', lambda: receipt), ('verify_files', lambda _r: None),
                ('approved_overlays', lambda: overlays), ('inspect', lambda name: copy.deepcopy(live[name])),
                ('resolve_stack', lambda name, _files, extra=(): copy.deepcopy(desired[name] if extra else original[name])),
                ('protected_state', lambda _db: 'unchanged'), ('sqlite_state', sqlite), ('probe_live', lambda: None),
                ('run', fake_run), ('file_hash', lambda path, private=False: m.fingerprint(Path(path).read_text())),
                ('subprocess.run', lambda *_args, **_kw: types.SimpleNamespace(returncode=1, stderr=b'No such image'))]:
                stack.enter_context(patch_target(m, target, replacement))
            with redirect_stdout(io.StringIO()):
                try: m.main()
                except RuntimeError as exc: error = exc
        return m, calls, error

    def test_success_switches_only_two_apps_and_keeps_flags_off(self):
        m, calls, error = self.simulate()
        self.assertIsNone(error, str(error))
        self.assertEqual(calls, ['v79-hub', 'v79marketing-app'])
        record = json.loads((m.WORK/'deployment-disabled.json').read_text())
        self.assertFalse(record['generationEnabled']); self.assertFalse(record['publicationEnabled'])

    def test_failed_hub_does_not_switch_marketing_or_retry_or_rollback(self):
        m, calls, error = self.simulate(fail_service='v79-hub')
        self.assertIsNotNone(error); self.assertEqual(calls, ['v79-hub'])
        self.assertEqual(m.attempted, ['v79-hub'])
        self.assertFalse((m.WORK/'deployment-disabled.json').exists())

    def test_failed_marketing_records_mixed_rollout_without_retry_or_rollback(self):
        m, calls, error = self.simulate(fail_service='v79marketing-app')
        self.assertIsNotNone(error); self.assertEqual(calls, ['v79-hub', 'v79marketing-app'])
        self.assertTrue((m.WORK/'switch-verified-v79-hub.json').exists())
        self.assertFalse((m.WORK/'deployment-disabled.json').exists())

    def test_customer_or_provider_drift_after_hub_stops_before_marketing(self):
        m, calls, error = self.simulate(data_drift=True)
        self.assertIsNotNone(error); self.assertEqual(calls, ['v79-hub'])
        self.assertFalse((m.WORK/'switch-attempted-v79marketing-app.json').exists())

def patch_target(module, dotted, replacement):
    target = module
    parts = dotted.split('.')
    for name in parts[:-1]: target = getattr(target, name)
    return patch.object(target, parts[-1], replacement)

if __name__ == '__main__':
    unittest.main()
