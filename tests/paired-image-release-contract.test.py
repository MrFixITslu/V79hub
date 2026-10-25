import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('paired_contract', Path(__file__).resolve().parents[1] / 'scripts/paired-image-release-contract.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ContractTests(unittest.TestCase):
    def models(self):
        before = {'name': 'existing-project', 'services': {
            'v79-hub': {'image': 'historical-tag', 'environment': {'WIPAY_ENV': 'sandbox', 'PRICE': '$150', 'V79_REQUIRE_ADMIN_MFA': '1'},
                        'volumes': [{'type': 'bind', 'source': '/existing', 'target': '/app/data', 'read_only': False}],
                        'security_opt': ['no-new-privileges:true']},
            'database': {'image': 'unchanged', 'volumes': ['database:/data']},
        }, 'volumes': {'database': {'external': True}}, 'networks': {'proxy': {'external': True}}}
        candidate, rollback = copy.deepcopy(before), copy.deepcopy(before)
        candidate['services']['v79-hub']['image'] = contract.CANDIDATE['v79-hub']
        rollback['services']['v79-hub']['image'] = contract.CURRENT['v79-hub']
        return before, candidate, rollback

    def check(self, models):
        return contract.verify_models(*models, {'v79-hub': contract.CURRENT['v79-hub']})

    def test_exact_model_and_immutable_rollback(self):
        models = self.models()
        receipt = self.check(models)
        self.assertTrue(receipt['candidate_only_image_delta'])
        self.assertFalse(receipt['deployment_authorized'])
        self.assertNotIn('$150', str(receipt))
        self.assertEqual(models[0]['services']['v79-hub']['image'], 'historical-tag')

    def test_rejects_each_material_runtime_change(self):
        for field, value in [('environment', {'WIPAY_ENV': 'live'}), ('volumes', []),
                             ('security_opt', []), ('privileged', True), ('command', ['different']),
                             ('user', 'root'), ('ports', ['0.0.0.0:3040:3000'])]:
            with self.subTest(field=field):
                models = self.models()
                models[1]['services']['v79-hub'][field] = value
                with self.assertRaises(contract.Refused): self.check(models)

    def test_other_service_and_top_level_changes_rejected(self):
        for change in ('other_service', 'network', 'volume'):
            with self.subTest(change=change):
                models = self.models()
                if change == 'other_service': models[1]['services']['database']['image'] = 'different'
                elif change == 'network': models[1]['networks'] = {}
                else: models[1]['volumes'] = {}
                with self.assertRaises(contract.Refused): self.check(models)

    def test_rollback_data_security_or_tag_drift_rejected(self):
        for change in ('tag', 'environment', 'volume', 'other_service'):
            with self.subTest(change=change):
                models = self.models()
                service = models[2]['services']['v79-hub']
                if change == 'tag': service['image'] = 'mutable-rollback-tag'
                elif change == 'environment': service['environment']['PRICE'] = '$999'
                elif change == 'volume': service['volumes'] = []
                else: models[2]['services']['database']['image'] = 'changed'
                with self.assertRaises(contract.Refused): self.check(models)

    def test_forged_baseline_rejected(self):
        with self.assertRaises(contract.Refused):
            contract.verify_models(*self.models(), {'v79-hub': 'sha256:wrong'})

    def test_tiquet_project_validated_separately(self):
        before = {'services': {'v79-tiquet-manager': {'image': 'old', 'environment': {'PLAN_PRICE_STARTER': '$150', 'V79_ALLOW_LEGACY_AUTH': '0'}}}}
        candidate, rollback = copy.deepcopy(before), copy.deepcopy(before)
        candidate['services']['v79-tiquet-manager']['image'] = contract.CANDIDATE['v79-tiquet-manager']
        rollback['services']['v79-tiquet-manager']['image'] = contract.CURRENT['v79-tiquet-manager']
        self.assertTrue(contract.verify_models(before, candidate, rollback, {'v79-tiquet-manager': contract.CURRENT['v79-tiquet-manager']})['rollback_complete_model_match'])

    def images(self):
        config = {'Env': ['PATH=/usr/bin', 'FEATURE=off'], 'Cmd': ['node', 'server.js'], 'Entrypoint': ['entrypoint.sh'], 'User': 'node', 'WorkingDir': '/app'}
        old = {'Id': contract.CURRENT['v79-hub'], 'Config': copy.deepcopy(config)}
        new = {'Id': contract.CANDIDATE['v79-hub'], 'Config': copy.deepcopy(config)}
        new['Config']['Labels'] = {'org.opencontainers.image.revision': contract.REVISIONS['v79-hub']}
        return old, new

    def test_candidate_inherited_defaults_and_source(self):
        self.assertFalse(contract.verify_image_defaults('v79-hub', {}, *self.images())['deployment_authorized'])

    def test_default_environment_cannot_add_hidden_flag(self):
        old, new = self.images()
        new['Config']['Env'].append('UNAPPROVED_FLAG=on')
        with self.assertRaises(contract.Refused): contract.verify_image_defaults('v79-hub', {}, old, new)

    def test_explicit_environment_preserves_existing_override(self):
        old, new = self.images()
        new['Config']['Env'] = ['PATH=/usr/bin', 'FEATURE=new-default']
        contract.verify_image_defaults('v79-hub', {'environment': {'FEATURE': 'same-explicit-value'}}, old, new)

    def test_null_process_override_still_inherits(self):
        old, new = self.images()
        new['Config']['Cmd'] = ['unexpected']
        with self.assertRaises(contract.Refused): contract.verify_image_defaults('v79-hub', {'command': None}, old, new)
        contract.verify_image_defaults('v79-hub', {'command': []}, old, new)

    def test_duplicate_environment_and_unresolved_environment_rejected(self):
        old, new = self.images()
        new['Config']['Env'].append('FEATURE=duplicate')
        with self.assertRaises(contract.Refused): contract.verify_image_defaults('v79-hub', {}, old, new)
        with self.assertRaises(contract.Refused): contract.verify_image_defaults('v79-hub', {'environment': {'MISSING': None}}, *self.images())

    def test_new_implicit_volume_and_healthcheck_rejected(self):
        for key, value in [('Volumes', {'/new': {}}), ('Healthcheck', {'Test': ['NONE']})]:
            old, new = self.images()
            new['Config'][key] = value
            with self.assertRaises(contract.Refused): contract.verify_image_defaults('v79-hub', {}, old, new)

    def test_candidate_provenance_rejected(self):
        old, new = self.images()
        new['Config']['Labels']['org.opencontainers.image.revision'] = 'unapproved'
        with self.assertRaises(contract.Refused): contract.verify_image_defaults('v79-hub', {}, old, new)


if __name__ == '__main__': unittest.main()
