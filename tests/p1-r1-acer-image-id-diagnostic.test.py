"""R1 safe offline unit tests for read-only Podman/Docker ID diagnostics."""
import importlib.util
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
            [{"Config":f"blobs/sha256/{pins[0]}","RepoTags":None}]),{pins[0]})

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

    def test_no_import_deletion_mutation_or_network_in_diagnostic(self):
        code=SRC.read_text()
        self.assertIn('PODMAN = ("podman", "--remote=false")',code)
        self.assertIn("RUN_ONLY_ON_ACER",code)
        self.assertIn("NO_ROOT_PODMAN",code)
        self.assertIn("REMOTE_CONTAINER_CONTEXT_REFUSED",code)
        self.assertIn('tarfile.open(fileobj=decrypt.stdout, mode="r|")',code)
        self.assertIn("R1_DATABASE_RESTORE=NOT_RUN",code)
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
