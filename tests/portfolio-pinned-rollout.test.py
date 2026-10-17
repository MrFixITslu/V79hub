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
            path = Path(tmp)/'frozen.pinned.yml'
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
                 patch.object(r, 'public_checkout_modes'), \
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

class MountOrderingRegressionTests(unittest.TestCase):
    def sample(self):
        original = row('v79-hub')
        original['HostConfig'].update({
            'Binds': ['/host/data:/app/data:rw', '/host/key:/run/key:ro'],
            'Mounts': [{'Type': 'bind', 'Source': '/host/reports', 'Target': '/run/reports', 'ReadOnly': True,
                        'BindOptions': {'Propagation': 'rprivate'}},
                       {'Type': 'volume', 'Source': 'uploads', 'Target': '/app/uploads', 'ReadOnly': False}]})
        return original

    def test_real_reported_binds_and_mounts_order_only_is_equal(self):
        original = self.sample()
        changed = copy.deepcopy(original)
        changed['HostConfig']['Binds'].reverse()
        changed['HostConfig']['Mounts'].reverse()
        self.assertEqual(r.fingerprint(original), r.fingerprint(changed))
        # Canonicalization must not mutate the captured evidence.
        self.assertNotEqual(original['HostConfig']['Binds'], changed['HostConfig']['Binds'])

    def test_full_mount_specs_remain_checked_after_reordering(self):
        original = self.sample()
        for field, value in [('Source', '/wrong'), ('Target', '/different'), ('ReadOnly', False),
                             ('Type', 'volume'), ('BindOptions', {'Propagation': 'rshared'})]:
            changed = copy.deepcopy(original)
            changed['HostConfig']['Mounts'][0][field] = value
            changed['HostConfig']['Mounts'].reverse()
            self.assertNotEqual(r.fingerprint(original), r.fingerprint(changed), field)
        for value in ['/wrong:/app/data:rw', '/host/data:/different:rw', '/host/data:/app/data:ro']:
            changed = copy.deepcopy(original)
            changed['HostConfig']['Binds'][0] = value
            self.assertNotEqual(r.fingerprint(original), r.fingerprint(changed))

    def test_duplicate_destinations_are_rejected(self):
        for field, value in [('Binds', ['/a:/same:rw', '/b:/same:rw']),
                             ('Mounts', [{'Type': 'bind', 'Source': '/a', 'Target': '/same'},
                                         {'Type': 'bind', 'Source': '/b', 'Target': '/same'}])]:
            original = row('v79-hub')
            original['HostConfig'][field] = value
            with self.assertRaisesRegex(r.Stop, 'AMBIGUOUS_MOUNT_DESTINATIONS'):
                r.fingerprint(original)

    def test_unrelated_list_order_is_not_ignored(self):
        original = self.sample()
        original['HostConfig']['DnsSearch'] = ['first.example', 'second.example']
        changed = copy.deepcopy(original)
        changed['HostConfig']['DnsSearch'].reverse()
        self.assertNotEqual(r.fingerprint(original), r.fingerprint(changed))

class CheckpointProofTests(unittest.TestCase):
    def fixture(self, root, symlink=False):
        import io
        import tarfile
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            for name in ['runtime-before.json', *[n+'-original.compose.json' for n in r.PINNED]]:
                info = tarfile.TarInfo(name)
                data = b'{"synthetic":true}'
                info.size = len(data)
                if symlink:
                    info.type = tarfile.SYMTYPE
                    info.linkname = '/unreviewed'
                tar.addfile(info, io.BytesIO(data))
        artifact = root/'runtime-and-config.tar.gpg'
        artifact.write_bytes(b'synthetic-ciphertext')
        manifest = {'files': [{'name': artifact.name, 'sha256': r.sha_file(artifact)}],
                    'source_images': {n: p['image_id'] for n, p in r.PINNED.items()},
                    'candidates': {n: 'sha256:'+'b'*64 for n in r.PINNED}}
        r.private_json(root/'manifest.json', manifest)
        return archive.getvalue()

    def test_proof_is_derived_from_decrypted_offhost_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.fixture(root)
            with patch.object(r, 'call', return_value=archive):
                proof = r.continuation_proof(root)
            self.assertEqual(len(proof['files']), 3)
            self.assertEqual(proof['manifest_sha256'], r.sha_file(root/'manifest.json'))

    def test_changed_ciphertext_stops_before_decryption_or_remote_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root/'runtime-and-config.tar.gpg').write_bytes(b'changed')
            with patch.object(r, 'call') as call:
                with self.assertRaisesRegex(r.Stop, 'OFFHOST_CONFIG_CIPHERTEXT_CHANGED'):
                    r.continuation_proof(root)
                call.assert_not_called()

    def test_symlink_archive_member_is_rejected_without_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.fixture(root, symlink=True)
            with patch.object(r, 'call', return_value=archive):
                with self.assertRaisesRegex(r.Stop, 'CONFIG_ARCHIVE_UNEXPECTED_MEMBER'):
                    r.continuation_proof(root)

class ContinuationLifecycleTests(unittest.TestCase):
    def exercise(self, failure=None, repaired=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root/'old'
            run = root/'new'
            old.mkdir(); run.mkdir(); (old/'checkpoint').mkdir()
            (old/'exit-code').write_text('1')
            before = {n: row(n, p['image_id']) for n, p in r.PINNED.items()}
            before['database'] = row('database')
            r.private_json(old/'runtime-before.json', before)
            ids = {n: 'sha256:' + ch*64 for n, ch in zip(r.PINNED, ('b', 'c'))}
            manifest = {'source_images': {n: p['image_id'] for n, p in r.PINNED.items()}, 'candidates': ids}
            r.private_json(old/'checkpoint/manifest.json', manifest)
            files = {'runtime-before.json'}
            for n in r.PINNED:
                model = {'services': {n: {'image': before[n]['Image'], 'environment': r.envmap(before[n]['Config']['Env']),
                                         'networks': {'private': {}}}}, 'networks': {'private': {'name': 'private'}}}
                r.private_json(old/(n+'-original.compose.json'), model)
                files.add(n+'-original.compose.json')
            proof = {'files': {n: r.sha_file(old/n) for n in files}, 'candidates': ids,
                     'manifest_sha256': r.sha_file(old/'checkpoint/manifest.json')}
            effective = dict(ids)
            if repaired:
                proof['tiquet_mode_repair'] = r.ACCEPTED_TIQUET_MODE_REPAIR
                effective['v79-tiquet-manager'] = r.ACCEPTED_TIQUET_MODE_REPAIR
            if failure == 'integrity':
                (old/'v79-hub-original.compose.json').write_text('{}')
            events = []; switches = []; output = []
            def fake_inspect(name, image=False):
                if image:
                    fixed = name == r.ACCEPTED_TIQUET_MODE_REPAIR
                    app = 'v79-tiquet-manager' if fixed else next(n for n in ids if ids[n] == name)
                    labels = {'org.opencontainers.image.revision': r.SOURCES[app][1]}
                    if fixed:
                        labels.update({'v79.public-source-modes':'git-v1', 'v79.mode-repair.base':ids[app]})
                    return {'Id': name, 'Config': {'Labels': labels}, 'RootFS': {'Layers':['base','repair'] if fixed else ['base']}}
                return copy.deepcopy(before[name])
            def fake_call(args, **kwargs):
                events.append(args)
                if args[:2] == ['docker', 'compose']:
                    return Path(args[args.index('-f') + 1]).read_bytes()
                return b''
            def fake_up(path, pin):
                switches.append(path.name)
                if failure in ('second', 'rollback') and path.name == 'v79-tiquet-manager-candidate.pinned.yml':
                    raise r.Stop('INJECTED_SWITCH_FAILURE')
                if failure == 'rollback' and path.name == 'v79-hub-original.pinned.yml':
                    raise r.Stop('INJECTED_ROLLBACK_FAILURE')
            def fake_health(name, image):
                value = copy.deepcopy(before[name]); value['Image'] = image
                if failure == 'config' and image == effective[name]:
                    value['HostConfig']['Privileged'] = True
                return value
            with patch.object(r, 'FAILED_RUN', old), \
                 patch.object(r, 'inspect', side_effect=fake_inspect), \
                 patch.object(r, 'check_original_inputs'), \
                 patch.object(r, 'call', side_effect=fake_call), \
                 patch.object(r, 'same_others'), \
                 patch.object(r, 'active_timers', return_value=['v79-workforce-task.timer']), \
                 patch.object(r, 'timers_idle'), \
                 patch.object(r, 'up', side_effect=fake_up), \
                 patch.object(r, 'health', side_effect=fake_health), \
                 patch.object(r, 'emit', side_effect=lambda k, v: output.append((k, v))):
                if failure:
                    with self.assertRaises(r.Stop):
                        r.continued_server_locked(run, old, proof)
                else:
                    r.continued_server_locked(run, old, proof)
            if repaired:
                self.assertEqual(json.loads((old/'checkpoint/manifest.json').read_text())['candidates'], ids)
                self.assertEqual(proof['candidates'], ids)
                model=json.loads((run/'v79-tiquet-manager-candidate.pinned.yml').read_text())
                self.assertEqual(model['services']['v79-tiquet-manager']['image'], r.ACCEPTED_TIQUET_MODE_REPAIR)
                if not failure:
                    self.assertEqual(json.loads((run/'release-receipt.json').read_text())['images'], effective)
            return events, switches, output

    def test_continuation_never_builds_stops_captures_or_imports(self):
        events, switches, output = self.exercise()
        self.assertEqual(len(switches), 2)
        self.assertIn(('RESULT', 'BOTH_APPS_DEPLOYED_HEALTHY'), output)
        self.assertFalse(any(e[:2] in (['docker', 'build'], ['docker', 'stop'], ['docker', 'cp'],
                                      ['docker', 'exec'], ['docker', 'image']) for e in events))
        self.assertIn(['systemctl', '--user', 'start', 'v79-workforce-task.timer'], events)

    def test_saved_config_integrity_failure_never_switches(self):
        _, switches, _ = self.exercise('integrity')
        self.assertEqual(switches, [])

    def test_security_difference_still_rolls_back(self):
        events, switches, output = self.exercise('config')
        self.assertEqual(switches, ['v79-hub-candidate.pinned.yml', 'v79-hub-original.pinned.yml'])
        self.assertIn(('ROLLBACK', 'ORIGINAL_IMAGES_HEALTHY'), output)
        self.assertIn(['systemctl', '--user', 'start', 'v79-workforce-task.timer'], events)

    def test_second_switch_failure_restores_both(self):
        _, switches, output = self.exercise('second')
        self.assertEqual(switches[-2:], ['v79-tiquet-manager-original.pinned.yml', 'v79-hub-original.pinned.yml'])
        self.assertIn(('ROLLBACK', 'ORIGINAL_IMAGES_HEALTHY'), output)

    def test_genuine_rollback_failure_is_not_hidden(self):
        _, _, output = self.exercise('rollback')
        self.assertIn(('ROLLBACK', 'FAILED_MANUAL_RECOVERY_REQUIRED'), output)
        self.assertIn(('ROLLBACK', 'v79-hub_NOT_PROVEN_MANUAL_REVIEW_REQUIRED'), output)


    def test_exact_repaired_image_is_used_without_rewriting_checkpoint(self):
        events, switches, output=self.exercise(repaired=True)
        self.assertIn(('RESULT','EXACT_SYNTHETICALLY_ACCEPTED_TIQUET_REPAIR_VERIFIED'),output)
        self.assertIn(('RESULT','BOTH_APPS_DEPLOYED_HEALTHY'),output)
        self.assertFalse(any(e[:2] in (['docker','build'],['docker','image'],['docker','cp'],['docker','stop']) for e in events))

    def test_repaired_image_failure_still_rolls_back_both_originals(self):
        _,switches,output=self.exercise('second',repaired=True)
        self.assertEqual(switches[-2:],['v79-tiquet-manager-original.pinned.yml','v79-hub-original.pinned.yml'])
        self.assertIn(('ROLLBACK','ORIGINAL_IMAGES_HEALTHY'),output)

class RepairedCandidateTests(unittest.TestCase):
    def fixture(self):
        source='sha256:'+'b'*64
        proof={'candidates':{'v79-hub':'sha256:'+'a'*64,'v79-tiquet-manager':source},'tiquet_mode_repair':r.ACCEPTED_TIQUET_MODE_REPAIR}
        base={'Id':source,'Config':{'User':'appuser','Env':['EXAMPLE=public'],'Labels':{'org.opencontainers.image.revision':r.SOURCES['v79-tiquet-manager'][1]}},'RootFS':{'Layers':['layer1','layer2']}}
        repaired=copy.deepcopy(base);repaired['Id']=r.ACCEPTED_TIQUET_MODE_REPAIR
        repaired['Config']['Labels'].update({'v79.public-source-modes':'git-v1','v79.mode-repair.base':source})
        repaired['RootFS']['Layers'].append('repair')
        return proof,base,repaired

    def test_unaccepted_id_rejected_without_queries(self):
        proof,_,_=self.fixture();proof['tiquet_mode_repair']='sha256:'+'c'*64
        with patch.object(r,'inspect') as inspect:
            with self.assertRaisesRegex(r.Stop,'UNACCEPTED_TIQUET_REPAIR_IMAGE'):
                r.effective_candidates(proof)
            inspect.assert_not_called()

    def test_runtime_security_or_environment_drift_rejected(self):
        for field,value in [('User','root'),('Env',['EXAMPLE=changed']),('Volumes',{'/production':{}}),('Cmd',['other'])]:
            proof,base,repaired=self.fixture();repaired['Config'][field]=value
            with patch.object(r,'inspect',side_effect=[base,repaired]):
                with self.assertRaisesRegex(r.Stop,'REPAIR_RUNTIME_DEFAULTS_CHANGED'):
                    r.effective_candidates(proof)

    def test_changed_base_provenance_rejected(self):
        proof,base,repaired=self.fixture();repaired['Config']['Labels']['v79.mode-repair.base']='foreign'
        with patch.object(r,'inspect',side_effect=[base,repaired]):
            with self.assertRaisesRegex(r.Stop,'REPAIR_PROVENANCE_CHANGED'):
                r.effective_candidates(proof)

    def test_changed_base_layers_rejected(self):
        proof,base,repaired=self.fixture();repaired['RootFS']['Layers']=['foreign','repair']
        with patch.object(r,'inspect',side_effect=[base,repaired]):
            with self.assertRaisesRegex(r.Stop,'REPAIR_BASE_LAYERS_CHANGED'):
                r.effective_candidates(proof)

    def test_failure_evidence_is_projected_before_rollback_without_raw_output(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=[]
            row={'Image':r.ACCEPTED_TIQUET_MODE_REPAIR,'State':{'ExitCode':1,'OOMKilled':False}}
            proc=SimpleNamespace(returncode=0,stdout=b'password=PRIVATE_DATA EACCES')
            with patch.object(r,'inspect',return_value=row),patch.object(r.subprocess,'run',return_value=proc),patch.object(r,'emit',side_effect=lambda k,v:output.append((k,v))):
                r.capture_failed_startup(root,'v79-tiquet-manager',r.ACCEPTED_TIQUET_MODE_REPAIR)
            report=(root/'v79-tiquet-manager-failed-startup-safe.json').read_text()
            self.assertNotIn('PRIVATE',report+json.dumps(output))
            self.assertIn('FILESYSTEM_PERMISSION',report)

    def test_failure_evidence_error_cannot_prevent_rollback(self):
        with patch.object(r,'inspect',side_effect=RuntimeError('PRIVATE')),patch.object(r,'emit') as emit:
            r.capture_failed_startup(Path('/unused'),'v79-tiquet-manager',r.ACCEPTED_TIQUET_MODE_REPAIR)
            emit.assert_called_once_with('RESULT','v79-tiquet-manager_STARTUP_EVIDENCE_UNAVAILABLE')

class PublicCheckoutTests(unittest.TestCase):
    def test_private_umask_checkout_becomes_public_without_exposing_private_files(self):
        import os
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp); parent.chmod(0o700)
            stage = parent/'source'; stage.mkdir(mode=0o700)
            subprocess.run(['git', 'init', '-q', str(stage)], check=True)
            (stage/'server').mkdir(mode=0o700)
            code = stage/'server/index.js'; code.write_text('public source'); code.chmod(0o600)
            executable = stage/'run.sh'; executable.write_text('public executable'); executable.chmod(0o700)
            subprocess.run(['git', '-C', str(stage), 'add', '.'], check=True)
            private = stage/'untracked-secret'; private.write_text('PRIVATE'); private.chmod(0o600)
            r.public_checkout_modes(stage)
            self.assertEqual(code.stat().st_mode & 0o777, 0o644)
            self.assertEqual(executable.stat().st_mode & 0o777, 0o755)
            self.assertEqual((stage/'server').stat().st_mode & 0o777, 0o755)
            self.assertEqual(parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            self.assertEqual(code.read_text(), 'public source')

    def test_symlink_is_rejected_before_permission_changes(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            outside = stage/'private'; outside.write_text('PRIVATE'); outside.chmod(0o600)
            (stage/'link').symlink_to(outside)
            subprocess.run(['git', 'init', '-q', str(stage)], check=True)
            subprocess.run(['git', '-C', str(stage), 'add', 'link'], check=True)
            with self.assertRaisesRegex(r.Stop, 'PUBLIC_SOURCE_MODE_UNREVIEWED'):
                r.public_checkout_modes(stage)
            self.assertEqual(outside.stat().st_mode & 0o777, 0o600)

if __name__ == '__main__':
    unittest.main()
