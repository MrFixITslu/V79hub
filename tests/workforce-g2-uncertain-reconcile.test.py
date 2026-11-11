import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).parents[1] / "scripts/workforce-g2-uncertain-reconcile.py"
spec = importlib.util.spec_from_file_location("reconcile", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ReconcileTests(unittest.TestCase):
 def test_known_message_never_displays_unknown_log_content(self):
  self.assertIsNone(mod.known_message("HTTP ERROR: sensitive header"))
  self.assertIsNone(mod.known_message("TASK_WORKER=TOKEN_VALUE"))
  self.assertEqual(mod.known_message("TASK_WORKER=BLOCKED_PENDING_OPERATOR_RECONCILIATION"),"BLOCKED")
  self.assertEqual(mod.known_message("TASK_WORKER=UNCERTAIN_RECONCILIATION_REQUIRED"),"UNCERTAIN")

 def test_private_file_refuses_symlink_public_or_large(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);target=root/"marker";target.write_text('{"state":"uncertain"}')
   target.chmod(0o600)
   self.assertEqual(mod.private_file(target),b'{"state":"uncertain"}')
   link=root/"link";link.symlink_to(target)
   self.assertIsNone(mod.private_file(link))
   target.chmod(0o644);self.assertIsNone(mod.private_file(target))
   target.chmod(0o600);target.write_bytes(b"X"*4097)
   self.assertIsNone(mod.private_file(target))

 def test_marker_schema_rejected_if_not_exact(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);root.chmod(0o700)
   p=root/"uncertain.json"
   p.write_text(json.dumps({"state":"uncertain","action":"anything_else"}));p.chmod(0o600)
   with patch.object(mod,"ROOT",root):
    self.assertIsNone(mod.marker_information())
   p.write_text(json.dumps({"state":"uncertain","action":"inspect_signed_queue_before_reset"}))
   self.assertEqual(os.stat(p).st_mode & 0o077,0)
   with patch.object(mod,"ROOT",root):
    self.assertIsNotNone(mod.marker_information())

 def test_wrong_host_stops_before_any_file_reads(self):
  with patch.object(mod.socket,"gethostname",return_value="other-server"), \
       patch.object(mod,"marker_information") as read:
   with self.assertRaises(SystemExit):
    mod.main()
   read.assert_not_called()

 def test_journal_synthetic_secret_never_emitted(self):
  lines=[
   {"__REALTIME_TIMESTAMP":"1793149200000000",
    "MESSAGE":"TASK_WORKER=UNCERTAIN_RECONCILIATION_REQUIRED"},
   {"__REALTIME_TIMESTAMP":"1793149260000000","MESSAGE":"PRIVATE_KEY=abc"},
  ]
  with patch.object(mod,"run",return_value="\n".join(map(json.dumps,lines))):
   from contextlib import redirect_stdout
   import io
   out=io.StringIO()
   with redirect_stdout(out):mod.journal(dt.datetime.fromtimestamp(1793149200, dt.timezone.utc))
   self.assertNotIn("abc",out.getvalue())
   self.assertIn("UNCERTAIN",out.getvalue())

if __name__=="__main__":
 unittest.main()
