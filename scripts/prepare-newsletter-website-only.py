#!/usr/bin/env python3
"""Read-only production preparation of a sealed WEBSITE-ONLY newsletter transaction.

The already accepted lead-release state and the build receipt are immutable inputs.
The only Docker writes permitted are original-engine nonce-owned, never-started
synthetic candidate profile objects; no application containers are touched.
This script neither deploys nor arms an expiry watchdog.
"""
import ast
import copy
import fcntl
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import stat
import textwrap

OLD = Path('/home/firelion/v79-lead-release-2pvsb2mo-r2')
NEW = Path('/home/firelion/v79-newsletter-website-release-20261028')
BUILD = Path('/home/firelion/v79-newsletter-candidate-9b66hdwg/receipt.json')
OLD_CONTROLLER_SHA = '2f7ba81b89ca4722fabc904d180bf26b1e957bb4db71beeab4a68151e6f20580'
OLD_MANIFEST = '8275be9290073c55683bce2458971dec7276465ca1631ca25a6b4fee447fa68d'
OLD_ADAPTER_SHA = '4f48879bf79c5353ea3aecaf57c8dd85bde7084e371a5dbf5f0c3d90782cbe1c'
CURRENT = {'v79-hub': 'sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec',
           'V79website': 'sha256:2bf0b35a8b7d71b183b34fa09a08ba7fb1b3c7637448b523c1bd07f8a02fa1fb'}
SOURCE = 'db84a4a07cf637c9115769706301814c8cb3df4b'
IMAGE = 'sha256:00ebb4212a271bbc9400fcf373f72bf02cb4287b07a41e7b2b650e18a34dade2'
TIMERS = ('v79-g2-approved-task-worker.timer', 'v79-workforce-morning.timer',
          'v79-workforce-evening.timer')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def private_directory(path):
    st = path.lstat()
    require(stat.S_ISDIR(st.st_mode) and not path.is_symlink() and
            st.st_uid == os.geteuid() and stat.S_IMODE(st.st_mode) == 0o700,
            'PRIVATE_DIRECTORY_REQUIRED')


def private_file(path):
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and not path.is_symlink() and
            st.st_uid == os.geteuid() and st.st_nlink == 1 and not st.st_mode & 0o077,
            'PRIVATE_INPUT_REQUIRED')
    return path.read_bytes()


def write(root, name, payload):
    require('/' not in name and name not in ('.', '..'), 'INVALID_PRIVATE_OUTPUT_NAME')
    fd = os.open(root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def selected_profile(engine):
    # The only alteration to the pinned engine's profile function is one
    # selection guard. Its original nonce cleanup/finally remains unchanged.
    tree = ast.parse(textwrap.dedent(inspect.getsource(engine.stopped_profiles)))
    f = tree.body[0]
    require(isinstance(f, ast.FunctionDef) and f.name == 'stopped_profiles',
            'PROFILE_FUNCTION_CHANGED')
    loops = [n for n in ast.walk(f) if isinstance(n, ast.For) and
             isinstance(n.target, ast.Name) and n.target.id == 'which' and
             isinstance(n.iter, ast.Tuple) and
             [getattr(e, 'value', None) for e in n.iter.elts] == ['candidate', 'rollback']]
    require(len(loops) == 1, 'PROFILE_SELECTION_CHANGED')
    loops[0].body.insert(0, ast.parse("if (name, which) != ('V79website', 'candidate'):\n    continue").body[0])
    f.name = 'website_candidate_profile'
    ast.fix_missing_locations(tree)
    scope = dict(engine.__dict__)
    exec(compile(tree, '<pinned-engine-selection-only>', 'exec'), scope)
    return scope['website_candidate_profile']


def prepare():
    os.umask(0o077)
    private_directory(OLD)
    require(not NEW.exists() and not NEW.is_symlink(), 'NEWSLETTER_PREPARATION_ALREADY_EXISTS')
    controller_raw = private_file(OLD / 'lead-release-supervisor.py')
    require(digest(controller_raw) == OLD_CONTROLLER_SHA, 'ACCEPTED_CONTROLLER_CHANGED')
    adapter_raw = private_file(OLD / 'lead-release-compat.py')
    require(digest(adapter_raw) == OLD_ADAPTER_SHA, 'ACCEPTED_ADAPTER_CHANGED')
    lock_fd = os.open(OLD / 'binding.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        controller = load('accepted_newsletter_prior_controller', OLD / 'lead-release-supervisor.py')
        prior_state = controller.State(OLD)
        accepted = prior_state.read()
        require(accepted and accepted.get('phase') == 'ACCEPTED' and
                accepted.get('manifest_sha256') == OLD_MANIFEST and
                accepted.get('acceptance') == 'MATCHED_EXISTING_OPERATOR_TEST_LEAD' and
                accepted.get('receipt_sha256') and
                not accepted.get('rollback_failed') and
                accepted.get('engine_rollback_complete') is not True,
                'ACCEPTED_LEAD_RELEASE_REQUIRED')
        for name in ('v79-hub', 'V79website'):
            variant = accepted.get('replacements', {}).get(name, {}).get('candidate', {})
            require(re.fullmatch('[0-9a-f]{64}', variant.get('created_id') or '') is not None,
                    'ACCEPTED_RUNTIME_ID_REQUIRED')
        require(controller.prop(controller.TIMER, 'ActiveState') == 'inactive',
                'OLD_EXPIRY_TIMER_NOT_INACTIVE')
        engine, oldbackend, oldplan, helper = controller.load_context(prior_state)
        require(digest(private_file(OLD / 'transaction.json')) == OLD_MANIFEST and
                set(oldplan['apps']) == set(CURRENT) and len(oldplan['protected']) == 41 and
                len(oldplan.get('workforce_timers', {})) == len(TIMERS),
                'ACCEPTED_PLAN_SCOPE_CHANGED')
        oldbackend.check_files()
        oldbackend.protected()
        require(helper.timer_states() == oldplan['workforce_timers'],
                'WORKFORCE_TIMERS_CHANGED')
        before = {}
        for name in CURRENT:
            row = oldbackend.inspect(name)
            require(row['Id'] == accepted['replacements'][name]['candidate']['created_id']
                    and row['Image'] == CURRENT[name], 'ACCEPTED_RUNTIME_CHANGED')
            # The *accepted* prior controller has an intentionally expired
            # supervision lease. Its healthy(candidate) method requests a
            # fresh lease even for a read-only check. Verify the exact sealed
            # runtime contract directly; require genuine healthy/running state
            # without extending or recreating that accepted controller's lease.
            oldbackend.verify(name, 'candidate', row)
            require(controller.healthy(row), 'ACCEPTED_RUNTIME_NOT_HEALTHY')
            before[name] = row
        oldbackend.protected()
        raw = private_file(BUILD)
        receipt = json.loads(raw)
        require(receipt.get('result') == 'PASS_NEWSLETTER_CANDIDATE_BUILT_FOCUSED_ONLY' and
                receipt.get('website', {}).get('commit') == SOURCE and
                receipt['website'].get('image') == IMAGE and
                receipt.get('newsletter_checks') == 'PASS' and
                receipt.get('compiled_http_flow') == 'PASS' and
                receipt.get('hub_rebuilt') is False and
                receipt.get('previous_lead_checks_repeated') is False and
                receipt.get('production_container_count') == 43 and
                receipt.get('live_runtime_unchanged') is True and
                receipt.get('deployed') is False,
                'FOCUSED_BUILD_RECEIPT_CHANGED')
        candidate_metadata, candidate_manifest = helper.image_metadata(IMAGE)
        require(candidate_metadata['Id'] == IMAGE and
                (candidate_metadata['Config'].get('Labels') or {}).get('org.opencontainers.image.revision') == SOURCE,
                'NEWSLETTER_IMAGE_SOURCE_CHANGED')
        existing = copy.deepcopy(oldplan['apps']['V79website'])
        existing_model = json.loads(private_file(Path(existing['candidate_file'])))
        service = existing['service']
        require(existing_model['services'][service]['image'] == CURRENT['V79website'] and
                existing_model['services'][service].get('environment') ==
                engine.environment(before['V79website']['Config'].get('Env') or []),
                'ACCEPTED_CONFIGURATION_MODEL_CHANGED')
        require(existing.get('compose_version') == '5.6.1', 'ACCEPTED_COMPOSE_VERSION_CHANGED')
        helper.verify_compose_version(controller.command(['docker', 'compose', 'version', '--short']).stdout.decode().strip(),
                                      existing['compose_version'])
        new_model = copy.deepcopy(existing_model)
        new_model['services'][service]['image'] = IMAGE  # the ONLY service configuration change
        require(set(existing_model['services']) == {service} and
                set(new_model['services']) == {service}, 'WEBSITE_COMPOSE_SERVICE_SCOPE_CHANGED')

        # New transaction protects Hub like every other non-website container.
        plan = copy.deepcopy(oldplan)
        plan['schema'] = 'v79-newsletter-website-only-v1'
        plan['apps'] = {'V79website': existing}
        plan['protected']['v79-hub'] = before['v79-hub']
        require(set(plan['protected']).isdisjoint(plan['apps']) and
                len(plan['protected']) == 42, 'WEBSITE_ONLY_PROTECTION_SCOPE_CHANGED')
        entry = plan['apps']['V79website']
        entry.pop('_replaced_id', None)
        entry['baseline'] = before['V79website']
        entry['candidate_image'] = candidate_metadata
        entry['rollback_image'] = copy.deepcopy(existing['candidate_image'])
        require(entry['rollback_image']['Id'] == CURRENT['V79website'],
                'ROLLBACK_MUST_BE_ACCEPTED_WEBSITE')
        entry['image_manifests'] = {
            CURRENT['V79website']: existing['image_manifests'][CURRENT['V79website']],
            IMAGE: candidate_manifest}
        entry['model'] = new_model
        plan['prior_accepted_manifest_sha256'] = OLD_MANIFEST
        plan['focused_build_receipt_sha256'] = digest(raw)
        plan['newsletter_candidate_revision'] = SOURCE
        NEW.mkdir(mode=0o700)
        write(NEW, 'accepted-evidence-reference.json', canonical({
            'accepted_manifest_sha256': OLD_MANIFEST,
            'accepted_controller_sha256': OLD_CONTROLLER_SHA,
            'focused_receipt_sha256': digest(raw),
            'website_prior': CURRENT['V79website'],
            'website_candidate': IMAGE,
            'protected_count': 42,
        }))
        for filename, blob in helper.MODULES.items():
            source = private_file(OLD / filename)
            require(hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest() == blob,
                    'ORIGINAL_ENGINE_SOURCE_CHANGED')
            write(NEW, filename, source)
        write(NEW, 'lead-release-compat.py', adapter_raw)  # reviewed runtime/Compose compatibility
        for which, model in (('candidate', new_model), ('rollback', existing_model)):
            value = canonical(model)
            write(NEW, 'V79website.' + which + '.json', value)
            entry[which + '_file'] = str(NEW / ('V79website.' + which + '.json'))
            entry[which + '_sha256'] = digest(value)
        newengine = load('newsletter_existing_paired_engine', NEW / 'paired-compose-transaction.py')
        newhelper = load('newsletter_prior_adapter', NEW / 'lead-release-compat.py')
        newhelper.install_compat(newengine)
        manifest = newengine.seal_plan(NEW, plan)
        newbackend = newengine.ComposeBackend(NEW, plan)
        newhelper.protect_core_health(newbackend)
        newbackend.check_files()
        newbackend.protected()
        newbackend.eligible('V79website')
        # Exactly one new image-bound, never-started synthetic Compose profile.
        checked = []
        original = newengine.runtime_matches
        def capture(old, actual, model_entry, which, **kw):
            require(model_entry['release_name'] == 'V79website' and which == 'candidate' and
                    actual['Image'] == IMAGE, 'UNEXPECTED_PROFILE_SELECTED')
            result = original(old, actual, model_entry, which, **kw)
            checked.append('V79website/candidate')
            write(NEW, 'newsletter-candidate-profile.json', canonical({
                'result': 'RUNTIME_MATCHED', 'app': 'V79website', 'which': which,
                'image': actual['Image'], 'model_sha256': entry['candidate_sha256'],
                'runtime_before_sha256': newengine.digest(old),
                'runtime_after_sha256': newengine.digest(actual)}))
            return result
        newengine.runtime_matches = capture
        selected = selected_profile(newengine)
        print(json.dumps({'stage': 'new_website_candidate_profile', 'old_profiles_repeated': False,
                          'new_profiles': 1, 'deployed': False}), flush=True)
        # The original engine handles the entire stopped-profile and cleanup path.
        with newhelper.heartbeat(NEW):
            proof = selected(newbackend)
        require(proof.get('profiles_verified') == 1 and
                proof.get('temporary_resource_cleanup_verified') is True and
                checked == ['V79website/candidate'], 'NEWSLETTER_PROFILE_NOT_VERIFIED')
        for name, row in before.items():
            require(newengine.protected_fingerprint(oldbackend.inspect(name)) ==
                    newengine.protected_fingerprint(row), 'ACCEPTED_PAIR_CHANGED_DURING_PREPARATION')
        newbackend.protected()
        require(helper.timer_states() == oldplan['workforce_timers'] and
                controller.prop(controller.TIMER, 'ActiveState') == 'inactive',
                'TIMER_CHANGED_DURING_PREPARATION')
        return_value = {'result': 'PASS_NEWSLETTER_WEBSITE_ONLY_MANIFEST_PREPARED',
                        'directory': str(NEW), 'manifest_sha256': manifest,
                        'candidate_image': IMAGE, 'rollback_website_image': CURRENT['V79website'],
                        'hub_protected': True, 'protected_container_count': 42,
                        'new_profiles_verified': 1, 'old_profiles_repeated': False,
                        'original_engine_reused': True, 'private_credentials_reused': True,
                        'prior_accepted_release_preserved': True,
                        'workforce_timers_preserved': True,
                        'rollback_timer_armed': False, 'deployed': False}
        write(NEW, 'preparation-result.json', canonical(return_value))
        return return_value
    finally:
        os.close(lock_fd)


if __name__ == '__main__':
    try:
        print(json.dumps(prepare(), indent=2), flush=True)
    except Exception as error:
        name = str(error).split(':', 1)[0]
        reason = name if re.fullmatch('[A-Z][A-Z0-9_]+', name) else type(error).__name__
        print(json.dumps({'result': 'STOP_NEWSLETTER_WEBSITE_ONLY_PREPARATION',
                          'reason': reason, 'deployed': False}), flush=True)
        raise SystemExit(1)
