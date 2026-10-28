#!/usr/bin/env python3
"""New website-only supervisor safety checks; no Docker, production, timers or network."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'scripts/newsletter-website-supervisor.py'
spec = importlib.util.spec_from_file_location('newsletter_supervisor_under_test', PATH)
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)
SOURCE = PATH.read_text()


class FakeState:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.writes = []

    def read(self):
        return copy.deepcopy(self.value)

    def put(self, value):
        self.value = copy.deepcopy(value)
        self.writes.append(copy.deepcopy(value))


class FakeEngine:
    def protected_fingerprint(self, row):
        return row['Id'] + '/' + row['Image']

    def runtime_matches(self, before, after, entry, which, **kwargs):
        assert after['Image'] == entry[which + '_image']['Id']
        assert entry['_replaced_id'] == 'a' * 64
        assert entry['model']['services']['site']['image'] == after['Image']
        return True


class FakeBackend:
    def __init__(self, row):
        self.row = row
        self.calls = []
        self.sends = []
        self.plan = None

    def inspect(self, name, allow_missing=False):
        return self.row

    def call(self, args, **kwargs):
        self.calls.append(args)
        return b''

    def switch(self, name, which):
        self.sends.append((name, which))

    def journal(self, event, name):
        self.sends.append(('journal', event, name))


class NewsletterSupervisorTests(unittest.TestCase):
    def test_pinned_website_only(self):
        self.assertEqual(ns.APP, 'V79website')
        self.assertNotEqual(ns.BEFORE, ns.AFTER)
        self.assertNotEqual(ns.ROOT, ns.OLD)
        self.assertEqual(ns.MANIFEST, 'dd0566bd32da564c7b9ff7788c8f9b3c5981a18a3865023c5c56edfebaf1c6f4')

    def test_existing_hardened_engine_is_only_switcher(self):
        tree = ast.parse(SOURCE)
        words = [x.attr for x in ast.walk(tree) if isinstance(x, ast.Attribute)]
        self.assertIn('deploy', words)
        self.assertIn('rollback', words)
        self.assertIn('switch', words)
        self.assertNotIn('Popen', words)
        self.assertNotIn('smtplib', SOURCE)
        self.assertNotIn('sendLeadToTiquet', SOURCE)
        self.assertNotIn('V79_HUB_EVENT_REPLAY_LEAD_IDS', SOURCE)
        self.assertIn("set(plan.get('apps', {})) == {APP}", SOURCE)
        self.assertIn("len(plan.get('protected', {})) == 42", SOURCE)

    def test_timer_is_one_shot_no_restart(self):
        service, timer = ns.timer_units(1790000000)
        self.assertIn('Restart=no', service)
        self.assertIn('Type=oneshot', service)
        self.assertIn('--expire', service)
        self.assertIn('Persistent=true', timer)
        self.assertEqual(ns.WINDOW, 1200)
        self.assertNotEqual(ns.TIMER, ns.PREVIOUS_TIMER)

    def test_new_manifest_and_profile_receipts_required(self):
        for guard in ('PREPARATION_RECEIPT_NOT_ACCEPTED', 'NEW_PROFILE_EVIDENCE_CHANGED',
                      'WEBSITE_IMAGE_ONLY_MODEL_CHANGED',
                      'PRIOR_LEAD_RELEASE_NOT_ACCEPTED', 'WORKFORCE_OR_ACCEPTED_TIMER_CHANGED',
                      'CANDIDATE_SOURCE_CHANGED', 'CURRENT_ACCEPTED_WEBSITE_CHANGED'):
            with self.subTest(guard=guard):
                self.assertIn(guard, SOURCE)

    def test_rollback_original_no_recreation(self):
        image = ns.BEFORE
        row = {'Id': 'b'*64, 'Image': image, 'State': {'Running': True, 'Health': {'Status': 'healthy'}}}
        state = FakeState({'phase': 'DEPLOYING'})
        engine = FakeEngine()
        backend = FakeBackend(row)
        entry = {'baseline': copy.deepcopy(row), 'service': 'site', 'project': 'website',
                 'candidate_image': {'Id': ns.AFTER}, 'rollback_image': {'Id': ns.BEFORE}}
        ns.durable(engine, backend, { 'apps': {ns.APP: entry}, 'selinux_enabled': False}, state)
        backend.switch(ns.APP, 'rollback')
        self.assertEqual(backend.sends, [])

    def test_unreviewed_compose_command_refused(self):
        row = {'Id': 'b'*64, 'Image': ns.BEFORE}
        engine = FakeEngine()
        backend = FakeBackend(row)
        state = FakeState({'phase': 'DEPLOYING', 'replacements': {}})
        entry = {'baseline': row, 'service': 'site', 'project': 'website',
                 'directory': '/trusted', 'candidate_file': '/trusted/candidate.json',
                 'rollback_file': '/trusted/rollback.json',
                 'candidate_image': {'Id': ns.AFTER}, 'rollback_image': {'Id': ns.BEFORE}}
        ns.durable(engine, backend, {'apps': {ns.APP: entry}}, state)
        with self.assertRaisesRegex(ValueError, 'UNREVIEWED_COMPOSE_MUTATION'):
            backend.call(['docker', 'compose', 'up', 'other-service'])
        self.assertEqual(backend.calls, [])

    def test_unknown_start_id_is_refused(self):
        backend = FakeBackend({'Id': 'b'*64, 'Image': ns.BEFORE})
        state = FakeState({'phase': 'DEPLOYING', 'replacements': {ns.APP: {'candidate':
                           {'created_id': 'c'*64}}}})
        entry = {'service': 'site'}
        ns.durable(FakeEngine(), backend, {'apps': {ns.APP: entry}}, state)
        with self.assertRaisesRegex(ValueError, 'UNVERIFIED_DOCKER_START_ID'):
            backend.call(['docker', 'start', 'd'*64])
        self.assertEqual(backend.calls, [])

    def test_durable_intent_written_before_compose_call(self):
        backend = FakeBackend({'Id': 'b'*64, 'Image': ns.BEFORE})
        state = FakeState({'phase': 'DEPLOYING', 'replacements': {}})
        entry = {'service': 'site', 'directory': '/trusted', 'project': 'website',
                 'candidate_file': '/trusted/candidate.json', 'rollback_file': '/trusted/rollback.json',
                 'baseline': {}, 'candidate_image': {'Id': ns.AFTER},
                 'rollback_image': {'Id': ns.BEFORE}}
        ns.durable(FakeEngine(), backend, {'apps': {ns.APP: entry}}, state)
        args = ['docker', 'compose', '--env-file', '/dev/null', '--project-directory',
                '/trusted', '--project-name', 'website', '-f', '/trusted/candidate.json',
                'up', '--no-start', '--no-deps', '--no-build', '--pull', 'never',
                '--force-recreate', 'site']
        backend.call(args)
        self.assertEqual(backend.calls, [args])
        self.assertIn(ns.APP, state.read()['replacements'])
        self.assertIn('candidate', state.read()['replacements'][ns.APP])
        self.assertTrue(state.writes)

    def test_accepted_status_and_timer_required(self):
        self.assertIn("current['phase'] == 'AWAITING_ACCEPTANCE'", SOURCE)
        self.assertIn("time.time() < current['deadline_epoch'] - 30", SOURCE)
        self.assertIn("prop(TIMER, 'ActiveState') == 'active'", SOURCE)
        self.assertIn("current['phase'] = 'ACCEPTED'", SOURCE)


if __name__ == '__main__':
    unittest.main()
