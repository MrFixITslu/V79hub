import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('probe', Path(__file__).parents[1] / 'scripts/probe-website-candidate-startup.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProbeTests(unittest.TestCase):
    def test_snapshot_archive_is_private_and_readable_by_node(self):
        secret = b'[{"name":"secret","value":"encrypted-value"}]'
        with tarfile.open(fileobj=io.BytesIO(p.snapshot_archive(secret))) as archive:
            members = archive.getmembers()
            self.assertEqual(len(members), 1)
            member = members[0]
            self.assertEqual((member.name, member.uid, member.gid, member.mode),
                             ('v79-probe-documents.json', 1000, 1000, 0o600))
            self.assertEqual(archive.extractfile(member).read(), secret)

    def test_full_probe_cleans_exact_clone_keeps_production_and_redacts_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'binding.lock').touch()
            (root / 'lead-release-state.json').write_text('{"phase":"ROLLED_BACK"}')
            model = root / 'candidate.json'
            model.write_text(json.dumps({'services': {'web': {'environment': {'SECRET': 'private-token'}}}}))
            plan = {'apps': {
                'V79website': {'service': 'web', 'candidate_file': str(model),
                    'candidate_sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
                    'candidate_image': {'Id': p.IMAGE}, 'rollback_image': {'Id': 'old-web'}},
                'v79-hub': {'rollback_image': {'Id': 'old-hub'}}}}
            manifest = json.dumps(plan).encode()
            (root / 'transaction.json').write_bytes(manifest)
            calls = []
            cid = 'a' * 64
            selected_image = 'sha256:' + 'b' * 64
            def inspect(name):
                if name == cid:
                    probe_dir = next(root.glob('website-startup-probe-*'))
                    return {'Image': selected_image, 'HostConfig': {'NetworkMode': 'none'}, 'Mounts': [],
                        'Config': {'Labels': {'v79.startup.probe': probe_dir.name}},
                        'State': {'Running': False, 'ExitCode': 1, 'Health': {'Status': 'unhealthy'}}}
                return {'Id': name, 'Image': plan['apps'][name]['rollback_image']['Id'],
                        'Config': {}, 'HostConfig': {}, 'Mounts': [],
                        'State': {'Running': True, 'StartedAt': 'unchanged', 'Health': {'Status': 'healthy'}}}
            def call(args, **kwargs):
                calls.append(args)
                if args[:3] == ['docker', 'image', 'inspect']:
                    return json.dumps([{'Config': {'Cmd': ['node', 'dist/server/server.cjs'],
                        'User': 'node', 'WorkingDir': '/app', 'Entrypoint': ['docker-entrypoint.sh']}}]).encode()
                if args[:2] == ['docker', 'cp'] and 'stdout' in kwargs:
                    kwargs['stdout'].write(b'private-data-archive')
                if args[:2] == ['docker', 'exec']:
                    self.assertEqual(args[2:5], ['V79website', 'node', '-e'])
                    self.assertEqual(args[5], p.SNAPSHOT)
                    return b'[]'
                if args[:2] == ['docker', 'create']:
                    self.assertEqual(args[args.index('--network') + 1], 'none')
                    self.assertEqual(args[args.index('--restart') + 1], 'no')
                    self.assertNotIn('--mount', args)
                    envfile = Path(args[args.index('--env-file') + 1])
                    self.assertEqual(stat.S_IMODE(envfile.stat().st_mode), 0o600)
                    self.assertNotIn('private-token', str(args))
                    return cid.encode()
                return b''
            logs = b'[Startup] Server failed: Legacy vision79_saas.db detected private-token'
            stdout = io.StringIO()
            with patch.object(p, 'ROOT', root), patch.object(p, 'MANIFEST', hashlib.sha256(manifest).hexdigest()), \
                 patch.object(p, 'call', side_effect=call), patch.object(p, 'inspect', side_effect=inspect), \
                 patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, logs, b'')), \
                 contextlib.redirect_stdout(stdout):
                p.main(image_override=selected_image)
            self.assertNotIn('private-token', stdout.getvalue())
            self.assertIn('"legacy_database_rejected": true', stdout.getvalue())
            self.assertIn(['docker', 'rm', '-f', cid], calls)
            self.assertEqual([a for a in calls if a[:2] == ['docker', 'start']], [['docker', 'start', cid]])
            probe_dir = next(root.glob('website-startup-probe-*'))
            self.assertEqual(sorted(x.name for x in probe_dir.iterdir()), ['result.json', 'startup.log'])
            self.assertEqual((probe_dir / 'startup.log').read_bytes(), logs)
            self.assertEqual(stat.S_IMODE((probe_dir / 'startup.log').stat().st_mode), 0o600)

    def test_signal_output_contains_only_flags(self):
        result = p.signals('Error: EACCES user@example.org password-secret ERR_MODULE_NOT_FOUND')
        self.assertTrue(result['permission_denied'])
        self.assertTrue(result['module_missing'])
        self.assertTrue(all(isinstance(value, bool) for value in result.values()))


if __name__ == '__main__':
    unittest.main()
