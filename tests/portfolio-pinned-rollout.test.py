#!/usr/bin/env python3
"""Synthetic control-flow tests: never contacts Docker, SSH, GPG or production."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('rollout', Path(__file__).resolve().parents[1] / 'scripts/portfolio-pinned-rollout.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def row(name, image='sha256:' + 'a' * 64):
    env = ['V79_REQUIRE_ADMIN_MFA=1', 'V79_ALLOW_LEGACY_AUTH=0',
           'V79_ENTITLEMENT_RECHECK_ENABLED=1', 'V79_TIQUET_LAUNCH_SECRET=synthetic-only']
    return {'Id': name + '-old-id', 'Name': '/' + name, 'Image': image,
            'State': {'Status': 'running', 'Health': {'Status': 'healthy'}},
            'Config': {'Env': env, 'Labels': {'com.docker.compose.project': 'p',
              'com.docker.compose.service': name}, 'Cmd': ['node', 'server.js'], 'User': 'appuser'},
            'HostConfig': {'PortBindings': {}}, 'Mounts': [],
            'NetworkSettings': {'Networks': {'private': {}}}}

class ContractTests(unittest.TestCase):
    def test_complete_pins(self):
        self.assertEqual(len(r.PINNED['v79-hub']['compose_inputs']), 13)
        self.assertEqual(len(r.PINNED['v79-tiquet-manager']['compose_inputs']), 1)
        for pin in r.PINNED.values():
            self.assertRegex(pin['image_id'], r.IMAGE)
            for entry in pin['compose_inputs']:
                self.assertRegex(entry['sha256'], r'^[a-f0-9]{64}$')

    def test_runtime_projection_detects_security_drift(self):
        before = row('v79-hub')
        for section, key, value in [('Config', 'User', 'root'), ('Config', 'Cmd', ['sh']),
                                    ('HostConfig', 'Privileged', True)]:
            other = copy.deepcopy(before)
            other[section][key] = value
            self.assertNotEqual(r.fingerprint(before), r.fingerprint(other))
        for field in ('Env',):
            other = copy.deepcopy(before)
            other['Config'][field] = ['V79_REQUIRE_ADMIN_MFA=0']
            self.assertNotEqual(r.fingerprint(before), r.fingerprint(other))
        other = copy.deepcopy(before)
        other['Mounts'] = [{'Destination': '/app/data', 'Source': '/unexpected', 'RW': True}]
        self.assertNotEqual(r.fingerprint(before), r.fingerprint(other))
        other = copy.deepcopy(before)
        other['NetworkSettings']['Networks']['public'] = {}
        self.assertNotEqual(r.fingerprint(before), r.fingerprint(other))

    def test_runtime_projection_allows_only_dynamic_identity(self):
        before = row('v79-hub')
        other = copy.deepcopy(before)
        other.update(Id='new-id', Image='sha256:'+'b'*64)
        other['Config']['Labels']['com.docker.compose.project.config_files'] = '/new/frozen.json'
        other['NetworkSettings']['Networks']['private']['IPAddress'] = '172.19.0.7'
        self.assertEqual(r.fingerprint(before), r.fingerprint(other))

    def test_no_raw_output_or_duplicate_environment(self):
        with self.assertRaises(r.Stop):
            r.emit('STOP', 'password=value with secrets')
        with self.assertRaises(r.Stop):
            r.envmap(['A=first', 'A=second'])
        with patch.dict(r.os.environ, {'COMPOSE_FILE': 'untrusted', 'DOCKER_HOST': 'tcp://untrusted', 'GIT_CONFIG_COUNT': '1'}):
            self.assertNotIn('COMPOSE_FILE', r.clean_env())
            self.assertNotIn('DOCKER_HOST', r.clean_env())
            self.assertNotIn('GIT_CONFIG_COUNT', r.clean_env())

    def test_original_model_hash_and_env_drift_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'compose.json'
            p.write_text('{}')
            pin = {'compose_inputs': [{'path': str(p), 'sha256': r.sha_file(p)}],
                   'compose_project': 'p', 'compose_service': 'v79-hub', 'container': 'v79-hub'}
            original = row('v79-hub')
            original['Config']['Labels'].update({'com.docker.compose.project.config_files': str(p),
                                                 'com.docker.compose.project.working_dir': tmp})
            model = {'networks': {'private': {'name': 'private'}}, 'services': {'v79-hub': {'container_name': 'v79-hub', 'environment': {'A': 'wrong'}, 'networks': {'private': {}}}}}
            with patch.object(r, 'call', return_value=json.dumps(model).encode()), patch.object(r, 'inspect', return_value={'Config': {'Env': []}}):
                with self.assertRaisesRegex(r.Stop, 'RENDERED_ENV_DIFFERS'):
                    r.original_model(original, pin)
            p.write_text('changed')
            with self.assertRaisesRegex(r.Stop, 'COMPOSE_HASH_DRIFT'):
                r.original_model(original, pin)

    def test_storage_drift_cannot_enter_checkpoint_or_rollback(self):
        original = row('v79-hub')
        original['Mounts'] = [{'Type': 'volume', 'Name': 'original_data', 'Destination': '/app/data', 'RW': True}]
        model = {'volumes': {'data': {'name': 'original_data'}}, 'networks': {'private': {'name': 'private'}}}
        service = {'volumes': [{'type': 'volume', 'source': 'data', 'target': '/app/data'}], 'networks': {'private': {}}}
        r.validate_storage_and_networks(model, service, original)
        model['volumes']['data']['name'] = 'different_data'
        with self.assertRaisesRegex(r.Stop, 'RENDERED_VOLUME_NAME_DIFFERS'):
            r.validate_storage_and_networks(model, service, original)
        model['volumes']['data']['name'] = 'original_data'
        service['volumes'][0]['read_only'] = True
        with self.assertRaisesRegex(r.Stop, 'RENDERED_MOUNT_ACCESS_DIFFERS'):
            r.validate_storage_and_networks(model, service, original)
        service['volumes'][0]['read_only'] = False
        model['networks']['private']['name'] = 'other_network'
        with self.assertRaisesRegex(r.Stop, 'RENDERED_NETWORKS_DIFFER'):
            r.validate_storage_and_networks(model, service, original)

    def test_runtime_dollars_survive_compose_interpolation(self):
        original = {'ENV': 'literal$VALUE-and-$$-and-${HOME}'}
        escaped = r.compose_literal(original)
        self.assertEqual(escaped['ENV'], 'literal$$VALUE-and-$$$$-and-$${HOME}')
        self.assertEqual(r.compose_runtime(escaped), original)
        self.assertEqual(r.compose_literal(['sh', '-c', 'echo "$PORT"']), ['sh', '-c', 'echo "$$PORT"'])

    def test_up_is_strictly_one_service_no_dependencies(self):
        with patch.object(r, 'call') as call:
            r.up(Path('/frozen.json'), {'compose_project': 'p', 'compose_service': 'api'})
            args = call.call_args.args[0]
            self.assertEqual(args[-6:], ['-d', '--no-deps', '--no-build', '--pull', 'never', 'api'])
            self.assertNotIn('down', args)
            self.assertNotIn('--remove-orphans', args)

class ActualComposeSerializationTests(unittest.TestCase):
    @unittest.skipUnless(r.shutil.which('docker'), 'Docker CLI unavailable locally; required on GitHub Ubuntu runner')
    def test_actual_compose_preserves_literal_environment_and_command(self):
        # This invokes Compose config only: no daemon, containers or registry access.
        original = {'EXAMPLE': 'literal$VALUE-and-$$-and-${HOME}'}
        command = ['sh', '-c', 'printf "%s" "$EXAMPLE"']
        model = {'services': {'api': {'image': 'busybox:stable',
                  'environment': r.compose_literal(original), 'command': r.compose_literal(command)}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'frozen.json'
            r.private_json(path, model)
            actual = json.loads(r.call(r.compose(path, 'synthetic', 'config', '--format', 'json')))
            self.assertEqual(r.compose_runtime(actual['services']['api']['environment']), original)
            self.assertEqual(r.compose_runtime(actual['services']['api']['command']), command)

class SchedulerAndHealthTests(unittest.TestCase):
    def test_only_matching_active_v79_timers_are_selected(self):
        with patch.object(r, 'call', side_effect=[
            b'v79-workforce-task.timer loaded active waiting x\nunrelated.timer loaded active waiting x\n',
            b'inactive\n']):
            self.assertEqual(r.active_timers(), ['v79-workforce-task.timer'])

    def test_busy_scheduled_service_blocks_shutdown(self):
        with patch.object(r, 'call', return_value=b'active\n'):
            with self.assertRaisesRegex(r.Stop, 'SCHEDULED_WORK_CURRENTLY_RUNNING'):
                r.timers_idle(['v79-release.timer'])

    def test_exited_app_never_passes_health(self):
        exited = row('v79-hub')
        exited['State']['Status'] = 'exited'
        with patch.object(r, 'inspect', return_value=exited):
            with self.assertRaisesRegex(r.Stop, 'APPLICATION_EXITED'):
                r.health('v79-hub', exited['Image'])

    def test_healthy_wrong_image_is_not_success(self):
        with patch.object(r, 'inspect', return_value=row('v79-hub')), \
             patch.object(r.time, 'monotonic', side_effect=[0, 0, 1000]), \
             patch.object(r.time, 'sleep'):
            with self.assertRaisesRegex(r.Stop, 'APPLICATION_HEALTH_TIMEOUT'):
                r.health('v79-hub', 'sha256:'+'f'*64)

    def test_only_expected_healthy_image_passes(self):
        healthy = row('v79-hub')
        with patch.object(r, 'inspect', return_value=healthy):
            self.assertEqual(r.health('v79-hub', healthy['Image']), healthy)

class LifecycleTests(unittest.TestCase):
    def exercise(self, failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshots = {n: row(n, p['image_id']) for n, p in r.PINNED.items()}
            snapshots['database'] = row('database')
            for n, p in r.PINNED.items():
                snapshots[n]['Config']['Labels'] = {'com.docker.compose.project': p['compose_project'],
                                                    'com.docker.compose.service': p['compose_service']}
            events = []
            switches = []
            def fake_call(args, **kwargs):
                events.append(args)
                if args[:3] == ['docker', 'ps', '-a']:
                    return '\n'.join(snapshots).encode()
                if args[:2] == ['docker', 'inspect']:
                    return json.dumps(list(snapshots.values())).encode()
                if args[:4] == ['docker', 'compose', 'up', '--help']:
                    return b'--no-deps --no-build --pull'
                if args[:2] == ['docker', 'compose'] and '--format' in args:
                    return json.dumps({'services': {n: {'environment': r.envmap(v['Config']['Env'])} for n, v in snapshots.items()}}).encode()
                if args[:2] == ['docker', 'build'] and failure == 'build':
                    raise r.Stop('INJECTED_BUILD')
                if args[:2] == ['docker', 'stop'] and failure == 'stop':
                    raise r.Stop('INJECTED_STOP')
                if args[:2] == ['docker', 'start'] and failure == 'rollback':
                    raise r.Stop('INJECTED_ROLLBACK')
                if args[0] == 'gpg' and '--fingerprint' in args:
                    return ('fpr:::::::::' + r.RECIPIENT + ':').encode()
                if args[0] == 'git' and 'rev-parse' in args:
                    repo = Path(args[2]).name
                    return next(sha.encode() for _, (name, sha) in r.SOURCES.items() if name == repo)
                return b''
            def fake_model(original, pin):
                return {'services': {pin['compose_service']: {'image': original['Image']}}}
            def fake_inspect(name, image=False):
                if image:
                    return {'Id': 'sha256:'+'b'*64, 'Config': {'Volumes': None, 'User': 'appuser', 'Cmd': ['node', 'server.js']}}
                return copy.deepcopy(snapshots[name])
            def fake_encrypt(args, dest, gnupg):
                events.append(['checkpoint', dest.name])
                if failure in ('checkpoint', 'rollback') and dest.name.endswith('.dump.gpg'):
                    raise r.Stop('INJECTED_CHECKPOINT')
                dest.write_bytes(b'encrypted-synthetic')
            def fake_up(path, pin):
                switches.append(path.name)
                if path.name.endswith('-candidate.compose.json') and failure == pin['container']:
                    raise r.Stop('INJECTED_SWITCH')
            output = []
            with patch.object(r.socket, 'gethostname', return_value='v79sl'), \
                 patch.object(r.os, 'getuid', return_value=1000), \
                 patch.object(r.Path, 'home', return_value=root), \
                 patch.object(r.signal, 'signal'), \
                 patch.object(r.shutil, 'which', return_value='/synthetic'), \
                 patch.object(r.shutil, 'disk_usage', return_value=type('D', (), {'free': 99*1024**3})()), \
                 patch.object(r.Path, 'read_text', return_value='MemAvailable: 9000000 kB'), \
                 patch.object(r, 'call', side_effect=fake_call), \
                 patch.object(r, 'original_model', side_effect=fake_model), \
                 patch.object(r, 'inspect', side_effect=fake_inspect), \
                 patch.object(r, 'encrypted_stream', side_effect=fake_encrypt), \
                 patch.object(r, 'same_others'), \
                 patch.object(r, 'up', side_effect=fake_up), \
                 patch.object(r, 'emit', side_effect=lambda k, v: output.append((k, v))), \
                 patch.object(r, 'health', side_effect=lambda name, image: copy.deepcopy(snapshots[name])):
                if failure:
                    with self.assertRaises(r.Stop):
                        r.server(root, 'cHVibGljLWtleQ==')
                else:
                    r.server(root, 'cHVibGljLWtleQ==')
            return events, switches, output

    def test_build_failure_never_stops_apps(self):
        events, switches, output = self.exercise('build')
        self.assertFalse(any(e[:2] == ['docker', 'stop'] for e in events))
        self.assertEqual(switches, [])

    def test_stop_failure_still_restarts_original(self):
        events, _, output = self.exercise('stop')
        self.assertTrue(any(e[:2] == ['docker', 'start'] for e in events))
        self.assertIn(('ROLLBACK', 'ORIGINAL_IMAGES_HEALTHY'), output)

    def test_checkpoint_failure_restarts_both_without_switch(self):
        events, switches, output = self.exercise('checkpoint')
        self.assertEqual(len([e for e in events if e[:2] == ['docker', 'start']]), 2)
        self.assertEqual(switches, [])
        self.assertIn(('DATA_RESTORE', 'NOT_AUTOMATIC_IMAGE_ROLLBACK_ONLY'), output)

    def test_first_switch_failure_rolls_back_attempted_app(self):
        _, switches, output = self.exercise('v79-hub')
        self.assertEqual(switches, ['v79-hub-candidate.compose.json', 'v79-hub-original.compose.json'])
        self.assertIn(('ROLLBACK', 'ORIGINAL_IMAGES_HEALTHY'), output)

    def test_second_switch_failure_rolls_back_both_in_reverse_order(self):
        _, switches, _ = self.exercise('v79-tiquet-manager')
        self.assertEqual(switches[-2:], ['v79-tiquet-manager-original.compose.json', 'v79-hub-original.compose.json'])

    def test_failed_rollback_is_reported(self):
        _, _, output = self.exercise('rollback')
        self.assertIn(('ROLLBACK', 'FAILED_MANUAL_RECOVERY_REQUIRED'), output)

    def test_success_builds_before_stopping_and_captures_before_switch(self):
        events, switches, output = self.exercise()
        build = [i for i, e in enumerate(events) if e[:2] == ['docker', 'build']]
        stops = [i for i, e in enumerate(events) if e[:2] == ['docker', 'stop']]
        self.assertLess(max(build), min(stops))
        self.assertEqual(len(switches), 2)
        self.assertIn(('RESULT', 'BOTH_APPS_DEPLOYED_HEALTHY'), output)
        self.assertNotIn(('ROLLBACK', 'ORIGINAL_IMAGES_HEALTHY'), output)
        self.assertIn(('CUSTOMER_RELEASE', 'NO_GO'), output)

if __name__ == '__main__':
    unittest.main()
