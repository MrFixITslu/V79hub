import importlib.util
import io
from pathlib import Path
from unittest.mock import patch
import unittest

path = Path(__file__).parents[1]/"scripts/workforce-g2-guarded-update.py"
spec = importlib.util.spec_from_file_location("guarded", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class GuardTests(unittest.TestCase):
 def test_known_git_source_hash_guards(self):
  a=b"synthetic worker"
  self.assertEqual(len(mod.blob(a)),40)
  self.assertNotEqual(mod.blob(a),mod.OLD_BLOB)
  self.assertNotEqual(mod.blob(a),mod.NEW_BLOB)
 def test_actual_hash_constants_distinct(self):
  self.assertNotEqual(mod.OLD_BLOB,mod.NEW_BLOB)
  self.assertTrue(mod.HUB_IMAGE.startswith("sha256:"))
  self.assertIn("e52cb3bcc2f0c25bc79f205af4c6c7b881c2ff22",mod.CANDIDATE_URL)
 def test_wrong_host_refused_before_any_files_or_runtime(self):
  with patch.object(mod.socket,"gethostname",return_value="not-v79sl"), \
       patch.object(mod,"fixed_files") as files, \
       patch.object(mod.sys,"argv",["auditor","--apply"]):
   with self.assertRaises(RuntimeError):
    mod.main()
   files.assert_not_called()
 def test_redirect_does_not_follow(self):
  with self.assertRaises(RuntimeError):
   mod.NoRedirect().redirect_request(None,None,None,None,None,None)
 def test_unknown_source_raises_before_stop(self):
  with patch.object(mod,"unit_state",side_effect=[{"ActiveState":"active","UnitFileState":"enabled"},{"ActiveState":"inactive"}]), \
       patch.object(mod,"command") as run:
   with self.assertRaises(RuntimeError):
    mod.apply(Path("/tmp/a"),b"unknown",b"candidate")
   run.assert_not_called()
 def test_exact_image_verification_blocks_drift(self):
  fake={"Image":"sha256:"+"1"*64,"State":{"Health":{"Status":"healthy"}},
        "Config":{"Labels":{"org.opencontainers.image.revision":mod.HUB_REVISION}}}
  with patch.object(mod,"command",return_value=__import__("json").dumps([fake])):
   with self.assertRaisesRegex(RuntimeError,"differs"):
    mod.pinned_hub()

if __name__=="__main__":unittest.main()
