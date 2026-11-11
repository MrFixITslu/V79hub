"""Offline tests for exact, read-only Hub-only visual release review."""
import copy
import importlib.util
from pathlib import Path
import unittest

PATH=Path(__file__).parents[1]/"scripts/vision79-hub-only-model-review.py"
spec=importlib.util.spec_from_file_location("hub_visual_release_review",PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class VisualReviewTests(unittest.TestCase):
    def test_pins_five_live_images_and_detailed_mounts(self):
        self.assertEqual(set(module.LIVE),{
            "v79-hub","v79-tiquet-manager","v79-hub-postgres","tiquet-postgres","v79-business-agent"
        })
        self.assertEqual(sum(map(len,module.MOUNTS.values())),10)
        self.assertEqual(module.LIVE["v79-hub"][1],
            "sha256:66caa099adf1321b72a90b22f8125981e5a6d99b5920cebae0454541cccd9fa7")
        self.assertEqual(module.LIVE["v79-tiquet-manager"][1],
            "sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0")
        self.assertEqual(module.CHECKPOINT,"release-20261026T102542Z-def4da1b")

    def test_candidate_only_changes_one_image_not_auth_or_database(self):
        original={"name":"v79-hub","services":{
          "v79-hub":{"image":"sha256:old","environment":{"AUTH_SECRET":"private"}},
          "database":{"image":"sha256:original-db","environment":{"PASSWORD":"keep"}}},
          "networks":{"net":{"external":True}}}
        frozen=copy.deepcopy(original)
        target=module.candidate_model(original,"v79-hub","sha256:replacement")
        self.assertEqual(original,frozen)
        self.assertEqual(target["services"]["database"],original["services"]["database"])
        self.assertEqual(target["services"]["v79-hub"]["environment"],
                         original["services"]["v79-hub"]["environment"])
        self.assertEqual(target["services"]["v79-hub"]["image"],"sha256:replacement")

    def test_wrong_service_is_refused(self):
        with self.assertRaises(module.Halt):
            module.candidate_model({"services":{"v79-hub":{}}},"tiquet","sha256:new")
        with self.assertRaises(module.Halt):
            module.candidate_model({"services":{}},"v79-hub","sha256:new")

    def test_no_implicit_production_mutation_commands(self):
        s=PATH.read_text()
        for item in ["docker\",\"start","docker\",\"stop","docker\",\"rm","docker\",\"volume\",\"rm",
                     "docker\",\"compose\",\"up","docker\",\"image\",\"load"]:
            self.assertNotIn(item,s)
        self.assertIn("COMPOSE_RENDER_SERVICE_SCOPE_CHANGED",s)
        self.assertIn("NEW_IMAGE_UNREVIEWED_PROCESS_ENV_DEFAULTS",s)
        self.assertIn("PRODUCTION_CHANGES=NONE",s)

if __name__=="__main__":unittest.main()
