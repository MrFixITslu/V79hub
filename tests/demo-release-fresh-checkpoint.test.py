#!/usr/bin/env python3
"""Non-deploying tests for restored-Hub demo release with externally pinned fresh backup."""
import importlib.util
from pathlib import Path
import re
import unittest

SCRIPTS=Path(__file__).parents[1]/'scripts'

def module(name):
    spec=importlib.util.spec_from_file_location('demo_release_'+name.replace('-','_'), SCRIPTS/name)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class DemoV3(unittest.TestCase):
    def test_exported_sources_pin_current_hub(self):
        release=module('release-hardened-pair-demo-v3.py')
        current_review=(SCRIPTS/'demo-review-restored-hub-20261025.py').read_text()
        current_tx=(SCRIPTS/'paired-compose-transaction-demo-v2.py').read_text()
        self.assertEqual(release.SOURCES['review-hardened-release.py'],current_review)
        self.assertEqual(release.SOURCES['paired-compose-transaction.py'],current_tx)
        self.assertIsNone(release.CHECKPOINT)
        review=module('demo-review-restored-hub-20261025.py')
        self.assertEqual(review.RUNTIME_FINGERPRINTS['v79-hub'],
                         'b47583c80c1703a970e05650bb74319d61ae93a42e1244a4da574a7834152825')
        self.assertEqual(review.INPUT_HASHES['v79-hub'],
                         ['ccb8dd4027159615421c67861c2a4aff59155f2f38b0a71bafe13be6b5f8d5e1'])
    def test_demo_release_requires_explicit_recent_checkpoint_and_preserves_gate(self):
        release=module('release-hardened-pair-demo-v3.py')
        import datetime
        now=datetime.datetime.now(datetime.timezone.utc)
        release.fresh({'created_at':now.isoformat(),'verified_at':now.isoformat()})
        old=now-datetime.timedelta(hours=5)
        with self.assertRaisesRegex(release.Refused,'FOUR_HOUR_RELEASE_WINDOW'):
            release.fresh({'created_at':old.isoformat(),'verified_at':now.isoformat()})
        source=(SCRIPTS/'release-hardened-pair-demo-v3.py').read_text()
        self.assertIn("'FRESH_EXPLICIT_CHECKPOINT_NAME_REQUIRED'",source)
        self.assertGreaterEqual(source.count("'--checkpoint-name',CHECKPOINT"),4)
        self.assertIn("CHECKPOINT=args.checkpoint_name",source)
        self.assertIn("'--server-rollback',prepared['plan_sha256'],'--checkpoint-name',CHECKPOINT",source)
        self.assertNotIn("CHECKPOINT = 'release-20261025T173337Z-8f3f12bf'",source)
if __name__=='__main__':unittest.main()
