#!/usr/bin/env python3
"""Focused, isolated tests: current G2 incident cannot be erased or replayed."""
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/workforce-g2-20261028-marker-only.py"
spec = importlib.util.spec_from_file_location("g2_marker_only", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SOURCE = SRC.read_text()


class MarkerOnlyTests(unittest.TestCase):
    def test_current_accepted_runtime_and_worker_exact(self):
        self.assertEqual(mod.HUB_IMAGE,
                         "sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec")
        self.assertEqual(mod.WORKER_SHA256,
                         "5f629915d7715620fdd17ac0fed80cf595e65dab0035d0739a53c9bc5984fb3d")
        self.assertEqual(mod.MARKER_UTC.isoformat(),
                         "2026-10-28T15:32:12.142639+00:00")
        self.assertNotIn("2026-10-25T15:51:31.400148", SOURCE)

    def test_not_a_task_or_hub_deployment_tool(self):
        self.assertNotIn("engine.deploy(", SOURCE)
        self.assertNotIn("docker\", \"start", SOURCE)
        self.assertNotIn("docker\", \"compose", SOURCE)
        self.assertNotIn("method='POST'", SOURCE)
        self.assertNotIn("method=\"POST\"", SOURCE)
        self.assertNotIn("worker.py.candidate\"", SOURCE.split("def archive():")[-1])
        self.assertIn("os.rename(MARKER, ARCHIVE)", SOURCE)
        self.assertNotIn("MARKER.unlink()", SOURCE)
        self.assertNotIn("os.remove(MARKER)", SOURCE)

    def test_review_invokes_no_mutation_path(self):
        with patch.object(mod, "check_files") as files, \
             patch.object(mod, "check_runtime") as runtime, \
             patch.object(mod, "archive") as archive, \
             patch.object(mod.sys, "argv", ["reader", "--review"]):
            output = io.StringIO()
            with redirect_stdout(output):
                mod.main()
            files.assert_called_once()
            runtime.assert_called_once()
            archive.assert_not_called()
            self.assertIn("PASS_G2_20261028_MARKER_REVIEW_ONLY", output.getvalue())

    def test_archive_requires_explicit_switch(self):
        with patch.object(mod, "check_files"), \
             patch.object(mod, "check_runtime"), \
             patch.object(mod, "archive") as archive, \
             patch.object(mod.sys, "argv", ["reader", "--archive"]):
            mod.main()
            archive.assert_called_once()

    def test_private_file_rejects_symlink_and_loose_modes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a"
            p.write_text("ok")
            p.chmod(0o600)
            self.assertEqual(mod.safe_file(p)[0], b"ok")
            alias = Path(d) / "b"
            alias.symlink_to(p)
            with self.assertRaisesRegex(RuntimeError, "PRIVATE_FILE_CHANGED"):
                mod.safe_file(alias)
            p.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "PRIVATE_FILE_CHANGED"):
                mod.safe_file(p)

    def test_signed_ledger_is_read_only_and_strict(self):
        self.assertIn("store.read()", mod.READER)
        self.assertNotIn("store.transact(", mod.READER)
        self.assertIn("jobs.length===6&&good.length===5&&bad.length===1", mod.READER)
        self.assertIn("tasks.length===5&&created.length===5", mod.READER)
        self.assertIn("seen.every(x=>x.matched)", mod.READER)
        self.assertIn("created.every(e=>good.some(j=>j.id===e.jobId)&&before(e.at))", mod.READER)
        self.assertIn("groups.hubWorker===3&&groups.hubOwner===1", mod.READER)
        self.assertIn("groups.otherWorker===1&&groups.otherOwner===0&&groups.invalid===0", mod.READER)
        self.assertIn("inFlight.length===0", mod.READER)
        self.assertIn('"postMarkerTaskCount": 0', SOURCE)

    def test_stale_marker_and_pre_marker_receipt_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            root=home / "private"
            root.mkdir(mode=0o700)
            marker=root / "uncertain.json"
            marker.write_text(json.dumps(mod.MARKER_PAYLOAD))
            marker.chmod(0o600)
            os.utime(marker, (mod.MARKER_UTC.timestamp()+2,
                              mod.MARKER_UTC.timestamp()+2))
            with patch.object(mod,"ROOT",root), patch.object(mod,"MARKER",marker), \
                 patch.object(mod,"ARCHIVE",root/"archived.json"), \
                 patch.object(mod.socket,"gethostname",return_value="v79sl"):
                with self.assertRaisesRegex(RuntimeError,"EXACT_20261028_MARKER_CHANGED"):
                    mod.check_files()

    def test_current_hub_image_gate_and_timer_no_mutations(self):
        def fake(args,timeout=20):
            if args[:2]==["docker","inspect"]:
                return json.dumps([{"Image":"sha256:wrong",
                                    "State":{"Running":True,"Health":{"Status":"healthy"}}}])
            raise AssertionError("No extra commands")
        with patch.object(mod,"unit",side_effect=lambda x:{
            "ActiveState":"active","UnitFileState":"enabled"
        } if x==mod.TIMER else {"ActiveState":"inactive"}), \
             patch.object(mod,"cmd",side_effect=fake):
            with self.assertRaisesRegex(RuntimeError,"ACCEPTED_HUB_IMAGE_OR_HEALTH_CHANGED"):
                mod.check_runtime()


    def synthetic_ledger(self, wrong=None):
        import subprocess
        jobs, tasks, events = [], [], []
        created = "2026-10-28T09:00:00Z"
        approved = "2026-10-28T09:01:00Z"
        done = "2026-10-28T09:02:00Z"
        expires = "2026-10-28T10:00:00Z"
        for i in range(5):
            jid = "test-job-" + str(i)
            digest = "0" * 63 + str(i)
            sysname = "tiquet" if i == 4 else "hub"
            actor = "owner-test" if i == 3 else "coo-worker"
            jobs.append({"id":jid,"operation":"create_work_item","status":"succeeded",
                         "system":sysname,"organizationId":"test-org",
                         "digest":digest,"createdBy":"owner-test","createdAt":created,
                         "approval":{"by":"owner-test","digest":digest,"at":approved,
                                     "expiresAt":expires},
                         "result":{"taskId":"test-task-"+str(i),"at":done}})
            tasks.append({"id":"test-task-"+str(i),"jobId":jid,"organizationId":"test-org",
                          "system":sysname,"createdAt":done})
            events.extend([
               {"id":"proposed-"+str(i),"type":"proposed","jobId":jid,
                "actor":"owner-test","digest":digest,"at":created},
               {"id":"approved-"+str(i),"type":"approved","jobId":jid,
                "actor":"owner-test","digest":digest,"at":approved},
               {"id":"created-"+str(i),"type":"work_item_created","jobId":jid,
                "actor":actor,"digest":digest,"at":done}
            ])
        jobs.append({"id":"test-job-rejected","operation":"create_work_item",
                     "status":"rejected","createdAt":created})
        if wrong=="unexpected_actor":
            events[-1]["actor"]="not-approved-owner"
        if wrong=="cross_link":
            tasks[-1]["jobId"]="test-job-0"
        if wrong=="post_marker":
            events[-1]["at"]="2026-10-28T16:00:00Z"
        if wrong=="wrong_counts":
            jobs.append({"id":"unexpected","operation":"create_work_item",
                         "status":"approved","createdAt":created})
        state={"jobs":jobs,"tasks":tasks,"events":events,"paused":False}
        code=mod.READER.replace(
           "import {createWorkActionStore} from './server/workforce-action-store.mjs';",
           "const createWorkActionStore=()=>({read:async()=>("
           + json.dumps(state) + "),close:async()=>{}});"
        )
        result=subprocess.run(
          ["node","--input-type=module","-e",code,mod.STAMP],
          capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_exact_crossed_provenance_valid(self):
        v=self.synthetic_ledger()
        self.assertTrue(v["safe"])
        self.assertTrue(v["linked"])
        self.assertEqual(v["groups"],
                         {"hubWorker":3,"hubOwner":1,"otherWorker":1,
                          "otherOwner":0,"invalid":0})

    def test_wrong_execution_actor_is_rejected(self):
        self.assertFalse(self.synthetic_ledger("unexpected_actor")["safe"])

    def test_swapped_task_link_is_rejected(self):
        self.assertFalse(self.synthetic_ledger("cross_link")["safe"])

    def test_post_marker_event_is_rejected(self):
        self.assertFalse(self.synthetic_ledger("post_marker")["safe"])

    def test_unresolved_extra_job_is_rejected(self):
        self.assertFalse(self.synthetic_ledger("wrong_counts")["safe"])


if __name__ == "__main__":
    unittest.main()
