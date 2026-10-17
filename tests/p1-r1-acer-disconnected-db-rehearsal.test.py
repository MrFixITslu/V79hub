"""Synthetic R1 database restore safety tests — no Podman, GPG or network."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "scripts/p1-r1-acer-disconnected-db-rehearsal.py"
spec = importlib.util.spec_from_file_location("acer_r1_dbrestore_under_test", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class R1SyntheticSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="r1-acerdummy-")
        self.root = Path(self.tmp.name)
        os.chmod(self.root, 0o700)
        files=[]
        for name, kind in [("hub-pg.dump.gpg","pg"),
                           ("tiquet-pg.dump.gpg","pg"),
                           ("exact-images-and-rollback.tar.gpg","tar")]:
            data=("CI-SYNTHETIC-" + name).encode()
            (self.root/name).write_bytes(data)
            os.chmod(self.root/name, 0o600)
            files.append({"name":name,"type":kind,"bytes":len(data),
                          "sha256":hashlib.sha256(data).hexdigest()})
        for i in range(11):
            files.append({"name":f"dummy-{i}.tar.gpg","type":"tgz",
                          "bytes":0,"sha256":"0"*64})
        self.data={"schema":1,"status":"CAPTURED_NOT_RESTORED",
                   "images":m.IMAGES.copy(),"rollbackHub":m.ROLLBACK,"files":files}
        self.write_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def write_manifest(self):
        p=self.root/"ciphertext-manifest.json"
        p.write_text(json.dumps(self.data))
        os.chmod(p,0o600)

    def test_valid_pinned_manifest(self):
        self.assertEqual(m.validate_manifest(self.root),self.root)

    def test_reject_any_critical_ciphertext_mutation(self):
        for name in m.REQUIRED:
            with self.subTest(name=name):
                p=self.root/name
                previous=p.read_bytes()
                p.write_bytes(previous+b"bad")
                with self.assertRaisesRegex(m.Stop,"BACKUP_REQUIRED_COMPONENT_INTEGRITY_FAILURE"):
                    m.validate_manifest(self.root)
                p.write_bytes(previous)

    def test_reject_wrong_image_id_and_rollback_drift(self):
        self.data["images"]["v79-hub"]="sha256:"+"0"*64
        self.write_manifest()
        with self.assertRaisesRegex(m.Stop,"BACKUP_PROVENANCE_NOT_PINNED"):
            m.validate_manifest(self.root)
        self.data["images"]=m.IMAGES.copy()
        self.data["rollbackHub"]="sha256:"+"0"*64
        self.write_manifest()
        with self.assertRaisesRegex(m.Stop,"BACKUP_PROVENANCE_NOT_PINNED"):
            m.validate_manifest(self.root)

    def test_permissions_and_incomplete_marker_fail_closed(self):
        os.chmod(self.root,0o755)
        with self.assertRaisesRegex(m.Stop,"ARCHIVE_DIRECTORY_PERMISSIONS"):
            m.validate_manifest(self.root)
        os.chmod(self.root,0o700)
        (self.root/"CAPTURE_INCOMPLETE").write_text("")
        with self.assertRaisesRegex(m.Stop,"INCOMPLETE_BACKUP_SET"):
            m.validate_manifest(self.root)

    def test_restore_containers_are_disconnected_tmpfs_and_no_pull(self):
        args=m.db_run_args("synthetic-db-name",m.IMAGES["v79-hub-postgres"],"r1_hub_restore")
        self.assertIn("--remote=false",args)
        self.assertIn("--network=none",args)
        self.assertIn("--pull=never",args)
        self.assertIn("--rm",args)
        self.assertIn("--security-opt=no-new-privileges",args)
        self.assertIn("--tmpfs=/var/lib/postgresql/data:rw,size=1073741824,mode=0700",args)
        self.assertNotIn("-p",args)
        self.assertNotIn("--publish",args)
        self.assertNotIn("--volume",args)
        self.assertNotIn("--network=host",args)
        self.assertNotIn("--network=slirp4netns",args)
        self.assertEqual(args[-1],m.IMAGES["v79-hub-postgres"])
        self.assertTrue(any(a.startswith("POSTGRES_PASSWORD=") for a in args))
        self.assertNotIn("v79sl",str(args))

    def test_effective_inspect_denies_network_ports_and_unencrypted_persistent_mounts(self):
        base={
            "HostConfig":{
                "NetworkMode":"none","PortBindings":None,
                "Tmpfs":{"/var/lib/postgresql/data":"rw,size=1073741824,mode=0700"}},
            "Mounts":[{"Type":"tmpfs","Destination":"/var/lib/postgresql/data"}]}
        with mock.patch.object(m,"silent_run",return_value=json.dumps([base])):
            m.assert_disconnected_tmpfs_container("synthetic")
        for mutate in (
            lambda x:x["HostConfig"].update(NetworkMode="bridge"),
            lambda x:x["HostConfig"].update(PortBindings={"5432/tcp":[{"HostPort":"5432"}]}),
            lambda x:x["HostConfig"].update(Tmpfs={}),
            lambda x:x["Mounts"].append({"Type":"volume","Destination":"/var/lib/postgresql/data"}),
            lambda x:x["Mounts"].append({"Type":"bind","Destination":"/run/secrets/live"}),
        ):
            sample=json.loads(json.dumps(base))
            mutate(sample)
            with mock.patch.object(m,"silent_run",return_value=json.dumps([sample])):
                with self.assertRaises(m.Stop):
                    m.assert_disconnected_tmpfs_container("synthetic")

    def test_exact_oci_index_mapping_used_without_importing_images(self):
        # Different cryptographic OCI INDEX ids vs locally cached CONFIG IDs.
        values=list(m.IMAGES.values())+[m.ROLLBACK]
        indexes=[v.removeprefix("sha256:") for v in values]
        configs=[format(i+1, "064x") for i in range(5)]
        remap=dict(zip(indexes,configs))
        proof=SimpleNamespace(prep=lambda root:self.root/"encrypted",
                              stream_proof=lambda archive,return_mapping=False:remap)
        spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _p:None))
        inventory=json.dumps([{"Id":"sha256:"+c} for c in configs])
        with mock.patch.object(m.importlib.util,"spec_from_file_location",return_value=spec), \
             mock.patch.object(m.importlib.util,"module_from_spec",return_value=proof), \
             mock.patch.object(m,"silent_run",return_value=inventory), \
             mock.patch.object(m,"local_image_exists",return_value=True):
            resolved=m.prove_and_resolve_saved_images(self.root)
        self.assertEqual(resolved["v79-hub-postgres"],"sha256:"+configs[2])
        self.assertEqual(resolved["tiquet-postgres"],"sha256:"+configs[3])
        self.assertNotEqual(resolved["v79-hub-postgres"],m.IMAGES["v79-hub-postgres"])

    def test_missing_pin_cache_or_addressability_fails_closed(self):
        values=list(m.IMAGES.values())+[m.ROLLBACK]
        pins=[v.removeprefix("sha256:") for v in values]
        configs=[format(i+1,"064x") for i in range(5)]
        expected=dict(zip(pins,configs))
        spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _p:None))
        for reason in ("missing-pin","missing-local","not-addressable"):
            with self.subTest(reason=reason):
                mapping=dict(expected)
                if reason=="missing-pin":
                    mapping.pop(pins[0])
                proof=SimpleNamespace(prep=lambda root:self.root/"ciphertext",
                                      stream_proof=lambda archive,return_mapping=False:mapping)
                inventory=[{"Id":"sha256:"+c} for c in
                           (configs[:4] if reason=="missing-local" else configs)]
                with mock.patch.object(m.importlib.util,"spec_from_file_location",
                                       return_value=spec), \
                     mock.patch.object(m.importlib.util,"module_from_spec",
                                       return_value=proof), \
                     mock.patch.object(m,"silent_run",
                                       return_value=json.dumps(inventory)), \
                     mock.patch.object(m,"local_image_exists",
                                       return_value=reason!="not-addressable"):
                    with self.assertRaises(m.Stop):
                        m.prove_and_resolve_saved_images(self.root)

    def test_preflight_enforces_rootless_acer_and_no_ssh(self):
        code=SOURCE.read_text()
        self.assertNotIn("ssh_command",code)
        self.assertNotIn("ssh -",code)
        self.assertNotIn("http://",code)
        self.assertNotIn("https://",code)
        self.assertIn('socket.gethostname() == "firelion-Aspire-A315-51"',code)
        self.assertIn("REMOTE_CONTAINER_CONTEXT_REFUSED",code)
        self.assertIn('PODMAN, "rm", "-f", name',code)
        self.assertIn('R1_CUSTOMER_RELEASE=NO_GO',code)
        self.assertIn('prove_and_resolve_saved_images(root)',code)
        self.assertIn('R1_ORIGINAL_OCI_PIN_TO_LOCAL_CONFIG_IDS=PASS_5_OF_5',code)
        self.assertNotIn('"load"',code)
        self.assertNotIn('"pull"',code)

if __name__ == "__main__":
    unittest.main(verbosity=2)
