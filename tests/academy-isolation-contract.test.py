"""Synthetic data only; no Docker engine, subprocesses or production access."""
import ast
import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'scripts/academy-isolation-contract.py'
spec = importlib.util.spec_from_file_location('contract', PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
IMAGE = 'sha256:' + 'f' * 64
TOKEN = 'a' * 14
PUBLIC = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'NODE_VERSION': '20.19.0'}


def fixture(state='created'):
    return {'Name': '/v79-isolated-academy-' + TOKEN, 'Image': IMAGE,
            'State': {'Status': state, 'Running': state == 'running'},
            'Config': {'User': '1000:1000', 'Labels': {c.OWNER: TOKEN},
                       'ExposedPorts': {'3030/tcp': {}},
                       'Env': [k + '=' + v for k, v in {**PUBLIC, **c.SYNTHETIC}.items()]},
            'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True,
                           'IpcMode': 'private', 'CgroupnsMode': 'private', 'RestartPolicy': {'Name': 'no'},
                           'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true'],
                           'Memory': 512 * 1024**2, 'MemorySwap': 512 * 1024**2,
                           'PidsLimit': 64, 'NanoCpus': 750000000,
                           'Tmpfs': {p: 'rw,nosuid,nodev,size=' + size + ',uid=1000,gid=1000,mode=0700'
                                     for p, size in c.TMPFS.items()}},
            'NetworkSettings': {'Networks': {'none': {}}},
            'Mounts': [] if state == 'created' else [
                {'Type': 'tmpfs', 'Destination': p, 'RW': True, 'Source': ''} for p in c.TMPFS]}


class ContractTests(unittest.TestCase):
    def test_created_accepts_declared_unrealized_storage(self):
        self.assertEqual(c.validate(fixture(), IMAGE, TOKEN, PUBLIC), 'PASS_CREATED')

    def test_running_requires_realized_storage(self):
        row = fixture('running')
        self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'PASS_RUNNING')
        row['Mounts'] = []
        self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'REALIZED_MOUNTS_MISMATCH')

    def test_wrong_image_name_label_and_compose_ownership(self):
        for change in [lambda r: r.update(Image='sha256:' + 'b' * 64),
                       lambda r: r.update(Name='/foreign'),
                       lambda r: r['Config']['Labels'].update({c.OWNER: 'b' * 14}),
                       lambda r: r['Config']['Labels'].update({'com.docker.compose.project': 'production'})]:
            row = fixture(); change(row)
            self.assertFalse(c.validate(row, IMAGE, TOKEN, PUBLIC).startswith('PASS'))

    def test_privileges_and_resource_drift(self):
        changes = {'NetworkMode': 'host', 'Privileged': True, 'ReadonlyRootfs': False,
                   'CapDrop': [], 'CapAdd': ['SYS_ADMIN'], 'SecurityOpt': [],
                   'Memory': 0, 'MemorySwap': -1, 'NanoCpus': 0, 'PidsLimit': -1,
                   'Binds': ['/private:/app/data'], 'Mounts': [{'Type': 'bind'}],
                   'PortBindings': {'3030/tcp': [{'HostPort': '3030'}]}, 'IpcMode': 'host',
                   'PidMode': 'host', 'UTSMode': 'host', 'GroupAdd': ['0'],
                   'UsernsMode': 'host', 'CgroupnsMode': 'host', 'Devices': [{'PathOnHost': '/dev/x'}],
                   'DeviceRequests': [{'Count': -1}], 'VolumesFrom': ['production'],
                   'RestartPolicy': {'Name': 'always'}, 'ExtraHosts': ['secret:1.1.1.1']}
        for key, value in changes.items():
            with self.subTest(field=key):
                row = fixture(); row['HostConfig'][key] = value
                self.assertFalse(c.validate(row, IMAGE, TOKEN, PUBLIC).startswith('PASS'))
        row = fixture(); row['Config']['User'] = '0'
        self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'USER_MISMATCH')

    def test_tmpfs_options_are_bounded_and_not_duplicated(self):
        for value in ['rw', 'rw,nosuid,nodev,size=1g,uid=1000,gid=1000,mode=0700',
                      'rw,nosuid,nodev,size=64m,uid=0,gid=1000,mode=0700',
                      'rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0777',
                      'rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0700,suid']:
            row = fixture(); row['HostConfig']['Tmpfs']['/app/data'] = value
            self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'TMPFS_DECLARATION_MISMATCH')

    def test_duplicate_extra_bind_or_readonly_realized_mounts_rejected(self):
        for change in [lambda r: r['Mounts'].append(copy.deepcopy(r['Mounts'][0])),
                       lambda r: r['Mounts'][0].update(Type='bind'),
                       lambda r: r['Mounts'][0].update(Source='/private'),
                       lambda r: r['Mounts'][0].update(RW=False)]:
            row = fixture('running'); change(row)
            self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'REALIZED_MOUNTS_MISMATCH')

    def test_credential_extra_duplicate_and_changed_synthetic_env_rejected(self):
        for extra in ['OPENAI_API_KEY=SYNTHETIC', 'DATABASE_URL=SYNTHETIC',
                      'V79_PLATFORM_SHARED_SECRET=', 'UNKNOWN=SYNTHETIC', 'PORT=1']:
            row = fixture(); row['Config']['Env'].append(extra)
            self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'SYNTHETIC_ENV_MISMATCH')
        self.assertEqual(c.validate(fixture(), IMAGE, TOKEN, {'API_KEY': 'SYNTHETIC'}), 'IMAGE_ENV_ALLOWLIST_UNSAFE')

    def test_states_and_malformed_inputs_fail_closed_without_values(self):
        for state in ['exited', 'dead', 'paused', 'removing', 'restarting', 'unknown']:
            self.assertEqual(c.validate(fixture(state), IMAGE, TOKEN, PUBLIC), 'STATE_NOT_ACCEPTED')
        row = fixture(); row['State']['Running'] = True
        self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'STATE_INCONSISTENT')
        for row in [None, [], {'Config': 'PRIVATE_MARKER'}, {'Mounts': 'PRIVATE_MARKER'}]:
            self.assertNotIn('PRIVATE', c.validate(row, IMAGE, TOKEN, PUBLIC))

    def test_malformed_shapes_and_contradictory_flags_are_rejected(self):
        for value in ({}, '', False, None):
            row = fixture(); row['Mounts'] = value
            self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'INVALID_INPUT')
        row = fixture(); row['NetworkSettings']['Networks'] = ['none']
        self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'INVALID_INPUT')
        for field in ('Paused', 'Restarting', 'Dead', 'OOMKilled'):
            row = fixture('running'); row['State'][field] = True
            self.assertEqual(c.validate(row, IMAGE, TOKEN, PUBLIC), 'STATE_INCONSISTENT')

    def test_purity_no_docker_network_file_or_dynamic_execution(self):
        tree = ast.parse(PATH.read_text())
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].names[0].name, 're')
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(calls & {'open', 'exec', 'eval', '__import__', 'compile', 'print'})


if __name__ == '__main__':
    unittest.main()
