#!/usr/bin/env python3
"""Fresh image-bound attempt; preserve old evidence and reuse unchanged proofs."""
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
import textwrap
import urllib.request

OLD = Path('/home/firelion/v79-lead-release-2pvsb2mo')
NEW = Path('/home/firelion/v79-lead-release-2pvsb2mo-r2')
OLD_MANIFEST = '44c0625680f1dfb306aaa49d51f936a08eb76d67ba1e9c2fcddfd9b6be4f368e'
OLD_SUPERVISOR = 'f3c7b7650de77d8ae94a92a18f551cac0928e43c896dbd62baf347f7f8118a7a'
ADAPTER = 'a1d4842cb0625e1207fb454b5510c05bd2443a245fe7f3143d7be20c660d84e7'
IMAGE = 'sha256:2bf0b35a8b7d71b183b34fa09a08ba7fb1b3c7637448b523c1bd07f8a02fa1fb'
REVISION = '356b09e0cb5ebdda92b5f7d80e01a4d37feacdf0'
BUILD_RECEIPT = OLD / 'website-permission-rebuild-xvvs99g9/receipt.json'
CONTROLLER_URL = ('https://raw.githubusercontent.com/MrFixITslu/V79hub/'
                  '51e1b46f5fc0c84772581a9025b29a4e6746324a/scripts/lead-release-supervisor.py')
CONTROLLER_SHA = 'f116d4961b1b3c2437035b41a8584054c9d93d3dccd835c2fc7785c749697887'
REUSED = (('v79-hub', 'candidate', 'label-diagnostic.json'),
          ('v79-hub', 'rollback', 'v79-hub.rollback.profile-capture.json'),
          ('V79website', 'rollback', 'website-v2.rollback.profile-capture.json'))


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_constants(source, replacements):
    """Only selected top-level assignment values may differ; bodies stay byte-identical."""
    text = source.decode()
    lines = text.splitlines(keepends=True)
    nodes = {n.targets[0].id: n for n in ast.parse(text).body
             if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id in replacements}
    require(set(nodes) == set(replacements), 'BINDING_CONSTANTS_MISSING')
    for name, node in sorted(nodes.items(), key=lambda pair: pair[1].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [name + ' = ' + replacements[name] + '\n']
    result = ''.join(lines).encode()
    # Remove only assignment values to prove no functions, guards or imports changed.
    def shape(data):
        tree = ast.parse(data)
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id in replacements:
                node.value = ast.Constant(value='BOUND_CONSTANT')
        return ast.dump(tree, include_attributes=False)
    require(shape(source) == shape(result), 'BINDING_CHANGED_EXECUTABLE_BODY')
    compile(result, '<bound-release>', 'exec')
    return result


def selected_profile_function(engine):
    tree = ast.parse(textwrap.dedent(inspect.getsource(engine.stopped_profiles)))
    function = tree.body[0]
    require(isinstance(function, ast.FunctionDef) and function.name == 'stopped_profiles', 'PROFILE_SOURCE_CHANGED')
    loops = [n for n in ast.walk(function) if isinstance(n, ast.For)
             and isinstance(n.target, ast.Name) and n.target.id == 'which'
             and isinstance(n.iter, ast.Tuple)
             and [getattr(e, 'value', None) for e in n.iter.elts] == ['candidate', 'rollback']]
    require(len(loops) == 1, 'PROFILE_SELECTOR_NOT_UNIQUE')
    loops[0].body.insert(0, ast.parse('if (name, which) not in selection:\n    continue').body[0])
    function.name = 'selected_profiles'
    function.args.args.append(ast.arg(arg='selection'))
    ast.fix_missing_locations(tree)
    namespace = dict(engine.__dict__)
    exec(compile(tree, '<original-engine-single-profile>', 'exec'), namespace)
    return namespace['selected_profiles'], tree


def verify_reused(engine, helper, oldplan, newplan, name, which, filename):
    prior = json.loads(helper.private(OLD / filename))
    require(prior.get('app') == name and prior.get('which') == which
            and prior.get('engine_message') == 'RUNTIME_MATCHED', 'PASSED_PROFILE_RECEIPT_REQUIRED')
    sealed = oldplan['apps'][name]
    entry = prior['entry']
    pin = sealed[which + '_image']['Id']
    require(pin == newplan['apps'][name][which + '_image']['Id']
            and entry[which + '_sha256'] == sealed[which + '_sha256']
            and prior['after']['Image'] == pin
            and not prior['after']['State'].get('Running')
            and str(prior['after']['State'].get('StartedAt', '0001')).startswith('0001')
            and entry['approved_environment'] == newplan['apps'][name]['approved_environment']
            and entry['image_manifests'] == sealed['image_manifests'], 'PASSED_PROFILE_INPUTS_CHANGED')
    before = copy.deepcopy(prior['before'])
    after = copy.deepcopy(prior['after'])
    before['Config']['Env'] = copy.deepcopy(entry['baseline']['Config']['Env'])
    after['Config']['Labels']['com.docker.compose.image'] = entry['image_manifests'][pin]
    engine.runtime_matches(before, after, entry, which, selinux_enabled=oldplan['selinux_enabled'])


def prepare():
    os.umask(0o077)
    require(OLD.is_dir() and not OLD.is_symlink() and OLD.stat().st_uid == os.geteuid()
            and OLD.stat().st_mode & 0o077 == 0, 'PRIVATE_OLD_RELEASE_REQUIRED')
    require(not NEW.exists() and not NEW.is_symlink(), 'NEW_ATTEMPT_ALREADY_EXISTS_NO_REPLAY')
    lock = os.open(OLD / 'binding.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_source = (OLD / 'lead-release-supervisor.py').read_bytes()
        require(sha(old_source) == OLD_SUPERVISOR, 'PREVIOUS_CONTROLLER_CHANGED')
        previous = load('previous_lead_supervisor', OLD / 'lead-release-supervisor.py')
        oldstate = previous.State(OLD)
        require(oldstate.read().get('phase') == 'ROLLED_BACK'
                and oldstate.read().get('engine_rollback_complete') is True
                and not oldstate.read().get('rollback_failed'), 'CLEAN_PREVIOUS_ROLLBACK_REQUIRED')
        oldengine, oldbackend, oldplan, helper = previous.load_context(oldstate)
        require(sha(helper.private(OLD / 'transaction.json')) == OLD_MANIFEST, 'PREVIOUS_MANIFEST_CHANGED')
        require(previous.prop(previous.TIMER, 'ActiveState') == 'inactive', 'PREVIOUS_TIMER_NOT_INACTIVE')
        oldbackend.check_files()
        oldbackend.protected()
        current = {}
        for name in previous.ORDER:
            oldbackend.healthy(name, 'rollback')  # full original validator; no container mutations
            current[name] = oldbackend.inspect(name)
        receipt = json.loads(helper.private(BUILD_RECEIPT))
        require(receipt.get('result') == 'PASS_WEBSITE_REBUILT_AND_ISOLATED_STARTUP'
                and receipt.get('website', {}).get('image') == IMAGE
                and receipt['website'].get('commit') == REVISION
                and receipt.get('live_identities_unchanged') is True
                and receipt.get('deployed') is False, 'REPAIRED_IMAGE_RECEIPT_REQUIRED')
        isolated = receipt['isolated_startup']
        require(isolated.get('image') == IMAGE and isolated.get('running') is True
                and isolated.get('health') == 'healthy' and isolated.get('probe_removed') is True
                and isolated.get('originals_unchanged') is True, 'REPAIRED_STARTUP_PROOF_REQUIRED')
        images, image_manifest = helper.image_metadata(IMAGE)
        require((images['Config'].get('Labels') or {}).get('org.opencontainers.image.revision') == REVISION,
                'REPAIRED_SOURCE_CHANGED')
        old_inputs_raw = helper.private(OLD / 'configuration-inputs.json')
        require(sha(old_inputs_raw) == helper.INPUT_SHA, 'PREVIOUS_INPUTS_CHANGED')
        inputs = json.loads(old_inputs_raw)
        # Preserve all credential/org values, models, protected baselines and app settings.
        for name, row in current.items():
            inputs['baseline'][name] = row
        web = inputs['prepared']['V79website']
        web['candidate']['services'][web['service']]['image'] = IMAGE
        input_raw = helper.canonical(inputs)
        input_sha = sha(input_raw)
        with urllib.request.urlopen(CONTROLLER_URL, timeout=30) as response:
            controller_template = response.read(1_000_000)
        require(sha(controller_template) == CONTROLLER_SHA, 'CONTROLLER_TEMPLATE_CHANGED')
        adapter_source = helper.private(OLD / 'lead-release-compat.py')
        require(sha(adapter_source) == ADAPTER, 'PREVIOUS_ADAPTER_CHANGED')
        pins = copy.deepcopy(helper.PINS)
        pins['V79website'] = (REVISION, IMAGE)
        adapter_bound = replace_constants(adapter_source, {
            'ROOT': 'Path(' + repr(str(NEW)) + ')', 'INPUT_SHA': repr(input_sha), 'PINS': repr(pins)})
        adapter_sha = sha(adapter_bound)
        NEW.mkdir(mode=0o700)
        helper.write(NEW / 'binding.lock', b'')
        helper.write(NEW / 'configuration-inputs.json', input_raw)
        helper.write(NEW / 'lead-release-compat.py', adapter_bound)
        for name, pin in helper.MODULES.items():
            data = helper.private(OLD / name)
            require(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == pin,
                    'ENGINE_SOURCE_CHANGED')
            helper.write(NEW / name, data)
        newengine = load('permission_r2_pair_engine', NEW / 'paired-compose-transaction.py')
        plan = copy.deepcopy(oldplan)
        for name, entry in plan['apps'].items():
            entry.pop('_replaced_id', None)
            entry['baseline'] = current[name]
            if name == 'V79website':
                entry['candidate_image'] = images
                entry['image_manifests'] = {
                    entry['rollback_image']['Id']: entry['image_manifests'][entry['rollback_image']['Id']],
                    IMAGE: image_manifest}
            for which in ('candidate', 'rollback'):
                model = copy.deepcopy(inputs['prepared'][name][which])
                oldmodel = json.loads(helper.private(Path(oldplan['apps'][name][which + '_file'])))
                expected = copy.deepcopy(oldmodel)
                if name == 'V79website' and which == 'candidate':
                    expected['services'][entry['service']]['image'] = IMAGE
                require(model == expected, 'UNREVIEWED_MODEL_CHANGE')
                target = NEW / (name + '.' + which + '.json')
                data = helper.canonical(model)
                helper.write(target, data)
                entry[which + '_file'] = str(target)
                entry[which + '_sha256'] = sha(data)
                if which == 'candidate':
                    entry['model'] = model
        # Three unchanged image/model codecs are reused from their actual passed captures.
        for name, which, filename in REUSED:
            verify_reused(oldengine, helper, oldplan, plan, name, which, filename)
        manifest = newengine.seal_plan(NEW, plan)
        backend = newengine.ComposeBackend(NEW, plan)
        helper.protect_core_health(backend)
        backend.protected()
        backend.check_files()
        for name in plan['apps']:
            backend.eligible(name)
        original = newengine.runtime_matches
        capture = []
        def report(before, after, entry, which, **kwargs):
            require(entry['release_name'] == 'V79website' and which == 'candidate', 'PASSED_PROFILE_MUST_NOT_RECREATE')
            original(before, after, entry, which, **kwargs)
            helper.write(NEW / 'repaired-website.profile-capture.json', helper.canonical({
                'app': 'V79website', 'which': which, 'engine_message': 'RUNTIME_MATCHED',
                'before': before, 'after': after, 'entry': entry}))
            capture.append('V79website/candidate')
            print(json.dumps({'profile': 'V79website/candidate', 'reason': 'RUNTIME_MATCHED'}), flush=True)
            return True
        newengine.runtime_matches = report
        helper.install_compat(newengine)
        selected, _ = selected_profile_function(newengine)
        print(json.dumps({'reused_profiles': 3, 'new_profiles': 1, 'deployed': False}), flush=True)
        with helper.heartbeat(NEW):
            proof = selected(backend, frozenset((('V79website', 'candidate'),)))
        require(proof.get('profiles_verified') == 1 and capture == ['V79website/candidate'], 'NEW_PROFILE_NOT_VERIFIED')
        require(helper.timer_states() == plan['workforce_timers'], 'WORKFORCE_TIMER_STATE_CHANGED')
        for name, row in current.items():
            require(newengine.protected_fingerprint(backend.inspect(name)) == newengine.protected_fingerprint(row),
                    'TARGET_CHANGED_DURING_PREPARATION')
        backend.protected()
        controller_bound = replace_constants(controller_template, {
            'ROOT': 'Path(' + repr(str(NEW)) + ')', 'MANIFEST': repr(manifest),
            'ADAPTER_SHA': repr(adapter_sha),
            'TIMER': repr('vision79-lead-pair-permissions-r2-expiry.timer'),
            'SERVICE': repr('vision79-lead-pair-permissions-r2-expiry.service')})
        helper.write(NEW / 'lead-release-supervisor.py', controller_bound)
        binding = {'result': 'PASS_BOUND_ENGINE_AND_NEW_CONFIGURATION_PROFILES', 'engine_bound': True,
                   'manifest_sha256': manifest, 'validation_adapter_sha256': adapter_sha,
                   'profiles_verified': 4, 'new_profiles_verified': 1, 'reused_profiles': 3,
                   'temporary_cleanup_verified': True, 'workforce_timers_preserved': True,
                   'deployed': False}
        helper.write(NEW / 'binding-result.json', helper.canonical(binding))
        # Exercise the installed loader and its exact digests without arming or deploying.
        installed = load('permission_r2_supervisor', NEW / 'lead-release-supervisor.py')
        _, newbackend, newplan, _ = installed.load_context(installed.State(NEW))
        newbackend.protected()
        for name in newplan['apps']:
            newbackend.healthy(name, 'rollback')
        result = {'result': 'PASS_REPAIRED_IMAGE_RELEASE_PREPARED', 'directory': str(NEW),
                  'manifest_sha256': manifest, 'inputs_sha256': input_sha,
                  'controller_sha256': sha(controller_bound), 'validation_adapter_sha256': adapter_sha,
                  'website_image': IMAGE, 'hub_image_reused': True, 'new_profiles_verified': 1,
                  'reused_profiles': 3, 'credentials_reused': True, 'protected_container_count': len(plan['protected']),
                  'originals_unchanged': True, 'workforce_timers_preserved': True,
                  'previous_release_preserved': True, 'rollback_timer_armed': False, 'deployed': False}
        helper.write(NEW / 'preparation-result.json', helper.canonical(result))
        return result
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        print(json.dumps(prepare(), indent=2))
    except Exception as error:
        code = str(error).split(':', 1)[0]
        print(json.dumps({'result': 'STOP_REPAIRED_RELEASE_PREPARATION',
                          'reason': code if re.fullmatch('[A-Z][A-Z0-9_]+', code) else type(error).__name__,
                          'directory': str(NEW), 'deployed': False}))
        raise SystemExit(1)
