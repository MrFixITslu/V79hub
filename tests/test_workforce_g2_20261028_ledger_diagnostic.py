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


if __name__ == "__main__":
    unittest.main()
