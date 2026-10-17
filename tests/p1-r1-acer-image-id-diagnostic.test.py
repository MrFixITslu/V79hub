"""R1 safe offline unit tests for read-only Podman/Docker ID diagnostics."""
import importlib.util
import hashlib
import tempfile
import tarfile
import io
import os
import json
from pathlib import Path
import unittest
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "scripts/p1-r1-acer-image-id-diagnostic.py"
spec = importlib.util.spec_from_file_location("r1_acer_image_diag_under_test", SRC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class DiagnosticTests(unittest.TestCase):
    def test_expected_image_contract(self):
        self.assertEqual(len(m.IMAGES),5)
        self.assertEqual(len(set(m.IMAGES.values())),5)
        for digest in m.IMAGES.values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(m.FILE,"exact-images-and-rollback.tar.gpg")

    def test_docker_manifest_config_names_only_not_tags(self):
        pins=list(m.IMAGES.values())
        manifest=[
            {"Config":f"{d}.json","RepoTags":["mycompany/private:secret"],
             "Layers":["layer-private-name/layer.tar"]} for d in pins]
        self.assertEqual(m.docker_manifest_config_ids(manifest),set(pins))
        self.assertEqual(m.docker_manifest_config_ids(
            [{"Config":f"blobs/sha256/{pin}","RepoTags":None}
             for pin in pins]),set(pins))
        self.assertEqual(len(m.docker_manifest_config_paths(manifest)), 5)

    def test_malformed_docker_archive_manifest_is_rejected(self):
        cases=[None, {}, [], [{}], [{"Config":"../../etc/passwd"}],
               [{"Config":"not-a-digest.json"}],
               [{"Config":3}], ["not-object"], [{"Config":"x"*65+".json"}]]
        for bad in cases:
            with self.subTest(bad=bad),self.assertRaises(m.Stop):
                m.docker_manifest_config_ids(bad)

    def test_podman_image_inventory_normalizes_only_exact_ids(self):
        pins=list(m.IMAGES.values())
        values=[
            {"Id":"sha256:"+pins[0],"Repository":"SECRET_SUPPRESSED"},
            {"ID":pins[1],"Repository":"PRIVATE"},
            {"id":"sha256:"+pins[2]},
            {"Id":"4f7a"},{"Id":"sha256:"+"g"*64},
        ]
        self.assertEqual(m.podman_image_ids(values),set(pins[:3]))
        for invalid in ({},None):
            with self.assertRaises(m.Stop):
                m.podman_image_ids(invalid)

    def test_identity_lookup_is_separate_from_local_config_presence(self):
        target=next(iter(m.IMAGES.values()))
        class Result: returncode=1
        with mock.patch.object(m.subprocess,"run",return_value=Result()) as run:
            self.assertFalse(m.pin_lookup(target))
            argv=run.call_args.args[0]
            self.assertEqual(argv,list(m.PODMAN)+["image","exists","sha256:"+target])
            self.assertNotIn("pull",argv)

    def test_saved_runtime_inspect_id_only_requires_four_unique_records(self):
        ids=list(m.IMAGES.values())[:4]
        full=[{"Id":"sha256:" + hashlib.sha256(pin.encode()).hexdigest(),
               "Image":"sha256:"+pin,"HostConfig":{},"State":{},
               "Config":{"Env":["PRIVATE_SUPPRESSED"]}}
              for pin in ids]
        image_inspects=[{"Id":"sha256:"+pin,"RootFS":{},
                         "Architecture":"amd64"} for pin in ids]
        self.assertEqual(m.saved_runtime_image_ids(full),set(ids))
        self.assertEqual(m.saved_runtime_image_ids(image_inspects),set(ids))
        for bad in ([],full[:3],full+[full[0]],
                    [{"Image":"x","HostConfig":{},"State":{}}]*4,
                    [full[0]]*4):
            with self.assertRaises(m.Stop):
                m.saved_runtime_image_ids(bad)

    def test_ciphertext_provenance_against_manifest_without_decrypting(self):
        with tempfile.TemporaryDirectory(prefix="r1-image-provenance-") as temp:
            root=Path(temp)
            p=root/m.FILE
            p.write_bytes(b"CI-SYNTHETIC-ENCRYPTED-IMAGE-BYTES")
            os.chmod(p,0o600)
            row={"name":m.FILE,"bytes":p.stat().st_size,
                 "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
            (root/"ciphertext-manifest.json").write_text(json.dumps({"files":[row]}))
            self.assertEqual(m.verify_ciphertext(root,m.FILE),p)
            p.write_bytes(b"CORRUPTED")
            with self.assertRaises(m.Stop):
                m.verify_ciphertext(root,m.FILE)

    def test_three_way_comparisons_detect_consistent_but_wrong_images(self):
        known=set(m.IMAGES.values())
        runtime=set(list(m.IMAGES.values())[:4])
        alternative={"a"*64,"b"*64,"c"*64,"d"*64,"e"*64}
        self.assertEqual(len(alternative&known),0)
        self.assertEqual(len(alternative&alternative),5)
        self.assertEqual(len(alternative&runtime),0)
        # Archive and Podman agree with each other, but no exact runtime pins.
        # Such evidence must not grant an image provenance PASS.

    def test_archive_config_file_content_must_hash_to_real_manifest_id(self):
        expected=[]
        manifest=[]
        configs=[]
        for n in range(5):
            data=json.dumps({"synthetic":n,"labels":"TEST_ONLY"},
                            sort_keys=True).encode()
            digest=hashlib.sha256(data).hexdigest()
            expected.append(digest)
            manifest.append({"Config":digest+".json","RepoTags":None,"Layers":[]})
            configs.append((digest+".json",data))
        original_popen=m.subprocess.Popen

        def make_tar(path, changed=False, oci=False, manifest_last=False,
                     omit_index=None):
            contents = [(("blobs/sha256/" + name[:-5]) if oci else name, data)
                        for name, data in configs]
            descriptions = [{"Config":name,"RepoTags":None,"Layers":[]}
                            for name,_ in contents]
            with tarfile.open(path,mode="w") as tar:
                def add_manifest():
                    obj=json.dumps(descriptions).encode()
                    entry=tarfile.TarInfo("manifest.json")
                    entry.size=len(obj)
                    tar.addfile(entry,io.BytesIO(obj))
                if not manifest_last:
                    add_manifest()
                for i,(name,data) in enumerate(contents):
                    if i==omit_index:
                        continue
                    if changed and i==2:
                        data=b"CI-TAMPERED-CONFIG"
                    entry=tarfile.TarInfo(name)
                    entry.size=len(data)
                    tar.addfile(entry,io.BytesIO(data))
                if manifest_last:
                    add_manifest()

        def cat_instead_of_gpg(args,**kwargs):
            self.assertEqual(args[0],"gpg")
            return original_popen(["cat",args[-1]],**kwargs)

        with tempfile.TemporaryDirectory(prefix="r1-docker-config-ci-") as tmp:
            plain=Path(tmp)/"synthetic-image.tar"
            with mock.patch.object(m.subprocess,"Popen",side_effect=cat_instead_of_gpg):
                make_tar(plain)
                ids, stats, intact = m.read_archive_configs(plain)
                self.assertEqual(ids, set(expected))
                self.assertTrue(intact)
                self.assertEqual(stats, {
                    "members":5,"referenced":5,"missing":0,
                    "extra":0,"valid":5,"invalid":0,
                    "docker_json":5,"oci_blobs":0,"candidate_blobs":5,
                })
                make_tar(plain,oci=True,manifest_last=True)
                ids, stats, intact = m.read_archive_configs(plain)
                self.assertEqual(ids,set(expected))
                self.assertTrue(intact)
                self.assertEqual(stats["oci_blobs"],5)
                self.assertEqual(stats["docker_json"],0)
                self.assertEqual(stats["candidate_blobs"],5)
                self.assertEqual(stats["valid"],5)
                # OCI archives may also contain layer blobs with identical
                # path shape. These are NOT Config entries: skip large layers
                # and ignore small unreferenced ones.
                with tarfile.open(plain,mode="w") as tar:
                    obj=json.dumps([{"Config":"blobs/sha256/"+name[:-5],
                                     "RepoTags":None,"Layers":[]}
                                    for name,_ in configs]).encode()
                    info=tarfile.TarInfo("manifest.json")
                    info.size=len(obj)
                    tar.addfile(info,io.BytesIO(obj))
                    for name, data in configs:
                        info=tarfile.TarInfo("blobs/sha256/"+name[:-5])
                        info.size=len(data)
                        tar.addfile(info,io.BytesIO(data))
                    small_blob=b"CI-SYNTHETIC-UNREFERENCED-LAYER"
                    info=tarfile.TarInfo("blobs/sha256/"+
                                         hashlib.sha256(small_blob).hexdigest())
                    info.size=len(small_blob)
                    tar.addfile(info,io.BytesIO(small_blob))
                    large_blob=b"z"*(8*1024*1024+1)
                    info=tarfile.TarInfo("blobs/sha256/"+
                                         hashlib.sha256(large_blob).hexdigest())
                    info.size=len(large_blob)
                    tar.addfile(info,io.BytesIO(large_blob))
                ids, stats, intact=m.read_archive_configs(plain)
                self.assertTrue(intact)
                self.assertEqual(stats["members"],5)
                self.assertEqual(stats["valid"],5)
                self.assertEqual(stats["extra"],1)
                self.assertEqual(stats["candidate_blobs"],6)
                make_tar(plain,oci=True,omit_index=0)
                _, stats, intact = m.read_archive_configs(plain)
                self.assertFalse(intact)
                self.assertEqual(stats["missing"],1)
                self.assertEqual(stats["valid"],4)
                make_tar(plain,changed=True)
                ids, stats, intact = m.read_archive_configs(plain)
                self.assertEqual(ids, set(expected))
                self.assertFalse(intact)
                self.assertEqual(stats["members"],5)
                self.assertEqual(stats["referenced"],5)
                self.assertEqual(stats["valid"],4)
                self.assertEqual(stats["invalid"],1)

    def test_no_import_deletion_mutation_or_network_in_diagnostic(self):
        code=SRC.read_text()
        self.assertIn('PODMAN = ("podman", "--remote=false")',code)
        self.assertIn("RUN_ONLY_ON_ACER",code)
        self.assertIn("NO_ROOT_PODMAN",code)
        self.assertIn("REMOTE_CONTAINER_CONTEXT_REFUSED",code)
        self.assertIn('tarfile.open(fileobj=decrypt.stdout, mode="r|")',code)
        self.assertIn("R1_DATABASE_RESTORE=NOT_RUN",code)
        self.assertIn("R1_ARCHIVE_VS_LOCAL_SHARED_CONFIG_IDS=",code)
        self.assertIn("R1_SAVED_RUNTIME_INSPECT_IDS_MATCH=",code)
        self.assertIn("R1_SAVED_INSPECT_IMAGE_SHAPE_COUNT=",code)
        self.assertIn("R1_SAVED_INSPECT_CONTAINER_SHAPE_COUNT=",code)
        self.assertIn("R1_ARCHIVE_CONFIG_SHA256_VALID=",code)
        self.assertIn("R1_ARCHIVE_CONFIG_SHA256_INVALID=",code)
        self.assertIn("R1_ARCHIVE_OCI_BLOB_MEMBERS=",code)
        self.assertIn("R1_ARCHIVE_SMALL_BLOB_CANDIDATES=",code)
        self.assertIn('item.get("Image") if container else item.get("Id")',code)
        self.assertIn("R1_ARCHIVE_CONFIG_BYTE_INTEGRITY=",code)
        self.assertIn('require(archive_intact, "DOCKER_ARCHIVE_CONFIG_CONTENT_HASH_MISMATCH")',code)
        self.assertIn("CIPHERTEXT_COMPONENT_HASH_MISMATCH",code)
        self.assertIn("ORIGINAL_BACKUP_SET_PROVENANCE_NOT_MATCHED",code)
        self.assertIn('data.get("rollbackHub")',code)
        self.assertIn('len(data["files"]) == 14',code)
        self.assertNotIn("podman load",code)
        self.assertNotIn('"load"',code)
        self.assertNotIn('"pull"',code)
        self.assertNotIn('"run"',code)
        self.assertNotIn('"tag"',code)
        self.assertNotIn('"rm"',code)
        self.assertNotIn('"ssh"',code)
        self.assertNotIn('"https://"',code)

if __name__ == "__main__":
    unittest.main(verbosity=2)
