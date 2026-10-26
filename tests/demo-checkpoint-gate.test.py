#!/usr/bin/env python3
"""Non-deploying checks for owner-bound demo readiness/capture release gate."""
import base64
import importlib.util
import re
from pathlib import Path
import unittest

ROOT=Path(__file__).parents[1]/'scripts'
EXPECTED_PATH='/home/firelion/.v79-hardened-pair-releases/pair-20261025T204350Z-7a93ff4e6be0/v79-hub-rollback.json'
EXPECTED_HASH='ccb8dd4027159615421c67861c2a4aff59155f2f38b0a71bafe13be6b5f8d5e1'
def module(path):
    spec=importlib.util.spec_from_file_location('v79_demo_'+path.stem.replace('-','_'),path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
class DemoGate(unittest.TestCase):
    def test_exact_restored_compose_pin(self):
        ready=module(ROOT/'demo-readonly-inventory-20261025.py')
        self.assertEqual(ready.EXPECTED_HUB_SOURCES,{EXPECTED_PATH:EXPECTED_HASH})
        self.assertEqual(len(ready.EXPECTED_HUB_SOURCES),1)
        self.assertEqual(len(ready.EXPECTED_MOUNTS['v79-hub']),7)
    def test_capture_embeds_identical_readiness(self):
        capture=module(ROOT/'demo-capture-checkpoint-20261025.py')
        expected=(ROOT/'demo-readonly-inventory-20261025.py').read_bytes()
        self.assertEqual(base64.b64decode(capture.READINESS_B64),expected)
        self.assertIsNone(capture.INVENTORY)
        self.assertEqual(capture.TIMERS,[
            'v79-g2-approved-task-worker.timer',
            'v79-workforce-evening.timer',
            'v79-workforce-morning.timer'])
        self.assertEqual(len(capture.APPS),3)
    def test_explicit_inventory_pin_must_be_full_sha256(self):
        script=(ROOT/'demo-capture-checkpoint-20261025.py').read_text()
        self.assertIn("p.add_argument('--inventory-sha256')",script)
        self.assertIn("a.inventory_sha256",script)
        self.assertIn("'FRESH_EXTERNAL_INVENTORY_SHA256_REQUIRED'",script)
        self.assertIn("'--server-capture',directory",script)
        self.assertIn("'--inventory-sha256',INVENTORY",script)
        self.assertNotIn("INVENTORY = 'f6774eb6706d6fb363bb9331f6f3ea97bc5002e194dca5589757fb8c4a1962d2'",script)
if __name__=='__main__':
    unittest.main()
