"""Policy tests for disconnected recovered-data smoke runner (synthetic only)."""
import importlib.util
from pathlib import Path
import unittest

SRC=Path(__file__).resolve().parents[1]/"scripts/p1-r1-acer-four-image-boot.py"
spec=importlib.util.spec_from_file_location("r1boot",SRC)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SafetyContractTests(unittest.TestCase):
    def test_only_those_three_real_application_mounts_selected(self):
        self.assertEqual(set(m.TARGETS),{
            ("v79-hub","/app/data"),
            ("v79-tiquet-manager","/app/data"),
            ("v79-tiquet-manager","/app/uploads")})
        self.assertEqual(len(set(m.TARGETS.values())),3)

    def test_db_image_is_forced_local_and_pod(self):
        args=m.pod_command("r1-synthetic", "sha256:"+"1"*64,
                           "r1-test-pod",{"SYNTHETIC":"1"})
        self.assertIn("--pull=never",args)
        self.assertIn("--pod",args)
        self.assertIn("--security-opt=no-new-privileges",args)
        self.assertNotIn("-p",args)
        self.assertNotIn("--publish",args)
        self.assertEqual(args[-1],"sha256:"+"1"*64)

    def test_proof_and_ram_scratch_only(self):
        src=SRC.read_text()
        for x in (
            "RUN_ONLY_ON_ACER" if False else "ACER_HOST_ONLY",
            'fs=="tmpfs"',
            "ACTIVE_SWAP_REJECTED_FOR_PRIVATE_RECOVERY",
            'dir="/dev/shm"',
            '"--network=none"',
            "R1_ORIGINAL_OCI_PIN_TO_LOCAL_CONFIG_IDS" if False else
                 "prove_and_resolve_saved_images",
            "R1_EPHEMERAL_POD_AND_RAM_SCRATCH_REMOVED",
            "R1_OWNER_MFA_POSITIVE",
            "R1_SSO_TENANT_ISOLATION",
            "R1_ROLLBACK_BOOT",
            "R1_CUSTOMER_RELEASE",
        ):
            self.assertIn(x,src)
        for danger in ('"ssh"','"docker"','"load"','"pull"',
                       '"tag"',"extractall"):
            self.assertNotIn(danger,src)

if __name__=="__main__":
    unittest.main(verbosity=2)
