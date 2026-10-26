#!/usr/bin/env python3
"""Verify the exact accepted archive size and sanitized failure reporting before live cutover."""
import importlib.util
from pathlib import Path
import re
import unittest
P=Path(__file__).parents[1]/'scripts'
class TransferTests(unittest.TestCase):
    def test_v4_archive_limit_matches_verified_accepted_member_size(self):
        name='release-hardened-pair-demo-v4.py'
        spec=importlib.util.spec_from_file_location('v79_demo_release_v4',P/name)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        manifest=(P/'continue-manifest-bound-pair.py').read_text()
        declared=re.search(r'^INNER_BYTES=([0-9]+)$',manifest,re.M)
        self.assertIsNotNone(declared)
        self.assertEqual(mod.INNER_BYTES,int(declared.group(1)))
        self.assertEqual(mod.INNER_BYTES,204488782)
        self.assertIsNone(mod.CHECKPOINT)
        source=(P/name).read_text()
        self.assertIn("total+=len(block);need(total<=INNER_BYTES,'TRANSFER_TOO_LARGE')",source)
        self.assertIn("need(total==INNER_BYTES,'TRANSFER_SIZE_MISMATCH')",source)
        self.assertIn("z.getinfo('patched-pair.docker.tar.gz').file_size==INNER_BYTES",source)
        self.assertIn("need(h.hexdigest()==args.server_load,'ACCEPTED_IMAGE_TRANSFER_HASH_MISMATCH')",source)
        self.assertIn("archive_file,'sha256').hexdigest()==review.ARCHIVE_SHA",source)
        self.assertNotIn("total<=203470115",source)
    def test_failed_transport_reveals_only_allowlisted_remote_reason(self):
        src=(P/'release-hardened-pair-demo-v4.py').read_text()
        self.assertIn("reason=report.get('reason') if report.get('status')=='BLOCKED' else None",src)
        self.assertIn("re.fullmatch(r'[A-Z][A-Z0-9_]{0,96}',reason)",src)
        self.assertIn("raise Refused('IMAGE_TRANSFER_'+reason)",src)
        self.assertIn("raise Refused('IMAGE_TRANSFER_OR_LOAD_FAILED')",src)
        self.assertIn('stderr=subprocess.DEVNULL',src)
    def test_private_http_preflight_no_host_port_assumption(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('v79_demo_health_v4',
            P/'release-hardened-pair-demo-v4.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with patch.object(mod.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as invoke:
            mod.local_health_pair()
            self.assertEqual(invoke.call_count,2)
            first=invoke.call_args_list[0].args[0]
            second=invoke.call_args_list[1].args[0]
            self.assertEqual(first[:3],['docker','exec','v79-hub'])
            self.assertEqual(second[:3],['docker','exec','v79-tiquet-manager'])
            self.assertIn('http://127.0.0.1:3040/api/health',first)
            self.assertIn('http://127.0.0.1:3050/health',second)
        with patch.object(mod.subprocess,'run',return_value=SimpleNamespace(returncode=2)):
            with self.assertRaisesRegex(mod.Refused,'SELECTED_PRIVATE_HTTP_HEALTH_FAILED'):
                mod.local_health_pair()
        source=(P/'release-hardened-pair-demo-v4.py').read_text()
        self.assertIn('    local_health_pair()\n    need(hashlib.sha256(payload[',source)
        self.assertNotIn("urllib.request.urlopen(url",source)

    def test_historical_v3_and_mounted_transaction_unmodified(self):
        original=(P/'release-hardened-pair-demo-v3.py').read_text()
        changed=(P/'release-hardened-pair-demo-v4.py').read_text()
        self.assertIn('203470115',original)
        self.assertIn('INNER_BYTES = 204488782',changed)
        spec=importlib.util.spec_from_file_location('v79_demo_release_v4',P/'release-hardened-pair-demo-v4.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        self.assertEqual(mod.SOURCES['paired-compose-transaction.py'],
                        (P/'paired-compose-transaction-demo-v2.py').read_text())
if __name__=='__main__':unittest.main()
