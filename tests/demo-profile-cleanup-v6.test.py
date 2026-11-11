#!/usr/bin/env python3
"""Pure release checks for v6 disposable synthetic profile failure diagnosis."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).parents[1]/'scripts'
def module(name):
    spec=importlib.util.spec_from_file_location('demo_'+name.replace('-','_'),ROOT/name)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
class ExactProfileCleanup(unittest.TestCase):
    def test_v6_packages_exact_enhanced_transaction(self):
        release=module('release-hardened-pair-demo-v6.py')
        new=(ROOT/'paired-compose-transaction-demo-v3.py').read_text()
        old=(ROOT/'paired-compose-transaction-demo-v2.py').read_text()
        self.assertEqual(release.SOURCES['paired-compose-transaction.py'],new)
        self.assertNotEqual(new,old)
        oldrelease=module('release-hardened-pair-demo-v5.py')
        for name,raw in oldrelease.SOURCES.items():
            if name!='paired-compose-transaction.py':
                self.assertEqual(release.SOURCES[name],raw)
        self.assertIsNone(release.CHECKPOINT)
        self.assertEqual(release.INNER_BYTES,204488782)

    def test_cleanup_checks_exact_nonce_ownership_and_attachments(self):
        s=(ROOT/'paired-compose-transaction-demo-v3.py').read_text()
        required=(
            "volume=probe+'-volume-'+str(index)",
            "re.fullmatch(re.escape(nonce)+r'-[0-9]+-volume-[0-9]+',volume)",
            "(info.get('Labels') or {}).get('v79.profile.scope')!=nonce",
            "['docker','ps','--all','--filter','volume='+volume",
            "if attached:raise Refused('PROFILE_VOLUME_STILL_ATTACHED')",
            "for attempt in range(3)",
            "backend.call(['docker','volume','rm',volume])",
            "backend.journal('PROFILE_VOLUME_CLEANUP_FAILED'",
            "backend.journal('PROFILE_CONTAINER_CLEANUP_FAILED'",
            "if cleanup_failed:",
            "raise Refused('PROFILE_OWNED_CLEANUP_INCOMPLETE')",
        )
        for value in required:self.assertIn(value,s)
        self.assertNotIn("'docker','volume','prune'",s)
        self.assertNotIn("'docker','system','prune'",s)
        self.assertNotIn("'docker','rm','-f'",s)

    def test_original_failure_classified_without_raw_logging(self):
        s=(ROOT/'paired-compose-transaction-demo-v3.py').read_text()
        self.assertIn("backend.journal('PROFILE_COMPOSE_CREATE_FAILED',name,reason)",s)
        self.assertIn("raise Refused('PROFILE_COMPOSE_'+reason)",s)
        self.assertIn("process.stderr[:65536].decode('utf-8','replace').lower()",s)
        self.assertIn("'PROFILE_COMPOSE_CREATE_UNAVAILABLE'",s)
        self.assertIn("stdout=subprocess.DEVNULL",s)
        self.assertIn("stderr=subprocess.PIPE",s)
        self.assertIn("'DOCKER_COMPOSE_UP_FAILED'",s)

    def test_previous_transaction_and_data_guards_remain(self):
        current=(ROOT/'paired-compose-transaction-demo-v3.py').read_text()
        previous=(ROOT/'paired-compose-transaction-demo-v2.py').read_text()
        import ast
        def functions(code):
            tree=ast.parse(code)
            return {node.name:ast.dump(node,include_attributes=False)
                    for node in tree.body if isinstance(node,ast.FunctionDef)}
        a=functions(current);b=functions(previous)
        self.assertEqual(set(a),set(b))
        for name in ('rollback','deploy','runtime_matches','protected_fingerprint'):
            self.assertEqual(a[name],b[name])
        self.assertIn("backend.protected();backend.check_files()",current)
        self.assertIn("backend.journal('CANDIDATE_INTENT',name)",current)

if __name__=='__main__':unittest.main()
