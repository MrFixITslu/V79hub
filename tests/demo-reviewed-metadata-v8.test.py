#!/usr/bin/env python3
"""V8 release regression tests: explicit Compose env is preserved, not waived."""
import ast
import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).parents[1]/'scripts'
def load(name):
    spec=importlib.util.spec_from_file_location('v79_v8_'+name.replace('-','_'),P/name)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def entry(env,removed):
    return {'service':'v79-hub',
            'model':{'services':{'v79-hub':{'environment':env}}},
            'removed_metadata':removed}

class TestV8ReviewedEnvironment(unittest.TestCase):
    def setUp(self):
        self.m=load('paired-compose-transaction-demo-v5.py')

    def normalize(self,old,new,env=None,removed=None,which='candidate'):
        return self.m.review_metadata_environment(
            old,new,entry(env or {},removed or ['NODE_VERSION','YARN_VERSION']),which)

    def test_only_reviewed_absent_metadata_is_removed(self):
        old={'NODE_VERSION':'22.0','YARN_VERSION':'1.2','DATABASE_URL':'same'}
        new={'DATABASE_URL':'same'}
        a,b=self.normalize(old.copy(),new.copy())
        self.assertEqual(a,b)
        self.assertEqual(a,{'DATABASE_URL':'same'})

    def test_explicit_metadata_override_kept_when_actual_matches(self):
        old={'NODE_VERSION':'22.0','DATABASE_URL':'unchanged'}
        new={'NODE_VERSION':'22.0','DATABASE_URL':'unchanged'}
        a,b=self.normalize(old.copy(),new.copy(),{'NODE_VERSION':'22.0'},['NODE_VERSION'])
        self.assertEqual(a,b)
        self.assertEqual(a['NODE_VERSION'],'22.0')

    def test_explicit_metadata_override_drift_refused(self):
        for old,new,pinned in [
            ('22.0','23.0','22.0'),
            ('21.0','22.0','22.0'),
            ('22.0','22.0','23.0')]:
            with self.subTest(old=old,new=new,pinned=pinned):
                with self.assertRaisesRegex(self.m.Refused,
                          'EXPLICIT_IMAGE_METADATA_OVERRIDE_MISMATCH'):
                    self.normalize({'NODE_VERSION':old},{'NODE_VERSION':new},
                                   {'NODE_VERSION':pinned},['NODE_VERSION'])
        with self.assertRaisesRegex(self.m.Refused,'EXPLICIT_IMAGE_METADATA_OVERRIDE_MISMATCH'):
            self.normalize({'NODE_VERSION':'22.0'}, {}, {'NODE_VERSION':'22.0'},['NODE_VERSION'])

    def test_unapproved_metadata_key_never_ignored(self):
        with self.assertRaisesRegex(self.m.Refused,'UNREVIEWED_IMAGE_ENVIRONMENT_CHANGE'):
            self.normalize({'SECRET_VALUE':'x'}, {}, {}, ['SECRET_VALUE'])

    def test_duplicate_review_names_rejected(self):
        with self.assertRaisesRegex(self.m.Refused,'REVIEWED_METADATA_LIST_INVALID'):
            self.normalize({'NODE_VERSION':'22'}, {}, {}, ['NODE_VERSION','NODE_VERSION'])

    def test_unrelated_environment_differences_are_not_normalized(self):
        a,b=self.normalize({'NODE_VERSION':'22','API_KEY':'first'},
                           {'API_KEY':'second'}, {}, ['NODE_VERSION'])
        self.assertNotEqual(a,b)

    def test_rollback_never_normalizes(self):
        a,b=self.normalize({'NODE_VERSION':'22'}, {}, {},
                           ['NODE_VERSION'],which='rollback')
        self.assertNotEqual(a,b)

    def test_v8_packages_exact_module_and_unmodified_transaction_functions(self):
        release=load('release-hardened-pair-demo-v8.py')
        old=load('release-hardened-pair-demo-v7.py')
        self.assertEqual(release.SOURCES['paired-compose-transaction.py'],
                         (P/'paired-compose-transaction-demo-v5.py').read_text())
        for name,source in old.SOURCES.items():
            if name!='paired-compose-transaction.py':
                self.assertEqual(release.SOURCES[name],source)
        self.assertEqual(release.INNER_BYTES,204488782)
        self.assertIsNone(release.CHECKPOINT)
        prev=ast.parse((P/'paired-compose-transaction-demo-v4.py').read_text())
        curr=ast.parse((P/'paired-compose-transaction-demo-v5.py').read_text())
        extract=lambda t:{n.name:ast.dump(n,include_attributes=False)
                          for n in t.body if isinstance(n,ast.FunctionDef)}
        a,b=extract(prev),extract(curr)
        self.assertEqual(set(a)|{'review_metadata_environment'},set(b))
        for name in a:
            if name!='runtime_matches':
                self.assertEqual(a[name],b[name])
        self.assertIn("old_env,new_env=review_metadata_environment(old_env,new_env,entry,which)",
                      (P/'paired-compose-transaction-demo-v5.py').read_text())
        self.assertIn("if old_env!=new_env:raise Refused('ACTUAL_ENVIRONMENT_CHANGED')",
                      (P/'paired-compose-transaction-demo-v5.py').read_text())

if __name__=='__main__':unittest.main()
