#!/usr/bin/env python3
"""No-Docker scope/regression tests for guarded newsletter manifest preparation."""
import ast
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'prepare-newsletter-website-only.py'
spec = importlib.util.spec_from_file_location('newsletter_manifest_prepare', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SOURCE = SCRIPT.read_text()


class NewsletterPreparationSafety(unittest.TestCase):
    def test_pins(self):
        self.assertEqual(module.SOURCE, 'db84a4a07cf637c9115769706301814c8cb3df4b')
        self.assertEqual(module.IMAGE, 'sha256:00ebb4212a271bbc9400fcf373f72bf02cb4287b07a41e7b2b650e18a34dade2')
        self.assertNotEqual(module.OLD, module.NEW)

    def test_immutable_accepted_reference(self):
        for guard in ('ACCEPTED_LEAD_RELEASE_REQUIRED', 'ACCEPTED_CONTROLLER_CHANGED',
                      'ACCEPTED_ADAPTER_CHANGED', 'OLD_EXPIRY_TIMER_NOT_INACTIVE',
                      'NEWSLETTER_PREPARATION_ALREADY_EXISTS'):
            with self.subTest(guard=guard):
                self.assertIn(guard, SOURCE)

    def test_only_one_changed_service_image(self):
        self.assertIn("new_model['services'][service]['image'] = IMAGE", SOURCE)
        tree = ast.parse(SOURCE)
        assignment = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Subscript) and
                              isinstance(target.value, ast.Subscript) and
                              isinstance(target.value.value, ast.Subscript) and
                              isinstance(target.value.value.value, ast.Name) and
                              target.value.value.value.id == 'new_model'
                              for target in node.targets)]
        self.assertEqual(len(assignment), 1)

    def test_accepted_prior_release_does_not_need_a_fresh_lease(self):
        # The previous release is already ACCEPTED and its 30-second
        # supervision lease correctly expired. The original engine's
        # healthy(candidate) requests a lease; direct verify is read-only.
        self.assertNotIn("oldbackend.healthy(", SOURCE)
        self.assertIn("oldbackend.verify(name, 'candidate', row)", SOURCE)
        self.assertIn("require(controller.healthy(row), 'ACCEPTED_RUNTIME_NOT_HEALTHY')", SOURCE)
        self.assertIn("NEW.mkdir(mode=0o700)", SOURCE)
        self.assertLess(SOURCE.index("oldbackend.verify(name, 'candidate', row)"),
                        SOURCE.index("NEW.mkdir(mode=0o700)"))

    def test_hub_and_42_nonwebsite_containers_protected(self):
        self.assertIn("plan['protected']['v79-hub'] = before['v79-hub']", SOURCE)
        self.assertIn("len(plan['protected']) == 42", SOURCE)
        self.assertIn("set(plan['protected']).isdisjoint(plan['apps'])", SOURCE)

    def test_pinned_engine_single_stopped_profile(self):
        self.assertIn("selected_profile(newengine)", SOURCE)
        self.assertIn("if (name, which) != ('V79website', 'candidate')", SOURCE)
        self.assertIn("temporary_resource_cleanup_verified", SOURCE)
        self.assertNotIn('engine.deploy(', SOURCE)
        self.assertNotIn('engine.rollback(', SOURCE)

    def test_no_rollback_timer_or_deployment(self):
        self.assertIn("'rollback_timer_armed': False", SOURCE)
        self.assertIn("'deployed': False", SOURCE)
        self.assertIn("PASS_NEWSLETTER_WEBSITE_ONLY_MANIFEST_PREPARED", SOURCE)
        self.assertNotIn("['docker', 'start'", SOURCE)
        self.assertNotIn("['docker', 'compose', 'up'", SOURCE)

    def test_no_provider_or_campaign_side_effect(self):
        self.assertNotIn('smtplib', SOURCE)
        self.assertNotIn('SMTP_PASSWORD', SOURCE)
        self.assertNotIn('send_email(', SOURCE)
        self.assertNotIn('leadEventStatus', SOURCE)


if __name__ == '__main__':
    unittest.main()
