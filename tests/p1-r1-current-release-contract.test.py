"""Synthetic-only P1-R1 runtime contract regressions; no Docker or network."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "p1-r1-current-release-contract.py"
spec = importlib.util.spec_from_file_location("p1_r1_contract", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

HUB = "sha256:" + "a" * 64
TIQUET = "sha256:" + "b" * 64
PG = "sha256:" + "c" * 64
EXPECTED = {"v79-hub": HUB, "v79-tiquet-manager": TIQUET}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.files = [Path(self.tmp.name) / "first.yml", Path(self.tmp.name) / "second.yml"]
        for file in self.files:
            file.write_text("services: {}\n", encoding="utf-8")
        self.rows = []
        for name, image in (
            ("v79-hub", HUB), ("v79-tiquet-manager", TIQUET),
            ("v79-hub-postgres", PG), ("tiquet-postgres", PG),
        ):
            self.rows.append({
                "Name": "/" + name,
                "Image": image,
                "State": {"Status": "running", "Health": {"Status": "healthy"}},
                "Config": {"Env": [], "Labels": {}},
                "Mounts": [],
            })
        self.rows[0]["Config"]["Env"] = [
            "V79_REQUIRE_ADMIN_MFA=1", "WIPAY_API_KEY=SYNTHETIC_SECRET_SHOULD_NOT_LEAK",
        ]
        self.rows[0]["Config"]["Labels"] = {
            "com.docker.compose.project.config_files": ",".join(map(str, self.files)),
        }
        self.rows[1]["Config"]["Env"] = [
            "V79_ENTITLEMENT_RECHECK_ENABLED=1", "V79_ALLOW_LEGACY_AUTH=0",
            "V79_TIQUET_LAUNCH_SECRET=SYNTHETIC_SECRET_SHOULD_NOT_LEAK",
        ]

    def run_contract(self, rows=None, exists=lambda sha: True):
        return audit.evaluate(
            copy.deepcopy(self.rows if rows is None else rows),
            EXPECTED, exists, lambda name: Path(name).read_bytes()
        )

    def assert_rejected(self, code, rows=None, exists=lambda sha: True):
        with self.assertRaisesRegex(RuntimeError, code):
            self.run_contract(rows, exists)

    def test_happy_path_redacts_all_secret_values(self):
        result = self.run_contract()
        serialized = __import__("json").dumps(result)
        self.assertEqual(result["result"], "PASS_CURRENT_RUNTIME_CONTRACT_ONLY")
        self.assertEqual(result["compose_count"], 2)
        self.assertFalse(result["restore_verified"])
        self.assertFalse(result["customer_release_authorized"])
        self.assertNotIn("SYNTHETIC_SECRET", serialized)
        self.assertNotIn(str(self.files[0].parent), serialized)

    def test_drift_rejected(self):
        self.rows[0]["Image"] = PG
        self.assert_rejected("LIVE_IMAGE_DRIFT")

    def test_unhealthy_rejected(self):
        self.rows[1]["State"]["Health"]["Status"] = "unhealthy"
        self.assert_rejected("CORE_HEALTH_NOT_VERIFIED")

    def test_disabled_mfa_rejected(self):
        self.rows[0]["Config"]["Env"] = ["V79_REQUIRE_ADMIN_MFA=0"]
        self.assert_rejected("HUB_MFA_NOT_ENABLED")

    def test_missing_entitlement_rejected(self):
        self.rows[1]["Config"]["Env"] = ["V79_ALLOW_LEGACY_AUTH=0"]
        self.assert_rejected("TIQUET_ENTITLEMENT_RECHECK_NOT_ENABLED")

    def test_legacy_auth_rejected(self):
        self.rows[1]["Config"]["Env"][1] = "V79_ALLOW_LEGACY_AUTH=1"
        self.assert_rejected("TIQUET_LEGACY_AUTH_NOT_DISABLED")

    def test_duplicate_compose_layer_rejected(self):
        self.rows[0]["Config"]["Labels"]["com.docker.compose.project.config_files"] = (
            str(self.files[0]) + "," + str(self.files[0])
        )
        self.assert_rejected("COMPOSE_CHAIN_MISSING_DUPLICATE")

    def test_symlink_compose_layer_rejected(self):
        link = Path(self.tmp.name) / "link.yml"
        link.symlink_to(self.files[0])
        self.rows[0]["Config"]["Labels"]["com.docker.compose.project.config_files"] = str(link)
        self.assert_rejected("COMPOSE_SYMLINK_NOT_ALLOWED")

    def test_missing_compose_layer_rejected(self):
        self.files[0].unlink()
        self.assert_rejected("COMPOSE_FILE_UNAVAILABLE")

    def test_missing_pinned_image_rejected(self):
        self.assert_rejected("CURRENT_RELEASE_IMAGE_MISSING", exists=lambda sha: sha != TIQUET)

    def test_unexpected_container_rejected(self):
        self.rows[0]["Name"] = "/arbitrary"
        self.assert_rejected("CORE_CONTAINER_IDENTITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()
