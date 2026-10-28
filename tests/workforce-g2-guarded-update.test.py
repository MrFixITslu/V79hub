import importlib.util
import json
import os
import tempfile
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
 def test_exact_marker_and_preincident_idle_receipt_required(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);root.chmod(0o700)
   marker=root/"uncertain.json"
   marker.write_text(json.dumps({"state":"uncertain","action":"inspect_signed_queue_before_reset"}))
   marker.chmod(0o600)
   os.utime(marker,(mod.MARKER_TIME.timestamp(),mod.MARKER_TIME.timestamp()))
   receipt=root/"status.json"
   receipt.write_text(json.dumps({"state":"idle","operation":"create_work_item"}))
   receipt.chmod(0o600)
   os.utime(receipt,(mod.MARKER_TIME.timestamp()-65,mod.MARKER_TIME.timestamp()-65))
   with patch.object(mod,"ROOT",root):
    m,a=mod.reviewed_marker()
    self.assertEqual(m,marker)
    self.assertFalse(a.exists())
    os.utime(marker,(mod.MARKER_TIME.timestamp()+5,mod.MARKER_TIME.timestamp()+5))
    with self.assertRaisesRegex(RuntimeError,"timestamp"):
     mod.reviewed_marker()
    os.utime(marker,(mod.MARKER_TIME.timestamp(),mod.MARKER_TIME.timestamp()))
    receipt.write_text(json.dumps({"state":"succeeded","operation":"create_work_item"}))
    with self.assertRaisesRegex(RuntimeError,"pre-marker idle"):
     mod.reviewed_marker()

 def test_current_signed_ledger_shape_is_strict_and_fail_closed(self):
  correct={"paused":False,"blocked":False,"matching":True,"created":4,"tasks":4,
   "verifiedBy":"current-hmac-store-no-historical-continuity-assertion"}
  with patch.object(mod,"command",return_value=json.dumps(correct)):
   self.assertEqual(mod.signed_reconcile()["matching"],True)
   for k,value in (("paused",True),("blocked",True),("matching",False),("tasks",5)):
    bad={**correct,k:value}
    with patch.object(mod,"command",return_value=json.dumps(bad)):
     with self.assertRaisesRegex(RuntimeError,"ledger changed"):
      mod.signed_reconcile()

 def test_original_marker_is_preserved_on_review_mode(self):
  with patch.object(mod.socket,"gethostname",return_value="v79sl"), \\
       patch.object(mod,"fixed_files",return_value=(Path("/tmp/notactuallyused"),b"original")), \\
       patch.object(mod,"pinned_hub"), \\
       patch.object(mod,"unit_state",side_effect=[{"ActiveState":"inactive"},{"ActiveState":"active"}]), \\
       patch.object(mod,"candidate",return_value=b"candidate"), \\
       patch.object(mod,"blob",side_effect=lambda data: mod.OLD_BLOB if data==b"original" else mod.NEW_BLOB), \\
       patch.object(mod,"reviewed_marker"), \\
       patch.object(mod,"signed_reconcile"), \\
       patch.object(mod,"apply") as apply, \\
       patch.object(mod.sys,"argv",["runner","--review-marker"]):
   mod.main()
   apply.assert_not_called()

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
