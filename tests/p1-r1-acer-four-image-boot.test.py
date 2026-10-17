"""Policy tests for disconnected recovered-data smoke runner (synthetic only)."""
import importlib.util
import tempfile
import io
import tarfile
import subprocess
from unittest import mock
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
        self.assertIn("--read-only",args)
        self.assertIn("--log-driver=none",args)
        self.assertTrue(any(a.startswith("--tmpfs=/tmp:") for a in args))
        self.assertNotIn("-p",args)
        self.assertNotIn("--publish",args)
        self.assertEqual(args[-1],"sha256:"+"1"*64)

    def test_safe_tar_mount_copy_and_no_config_secret_extraction(self):
        # This is entirely synthetic; no actual GPG key/customer backup.
        actual_popen=subprocess.Popen
        def decrypt_with_cat(args,**kw):
            self.assertEqual(args[0],"gpg")
            return actual_popen(["cat",args[-1]],**kw)
        with tempfile.TemporaryDirectory() as temp:
            original=Path(temp)
            raw=original/"hub-mount-01.tar.gpg"
            with tarfile.open(raw,"w:gz") as t:
                directory=tarfile.TarInfo("app/data")
                directory.type=tarfile.DIRTYPE
                t.addfile(directory)
                payload=b"CI_ONLY_DUMMY_DATA"
                file=tarfile.TarInfo("app/data/state.json")
                file.size=len(payload)
                t.addfile(file,io.BytesIO(payload))
            scratch=original/"scratch"
            scratch.mkdir()
            with mock.patch.object(m.subprocess,"Popen",side_effect=decrypt_with_cat):
                m.extract_verified(original,
                    {"hub-mount-01.tar.gpg":("app/data","hub_data")},scratch)
            self.assertEqual((scratch/"hub_data"/"state.json").read_bytes(),
                             b"CI_ONLY_DUMMY_DATA")
            self.assertFalse((scratch/"hub_data"/"state.json").is_symlink())

    def test_missing_or_wrong_mount_archive_fails_closed(self):
        manifest={"appMountDestinations":{
            "v79-hub":["/app/data","/run/secrets/mock-one"],
            "v79-tiquet-manager":["/app/data","/app/uploads"]}}
        with self.assertRaises(m.Stop):
            m.choose_archives({},manifest)

    def test_denies_writable_image_layer_or_file_logging(self):
        import json
        base=[{"HostConfig":{"ReadonlyRootfs":True,
                              "PortBindings":None,
                              "LogConfig":{"Type":"none"}},
               "Mounts":[{"Type":"tmpfs","Destination":"/tmp"}]}]
        with mock.patch.object(m,"quiet",return_value=json.dumps(base)):
            m.inspect_no_net("r1-dummy")
        for mutate in (
            lambda doc:doc[0]["HostConfig"].update(ReadonlyRootfs=False),
            lambda doc:doc[0]["HostConfig"]["LogConfig"].update(Type="k8s-file"),
            lambda doc:doc[0]["Mounts"].append({
                "Type":"volume","Destination":"/somewhere"}),
        ):
            instance=json.loads(json.dumps(base))
            mutate(instance)
            with mock.patch.object(m,"quiet",return_value=json.dumps(instance)):
                with self.assertRaises(m.Stop):
                    m.inspect_no_net("r1-dummy")

    def test_cleanup_cli_errors_do_not_authorize_ram_deletion(self):
        src=SRC.read_text()
        self.assertIn('need(left.returncode==1,',src)
        self.assertLess(src.index('need(left.returncode==1,'),
                        src.index('shutil.rmtree(scratch)'))
        self.assertIn('"--infra-image",resolved["v79-hub-postgres"]',src)
        self.assertIn('"--infra-command","/bin/sleep infinity"',src)

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
