import ast
import copy
import importlib.util
import json
from pathlib import Path
import unittest

source=Path(__file__).parents[1]/'scripts/diagnose-website-lead-label.py'
spec=importlib.util.spec_from_file_location('label_diagnostic',source)
diagnostic=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic)


class DiagnosticTests(unittest.TestCase):
    def test_reports_safe_label_identity_but_no_private_names_or_values(self):
        before={'Config':{'Labels':{'com.docker.compose.oneoff':'False','private-secret-name':'secret-a'}}}
        after={'Config':{'Labels':{'com.docker.compose.oneoff':'True','private-secret-name':'secret-b'}}}
        result=diagnostic.label_report('APPLICATION_LABELS_CHANGED:com.docker.compose.oneoff,private-secret-name',before,after)
        encoded=json.dumps(result)
        self.assertIn('com.docker.compose.oneoff',encoded)
        for sensitive in ('private-secret-name','secret-a','secret-b'):self.assertNotIn(sensitive,encoded)
        self.assertFalse(result[0]['values_equal']);self.assertIn('key_sha256',result[1])

    def test_metadata_expectations_match_original_validator_without_mutating_source(self):
        before={'Config':{'Labels':{'org.opencontainers.image.revision':'old'}}}
        after={'Config':{'Labels':{'org.opencontainers.image.revision':'old'}}}
        entry={'rollback_image':{'Config':{'Labels':{'org.opencontainers.image.revision':'old'}}},
            'candidate_image':{'Config':{'Labels':{'org.opencontainers.image.revision':'new'}}},
            'model':{'services':{'hub':{}}},'service':'hub','directory':'/private'}
        original=copy.deepcopy(before)
        report=diagnostic.label_report('APPLICATION_LABELS_CHANGED:org.opencontainers.image.revision',before,after,entry)
        self.assertFalse(report[0]['values_equal']);self.assertTrue(report[0]['expected_matches_image'])
        self.assertFalse(report[0]['actual_matches_image']);self.assertEqual(before,original)

    def test_narrow_probe_protects_website_and_has_no_cutover_call(self):
        plan={'apps':{'v79-hub':{'baseline':{'Id':'hub'}},'V79website':{'baseline':{'Id':'website'}}},
            'protected':{'database':{'Id':'db'}}}
        original=copy.deepcopy(plan);one=diagnostic.narrow(plan)
        self.assertEqual(set(one['apps']),{'v79-hub'})
        self.assertEqual(one['protected']['V79website'],{'Id':'website'});self.assertEqual(plan,original)
        tree=ast.parse(source.read_text())
        calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        for forbidden in ('deploy','rollback','switch','start','stop','arm','disarm'):
            self.assertNotIn(forbidden,calls)
        self.assertEqual(calls.count('stopped_profiles'),1)


if __name__=='__main__':unittest.main()
