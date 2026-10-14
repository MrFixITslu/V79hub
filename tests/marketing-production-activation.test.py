"""Generation-only activation scope and failure checks; no live server access."""
import ast
import copy
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]/'scripts/marketing-production-activate-generation.py'

def load():
    spec = importlib.util.spec_from_file_location('activation', SOURCE)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

class ActivationTests(unittest.TestCase):
    def setUp(self): self.m = load()

    def test_generation_flag_is_only_allowed_config_difference(self):
        m = self.m
        for name in m.SPECS:
            service = m.SPECS[name][1]
            old = {'services': {service: {'image': m.SPECS[name][5], 'environment': {
                'V79_MARKETING_PRODUCTION_ENABLED': '0', 'AUDIT_KEY': 'preserved',
                'V79_MARKETING_PRODUCTION_PUBLISH_ENABLED': '0'}, 'mem_limit': '805306368', 'cpus': 1.0,
                'volumes': [{'source': 'original', 'target': '/app/data'}]}, 'unrelated': {'image': 'original'}}}
            new = copy.deepcopy(old); new['services'][service]['environment']['V79_MARKETING_PRODUCTION_ENABLED'] = '1'
            m.activation_config_parity(name, old, new)
            for change in ('publication', 'audit', 'image', 'mount', 'unrelated'):
                bad = copy.deepcopy(new); target = bad['services'][service]
                if change == 'publication': target['environment']['V79_MARKETING_PRODUCTION_PUBLISH_ENABLED'] = '1'
                if change == 'audit': target['environment']['AUDIT_KEY'] = 'rotated'
                if change == 'image': target['image'] = 'different'
                if change == 'mount': target['volumes'][0]['source'] = 'different'
                if change == 'unrelated': bad['services']['unrelated']['image'] = 'different'
                with self.assertRaises(RuntimeError): m.activation_config_parity(name, old, bad)

    def test_pristine_gate_rejects_existing_ledger_or_changed_owner(self):
        m = self.m
        state = {'productionLedgerDigest': None, 'founderLinks': [{'businessId': m.OWNER_ORG,
            'organizationId': m.OWNER_ORG, 'scopedHubUserId': m.OWNER_SCOPED_ID}]}
        m.assert_pristine_production(state)
        for field, value in [('productionLedgerDigest', 'existing'), ('founderLinks', [])]:
            bad = copy.deepcopy(state); bad[field] = value
            with self.assertRaises(RuntimeError): m.assert_pristine_production(bad)

    def test_production_ledger_initialization_does_not_exempt_customer_or_provider_drift(self):
        m = self.m
        before = {'digest': 'customers', 'founderLinks': ['owner'], 'ownerConnectedPlatforms': ['youtube'], 'productionLedgerDigest': None}
        after = copy.deepcopy(before); after['productionLedgerDigest'] = 'new-signed-paused-ledger'
        m.protected_marketing_equal(before, after)
        for field in ('digest', 'founderLinks', 'ownerConnectedPlatforms'):
            bad = copy.deepcopy(after); bad[field] = 'changed'
            with self.assertRaises(RuntimeError): m.protected_marketing_equal(before, bad)

    def test_all_functions_are_defined_before_main_and_embedded_node_probes_parse(self):
        m = self.m; tree = ast.parse(SOURCE.read_text())
        self.assertIsInstance(tree.body[-1], ast.If)
        captured = []
        with patch.object(m, 'run', lambda args, data=None, **_kw: captured.append((args, data))):
            m.paired_live_boundaries(); m.probe_live()
        self.assertEqual(len(captured), 5)
        for args, program in captured:
            kind = args[args.index('node')+1]
            parsed = subprocess.run(['node', kind, '--check', '-'], input=program, capture_output=True)
            self.assertEqual(parsed.returncode, 0, parsed.stderr.decode())
        self.assertIn(b'mfaVerifiedAt:null', captured[1][1])
        self.assertNotIn(b'mfaVerifiedAt:Date.now()', captured[1][1])
        self.assertIn(b'state.paused,true', captured[2][1])
        self.assertIn(b'state.jobs,[]', captured[2][1])

    def simulate(self, failure=None, existing_ledger=False, provider_drift=False):
        m = self.m; tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); m.WORK = root/'cutover'; m.WORK.mkdir(mode=0o700)
        m.ACTIVATION = m.WORK/'generation-only-v1'; m.RECOVERY = root/'recovery'; m.RECOVERY.mkdir(mode=0o700)
        def save(path, value):
            path.write_text(json.dumps(value)); path.chmod(0o600)
        save(m.RECOVERY/'rehearsal-receipt.json', {})
        save(m.RECOVERY/'g3-protected-keys.json', {'shared': 'a'*64, 'audit': 'b'*64})
        old = {}; original = {}; disabled = {}
        for name, image in m.BASELINES.items():
            old[name] = {'Id': 'accepted-'+name, 'Image': image,
                'Config': {'Env': [], 'Labels': {}, 'Image': image, 'Cmd': ['original']}, 'HostConfig': {'Memory': 0, 'NanoCpus': 0},
                'Mounts': [], 'State': {'StartedAt': 'fixed', 'Running': True, 'Health': {'Status': 'healthy'}},
                'NetworkSettings': {'Networks': {'private': {}}}}
        for name, (project, service, working, files, filename, image, _commit) in m.SPECS.items():
            old[name]['Image'] = image; old[name]['Config']['Image'] = image
            environment = {'V79_WORKFORCE_ACTIONS_ENABLED': '1', 'V79_WORKFORCE_AUDIT_KEY': 'c'*64,
                'V79_WORKFORCE_TOKEN_FILE': '/run/secrets/v79-workforce-token'} if name == 'v79-hub' else {}
            original[name] = {'services': {service: {'image': m.BASELINES[name], 'environment': environment}}}
            overlay = {'image': image, 'environment': {'V79_MARKETING_PRODUCTION_ENABLED': '0',
                'V79_MARKETING_PRODUCTION_SHARED_SECRET': 'a'*64}}
            if name == 'v79marketing-app':
                overlay.update(mem_limit=805306368, cpus=1.0)
                overlay['environment'].update(V79_MARKETING_PRODUCTION_PUBLISH_ENABLED='0',
                    V79_MARKETING_PRODUCTION_AUDIT_KEY='b'*64, V79_MARKETING_PRODUCTION_OWNER_ORG_ID=m.OWNER_ORG,
                    V79_PRODUCTION_ASSET_DIR='/app/data/production-assets')
                old[name]['HostConfig'].update(Memory=805306368, NanoCpus=1000000000)
            save(m.RECOVERY/filename, {'services': {service: overlay}})
            disabled[name] = copy.deepcopy(original[name]); target = disabled[name]['services'][service]
            target['image'] = image; target['environment'].update(overlay['environment'])
            if name == 'v79marketing-app': target.update(mem_limit='805306368', cpus=1.0)
            old[name]['Config']['Env'] = [key+'='+str(value) for key, value in target['environment'].items()]
            old[name]['Config']['Labels'] = {'com.docker.compose.project': project, 'com.docker.compose.service': service,
                'com.docker.compose.project.working_dir': working,
                'com.docker.compose.project.config_files': ','.join(files+[str(m.RECOVERY/filename)]),
                'com.docker.compose.config-hash': 'disabled'}
        live = copy.deepcopy(old); candidates = {name: spec[5] for name, spec in m.SPECS.items()}
        state = {'digest': 'protected', 'productionLedgerDigest': 'existing' if existing_ledger else None,
            'founderLinks': [{'businessId': m.OWNER_ORG, 'organizationId': m.OWNER_ORG, 'scopedHubUserId': m.OWNER_SCOPED_ID}],
            'ownerConnectedPlatforms': [{'platform': 'youtube', 'connected': 1, 'tokenRecords': 1}]}
        recovery = {'configurationHashes': {}, 'preparedOverlayHashes': {name: m.file_hash(m.RECOVERY/name, True) for name in m.PREPARED},
            'ownerConnectedPlatforms': state['ownerConnectedPlatforms']}
        manifest = {'candidateImages': candidates, 'baselineImages': m.BASELINES, 'recoveryDirectory': str(m.RECOVERY),
            'recoveryReceiptSha256': m.file_hash(m.RECOVERY/'rehearsal-receipt.json', True),
            'preparedOverlayHashes': recovery['preparedOverlayHashes'], 'originalConfigurationHashes': {},
            'originalContainerIds': {name: meta['Id'] for name, meta in old.items()},
            'desiredResolvedConfigurationHashes': {name: m.fingerprint(value) for name, value in disabled.items()}}
        save(m.WORK/'manifest.json', manifest)
        save(m.WORK/'deployment-disabled.json', {'candidateImages': candidates, 'healthy': True,
            'generationEnabled': False, 'publicationEnabled': False, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'g2SignedAcceptanceReplayDenialAndWorkerVisibilityVerified': True, 'protectedStatePreserved': True, 'untouchedContainerIdsPreserved': True})
        calls = []
        def resolved(name, _files, extra=()):
            if not extra: return copy.deepcopy(original[name])
            value = copy.deepcopy(disabled[name])
            if len(extra) == 2: value['services'][m.SPECS[name][1]]['environment']['V79_MARKETING_PRODUCTION_ENABLED'] = '1'
            return value
        def run(args, data=None, **_kw):
            if args[:3] == ['docker', 'image', 'inspect']:
                name = next(name for name, spec in m.SPECS.items() if spec[5] == args[3])
                return json.dumps([{'Id': args[3], 'Config': {'Labels': {'org.opencontainers.image.revision': m.SPECS[name][6]}}}]).encode()
            self.assertEqual(args[:2], ['docker', 'compose'])
            name = next(name for name, spec in m.SPECS.items() if spec[1] == args[-1])
            self.assertTrue((m.ACTIVATION/('switch-attempted-'+name+'.json')).is_file())
            self.assertIn('--no-build', args); self.assertIn('--no-deps', args)
            self.assertEqual(args[args.index('--pull')+1], 'never')
            calls.append(name)
            if failure == name: raise RuntimeError('Synthetic uncertain restart')
            meta = live[name]; meta['Id'] = 'activated-'+name
            environment = m.env_map(meta['Config']['Env']); environment['V79_MARKETING_PRODUCTION_ENABLED'] = '1'
            meta['Config']['Env'] = [key+'='+value for key, value in environment.items()]
            meta['Config']['Labels']['com.docker.compose.project.config_files'] += ','+str(m.ACTIVATION/('enable-'+name+'.yml'))
            meta['Config']['Labels']['com.docker.compose.config-hash'] = 'active'
            return b''
        def sqlite(_name):
            value = copy.deepcopy(state)
            if provider_drift and calls: value['digest'] = 'changed'
            if 'v79marketing-app' in calls and failure != 'v79marketing-app': value['productionLedgerDigest'] = 'new-signed-paused-ledger'
            return value
        real_stat = Path.stat
        def owned_stat(path, *args, **kwargs):
            values = list(real_stat(path, *args, **kwargs)); values[4] = 1000
            return os.stat_result(values)
        error = None
        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, 'stat', owned_stat))
            for target, field, replacement in [(m.socket, 'gethostname', lambda: 'v79sl'),
                (m.pwd, 'getpwuid', lambda _uid: types.SimpleNamespace(pw_name='firelion')), (m.os, 'getuid', lambda: 1000),
                (m.shutil, 'which', lambda _name: '/synthetic/docker'), (m, 'verify_checkpoint', lambda: recovery),
                (m, 'verify_files', lambda _receipt: None), (m, 'inspect', lambda name: copy.deepcopy(live[name])),
                (m, 'resolve_stack', resolved), (m, 'run', run), (m, 'protected_state', lambda _db: 'protected'),
                (m, 'sqlite_state', sqlite), (m, 'paired_live_boundaries', lambda: None), (m, 'probe_live', lambda: None)]:
                stack.enter_context(patch.object(target, field, replacement))
            with redirect_stdout(io.StringIO()):
                try: m.main()
                except RuntimeError as exc: error = exc
        return m, calls, error

    def test_success_changes_only_two_generation_flags_and_records_publication_off(self):
        m, calls, error = self.simulate(); self.assertIsNone(error, str(error))
        self.assertEqual(calls, ['v79-hub', 'v79marketing-app'])
        receipt = json.loads((m.ACTIVATION/'generation-enabled.json').read_text())
        self.assertTrue(receipt['generationEnabled']); self.assertFalse(receipt['publicationEnabled'])
        self.assertFalse(receipt['ownerBrandPlanAccepted']); self.assertFalse(receipt['firstDraftAccepted'])

    def test_restart_failures_never_retry_rollback_or_record_success(self):
        for failed, expected in [('v79-hub', ['v79-hub']), ('v79marketing-app', ['v79-hub', 'v79marketing-app'])]:
            self.m = load(); m, calls, error = self.simulate(failure=failed)
            self.assertIsNotNone(error); self.assertEqual(calls, expected)
            self.assertFalse((m.ACTIVATION/'generation-enabled.json').exists())

    def test_existing_ledger_stops_before_workspace_or_restart(self):
        m, calls, error = self.simulate(existing_ledger=True)
        self.assertIsNotNone(error); self.assertEqual(calls, []); self.assertFalse(m.ACTIVATION.exists())

    def test_provider_data_drift_after_hub_stops_before_marketing(self):
        m, calls, error = self.simulate(provider_drift=True)
        self.assertIsNotNone(error); self.assertEqual(calls, ['v79-hub'])
        self.assertFalse((m.ACTIVATION/'switch-attempted-v79marketing-app.json').exists())

if __name__ == '__main__': unittest.main()
