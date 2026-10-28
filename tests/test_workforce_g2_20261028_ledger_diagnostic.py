import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

FILE = Path(__file__).resolve().parents[1] / "scripts/workforce-g2-20261028-ledger-diagnostic.py"
spec = importlib.util.spec_from_file_location("diagnostic", FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DiagnosticTests(unittest.TestCase):
    def test_no_task_mutation_or_secret_prints(self):
        self.assertIn("store.read()", m.READER)
        for disallowed in ("store.transact(", "fetch(", "process.stdout.write(v)",
                           "console.log(v)", "docker\", \"compose", "method: 'POST'",
                           "subprocess.run(['systemctl'"):
            self.assertNotIn(disallowed, FILE.read_text())

    def test_only_boolean_and_bounded_count_contract(self):
        self.assertIn("all(isinstance(x, bool) for x in raw[\"checks\"].values())", FILE.read_text())
        self.assertIn("0 <= x <= 10000", FILE.read_text())
        self.assertIn("set(raw[\"checks\"])", FILE.read_text())
        self.assertIn("allCreatedEvents", m.READER)

    def test_exact_current_accepted_hub_and_marker(self):
        self.assertIn("29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec", m.IMAGE)
        self.assertEqual(m.MARKER, 1793201532.142639)
        self.assertEqual(m.WORKER_SHA, "5f629915d7715620fdd17ac0fed80cf595e65dab0035d0739a53c9bc5984fb3d")

    def test_docker_inspect_projects_only_image_running_health(self):
        source = FILE.read_text()
        self.assertIn('"docker", "inspect", "--format", fmt, "v79-hub"', source)
        self.assertNotIn('run(["docker", "inspect", "v79-hub"])', source)
        self.assertIn('{{json .Image}}|{{json .State.Running}}|{{json .State.Health.Status}}', source)
        self.assertIn('require(image == IMAGE and running is True and health == "healthy"', source)

    def test_projected_docker_output_stays_bounded(self):
        source = FILE.read_text()
        self.assertIn('len(p.stdout) < 12000', source)
        self.assertIn('"HUB_IDENTITY_PROJECTION_INVALID"', source)

    def test_cannot_progress_when_marker_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(m, "ROOT", Path(temp)), patch.object(m.socket, "gethostname", return_value="v79sl"):
                with patch.object(m, "run") as run:
                    with self.assertRaises(Exception):
                        m.main()
                    run.assert_not_called()

    def test_no_untrusted_ids_or_detail_leave_js(self):
        output = m.READER.split("console.log(JSON.stringify(", 1)[1]
        self.assertNotIn("jobs:", output)
        self.assertNotIn("tasks:", output)
        self.assertNotIn("events:", output)
        self.assertNotIn("detail:", output)
        self.assertNotIn("title:", output)
        self.assertIn("checks,counters", output)


    def run_synthetic_cohort(self, bad=None):
        import subprocess
        import copy
        # Fully synthetic ledger; no network, production credentials or real jobs.
        jobs, tasks, events = [], [], []
        base = "2026-10-28T09:00:00Z"
        approved = "2026-10-28T09:05:00Z"
        done = "2026-10-28T09:06:00Z"
        expires = "2026-10-28T10:00:00Z"
        for i in range(5):
            jid = "synthetic-" + str(i)
            system = "hub" if i < 4 else "tiquet"
            actor = "coo-worker" if i < 4 else "owner-synthetic"
            digest = ("0" * 63) + str(i)
            jobs.append({"id": jid, "system": system,
                         "organizationId": "synthetic-org", "operation": "create_work_item",
                         "status": "succeeded", "digest": digest,
                         "createdAt": base, "createdBy": "owner-synthetic",
                         "approval": {"by": "owner-synthetic", "digest": digest,
                                      "at": approved, "expiresAt": expires},
                         "result": {"taskId": "synthetic-task-" + str(i), "at": done}})
            tasks.append({"id": "synthetic-task-" + str(i), "jobId": jid,
                          "organizationId": "synthetic-org", "system": system,
                          "createdAt": done})
            events.append({"type":"approved", "actor":"owner-synthetic", "jobId":jid,
                           "digest":digest, "at":approved})
            events.append({"type":"work_item_created", "actor":actor, "jobId":jid,
                           "digest":digest, "at":done})
        jobs.append({"id":"synthetic-rejected","system":"hub",
                     "operation":"create_work_item","status":"rejected",
                     "createdAt":base})
        if bad == "wrong_actor":
            events[-1]["actor"] = "different-owner"
        if bad == "wrong_job_link":
            tasks[-1]["jobId"] = "synthetic-0"
        state = {"paused":False,"jobs":jobs,"tasks":tasks,"events":events}
        code = m.READER.replace(
            "import {createWorkActionStore} from './server/workforce-action-store.mjs';",
            "const createWorkActionStore=()=>({read:async()=>("
            + json.dumps(state) + "),close:async()=>{}});"
        )
        result = subprocess.run(["node", "--input-type=module", "-e", code],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_synthetic_four_worker_one_owner_cohort(self):
        data = self.run_synthetic_cohort()
        self.assertTrue(data["cohort"]["allFiveEffectsBelongToFiveSuccesses"])
        self.assertTrue(data["cohort"]["otherSystemApprovalActorMatches"])
        self.assertEqual(data["cohortCounts"]["hubSuccessfulJobs"], 4)
        self.assertEqual(data["cohortCounts"]["otherSystemSuccessfulJobs"], 1)

    def test_synthetic_wrong_owner_actor_fails_closed(self):
        data = self.run_synthetic_cohort("wrong_actor")
        self.assertFalse(data["cohort"]["otherSystemApprovalActorMatches"])
        self.assertFalse(data["cohort"]["allFiveEffectsBelongToFiveSuccesses"])

    def test_synthetic_wrong_task_link_fails_closed(self):
        data = self.run_synthetic_cohort("wrong_job_link")
        self.assertFalse(data["cohort"]["otherSystemTaskEventSameJob"])
        self.assertFalse(data["cohort"]["allFiveEffectsBelongToFiveSuccesses"])


if __name__ == "__main__":
    unittest.main()
