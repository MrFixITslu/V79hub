#!/usr/bin/env python3
"""Website-only release supervisor; delegates all Docker switches to the pinned hardened engine.

Deployment and rollback require an immutable, already-prepared single-website manifest.
No Hub switch, email, lead replay, payment, migration or configuration regeneration.
"""
import argparse
import contextlib
import copy
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/home/firelion/v79-newsletter-website-release-20261028')
OLD = Path('/home/firelion/v79-lead-release-2pvsb2mo-r2')
MANIFEST = 'dd0566bd32da564c7b9ff7788c8f9b3c5981a18a3865023c5c56edfebaf1c6f4'
OLD_MANIFEST = '8275be9290073c55683bce2458971dec7276465ca1631ca25a6b4fee447fa68d'
HUB = 'sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec'
BEFORE = 'sha256:2bf0b35a8b7d71b183b34fa09a08ba7fb1b3c7637448b523c1bd07f8a02fa1fb'
AFTER = 'sha256:00ebb4212a271bbc9400fcf373f72bf02cb4287b07a41e7b2b650e18a34dade2'
REVISION = 'db84a4a07cf637c9115769706301814c8cb3df4b'
APP = 'V79website'
TIMER = 'v79-newsletter-website-20261028-expiry.timer'
SERVICE = 'v79-newsletter-website-20261028-expiry.service'
PREVIOUS_TIMER = 'vision79-lead-pair-permissions-r2-expiry.timer'
WINDOW = 20 * 60


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def private(path):
    import stat
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and not path.is_symlink() and
            st.st_uid == os.geteuid() and st.st_nlink == 1 and
            st.st_mode & 0o077 == 0, 'PRIVATE_FILE_REQUIRED')
    return path.read_bytes()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def atomic(path, content):
    tmp = path.parent / ('.' + path.name + '-' + str(os.getpid()))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def healthy(row):
    return bool(row and row['State'].get('Running') and
                row['State'].get('Health', {}).get('Status') == 'healthy')


class State:
    def __init__(self):
        self.path = ROOT / 'newsletter-release-state.json'

    def read(self):
        if not self.path.exists():
            return None
        state = json.loads(private(self.path))
        require(state.get('manifest_sha256') == MANIFEST and
                state.get('supervisor_sha256') == sha(private(Path(__file__))),
                'NEWSLETTER_STATE_OR_CONTROLLER_CHANGED')
        return state

    def put(self, data):
        require(data['manifest_sha256'] == MANIFEST and
                data['supervisor_sha256'] == sha(private(Path(__file__))),
                'NEWSLETTER_STATE_OR_CONTROLLER_CHANGED')
        atomic(self.path, canon(data))


def command(args, *, user=False, check=True, timeout=45):
    env = None
    if user:
        uid = str(os.geteuid())
        env = {**os.environ, 'XDG_RUNTIME_DIR': '/run/user/' + uid,
               'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/' + uid + '/bus'}
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=env, timeout=timeout)
    if check:
        require(result.returncode == 0, 'REDACTED_COMMAND_FAILURE')
    return result


def ctl(*args, check=True):
    return command(['systemctl', '--user', *args], user=True, check=check)


def prop(unit, key):
    return ctl('show', unit, '--property=' + key, '--value').stdout.decode().strip()


def timer_units(deadline):
    due = datetime.datetime.fromtimestamp(deadline, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    service = ('[Unit]\nDescription=V79 newsletter website-only release expiry\n'
               '[Service]\nType=oneshot\nRestart=no\nTimeoutStartSec=1200\n'
               'ExecStart=/usr/bin/sg docker -c "/usr/bin/python3 -B ' +
               str(ROOT / 'newsletter-website-supervisor.py') + ' --expire"\n')
    timer = ('[Unit]\nDescription=V79 newsletter website-only acceptance deadline\n'
             '[Timer]\nOnCalendar=' + due + '\nPersistent=true\nAccuracySec=1s\n'
             'Unit=' + SERVICE + '\n[Install]\nWantedBy=timers.target\n')
    return service, timer


def arm(deadline):
    directory = Path.home() / '.config/systemd/user'
    require(directory.is_dir() and not directory.is_symlink() and
            directory.stat().st_uid == os.geteuid(), 'USER_SYSTEMD_DIRECTORY_UNAVAILABLE')
    require(command(['loginctl', 'show-user', 'firelion', '--property=Linger',
                     '--value']).stdout.decode().strip() == 'yes',
            'DURABLE_SYSTEMD_USER_REQUIRED')
    require(prop(PREVIOUS_TIMER, 'ActiveState') == 'inactive', 'ACCEPTED_RELEASE_TIMER_CHANGED')
    for name in (TIMER, SERVICE):
        require(not (directory / name).exists(), 'NEW_EXPIRY_UNIT_ALREADY_EXISTS')
    require(prop(SERVICE, 'ActiveState') in ('inactive', 'failed'), 'NEW_EXPIRY_SERVICE_BUSY')
    for name, data in zip((SERVICE, TIMER), timer_units(deadline)):
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    ctl('daemon-reload')
    ctl('enable', '--now', TIMER)
    require(prop(TIMER, 'ActiveState') == 'active' and
            prop(TIMER, 'NextElapseUSecRealtime') not in ('', 'n/a', 'N/A', 'infinity'),
            'NEW_EXPIRY_TIMER_NOT_ARMED')


def disarm():
    response = ctl('disable', '--now', TIMER, check=False)
    return response.returncode == 0 and prop(TIMER, 'ActiveState') == 'inactive'


def durable(engine, backend, plan, state):
    call_original = backend.call
    switch_original = backend.switch
    journal_original = backend.journal

    def verify(name, which, row=None):
        require(name == APP and which in ('candidate', 'rollback'), 'FOREIGN_RELEASE_APP')
        entry = copy.deepcopy(plan['apps'][name])
        row = row or backend.inspect(name)
        if which == 'rollback' and row['Id'] == entry['baseline']['Id']:
            require(engine.protected_fingerprint(row) ==
                    engine.protected_fingerprint(entry['baseline']),
                    'ACCEPTED_WEBSITE_ORIGINAL_CHANGED')
            return True
        current = state.read()
        context = (current or {}).get('replacements', {}).get(name, {}).get(which)
        require(isinstance(context, dict) and 'previous_id' in context,
                'DURABLE_REPLACEMENT_CONTEXT_MISSING')
        entry['_replaced_id'] = context['previous_id']
        payload = private(Path(entry[which + '_file']))
        require(sha(payload) == entry[which + '_sha256'], 'SEALED_SELECTED_MODEL_CHANGED')
        entry['model'] = json.loads(payload)
        require(context.get('created_id') in (None, row['Id']),
                'REPLACEMENT_ID_CHANGED')
        result = engine.runtime_matches(entry['baseline'], row, entry, which,
                                        selinux_enabled=plan['selinux_enabled'])
        if context.get('created_id') is None:
            context['created_id'] = row['Id']
            state.put(current)
        return result

    def call(args, **kw):
        if args[:2] == ['docker', 'compose']:
            require('up' in args, 'UNREVIEWED_ENGINE_COMMAND')
            entry = plan['apps'][APP]
            matches = []
            for which in ('candidate', 'rollback'):
                expected = ['docker', 'compose', '--env-file', '/dev/null',
                            '--project-directory', entry['directory'],
                            '--project-name', entry['project'], '-f',
                            entry[which + '_file'], 'up', '--no-start',
                            '--no-deps', '--no-build', '--pull', 'never',
                            '--force-recreate', entry['service']]
                if args == expected:
                    matches.append(which)
            require(len(matches) == 1, 'UNREVIEWED_COMPOSE_MUTATION')
            which = matches[0]
            previous_id = entry.get('_replaced_id')
            require(previous_id is None or re.fullmatch('[0-9a-f]{64}', previous_id),
                    'INVALID_PREVIOUS_CONTAINER_ID')
            current = state.read()
            require(current and current['phase'] != 'ACCEPTED',
                    'ACCEPTED_RELEASE_NO_MUTATION')
            current.setdefault('replacements', {}).setdefault(APP, {})[which] = {
                'previous_id': previous_id, 'created_id': None}
            state.put(current)  # durable BEFORE a potentially ambiguous Compose result
        elif args[:2] == ['docker', 'start']:
            current = state.read()
            permitted = {r.get('created_id') for v in
                         (current or {}).get('replacements', {}).values()
                         for r in v.values()}
            require(len(args) == 3 and args[2] in permitted and args[2] is not None,
                    'UNVERIFIED_DOCKER_START_ID')
        else:
            require(args == ['docker', 'ps', '--all', '--format', '{{.Names}}'],
                    'UNREVIEWED_ENGINE_COMMAND')
        return call_original(args, **kw)

    def switch(name, which):
        require(name == APP, 'FOREIGN_RELEASE_APP')
        if which == 'rollback':
            row = backend.inspect(APP, allow_missing=True)
            if healthy(row) and row['Image'] == BEFORE:
                try:
                    verify(APP, 'rollback', row)
                except Exception:
                    pass
                else:
                    return
        return switch_original(name, which)

    def journal(event, name=None):
        journal_original(event, name)
        if event in ('CANDIDATE_INTENT', 'ROLLBACK_INTENT',
                     'ROLLBACK_FAILED', 'ORIGINAL_PAIR_RESTORED'):
            current = state.read()
            require(current and (name is None or name == APP), 'FOREIGN_RELEASE_EVENT')
            if event == 'CANDIDATE_INTENT' and APP not in current['touched']:
                current['touched'].append(APP)
            if event == 'ROLLBACK_INTENT':
                current['engine_rollback_started'] = True
            if event == 'ROLLBACK_FAILED':
                current['rollback_failed'] = True
            if event == 'ORIGINAL_PAIR_RESTORED':
                current['engine_rollback_complete'] = True
            state.put(current)

    backend.verify = verify
    backend.call = call
    backend.switch = switch
    backend.journal = journal
    return backend


def context(state):
    require(ROOT.is_dir() and not ROOT.is_symlink() and
            ROOT.stat().st_uid == os.geteuid() and ROOT.stat().st_mode & 0o077 == 0,
            'PRIVATE_RELEASE_DIRECTORY_REQUIRED')
    require(Path(__file__).resolve() == ROOT / 'newsletter-website-supervisor.py',
            'INSTALL_SUPERVISOR_IN_PREPARED_DIRECTORY')
    proof = json.loads(private(ROOT / 'preparation-result.json'))
    require(proof.get('result') == 'PASS_NEWSLETTER_WEBSITE_ONLY_MANIFEST_PREPARED' and
            proof.get('manifest_sha256') == MANIFEST and
            proof.get('candidate_image') == AFTER and
            proof.get('rollback_website_image') == BEFORE and
            proof.get('hub_protected') is True and
            proof.get('protected_container_count') == 42 and
            proof.get('new_profiles_verified') == 1 and
            proof.get('old_profiles_repeated') is False and
            proof.get('workforce_timers_preserved') is True and
            proof.get('rollback_timer_armed') is False and
            proof.get('deployed') is False, 'PREPARATION_RECEIPT_NOT_ACCEPTED')
    old = json.loads(private(OLD / 'lead-release-state.json'))
    require(old.get('phase') == 'ACCEPTED' and
            old.get('manifest_sha256') == OLD_MANIFEST and
            old.get('acceptance') == 'MATCHED_EXISTING_OPERATOR_TEST_LEAD' and
            old.get('receipt_sha256') and not old.get('rollback_failed'),
            'PRIOR_LEAD_RELEASE_NOT_ACCEPTED')
    require(prop(PREVIOUS_TIMER, 'ActiveState') == 'inactive',
            'PRIOR_RELEASE_TIMER_CHANGED')
    helper = load('newsletter_guarded_compat', ROOT / 'lead-release-compat.py')
    for filename, blob in helper.MODULES.items():
        raw = private(ROOT / filename)
        require(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == blob,
                'ORIGINAL_ENGINE_SOURCE_CHANGED')
    engine = load('newsletter_hardened_engine', ROOT / 'paired-compose-transaction.py')
    plan = engine.load_plan(ROOT, MANIFEST)
    require(plan.get('schema') == 'v79-newsletter-website-only-v1' and
            set(plan.get('apps', {})) == {APP} and
            len(plan.get('protected', {})) == 42 and
            'v79-hub' in plan['protected'] and
            plan['protected']['v79-hub']['Image'] == HUB and
            plan.get('requires_supervision') is True,
            'WEBSITE_ONLY_PLAN_SCOPE_CHANGED')
    entry = plan['apps'][APP]
    require(entry['baseline']['Image'] == BEFORE and
            entry['rollback_image']['Id'] == BEFORE and
            entry['candidate_image']['Id'] == AFTER and
            entry.get('release_name') == APP and
            entry.get('compose_version') == '5.6.1',
            'PINNED_WEBSITE_IMAGE_OR_COMPOSE_CHANGED')
    helper.verify_compose_version(
        command(['docker', 'compose', 'version', '--short']).stdout.decode().strip(),
        '5.6.1')
    candidate = json.loads(private(Path(entry['candidate_file'])))
    rollback_model = json.loads(private(Path(entry['rollback_file'])))
    expected = copy.deepcopy(rollback_model)
    service = entry['service']
    require(set(rollback_model.get('services', {})) == {service} and
            expected['services'][service]['image'] == BEFORE,
            'ROLLBACK_SERVICE_MODEL_CHANGED')
    expected['services'][service]['image'] = AFTER
    require(candidate == expected and entry['model'] == candidate and
            entry['candidate_sha256'] == sha(canon(candidate)) and
            entry['rollback_sha256'] == sha(canon(rollback_model)),
            'WEBSITE_IMAGE_ONLY_MODEL_CHANGED')
    capture = json.loads(private(ROOT / 'newsletter-candidate-profile.json'))
    require(capture.get('result') == 'RUNTIME_MATCHED' and
            capture.get('image') == AFTER and
            capture.get('app') == APP and capture.get('which') == 'candidate' and
            capture.get('model_sha256') == entry['candidate_sha256'],
            'NEW_PROFILE_EVIDENCE_CHANGED')
    helper.install_compat(engine)
    backend = engine.ComposeBackend(ROOT, plan)
    helper.protect_core_health(backend)
    old_protected = backend.protected

    def protected():
        old_protected()
        require(helper.timer_states() == plan['workforce_timers'] and
                prop(PREVIOUS_TIMER, 'ActiveState') == 'inactive',
                'WORKFORCE_OR_ACCEPTED_TIMER_CHANGED')
    backend.protected = protected
    durable(engine, backend, plan, state)
    return engine, backend, plan, helper


def preflight(engine, backend, plan, helper, state):
    backend.check_files()
    backend.protected()
    row = backend.inspect(APP)
    require(row['Id'] == plan['apps'][APP]['baseline']['Id'] and
            engine.protected_fingerprint(row) ==
            engine.protected_fingerprint(plan['apps'][APP]['baseline']) and
            healthy(row), 'CURRENT_ACCEPTED_WEBSITE_CHANGED')
    backend.eligible(APP)
    for which in ('candidate', 'rollback'):
        entry = plan['apps'][APP]
        pin = entry[which + '_image']['Id']
        metadata, manifest = helper.image_metadata(pin)
        require(metadata['Id'] == pin and
                entry['image_manifests'][pin] == manifest,
                'SEALED_IMAGE_MANIFEST_CHANGED')
    require((plan['apps'][APP]['candidate_image']['Config'].get('Labels') or {})
            .get('org.opencontainers.image.revision') == REVISION,
            'CANDIDATE_SOURCE_CHANGED')
    require(state.read() is None, 'RELEASE_ALREADY_STARTED_NO_REPLAY')
    require(prop(TIMER, 'ActiveState') in ('inactive', 'failed') and
            prop(SERVICE, 'ActiveState') in ('inactive', 'failed'), 'NEW_EXPIRY_ALREADY_ACTIVE')
    return {'result': 'PASS_NEWSLETTER_WEBSITE_ONLY_SUPERVISOR_PREFLIGHT',
            'manifest_sha256': MANIFEST, 'hub_protected': True,
            'protected_container_count': 42, 'previous_release_preserved': True,
            'rollback_timer_armed': False, 'deployed': False}


def rollback(engine, backend, state):
    current = state.read()
    require(current and current['phase'] != 'ACCEPTED', 'ACCEPTED_RELEASE_NO_ROLLBACK')
    require(not current.get('rollback_failed'), 'PREVIOUS_ROLLBACK_FAILURE_OPERATOR_REQUIRED')
    names = current.get('touched', [])
    require(names in ([], [APP]), 'TOUCHED_SCOPE_CHANGED')
    current['phase'] = 'ROLLING_BACK'
    state.put(current)
    try:
        result = engine.rollback(backend, names)
        require(result.get('status') == 'PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED',
                'HARDENED_ROLLBACK_INCOMPLETE')
        row = backend.inspect(APP)
        require(healthy(row) and backend.verify(APP, 'rollback', row),
                'WEBSITE_ROLLBACK_RUNTIME_NOT_VERIFIED')
        backend.protected()
        current = state.read()
        current['phase'] = 'ROLLED_BACK'
        state.put(current)
        return result
    except BaseException:
        current = state.read()
        current['phase'] = 'ROLLBACK_REQUIRES_OPERATOR'
        state.put(current)
        raise


def deploy(engine, backend, plan, helper, state):
    preflight(engine, backend, plan, helper, state)
    deadline = time.time() + WINDOW
    state.put({'manifest_sha256': MANIFEST,
               'supervisor_sha256': sha(private(Path(__file__))),
               'phase': 'ARMING', 'deadline_epoch': deadline,
               'touched': [], 'replacements': {}})
    try:
        arm(deadline)
    except BaseException:
        current = state.read()
        current['phase'] = 'TIMER_ARMING_REQUIRES_OPERATOR'
        state.put(current)
        raise
    current = state.read()
    current['phase'] = 'DEPLOYING'
    state.put(current)
    try:
        with helper.heartbeat(ROOT):
            result = engine.deploy(backend)
            if result.get('status') != 'PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING':
                current = state.read()
                current['candidate_failure_reason'] = result.get('candidate_failure_reason',
                                                                 'CANDIDATE_FAILED')
                state.put(current)
                require(False, 'CANDIDATE_FAILED_OR_ROLLED_BACK')
            backend.healthy(APP, 'candidate')
            backend.protected()
            require(time.time() < deadline - 45, 'ACCEPTANCE_WINDOW_TOO_SHORT')
            current = state.read()
            current['phase'] = 'AWAITING_ACCEPTANCE'
            state.put(current)
            return {'result': 'PASS_NEWSLETTER_CANDIDATE_HEALTHY_AWAITING_ACCEPTANCE',
                    'candidate_image': AFTER,
                    'rollback_website_image': BEFORE,
                    'protected_container_count': 42,
                    'rollback_timer_armed': True, 'deployed': True,
                    'runtime_acceptance': False,
                    'deadline_saint_lucia': datetime.datetime.fromtimestamp(
                        deadline, datetime.timezone(datetime.timedelta(hours=-4))).isoformat()}
    except BaseException as error:
        current = state.read()
        if current.get('phase') == 'ACCEPTED':
            raise
        try:
            if current.get('rollback_failed'):
                current['phase'] = 'ROLLBACK_REQUIRES_OPERATOR'
                state.put(current)
                return {'result': 'RELEASE_REQUIRES_OPERATOR', 'deployed': 'UNCONFIRMED'}
            if current.get('engine_rollback_complete'):
                row = backend.inspect(APP)
                require(healthy(row) and backend.verify(APP, 'rollback', row),
                        'PREVIOUS_ENGINE_ROLLBACK_NOT_VERIFIED')
                backend.protected()
                current['phase'] = 'ROLLED_BACK'
                state.put(current)
            else:
                rollback(engine, backend, state)
            closed = disarm()
            return {'result': 'NEWSLETTER_RELEASE_FAILED_ORIGINAL_RESTORED',
                    'rollback_timer_disabled': closed, 'deployed': False}
        except BaseException:
            return {'result': 'RELEASE_REQUIRES_OPERATOR',
                    'rollback_timer_state': 'UNCONFIRMED',
                    'deployed': 'UNCONFIRMED'}


def accept(backend, state):
    current = state.read()
    require(current and current['phase'] == 'AWAITING_ACCEPTANCE',
            'NO_PENDING_WEBSITE_RELEASE')
    require(current['touched'] == [APP] and
            time.time() < current['deadline_epoch'] - 30,
            'ACCEPTANCE_DEADLINE_EXPIRED')
    require(prop(TIMER, 'ActiveState') == 'active', 'ROLLBACK_TIMER_NOT_ACTIVE')
    row = backend.inspect(APP)
    require(row['Image'] == AFTER and healthy(row) and
            backend.verify(APP, 'candidate', row),
            'WEBSITE_CANDIDATE_RUNTIME_NOT_VERIFIED')
    backend.protected()
    current['phase'] = 'ACCEPTED'
    current['accepted_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state.put(current)
    closed = disarm()
    return {'result': 'PASS_NEWSLETTER_WEBSITE_RUNTIME_ACCEPTED' if closed else
            'ACCEPTED_EXPIRY_DISARM_REQUIRES_REVIEW',
            'website_image': AFTER, 'hub_protected': True,
            'protected_container_count': 42, 'rollback_timer_disabled': closed,
            'commercial_launch': 'SEPARATE_GATE', 'deployed': True}


def status(engine, backend, state):
    current = state.read()
    row = backend.inspect(APP, allow_missing=True)
    return {'phase': current['phase'] if current else 'NOT_STARTED',
            'website_image': row['Image'] if row else None,
            'website_healthy': healthy(row),
            'rollback_timer': prop(TIMER, 'ActiveState'),
            'accepted_lead_timer': prop(PREVIOUS_TIMER, 'ActiveState'),
            'manifest_sha256': MANIFEST}


def main():
    p = argparse.ArgumentParser()
    modes = p.add_mutually_exclusive_group(required=True)
    for arg in ('preflight', 'deploy', 'accept', 'expire', 'rollback', 'status'):
        modes.add_argument('--' + arg, action='store_true')
    args = p.parse_args()
    os.umask(0o077)
    lock = os.open(ROOT / 'newsletter-release.lock',
                   os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX if args.expire else
                    fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = State()
        engine, backend, plan, helper = context(state)
        if args.preflight:
            result = preflight(engine, backend, plan, helper, state)
        elif args.deploy:
            result = deploy(engine, backend, plan, helper, state)
        elif args.accept:
            result = accept(backend, state)
        elif args.status:
            result = status(engine, backend, state)
        else:
            current = state.read()
            if current and current['phase'] == 'ACCEPTED' and args.expire:
                result = {'result': 'NOOP_ACCEPTED_NEWSLETTER_RELEASE'}
            elif current and current['phase'] == 'ROLLED_BACK' and args.expire:
                result = {'result': 'NOOP_WEBSITE_ALREADY_RESTORED'}
            else:
                require(current is not None, 'RELEASE_STATE_MISSING')
                if args.expire:
                    require(time.time() >= current['deadline_epoch'] - 3,
                            'EXPIRY_BEFORE_DEADLINE')
                rollback(engine, backend, state)
                closed = disarm()
                result = {'result': 'PASS_NEWSLETTER_ORIGINAL_RESTORED',
                          'rollback_timer_disabled': closed, 'deployed': False}
        print(json.dumps(result, indent=2), flush=True)
        if result.get('result') in ('NEWSLETTER_RELEASE_FAILED_ORIGINAL_RESTORED',
                                    'RELEASE_REQUIRES_OPERATOR',
                                    'ACCEPTED_EXPIRY_DISARM_REQUIRES_REVIEW'):
            raise SystemExit(1)
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        prefix = str(error).split(':', 1)[0]
        print(json.dumps({'result': 'STOP_NEWSLETTER_WEBSITE_SUPERVISOR',
                          'reason': prefix if re.fullmatch('[A-Z][A-Z0-9_]+', prefix)
                          else type(error).__name__}), flush=True)
        raise SystemExit(1)
