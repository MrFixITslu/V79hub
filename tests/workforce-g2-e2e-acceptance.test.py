"""No live Hub connections. Founder owner-only read-only G2 acceptance auditor."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

script=Path(__file__).parents[1]/"scripts/workforce-g2-e2e-acceptance.py"
spec=importlib.util.spec_from_file_location("g2acceptance",script)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class G2E2EAcceptanceTests(unittest.TestCase):
 def test_git_blob_uses_real_nul_separator(self):
  data=b"sample\n"
  expected=hashlib.sha1(b"blob 7\0sample\n").hexdigest()
  self.assertEqual(mod.git_blob(data),expected)
  self.assertNotEqual(mod.git_blob(data),hashlib.sha1(b"blob 7\\0sample\n").hexdigest())

 def test_private_file_refuses_symlinks_and_world_readable_files(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/"worker.py"
   p.write_text("print('ok')\n");p.chmod(0o600)
   self.assertEqual(mod.private_bytes(p),b"print('ok')\n")
   link=Path(directory)/"worker-link.py"
   link.symlink_to(p)
   self.assertIsNone(mod.private_bytes(link))
   p.chmod(0o644)
   self.assertIsNone(mod.private_bytes(p))

 def test_incorrect_host_stops_before_runtime_inspection(self):
  with patch.object(mod.socket,"gethostname",return_value="wrong"), \
       patch.object(mod,"private_bytes") as read:
   with self.assertRaises(SystemExit):
    mod.check_host()
   read.assert_not_called()

 def _audit(self, summary):
  out=io.StringIO()
  with patch.object(mod,"check_host"), \
       patch.object(mod,"run",return_value=json.dumps(summary)), \
       contextlib.redirect_stdout(out):
   mod.main()
  return out.getvalue()

 def test_readonly_pending_ledger_redacted_result(self):
  item={
   "signature":"validated_by_HMAC_store",
   "status":"AWAITING_FOUNDER_MFA_APPROVAL",
   "jobCount":1,"jobStatus":"pending","scopeExact":True,
   "approvedEvents":0,"workerEvents":0,"linkedTasks":0,
   "paused":False,"sideEffects":"NONE",
   "claim":"COO_TASK_CREATION_ONLY_NOT_UNDERLYING_TASK_COMPLETION"
  }
  output=self._audit(item)
  self.assertIn("G2_STATUS=AWAITING_FOUNDER_MFA_APPROVAL",output)
  self.assertIn("PRODUCTION_CHANGES=NONE",output)
  self.assertNotIn(mod.DETAIL,output)

 def test_pass_requires_expected_signed_event_summary_only(self):
  item={
   "signature":"validated_by_HMAC_store",
   "status":"PASS_CREATED_EXACTLY_ONCE_BY_COO_WORKER",
   "jobCount":1,"jobStatus":"succeeded","scopeExact":True,
   "approvedEvents":1,"workerEvents":1,"linkedTasks":1,
   "paused":False,"sideEffects":"NONE",
   "claim":"COO_TASK_CREATION_ONLY_NOT_UNDERLYING_TASK_COMPLETION"
  }
  out=self._audit(item)
  self.assertIn("PASS_CREATED_EXACTLY_ONCE_BY_COO_WORKER",out)
  self.assertIn("G2_LINKEDTASKS=1",out)

 def test_malformed_output_rejected_without_dumping_credential(self):
  item={"signature":"validated_by_HMAC_store",
        "status":"PASS_CREATED_EXACTLY_ONCE_BY_COO_WORKER",
        "token":"PRIVATE_CREDENTIAL_DO_NOT_SHOW",
        "sideEffects":"NONE",
        "claim":"COO_TASK_CREATION_ONLY_NOT_UNDERLYING_TASK_COMPLETION"}
  out=io.StringIO()
  with patch.object(mod,"check_host"), \
       patch.object(mod,"run",return_value=json.dumps(item)), \
       contextlib.redirect_stdout(out):
   with self.assertRaises(SystemExit) as err:
    mod.main()
  self.assertNotIn("PRIVATE_CREDENTIAL",out.getvalue())
  self.assertIn("UNKNOWN_UNEXPECTED_AUDIT_SHAPE",str(err.exception))

 def test_only_reads_signed_store_without_task_action_or_write(self):
  src=mod.LEDGER_READER
  self.assertIn("store.read()",src)
  for forbidden in ("store.transact(","fetch(","POST","execute-work-item","workerToken"):
   self.assertNotIn(forbidden,src)

if __name__=="__main__":unittest.main()
