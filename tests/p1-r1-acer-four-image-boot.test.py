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

    def test_required_app_startup_settings_and_security_remain_enabled(self):
        hub,tiquet=m.application_environment("dummy-h","dummy-t","hub-test","tiquet-test")
        self.assertEqual(hub["V79_HUB_ADMIN_EMAIL"],"vision79slu@gmail.com")
        self.assertEqual(hub["V79_TIQUET_LAUNCH_SECRET"],tiquet["V79_TIQUET_LAUNCH_SECRET"])
        self.assertGreaterEqual(len(tiquet["V79_TIQUET_LAUNCH_SECRET"]),32)
        self.assertEqual(hub["V79_REQUIRE_ADMIN_MFA"],"1")
        self.assertEqual(tiquet["V79_ENTITLEMENT_RECHECK_ENABLED"],"1")
        self.assertEqual(tiquet["V79_ALLOW_LEGACY_AUTH"],"0")
        self.assertEqual(tiquet["V79_ALLOW_EMAIL_ACCOUNT_LINK"],"0")
        other_hub,other_tiquet=m.application_environment("a","b","c","d")
        self.assertNotEqual(hub["V79_TIQUET_LAUNCH_SECRET"],other_hub["V79_TIQUET_LAUNCH_SECRET"])

    def test_db_image_is_forced_local_and_pod(self):
        args=m.pod_command("r1-synthetic", "sha256:"+"1"*64,
                           "r1-test-pod",{"SYNTHETIC":"1"})
        self.assertIn("--pull=never",args)
        self.assertIn("--pod",args)
        self.assertIn("--security-opt=no-new-privileges",args)
        self.assertIn("--image-volume=ignore",args)
        self.assertIn("--read-only",args)
        self.assertIn("--log-driver=none",args)
        self.assertTrue(any(a.startswith("--tmpfs=/tmp:") for a in args))
        self.assertNotIn("-p",args)
        self.assertNotIn("--publish",args)
        self.assertEqual(args[-1],"sha256:"+"1"*64)

    def test_database_tmpfs_destinations_unique_for_both_images(self):
        for commands in (None, ["postgres", "-c", "port=5433"]):
            args=m.pod_command("r1-test", "sha256:"+"1"*64, "r1-pod",
                               {"POSTGRES_PASSWORD":"SYNTHETIC_ONLY"},
                               extra=m.database_tmpfs(), commands=commands)
            mounts=[a.split("=",1)[1].split(":",1)[0]
                    for a in args if a.startswith("--tmpfs=")]
            self.assertEqual(len(mounts),len(set(mounts)))
            self.assertEqual(set(mounts),{
                "/tmp","/var/lib/postgresql/data","/var/run/postgresql"})
            self.assertIn("--read-only",args)
            self.assertIn("--log-driver=none",args)

    def test_failure_categories_do_not_disclose_stderr_or_arguments(self):
        from contextlib import redirect_stdout
        for error, category in (
            (b"duplicate mount destination /tmp PRIVATE_TOKEN", "DUPLICATE_MOUNT"),
            (b"unknown flag PRIVATE_TOKEN", "CLI_OPTION_UNSUPPORTED"),
            (b"permission denied PRIVATE_TOKEN", "PERMISSION_DENIED"),
            (b"PRIVATE_TOKEN other error", "UNCLASSIFIED"),
        ):
            output=io.StringIO()
            result=subprocess.CompletedProcess([],125,b"PRIVATE_DATA",error)
            with mock.patch.object(m.subprocess,"run",return_value=result):
                with redirect_stdout(output), self.assertRaises(m.Stop):
                    m.quiet(["podman","run","SECRET_ARGUMENT"])
            self.assertIn("R1_LOCAL_COMMAND_ERROR_CATEGORY="+category,output.getvalue())
            self.assertNotIn("PRIVATE",output.getvalue())
            self.assertNotIn("SECRET",output.getvalue())

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
                        src.index('quiet([*PD,"unshare","rm"'))
        self.assertIn('create_closed_pod(pod,resolved["v79-hub"])',src)
        self.assertIn('"--infra-command","/bin/sleep infinity"',src)

    def test_startup_observer_never_prints_raw_app_output(self):
        from contextlib import redirect_stdout
        process=mock.Mock()
        process.stdout=io.BytesIO(b"SECRET_CUSTOMER_DATA EACCES private-path at /app/server.ts:321:5")
        process.poll.return_value=1
        args=m.pod_command("r1-app","sha256:dummy","r1-pod",{})
        output=io.StringIO()
        with mock.patch.object(m,"quiet",return_value="created") as q:
            with mock.patch.object(m.subprocess,"Popen",return_value=process):
                with redirect_stdout(output):
                    observer=m.start_app(args)
                    observer[1].join(timeout=2)
        self.assertEqual(observer[2],{"PERMISSION_DENIED"})
        self.assertGreater(observer[0].r1_meta["bytes"],0)
        self.assertEqual(observer[0].r1_meta["locations"],{"server.ts:321:5"})
        self.assertEqual(output.getvalue(),"")
        self.assertIn("create",q.call_args.args[0])
        self.assertNotIn("--detach",q.call_args.args[0])
        self.assertIn("--log-driver=none",q.call_args.args[0])

    def test_infra_image_declared_volumes_rejected(self):
        with mock.patch.object(m,"quiet",return_value='{"/var/lib/postgresql/data":{}}') as q:
            with self.assertRaises(m.Stop): m.create_closed_pod("r1-test","sha256:dummy")
            self.assertEqual(q.call_count,1)
        with mock.patch.object(m,"quiet",side_effect=['null','podid']) as q:
            m.create_closed_pod("r1-test","sha256:dummy")
            self.assertIn("--network=none",q.call_args.args[0])

    def test_app_data_not_decrypted_until_both_databases_start(self):
        src=SRC.read_text()
        self.assertLess(src.index('wait_sql(pg_t,5433,db_t)'),
                        src.index('extract_verified(root,selected,scratch)'))

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
