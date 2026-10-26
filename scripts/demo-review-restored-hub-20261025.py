#!/usr/bin/env python3
"""Acer archive -> Dell read-only candidate/rollback review. Never loads images.

Reuses the already verified bceb8f08 helper in Downloads. No remote files,
containers, networks, services, application data or prices are changed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shlex
import socket
import subprocess
import tarfile
import zipfile

ARCHIVE_SHA = '5dccf932e8693fecbe0082dd3a78658f97aadb52b251152b9f3df2fdef7e6586'
HELPER_SHA = 'bceb8f08197377ed6be672120a8645c896eb0cb0da64b589d65d66f1df86c938'
EXPECTED = {
    'v79-hub': ('20504c556eea55af7d0f1ef85241582715e95b08fce00386335e41035decd9de', 'c12e54bdb52f8996fae19688d74354d731e7de27'),
    'v79-tiquet-manager': ('6bb9acb1f0c8e8866082882f1cbb3d6cc9823ead559ef10a266618b013f793e1', 'f47bbb65d1c81918017648a0a9b0464e4c167414'),
}
RUNTIME_FINGERPRINTS = {
    'v79-hub': 'b47583c80c1703a970e05650bb74319d61ae93a42e1244a4da574a7834152825',
    'v79-tiquet-manager': '28b64029b1230b4cf19c0a8dca037312a135508a2926deb6f0546f2a71fd2386',
}
INPUT_HASHES = {
    'v79-hub': ['ccb8dd4027159615421c67861c2a4aff59155f2f38b0a71bafe13be6b5f8d5e1'],
    'v79-tiquet-manager': [
        '0d4f42f9d5c2f22bbfcc946a6c0d626d1780d1e6e3970953a2722eb47f6acb72',
        'eba39a0059fa455d18af33c0ec519596cc2238321e3c652c4c0b7c7fefa315f7'],
}
# Generated single-file export of paired-image-release-contract.py is inserted
# below; tests require byte identity with that reviewed source module.
CONTRACT_SOURCE = '#!/usr/bin/env python3\n"""Pure image-only plan validation. No Docker, files, network or deployment.\n\nThe caller must supply fresh inspected identities and fully rendered models.\nThis contract is a preparation gate, never a production authorization.\n"""\nimport copy\nimport hashlib\nimport json\n\nCURRENT = {\n    \'v79-hub\': \'sha256:d722f357206fec938eca691c92ddfe57ece62811f62124f6fbf760258b2b6940\',\n    \'v79-tiquet-manager\': \'sha256:18fc67f82ec3dc33a7b281da79d6ab8e6b17f2983f419833bd008101d5711fc3\',\n}\nCANDIDATE = {\n    \'v79-hub\': \'sha256:20504c556eea55af7d0f1ef85241582715e95b08fce00386335e41035decd9de\',\n    \'v79-tiquet-manager\': \'sha256:6bb9acb1f0c8e8866082882f1cbb3d6cc9823ead559ef10a266618b013f793e1\',\n}\nREVISIONS = {\n    \'v79-hub\': \'c12e54bdb52f8996fae19688d74354d731e7de27\',\n    \'v79-tiquet-manager\': \'f47bbb65d1c81918017648a0a9b0464e4c167414\',\n}\n\n\nclass Refused(ValueError):\n    """Fixed safe diagnostics; never include raw model or secret values."""\n\n\ndef fingerprint(value):\n    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(\',\', \':\')).encode()).hexdigest()\n\n\ndef verify_models(before, candidate, rollback, resolved_baseline):\n    """Verify complete rendered models for one project containing either app.\n\n    Both projects must be checked separately. Other services and all top-level\n    fields must remain identical. Rollback image refs are immutable original IDs.\n    No dollar decoding/reserialization happens here: preserve rendered values.\n    """\n    if not all(isinstance(v, dict) and isinstance(v.get(\'services\'), dict)\n               for v in (before, candidate, rollback)):\n        raise Refused(\'RENDERED_MODELS_REQUIRED\')\n    selected = set(before[\'services\']) & set(CURRENT)\n    if not selected or set(resolved_baseline) != selected:\n        raise Refused(\'BASELINE_RESOLUTION_SCOPE_INVALID\')\n    expected_candidate = copy.deepcopy(before)\n    expected_rollback = copy.deepcopy(before)\n    for service in selected:\n        if resolved_baseline[service] != CURRENT[service]:\n            raise Refused(\'CURRENT_IMAGE_CHANGED\')\n        if not isinstance(before[\'services\'][service].get(\'image\'), str):\n            raise Refused(\'BASELINE_IMAGE_REFERENCE_MISSING\')\n        expected_candidate[\'services\'][service][\'image\'] = CANDIDATE[service]\n        expected_rollback[\'services\'][service][\'image\'] = CURRENT[service]\n    if candidate != expected_candidate:\n        raise Refused(\'CANDIDATE_MUST_CHANGE_ONLY_APPROVED_IMAGES\')\n    if rollback != expected_rollback:\n        raise Refused(\'ROLLBACK_MUST_RESTORE_COMPLETE_ORIGINAL_MODEL\')\n    return {\n        \'mode\': \'PURE_PLAN_CONTRACT_ONLY\',\n        \'services\': sorted(selected),\n        \'candidate_only_image_delta\': True,\n        \'rollback_complete_model_match\': True,\n        \'baseline_model_sha256\': fingerprint(before),\n        \'candidate_model_sha256\': fingerprint(candidate),\n        \'rollback_model_sha256\': fingerprint(rollback),\n        \'deployment_authorized\': False,\n    }\n\n\ndef envmap(values):\n    if not isinstance(values, list) or any(not isinstance(v, str) or \'=\' not in v for v in values):\n        raise Refused(\'IMAGE_ENVIRONMENT_INVALID\')\n    pairs = [v.split(\'=\', 1) for v in values]\n    if len({p[0] for p in pairs}) != len(pairs):\n        raise Refused(\'DUPLICATE_IMAGE_ENVIRONMENT_KEY\')\n    return dict(pairs)\n\n\ndef verify_image_defaults(service_name, rendered_service, old_image, new_image):\n    """Reject hidden process/default-env changes caused by image inheritance.\n\n    Effective process comparison remains distinct from complete Docker runtime\n    parity and Compose codec calibration; callers must establish those separately.\n    """\n    if service_name not in CURRENT:\n        raise Refused(\'UNAPPROVED_SERVICE\')\n    if old_image.get(\'Id\') != CURRENT[service_name] or new_image.get(\'Id\') != CANDIDATE[service_name]:\n        raise Refused(\'INSPECTED_IMAGE_IDENTITY_CHANGED\')\n    before, after = old_image.get(\'Config\'), new_image.get(\'Config\')\n    if not isinstance(before, dict) or not isinstance(after, dict):\n        raise Refused(\'IMAGE_CONFIG_MISSING\')\n    if (after.get(\'Labels\') or {}).get(\'org.opencontainers.image.revision\') != REVISIONS[service_name]:\n        raise Refused(\'CANDIDATE_SOURCE_LABEL_MISMATCH\')\n    # A null value in Compose requests image inheritance. An explicit empty list\n    # is an override and must not accidentally be treated as null.\n    inherited = {\n        \'command\': \'Cmd\', \'entrypoint\': \'Entrypoint\', \'user\': \'User\',\n        \'working_dir\': \'WorkingDir\', \'stop_signal\': \'StopSignal\',\n    }\n    for compose_key, config_key in inherited.items():\n        if rendered_service.get(compose_key) is None and before.get(config_key) != after.get(config_key):\n            raise Refused(\'INHERITED_IMAGE_PROCESS_CHANGED\')\n    for key in (\'Volumes\', \'ExposedPorts\', \'Shell\', \'OnBuild\'):\n        if before.get(key) != after.get(key):\n            raise Refused(\'INHERITED_IMAGE_METADATA_CHANGED\')\n    # Partial healthcheck overrides still inherit the other image fields.\n    if before.get(\'Healthcheck\') != after.get(\'Healthcheck\'):\n        raise Refused(\'IMAGE_HEALTHCHECK_DEFAULT_CHANGED\')\n    configured = rendered_service.get(\'environment\') or {}\n    if not isinstance(configured, dict) or any(v is None for v in configured.values()):\n        raise Refused(\'UNRESOLVED_COMPOSE_ENVIRONMENT\')\n    old_env = envmap(before.get(\'Env\') or [])\n    new_env = envmap(after.get(\'Env\') or [])\n    if {**old_env, **configured} != {**new_env, **configured}:\n        raise Refused(\'INHERITED_IMAGE_ENVIRONMENT_CHANGED\')\n    return {\'image_source_identity\': True, \'inherited_process_and_environment_match\': True,\n            \'deployment_authorized\': False}\n'


class Refused(ValueError):
    pass


def archive_payload(archive, helper):
    if archive.is_symlink() or helper.is_symlink():
        raise Refused('LOCAL_INPUT_SYMLINK')
    before = archive.stat()
    if not archive.is_file() or before.st_size != 203470115:
        raise Refused('ARCHIVE_IDENTITY_MISMATCH')
    with archive.open('rb') as data:
        if hashlib.file_digest(data, 'sha256').hexdigest() != ARCHIVE_SHA:
            raise Refused('ARCHIVE_CHECKSUM_MISMATCH')
    if not helper.is_file() or helper.stat().st_size > 100000:
        raise Refused('EXISTING_HELPER_UNAVAILABLE')
    helper_bytes = helper.read_bytes()
    if hashlib.sha256(helper_bytes).hexdigest() != HELPER_SHA:
        raise Refused('EXISTING_HELPER_CHECKSUM_MISMATCH')
    wanted = {image: (name, revision) for name, (image, revision) in EXPECTED.items()}
    configs = {}
    with zipfile.ZipFile(archive) as z:
        if z.namelist().count('patched-pair.docker.tar.gz') != 1:
            raise Refused('IMAGE_ARCHIVE_MEMBER_INVALID')
        with z.open('patched-pair.docker.tar.gz') as stream:
            with tarfile.open(fileobj=stream, mode='r|gz') as tar:
                for member in tar:
                    image = member.name.removeprefix('blobs/sha256/')
                    if image not in wanted:
                        continue
                    if not member.isfile() or member.size > 1000000:
                        raise Refused('IMAGE_CONFIG_MEMBER_INVALID')
                    raw = tar.extractfile(member).read()
                    if hashlib.sha256(raw).hexdigest() != image:
                        raise Refused('IMAGE_CONFIG_DIGEST_MISMATCH')
                    name, revision = wanted[image]
                    config = json.loads(raw)['config']
                    if config.get('Labels', {}).get('org.opencontainers.image.revision') != revision:
                        raise Refused('IMAGE_SOURCE_IDENTITY_MISMATCH')
                    configs[name] = {'Id': 'sha256:' + image, 'Config': config}
    after = archive.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise Refused('ARCHIVE_CHANGED_DURING_READ')
    if set(configs) != set(EXPECTED):
        raise Refused('IMAGE_CONFIGS_INCOMPLETE')
    return {'helper': helper_bytes.decode(), 'configs': configs}


def check_defaults(contract, ns, name, service, old_image, candidate):
    old_image, candidate = copy.deepcopy(old_image), copy.deepcopy(candidate)
    old, new = old_image['Config'], candidate['Config']
    # Docker inspect and exported OCI configuration encode absent defaults
    # differently. Normalize only semantically equivalent empty values.
    for config in (old, new):
        for field in ('User', 'WorkingDir', 'StopSignal'):
            config[field] = config.get(field) or ''
        for field in ('Volumes', 'ExposedPorts'):
            config[field] = config.get(field) or {}
        config['Healthcheck'] = ns['health'](config.get('Healthcheck'))
    old_env, new_env = contract['envmap'](old.get('Env') or []), contract['envmap'](new.get('Env') or [])
    changes = sorted(key for key in set(old_env) | set(new_env) if old_env.get(key) != new_env.get(key))
    # These two absent keys describe tools shipped by the old Node base image.
    # Their removal is an explicit part of the reviewed no-npm runtime change.
    permitted = {'NODE_VERSION', 'YARN_VERSION'}
    metadata_only = [key for key in changes if key in permitted and key not in new_env]
    for key in metadata_only:
        old_env.pop(key, None)
    old['Env'] = [key + '=' + value for key, value in old_env.items()]
    new['Env'] = [key + '=' + value for key, value in new_env.items()]
    try:
        result = contract['verify_image_defaults'](name, service, old_image, candidate)
    except contract['Refused'] as error:
        raise Refused(str(error)) from error
    result['reviewed_removed_base_metadata_names'] = metadata_only
    return result


def review(payload, ns, render):
    contract = {'__name__': 'nonexecuting_contract'}
    exec(compile(CONTRACT_SOURCE, '<source-pinned-contract>', 'exec'), contract)
    rows = ns['run'](['docker', 'inspect', *ns['PINS']])
    original = {r['Name'].lstrip('/'): r for r in rows}

    def guard(rows_by_name):
        if set(rows_by_name) != set(ns['PINS']):
            raise Refused('CORE_SCOPE_CHANGED')
        for name, row in rows_by_name.items():
            if (row['Image'] != ns['PINS'][name] or not row['State']['Running']
                    or row['State'].get('Health', {}).get('Status') != 'healthy'):
                raise Refused('CORE_IMAGE_OR_HEALTH_CHANGED')

    def runtime_fingerprint(row):
        return ns['digest']({'Config': row['Config'], 'HostConfig': row['HostConfig'],
                            'Mounts': row.get('Mounts'),
                            'Networks': sorted(row.get('NetworkSettings', {}).get('Networks', {}).keys())})

    guard(original)
    report = {'mode': 'READ_ONLY_IMAGE_ONLY_MODEL_REVIEW', 'apps': {},
              'production_mutations': False, 'images_loaded': False,
              'release_decision': 'HOLD', 'remaining_gates': [
                  'full Docker runtime/codec and durable rollback execution',
                  'fresh encrypted release-window checkpoint and custody',
                  'selected-release supervised MFA/browser/provider acceptance',
                  'exact owner-approved production release/window']}
    observed_files = {}
    for name, row in original.items():
        if name not in EXPECTED:
            continue
        if runtime_fingerprint(row) != RUNTIME_FINGERPRINTS[name]:
            raise Refused('ACCEPTED_RUNTIME_CONFIG_CHANGED')
        files = ns['input_files'](row)
        if [f['sha256'] for f in files] != INPUT_HASHES[name]:
            raise Refused('ACCEPTED_ORDERED_COMPOSE_INPUTS_CHANGED')
        observed_files[name] = files
        labels = row['Config']['Labels']
        directory = labels['com.docker.compose.project.working_dir']
        service = labels['com.docker.compose.service']
        if service != name:
            raise Refused('UNEXPECTED_COMPOSE_SERVICE')
        args = ['docker', 'compose', '--project-directory', directory,
                '--project-name', labels['com.docker.compose.project']]
        for item in files:
            args.extend(['-f', item['path']])
        extra, _ = ns['interpolation_context'](row, files)
        values = ns['envmap'](row['Config']['Env'])
        for tier in ('STARTER', 'PRO', 'ENTERPRISE'):
            alias = 'V79_P1_FROZEN_PLAN_PRICE_' + tier
            if name == 'v79-tiquet-manager':
                source = 'PLAN_PRICE_' + tier
                if not values.get(source):
                    raise Refused('FROZEN_PRICE_SOURCE_UNAVAILABLE')
                extra[alias] = values[source]
        before = ns['run']([*args, 'config', '--format', 'json'], cwd=directory, extra_env=extra)
        old_ref = before['services'][service]['image']
        old_image = ns['run'](['docker', 'image', 'inspect', old_ref])[0]
        if old_image['Id'] != ns['PINS'][name]:
            raise Refused('BASELINE_IMAGE_REFERENCE_CHANGED')
        candidate_id = 'sha256:' + EXPECTED[name][0]
        candidate = render(args, directory, extra, {'services': {service: {'image': candidate_id}}})
        rollback = render(args, directory, extra, {'services': {service: {'image': ns['PINS'][name]}}})
        try:
            result = contract['verify_models'](before, candidate, rollback, {service: old_image['Id']})
        except contract['Refused'] as error:
            raise Refused(str(error)) from error
        result['image_defaults'] = check_defaults(contract, ns, name, before['services'][service], old_image, payload['configs'][name])
        result['ordered_compose_input_count'] = len(files)
        report['apps'][name] = result
    after = {r['Name'].lstrip('/'): r for r in ns['run'](['docker', 'inspect', *ns['PINS']])}
    guard(after)
    if any(after[n]['Id'] != original[n]['Id'] for n in original):
        raise Refused('CORE_CONTAINER_IDENTITY_CHANGED_DURING_READ')
    for name in EXPECTED:
        if ns['input_files'](after[name]) != observed_files[name] or runtime_fingerprint(after[name]) != RUNTIME_FINGERPRINTS[name]:
            raise Refused('CONFIGURATION_CHANGED_DURING_READ')
    report['status'] = 'PASS_RENDERED_MODELS_AND_INHERITED_DEFAULTS_ONLY'
    report['core_container_identity_and_health_unchanged'] = True
    return report


def remote_main():
    import os
    import sys
    try:
        if socket.gethostname() != 'v79sl':
            raise Refused('RUN_REMOTE_READ_ON_V79SL_ONLY')
        raw = sys.stdin.buffer.read(200000)
        payload = json.loads(raw)
        if hashlib.sha256(payload['helper'].encode()).hexdigest() != HELPER_SHA:
            raise Refused('EXISTING_HELPER_CHECKSUM_MISMATCH')
        ns = {'__name__': 'readonly_helpers'}
        exec(compile(payload['helper'], '<verified-existing-helper>', 'exec'), ns)

        def render(args, directory, extra, overlay):
            result = subprocess.run([*args, '-f', '-', 'config', '--format', 'json'],
                                    input=json.dumps(overlay).encode(), capture_output=True,
                                    timeout=45, cwd=directory, env={**os.environ, **extra})
            if result.returncode or len(result.stdout) > 16 * 1024**2:
                raise Refused('OVERLAY_RENDER_FAILED_REDACTED')
            return json.loads(result.stdout)

        print(json.dumps(review(payload, ns, render), indent=2))
    except Exception as error:
        helper_stop = locals().get('ns', {}).get('Stop', Refused)
        reason = str(error) if isinstance(error, (Refused, helper_stop)) else 'REVIEW_FAILED_REDACTED'
        print(json.dumps({'status': 'BLOCKED', 'reason': reason, 'production_mutations': False,
                          'images_loaded': False, 'release_decision': 'HOLD'}))
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path.home() / 'Downloads/hardened-pair-candidate.zip')
    parser.add_argument('--helper', type=Path, default=Path.home() / 'Downloads/Vision79_Tiquet_Parity_ReadOnly_bceb8f08.py')
    args = parser.parse_args()
    if socket.gethostname() != 'firelion-Aspire-A315-51':
        raise Refused('RUN_ON_ACER_ONLY')
    payload = archive_payload(args.archive, args.helper)
    code = Path(__file__).read_text() + '\nremote_main()\n'
    # The remote __name__ is deliberately not __main__; the Acer entrypoint
    # cannot run recursively, and the host-guarded remote reader runs once.
    remote = "ns={'__name__':'v79_remote_review'};exec(compile(" + repr(code) + ",'<pinned-review>','exec'),ns)"
    result = subprocess.run(['ssh', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                             'firelion@192.168.100.163', 'python3 -c ' + shlex.quote(remote)],
                            input=json.dumps(payload).encode(), timeout=240)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    try:
        main()
    except Refused as error:
        raise SystemExit('STOP=' + str(error))
