import datetime as dt
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

script = Path(__file__).parents[1]/"scripts/workforce-live-acceptance-audit.py"
spec = importlib.util.spec_from_file_location("workforce_audit", script)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

NOW = dt.datetime(2026, 10, 28, 0, 45, tzinfo=dt.timezone.utc)
SLOT = "2026-10-27-evening"

def fixture():
    return {"schema":1, "slot": SLOT, "state":"recorded",
            "checkedAt":"2026-10-27T23:00:17Z",
            "report":{"evidenceCollectedAt":"2026-10-27T23:00:00Z",
                      "noActionsExecuted":True, "coverage":"AVAILABLE",
                      "verifiedFindings":[], "missingSources":[]}}

class AcceptanceAuditTests(unittest.TestCase):
    def test_realistic_report_shape_is_only_contract_checked_not_attested(self):
        self.assertEqual(audit.inspect_report(fixture(), SLOT, NOW), ("AVAILABLE","17"))

    def test_missing_and_stale_data_cannot_claim_healthy(self):
        for key,value in (("checkedAt","2026-10-28T05:00:00Z"),
                          ("slot","2026-10-26-evening"),
                          ("state","executed")):
            raw=fixture();raw[key]=value
            self.assertEqual(audit.inspect_report(raw,SLOT,NOW)[0],"INVALID")
        raw=fixture();raw["report"]["evidenceCollectedAt"]="2026-10-27T22:30:00Z"
        self.assertEqual(audit.inspect_report(raw,SLOT,NOW)[0],"INVALID")

    def test_unavailable_sources_cannot_claim_full_coverage(self):
        raw=fixture();raw["report"]["missingSources"]=["sentinel"]
        self.assertEqual(audit.inspect_report(raw,SLOT,NOW)[0],"INVALID")
        raw["report"]["coverage"]="INCOMPLETE"
        self.assertEqual(audit.inspect_report(raw,SLOT,NOW)[0],"INCOMPLETE")

    def test_unexecuted_promise_and_malformed_findings_rejected(self):
        raw=fixture();raw["report"]["noActionsExecuted"]=False
        self.assertEqual(audit.inspect_report(raw,SLOT,NOW)[0],"INVALID")
        raw=fixture();raw["report"]["verifiedFindings"]=[{"system":"hub","metric":"health","value":True,"severity":"watch"}]
        self.assertEqual(audit.inspect_report(raw,SLOT,NOW)[0],"INVALID")

    def test_reject_symlink_and_world_accessible_private_report(self):
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname);root.chmod(0o700)
            target=root/"report";target.write_text("synthetic");target.chmod(0o600)
            self.assertEqual(audit.safe_file_bytes(target),b"synthetic")
            link=root/"link";link.symlink_to(target)
            self.assertIsNone(audit.safe_file_bytes(link))
            target.chmod(0o644)
            self.assertIsNone(audit.safe_file_bytes(target))
            target.chmod(0o600);root.chmod(0o755)
            self.assertIsNone(audit.safe_file_bytes(target))

    def test_refuse_to_run_on_wrong_host(self):
        with patch.object(audit.socket,"gethostname",return_value="test-box"):
            with self.assertRaises(SystemExit):
                audit.main()

if __name__=="__main__":
    unittest.main()
