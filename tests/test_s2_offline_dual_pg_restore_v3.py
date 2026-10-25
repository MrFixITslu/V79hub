import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts' / 'v79_s2_offline_dual_pg_restore_v3.py'
spec = importlib.util.spec_from_file_location('s2_verified', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def mock_container(mounts=None, network='none', readonly=True, binds=None):
    return json.dumps([{
        'HostConfig': {
            'NetworkMode': network, 'PortBindings': None,
            'ReadonlyRootfs': readonly,
            'Binds': [] if binds is None else binds,
            'LogConfig': {'Type': 'none'}
        }, 'Mounts': [] if mounts is None else mounts
    }]).encode()


class TestS2TableCountParser(unittest.TestCase):
    def test_valid_psql_bytes(self):
        for raw, expected in ((b'1',1),(b'25',25),(b'999999',999999)):
            self.assertEqual(m.parse_table_count(raw), expected)

    def test_rejects_invalid_and_customer_output(self):
        for bad in (b'', b'0', b'-1', b'1.5', b'12\\n', b'1000000',
                    b'tenant@example.com', b'12 34', '25', None):
            with self.subTest(value=repr(bad)):
                with self.assertRaisesRegex(m.Stop, 'RESTORE_USER_TABLE_COUNT_INVALID'):
                    m.parse_table_count(bad)


class TestS2PodmanMountSafety(unittest.TestCase):
    def test_runtime_tmpfs_three_mounts(self):
        with patch.object(m, 'call', return_value=mock_container()), patch.object(
            m.subprocess, 'run',
            return_value=subprocess.CompletedProcess([], 0, stdout=b'tmpfs\n')
        ) as runner:
            m.inspect_container('synthetic')
            self.assertEqual(runner.call_count, 3)
            for a in runner.call_args_list:
                self.assertEqual(a.args[0][0:2], ['podman', '--remote=false'])
                self.assertEqual(a.args[0][2:4], ['exec', 'synthetic'])
                self.assertEqual(a.args[0][4:8], ['stat', '-f', '-c', '%T'])

    def test_rejects_any_non_tmpfs(self):
        outputs = [b'tmpfs\n', b'overlay\n', b'tmpfs\n']
        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout=outputs.pop(0))
        with patch.object(m, 'call', return_value=mock_container()), patch.object(
            m.subprocess, 'run', side_effect=fake_run
        ):
            with self.assertRaisesRegex(m.Stop, 'DATABASE_NOT_TMPFS_BACKED'):
                m.inspect_container('synthetic')

    def test_rejects_inspect_persistent_volume(self):
        with patch.object(m, 'call', return_value=mock_container(
            mounts=[{'Type': 'volume', 'Destination': '/var/lib/postgresql/data'}]
        )), patch.object(m.subprocess, 'run') as runner:
            with self.assertRaisesRegex(m.Stop, 'PERSISTENT_MOUNT_REFUSED'):
                m.inspect_container('synthetic')
            runner.assert_not_called()

    def test_rejects_bind(self):
        with patch.object(m, 'call', return_value=mock_container(binds=['/x:/y'])):
            with self.assertRaisesRegex(m.Stop, 'UNREVIEWED_HOST_BIND'):
                m.inspect_container('synthetic')

    def test_rejects_network(self):
        with patch.object(m, 'call', return_value=mock_container(network='bridge')):
            with self.assertRaisesRegex(m.Stop, 'RESTORE_NETWORK_NOT_ISOLATED'):
                m.inspect_container('synthetic')

    def test_rejects_writable_root(self):
        with patch.object(m, 'call', return_value=mock_container(readonly=False)):
            with self.assertRaisesRegex(m.Stop, 'ROOT_FILESYSTEM_NOT_READONLY'):
                m.inspect_container('synthetic')

    def test_run_requires_ignored_builtin_image_volumes(self):
        seen=[]
        def no_start(args, **kwargs):
            seen.extend(args)
            raise m.Stop('SIMULATED_STARTUP_FAIL')
        def removal(args, **kwargs):
            return subprocess.CompletedProcess(args, 1 if 'exists' in args else 0, stdout=b'')
        with patch.object(m, 'call', side_effect=no_start), patch.object(
            m.subprocess, 'run', side_effect=removal):
            with self.assertRaisesRegex(m.Stop, 'SIMULATED_STARTUP_FAIL'):
                m.restore_one('hub', '0'*64, Path('/synthetic/not/used'))
        self.assertIn('--image-volume=ignore', seen)
        self.assertIn('--network=none', seen)
        self.assertIn('--read-only', seen)
        self.assertIn('--log-driver=none', seen)
        self.assertIn('--pull=never', seen)


if __name__ == '__main__':
    unittest.main()
