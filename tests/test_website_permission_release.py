import ast
import copy
import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load('permission_release', ROOT / 'scripts/prepare-website-permission-release.py')
fixtures = load('permission_binding_fixture', ROOT / 'tests/test_website_lead_binding.py')


class PermissionReleaseTests(unittest.TestCase):
    def test_controller_binding_changes_only_constants_and_executes_new_scope(self):
        source = (ROOT / 'scripts/lead-release-supervisor.py').read_bytes()
        constants = {'ROOT': "Path('/private/new-release')", 'MANIFEST': repr('a' * 64),
                     'ADAPTER_SHA': repr('b' * 64), 'TIMER': repr('new.timer'), 'SERVICE': repr('new.service')}
        bound = p.replace_constants(source, constants)
        original = ast.parse(source)
        changed = ast.parse(bound)
        self.assertEqual([ast.dump(n) for n in original.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))],
                         [ast.dump(n) for n in changed.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))])
        namespace = {'__name__': 'not_main'}
        exec(compile(bound, '<bound>', 'exec'), namespace)
        self.assertEqual(namespace['ROOT'], Path('/private/new-release'))
        self.assertEqual(namespace['MANIFEST'], 'a' * 64)
        self.assertEqual(namespace['TIMER'], 'new.timer')
        with self.assertRaisesRegex(ValueError, 'BINDING_CONSTANTS_MISSING'):
            p.replace_constants(source, {'NOT_A_CONSTANT': '1'})

    def test_selector_retains_original_engine_creation_validation_and_cleanup(self):
        engine = load('permission_profile_engine', ROOT / 'tests/fixtures/release-engine-b233/paired-compose-transaction.py')
        _, selected = p.selected_profile_function(engine)
        original = ast.parse(textwrap.dedent(inspect.getsource(engine.stopped_profiles)))
        function = selected.body[0]
        function.name = 'stopped_profiles'
        function.args.args.pop()
        loops = [n for n in ast.walk(function) if isinstance(n, ast.For)
                 and isinstance(n.target, ast.Name) and n.target.id == 'which']
        guard = loops[0].body.pop(0)
        self.assertIsInstance(guard, ast.If)
        self.assertIsInstance(guard.body[0], ast.Continue)
        self.assertEqual(ast.dump(original, include_attributes=False), ast.dump(selected, include_attributes=False))

    def test_cached_profile_reuse_runs_real_validator_and_rejects_changed_image_or_credentials(self):
        engine, before, after, entry = fixtures.BindingTests().fixture('candidate')
        # Store exactly the normalized format produced by the previous receipt wrapper.
        prior = {'app': 'v79-hub', 'which': 'candidate', 'engine_message': 'RUNTIME_MATCHED',
                 'entry': entry, 'before': before, 'after': after}
        after['State'] = {'Running': False, 'StartedAt': '0001-01-01T00:00:00Z'}
        entry['candidate_sha256'] = 'source-model-hash'
        pin = entry['candidate_image']['Id']
        entry['image_manifests'] = {pin: pin}
        old = {'apps': {'v79-hub': entry}, 'selinux_enabled': False}
        new = copy.deepcopy(old)
        helper = SimpleNamespace(private=lambda path: json.dumps(prior).encode())
        # Fixture already installs compatibility; this exercises the real validator.
        with patch.object(p, 'OLD', Path('/private/prior')):
            p.verify_reused(engine, helper, old, new, 'v79-hub', 'candidate', 'capture.json')
            changed = copy.deepcopy(new)
            changed['apps']['v79-hub']['candidate_image']['Id'] = 'sha256:' + '9' * 64
            with self.assertRaisesRegex(ValueError, 'PASSED_PROFILE_INPUTS_CHANGED'):
                p.verify_reused(engine, helper, old, changed, 'v79-hub', 'candidate', 'capture.json')
            changed = copy.deepcopy(new)
            changed['apps']['v79-hub']['approved_environment']['V79_WEBSITE_EVENT_SECRET'] = 'new-secret'
            with self.assertRaisesRegex(ValueError, 'PASSED_PROFILE_INPUTS_CHANGED'):
                p.verify_reused(engine, helper, old, changed, 'v79-hub', 'candidate', 'capture.json')


if __name__ == '__main__':
    unittest.main()
