"""Isolated tests for no-write source/readiness checks."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from read_only_acer_preflight import assess, PROTOCOL_PATHS, SENTINEL_SOURCE_RELATIVE

STAGING_SHA = "a" * 40
SENTINEL_SHA = "b" * 40


class ReadOnlyAcerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.staging = self.root / "hub-g2"
        self.sentinel = self.root / "sentinel"
        for p in PROTOCOL_PATHS:
            f = self.staging / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("synthetic test marker", encoding="utf-8")
        for p in SENTINEL_SOURCE_RELATIVE:
            f = self.sentinel / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("synthetic test marker", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def check(self, staging=None, sentinel=None, expected=STAGING_SHA):
        with patch("read_only_acer_preflight._git_head", side_effect=[STAGING_SHA, SENTINEL_SHA]):
            return assess(staging or self.staging, sentinel or self.sentinel, expected)

    def test_separate_expected_source_heads_are_reviewable_not_live_verified(self):
        result = self.check()
        self.assertEqual(result["result"], "source_layout_verified")
        self.assertTrue(result["isolatedStagingReadyForReview"])
        self.assertTrue(result["stagingHeadMatchesExpected"])
        self.assertFalse(result["productionReady"])
        self.assertFalse(result["liveDeploymentAuthorized"])
        self.assertFalse(result["trustedLiveCollectorVerified"])
        self.assertGreater(len(result["unverifiedLiveGates"]), 4)

    def test_unexpected_source_sha_fails_closed(self):
        result = self.check(expected="c" * 40)
        self.assertFalse(result["stagingHeadMatchesExpected"])
        self.assertEqual(result["result"], "needs_attention")
        self.assertFalse(result["isolatedStagingReadyForReview"])

    def test_missing_signer_and_mission_bridge_fail_closed(self):
        (self.staging / PROTOCOL_PATHS[0]).unlink()
        self.assertFalse(self.check()["isolatedStagingReadyForReview"])
        (self.sentinel / SENTINEL_SOURCE_RELATIVE[0]).unlink()
        self.assertFalse(self.check()["sentinelNocSourcePresent"])

    def test_sentinel_and_staging_same_or_nested_directory_rejected(self):
        self.assertFalse(self.check(staging=self.staging, sentinel=self.staging)["sourceTreesSeparate"])
        nested = self.staging / "sentinel_nested"
        self.assertFalse(self.check(staging=self.staging, sentinel=nested)["sourceTreesSeparate"])

    def test_absent_git_revision_does_not_verify_staging(self):
        with patch("read_only_acer_preflight._git_head", side_effect=[None, SENTINEL_SHA]):
            result = assess(self.staging, self.sentinel, STAGING_SHA)
        self.assertFalse(result["stagingHeadMatchesExpected"])
        self.assertFalse(result["isolatedStagingReadyForReview"])
        self.assertIsNone(result["stagingHead"])

    def test_output_contains_no_absolute_paths_or_source_content(self):
        import json
        result = self.check()
        text = json.dumps(result)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("synthetic test marker", text)
        self.assertNotIn("privateKeyPem", text)


if __name__ == "__main__":
    unittest.main()
