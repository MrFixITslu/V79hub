import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

spec = importlib.util.spec_from_file_location('diag', Path(__file__).resolve().parents[1]/'scripts/portfolio-tiquet-startup-diagnostic.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

class SafetyTests(unittest.TestCase):
    def test_error_projection_never_exposes_message_values(self):
        result = d.classify("password=PRIVATE_TOKEN code: '42703' column PRIVATE_CUSTOMER does not exist server/db.js:219:2")
        self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertIn('SCHEMA_COLUMN', result['categories'])
        self.assertEqual(result['source_locations'], ['server/db.js:219:2'])

    def test_permissions_native_modules_and_connection_failures_are_distinct(self):
        for text, category in [('EACCES', 'FILESYSTEM_PERMISSION'), ('ERR_DLOPEN_FAILED', 'NATIVE_MODULE'),
                               ('ECONNREFUSED', 'DATABASE_CONNECT'), ('42830', 'SCHEMA_FOREIGN_KEY')]:
            self.assertIn(category, d.classify(text)['categories'])

    def test_synthetic_mount_and_network_guards(self):
        row = {'Config': {'Labels': {d.LABEL:'x'}}, 'HostConfig': {'PortBindings': {}},
               'Mounts': [{'Type': 'tmpfs'}], 'NetworkSettings': {'Networks': {'internal': {}}}}
        d.validate_synthetic(row, 'x', 'internal')
        for field, value in [('Mounts', [{'Type': 'bind', 'Source': '/production'}]),
                             ('HostConfig', {'PortBindings': {'3050/tcp': []}}),
                             ('NetworkSettings', {'Networks': {'proxy_network': {}}})]:
            other = copy.deepcopy(row); other[field] = value
            with self.assertRaises(d.Stop):
                d.validate_synthetic(other, 'x', 'internal')

    def test_frozen_probe_accepts_only_unauthenticated_loopback_health(self):
        probe = ['CMD', 'wget', '-qO-', 'http://127.0.0.1:3050/health']
        self.assertEqual(d.safe_health_command(probe), probe[1:])
        self.assertIsNone(d.safe_health_command(['CMD-SHELL', 'arbitrary code']))
        for url in ['https://public.example/health', 'http://user:PRIVATE@127.0.0.1:3050/health',
                    'http://127.0.0.1:3050/health?token=PRIVATE', 'http://127.0.0.1:3050/api/customers']:
            self.assertIsNone(d.safe_health_command(['CMD', 'wget', '-qO-', url]))

    def test_health_status_does_not_return_response_bodies(self):
        from types import SimpleNamespace
        with patch.object(d, 'run', return_value=SimpleNamespace(stdout=b'200')):
            self.assertEqual(d.http_status('synthetic', 3050), 200)
        with patch.object(d, 'run', return_value=SimpleNamespace(stdout=b'PRIVATE_BODY')):
            self.assertEqual(d.http_status('synthetic', 3050), 0)

    def test_cleanup_refuses_foreign_resource(self):
        with patch.object(d, 'inspect', return_value={'Config': {'Labels': {d.LABEL:'foreign'}}}), patch.object(d, 'run') as run:
            with self.assertRaisesRegex(d.Stop, 'REFUSE_CLEANUP_FOREIGN_CONTAINER'):
                d.owned_cleanup(['synthetic'], 'internal', 'ours')
            run.assert_not_called()

    def test_failed_inspect_does_not_hide_daemon_failure_as_absence(self):
        from types import SimpleNamespace
        missing = SimpleNamespace(returncode=1, stdout=b'')
        with patch.object(d, 'run', side_effect=[missing, d.Stop('ENGINE_METADATA_UNAVAILABLE')]):
            with self.assertRaisesRegex(d.Stop, 'ENGINE_METADATA_UNAVAILABLE'):
                d.inspect('synthetic', optional=True)

    def test_failed_inspect_with_existing_resource_is_not_absence(self):
        from types import SimpleNamespace
        results = [SimpleNamespace(returncode=1, stdout=b''), SimpleNamespace(returncode=0, stdout=b'container-id')]
        with patch.object(d, 'run', side_effect=results):
            with self.assertRaisesRegex(d.Stop, 'CONTAINER_INSPECT_FAILED_NOT_ABSENCE'):
                d.inspect('synthetic', optional=True)

class LifecycleTests(unittest.TestCase):
    def exercise(self, fail=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'checkpoint').mkdir()
            core = ['v79-hub', 'v79-tiquet-manager', 'v79-hub-postgres', 'tiquet-postgres', 'v79-business-agent']
            before = {n: {'Id':n+'-id', 'Image':'sha256:'+'1'*64, 'Config': {'User':'appuser'},
                          'State': {'Health': {'Status':'healthy'}}} for n in core}
            before['tiquet-postgres']['Image'] = 'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685'
            candidate = 'sha256:'+'b'*64
            (root/'checkpoint/manifest.json').write_text(json.dumps({'candidates': {'v79-tiquet-manager':candidate},
                'source_images': {n:before[n]['Image'] for n in core[:2]}}))
            resources = {}; events = []; networks = {}
            metadata = {'uid':100, 'gid':100, 'paths':{}}
            class Result:
                returncode=0
                stdout=b''
            def result(data=b'', code=0):
                obj=Result(); obj.stdout=data; obj.returncode=code; return obj
            def inspect(name, image=False, optional=False):
                if image:
                    return {'Config': {'Labels': {'org.opencontainers.image.revision':'7da53ebb71530366168bd72a7efd52b57d34a23c'}}}
                if name in before:
                    return copy.deepcopy(before[name])
                if name in resources:
                    return copy.deepcopy(resources[name])
                if optional:
                    return None
                raise AssertionError(name)
            def run(args, **kwargs):
                events.append(args)
                if args[1:3] == ['network', 'create']:
                    networks[args[-1]] = {'Internal':True, 'Labels': {d.LABEL:args[args.index('--label')+1].split('=',1)[1]}}
                elif args[1:3] == ['network', 'inspect']:
                    return result(json.dumps([networks[args[-1]]]).encode()) if args[-1] in networks else result(code=1)
                elif args[1:3] == ['network', 'rm']:
                    del networks[args[-1]]
                elif args[1] == 'create':
                    name=args[args.index('--name')+1]; network=args[args.index('--network')+1]
                    identity=args[args.index('--label')+1].split('=',1)[1]
                    resources[name]={'Config': {'Labels': {d.LABEL:identity}, 'User':'appuser'},
                        'HostConfig': {'PortBindings':{}}, 'Mounts': [],
                        'NetworkSettings': {'Networks': {network:{}}}, 'State': {'Running':True}}
                elif args[1] == 'start' and '--attach' in args:
                    return result(json.dumps(metadata).encode())
                elif args[1] == 'exec' and args[2] == 'v79-tiquet-manager':
                    return result(json.dumps(metadata).encode())
                elif args[1] == 'exec' and args[2].endswith('-app'):
                    return result(b'503' if fail else b'200')
                elif args[1] == 'rm':
                    del resources[args[-1]]
                return result()
            output=io.StringIO()
            with patch.object(d, 'RUN', root), patch.object(d.socket, 'gethostname', return_value='v79sl'), \
                 patch.object(d.os, 'getuid', return_value=1000), patch.object(d.signal, 'signal'), \
                 patch.object(d, 'inspect', side_effect=inspect), patch.object(d, 'run', side_effect=run), \
                 patch.object(d.time, 'sleep'), patch.object(d, 'report', return_value=d.classify('42703 PRIVATE_MARKER')), \
                 patch.object(d.sys, 'argv', ['diagnostic']), redirect_stdout(output):
                if fail:
                    with self.assertRaisesRegex(d.Stop, 'SYNTHETIC_CANDIDATE_STARTUP_FAILED'):
                        d.main()
                else:
                    d.main()
            self.assertEqual(resources,{})
            self.assertEqual(networks,{})
            self.assertNotIn('PRIVATE_', output.getvalue())
            for args in events:
                if args[1] in ('start', 'rm'):
                    self.assertTrue(args[-1].startswith('v79-tqdiag-'))
                self.assertNotIn(args[1], ('stop','restart','build','pull','load'))
            return output.getvalue()

    def test_success_cleans_only_synthetic_resources_and_keeps_core_healthy(self):
        output=self.exercise()
        self.assertIn('TIQUET_SYNTHETIC_STARTUP=PASS', output)
        self.assertIn('LIVE_FIVE_ORIGINAL_CONTAINERS=UNCHANGED_HEALTHY', output)

    def test_failure_still_cleans_without_replacing_production_apps(self):
        output=self.exercise(fail=True)
        self.assertIn('TIQUET_SYNTHETIC_STARTUP=FAIL', output)
        self.assertIn('SYNTHETIC_RESOURCE_CLEANUP=PASS', output)

if __name__ == '__main__':
    unittest.main()
