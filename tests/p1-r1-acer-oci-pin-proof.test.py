"""Synthetic OCI+Docker29 manifest vs config identity proof, no real data/network."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

SRC=Path(__file__).resolve().parents[1]/"scripts/p1-r1-acer-oci-pin-proof.py"
spec=importlib.util.spec_from_file_location("r1_oci_pin_proof",SRC)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def sha(payload):
    return hashlib.sha256(payload).hexdigest()

class OCIProofTests(unittest.TestCase):
    def mk_archive(self,target,break_config=None,break_manifest=None):
        config_digest=[]
        manifest_digest=[]
        blobs=[]
        for i in range(5):
            original=json.dumps({"syntheticConfig":i, "rootfs":{"diff_ids":[]}},
                                separators=(",",":"),sort_keys=True).encode()
            config_hash=sha(original)
            config_digest.append(config_hash)
            config_data=(b"CI-ALTERED-CFG" if break_config==i else original)
            blobs.append(("blobs/sha256/"+config_hash,config_data))
            manifest={
                "schemaVersion":2,
                "config":{"mediaType":"application/vnd.oci.image.config.v1+json",
                          "digest":"sha256:"+config_hash,"size":len(original)},
                "layers":[],
            }
            raw=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
            manifest_hash=sha(raw)
            manifest_digest.append(manifest_hash)
            payload=(b"CI-ALTERED-MANIFEST" if break_manifest==i else raw)
            blobs.append(("blobs/sha256/"+manifest_hash,payload))
        docker=[{"Config":"blobs/sha256/"+v,"RepoTags":None,"Layers":[]}
                for v in config_digest]
        index={"schemaVersion":2,"manifests":[
            {"mediaType":"application/vnd.oci.image.manifest.v1+json",
             "digest":"sha256:"+v,"size":1} for v in manifest_digest]}
        with tarfile.open(target,"w") as tar:
            # Place the Docker manifest at end; OCI blob traversal must not
            # depend on TAR member ordering.
            for name,data in blobs:
                info=tarfile.TarInfo(name)
                info.size=len(data)
                tar.addfile(info,io.BytesIO(data))
            for name,obj in (("index.json",index),("manifest.json",docker)):
                payload=json.dumps(obj).encode()
                info=tarfile.TarInfo(name)
                info.size=len(payload)
                tar.addfile(info,io.BytesIO(payload))
        return set(config_digest),set(manifest_digest)

    def execute(self, file, pins):
        actual_popen=subprocess.Popen
        def cat_gpg(args,**kw):
            self.assertEqual(args[0],"gpg")
            return actual_popen(["cat",args[-1]],**kw)
        log=io.StringIO()
        with mock.patch.object(m,"PINS",pins),mock.patch.object(
            m.subprocess,"Popen",side_effect=cat_gpg
        ),contextlib.redirect_stdout(log):
            try:
                m.stream_proof(file)
                return True,log.getvalue()
            except m.Stop:
                return False,log.getvalue()

    def test_docker29_manifest_pins_link_to_five_config_blobs(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"synthetic.tar"
            configs,pins=self.mk_archive(path)
            ok,log=self.execute(path,pins)
            self.assertTrue(ok,log)
            self.assertIn("R1_DOCKER_CONFIG_SHA_VALID=5/5",log)
            self.assertIn("R1_OCI_LINKED_IMAGE_MANIFESTS=5",log)
            self.assertIn("R1_PINNED_IDS_AS_MANIFEST_DIGESTS=5/5",log)
            self.assertIn("R1_PINNED_IDS_AS_INDEX_DIGESTS=0/5",log)
            self.assertIn("R1_PINNED_OCI_ID_TO_CONFIG_PROVENANCE=PASS_OFFLINE_ONLY",log)

    def test_old_config_ids_are_not_mistaken_for_manifest_based_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"synthetic.tar"
            configs,pins=self.mk_archive(path)
            ok,log=self.execute(path,configs)
            self.assertFalse(ok)
            self.assertIn("R1_PINNED_IDS_AS_MANIFEST_DIGESTS=0/5",log)
            self.assertNotIn("PASS_OFFLINE_ONLY",log)

    def test_corrupt_config_and_manifest_always_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"synthetic.tar"
            _,pins=self.mk_archive(path,break_config=1)
            ok,log=self.execute(path,pins)
            self.assertFalse(ok)
            self.assertIn("R1_DOCKER_CONFIG_SHA_VALID=4/5",log)
            _,pins=self.mk_archive(path,break_manifest=2)
            ok,log=self.execute(path,pins)
            self.assertFalse(ok)
            self.assertIn("R1_OCI_LINKED_IMAGE_MANIFESTS=4",log)

    def test_runtime_never_mutates_images_or_contacts_external_hosts(self):
        code=SRC.read_text()
        self.assertIn("RUN_ONLY_ON_ACER",code)
        self.assertIn("REMOTE_CONTAINER_CONTEXT_REJECTED",code)
        self.assertIn("OCI_PIN_TO_CONFIG_PROVENANCE_NOT_PROVEN",code)
        self.assertIn('tarfile.open(fileobj=p.stdout,mode="r|")',code)
        self.assertNotIn('"podman"',code)
        self.assertNotIn('"ssh"',code)
        for action in ('"pull"','"load"','"run"','"tag"','"rm"'):
            self.assertNotIn(action,code)

if __name__=="__main__":
    unittest.main(verbosity=2)
