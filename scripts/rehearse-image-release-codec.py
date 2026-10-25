#!/usr/bin/env python3
"""Stopped synthetic Docker probes; no application startup, data or image load.

Creates four owned containers, one empty named volume and a private temporary
directory, then removes only those verified resources. Uses the existing Tiquet
rollback image on Dell; CI uses Alpine. This is not an application rollback.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import tempfile
import uuid

MOUNT_CONTRACT_SOURCE = '#!/usr/bin/env python3\n"""Compare Docker storage semantics and every remaining HostConfig field.\n\nPure validation only. Recognized Binds/Mounts encodings may differ, but source,\naccess, propagation, creation/copy behavior and every supported option may not.\nUnsupported options reject; no runtime mutation or release authorization exists.\n"""\nimport copy\nimport posixpath\n\n\nclass Refused(ValueError):\n    pass\n\n\nPROPAGATIONS = {\'private\', \'rprivate\', \'shared\', \'rshared\', \'slave\', \'rslave\'}\nCONSISTENCIES = {\'consistent\', \'cached\', \'delegated\', \'default\'}\nRUNTIME_KEYS = {\'Type\', \'Name\', \'Source\', \'Destination\', \'Driver\', \'Mode\', \'RW\', \'Propagation\'}\nMOUNT_KEYS = {\'Type\', \'Source\', \'Target\', \'ReadOnly\', \'Consistency\', \'BindOptions\', \'VolumeOptions\'}\nBIND_KEYS = {\'Propagation\', \'NonRecursive\', \'CreateMountpoint\', \'ReadOnlyNonRecursive\', \'ReadOnlyForceRecursive\'}\nVOLUME_KEYS = {\'NoCopy\', \'Labels\', \'Subpath\', \'DriverConfig\'}\n\n\ndef absolute(value):\n    if not isinstance(value, str) or not value.startswith(\'/\') or posixpath.normpath(value) != value:\n        raise Refused(\'NONCANONICAL_MOUNT_PATH\')\n    if any(ord(char) < 32 for char in value) or \':\' in value:\n        raise Refused(\'UNSUPPORTED_MOUNT_PATH\')\n    return value\n\n\ndef consistency(value):\n    if value in (None, \'\', \'default\'):\n        return \'consistent\'\n    if value not in CONSISTENCIES:\n        raise Refused(\'UNSUPPORTED_MOUNT_CONSISTENCY\')\n    return value\n\n\ndef boolean(value):\n    if not isinstance(value, bool):\n        raise Refused(\'INVALID_MOUNT_BOOLEAN\')\n    return value\n\n\ndef canonical_host_storage(row):\n    host = copy.deepcopy(row.get(\'HostConfig\') or {})\n    actual = {}\n    for mount in row.get(\'Mounts\') or []:\n        if set(mount) - RUNTIME_KEYS or mount.get(\'Type\') not in (\'bind\', \'volume\'):\n            raise Refused(\'UNSUPPORTED_RUNTIME_MOUNT_FIELDS\')\n        target = absolute(mount.get(\'Destination\'))\n        if target in actual:\n            raise Refused(\'DUPLICATE_RUNTIME_MOUNT_TARGET\')\n        source = mount.get(\'Name\') if mount[\'Type\'] == \'volume\' else absolute(mount.get(\'Source\'))\n        if not isinstance(source, str) or not source:\n            raise Refused(\'MOUNT_SOURCE_IDENTITY_MISSING\')\n        mode = set(filter(None, mount.get(\'Mode\', \'\').split(\',\')))\n        if mode - ({\'ro\', \'rw\', \'nocopy\', \'z\', \'Z\'} | PROPAGATIONS | CONSISTENCIES):\n            raise Refused(\'UNSUPPORTED_RUNTIME_MOUNT_MODE\')\n        actual[target] = {\n            \'type\': mount[\'Type\'], \'source\': source,\n            \'resolved_source\': absolute(mount.get(\'Source\')),\n            \'driver\': mount.get(\'Driver\') or \'\',\n            \'read_only\': not boolean(mount.get(\'RW\')),\n            \'propagation\': (mount.get(\'Propagation\') or \'rprivate\') if mount[\'Type\'] == \'bind\' else (mount.get(\'Propagation\') or \'\'),\n            \'selinux\': sorted(mode & {\'z\', \'Z\'}),\n        }\n    declarations = {}\n\n    def add(kind, source, target, read_only, options):\n        if target not in actual or target in declarations:\n            raise Refused(\'MOUNT_DECLARATION_TARGET_MISMATCH\')\n        runtime = actual[target]\n        if kind != runtime[\'type\'] or source != runtime[\'source\'] or read_only != runtime[\'read_only\']:\n            raise Refused(\'MOUNT_DECLARATION_RUNTIME_MISMATCH\')\n        if kind == \'bind\' and options[\'propagation\'] != runtime[\'propagation\']:\n            raise Refused(\'BIND_PROPAGATION_RUNTIME_MISMATCH\')\n        if options.get(\'selinux\', []) != runtime[\'selinux\']:\n            raise Refused(\'SELINUX_RUNTIME_MISMATCH\')\n        declarations[target] = {\'runtime\': runtime, \'options\': options}\n\n    binds = host.pop(\'Binds\', None) or []\n    typed = host.pop(\'Mounts\', None) or []\n    if not isinstance(binds, list) or not isinstance(typed, list):\n        raise Refused(\'MOUNT_DECLARATIONS_INVALID\')\n    for bind in binds:\n        if not isinstance(bind, str) or len(bind.split(\':\')) not in (2, 3):\n            raise Refused(\'UNSUPPORTED_BIND_ENCODING\')\n        parts = bind.split(\':\')\n        source, target = parts[:2]\n        target = absolute(target)\n        flags = parts[2].split(\',\') if len(parts) == 3 else []\n        if len(flags) != len(set(flags)) or set(flags) - ({\'ro\', \'rw\', \'nocopy\', \'z\', \'Z\'} | PROPAGATIONS | CONSISTENCIES):\n            raise Refused(\'UNSUPPORTED_BIND_MODE\')\n        flags = set(flags)\n        if {\'ro\', \'rw\'} <= flags or len(flags & PROPAGATIONS) > 1 or len(flags & CONSISTENCIES) > 1 or {\'z\', \'Z\'} <= flags:\n            raise Refused(\'CONTRADICTORY_BIND_MODE\')\n        if target not in actual:\n            raise Refused(\'MOUNT_DECLARATION_TARGET_MISMATCH\')\n        kind = actual[target][\'type\']\n        common = {\'consistency\': consistency(next(iter(flags & CONSISTENCIES), \'\')),\n                  \'selinux\': sorted(flags & {\'z\', \'Z\'})}\n        if kind == \'bind\':\n            absolute(source)\n            if \'nocopy\' in flags:\n                raise Refused(\'INVALID_BIND_NOCOPY\')\n            options = {**common, \'propagation\': next(iter(flags & PROPAGATIONS), \'rprivate\'),\n                       \'create_mountpoint\': True, \'non_recursive\': False,\n                       \'read_only_non_recursive\': False, \'read_only_force_recursive\': False}\n        else:\n            if flags & (PROPAGATIONS | {\'z\', \'Z\'}):\n                raise Refused(\'UNSUPPORTED_VOLUME_BIND_FLAGS\')\n            options = {**common, \'no_copy\': \'nocopy\' in flags, \'subpath\': \'\',\n                       \'driver\': actual[target][\'driver\'], \'driver_options\': {}, \'labels\': {}}\n        add(kind, source, target, \'ro\' in flags, options)\n    for mount in typed:\n        if not isinstance(mount, dict) or set(mount) - MOUNT_KEYS:\n            raise Refused(\'UNSUPPORTED_TYPED_MOUNT_FIELDS\')\n        kind, source, target = mount.get(\'Type\'), mount.get(\'Source\'), absolute(mount.get(\'Target\'))\n        read_only = boolean(mount.get(\'ReadOnly\', False))\n        common = {\'consistency\': consistency(mount.get(\'Consistency\')), \'selinux\': []}\n        if kind == \'bind\':\n            absolute(source)\n            opts = mount.get(\'BindOptions\') or {}\n            if set(opts) - BIND_KEYS or mount.get(\'VolumeOptions\'):\n                raise Refused(\'UNSUPPORTED_TYPED_BIND_OPTIONS\')\n            propagation = opts.get(\'Propagation\') or \'rprivate\'\n            if propagation not in PROPAGATIONS:\n                raise Refused(\'UNSUPPORTED_BIND_PROPAGATION\')\n            options = {**common, \'propagation\': propagation,\n                       \'create_mountpoint\': boolean(opts.get(\'CreateMountpoint\', False)),\n                       \'non_recursive\': boolean(opts.get(\'NonRecursive\', False)),\n                       \'read_only_non_recursive\': boolean(opts.get(\'ReadOnlyNonRecursive\', False)),\n                       \'read_only_force_recursive\': boolean(opts.get(\'ReadOnlyForceRecursive\', False))}\n        elif kind == \'volume\':\n            opts = mount.get(\'VolumeOptions\') or {}\n            if set(opts) - VOLUME_KEYS or mount.get(\'BindOptions\') or target not in actual:\n                raise Refused(\'UNSUPPORTED_TYPED_VOLUME_OPTIONS\')\n            driver = opts.get(\'DriverConfig\') or {}\n            if set(driver) - {\'Name\', \'Options\'}:\n                raise Refused(\'UNSUPPORTED_VOLUME_DRIVER_FIELDS\')\n            options = {**common, \'no_copy\': boolean(opts.get(\'NoCopy\', False)),\n                       \'subpath\': opts.get(\'Subpath\') or \'\', \'labels\': opts.get(\'Labels\') or {},\n                       \'driver\': driver.get(\'Name\') or actual[target][\'driver\'],\n                       \'driver_options\': driver.get(\'Options\') or {}}\n        else:\n            raise Refused(\'UNSUPPORTED_TYPED_MOUNT_TYPE\')\n        add(kind, source, target, read_only, options)\n    if set(declarations) != set(actual):\n        raise Refused(\'UNACCOUNTED_RUNTIME_MOUNT\')\n    # Every field outside the two encoding alternatives stays in the comparison.\n    return {\'host_config\': host, \'mount_contract\': declarations}\n\n\ndef verify_host_storage(before, after):\n    if canonical_host_storage(before) != canonical_host_storage(after):\n        raise Refused(\'HOST_CONFIGURATION_OR_STORAGE_SEMANTICS_CHANGED\')\n    return {\'host_and_storage_semantics_match\': True, \'deployment_authorized\': False}\n'
PINS = {
    'v79-hub': 'sha256:d722f357206fec938eca691c92ddfe57ece62811f62124f6fbf760258b2b6940',
    'v79-tiquet-manager': 'sha256:18fc67f82ec3dc33a7b281da79d6ab8e6b17f2983f419833bd008101d5711fc3',
    'v79-business-agent': 'sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b',
    'v79-hub-postgres': 'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24',
    'tiquet-postgres': 'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685',
}
FIXTURE = {
    'V79_CODEC_STARTER': '$fixture-start ${never_expand}',
    'V79_CODEC_PRO': '$$fixture-pro $$$x',
    'V79_CODEC_ENTERPRISE': 'line one\nline two $fixture-end',
}


class Refused(ValueError):
    pass


def run(args, *, cwd=None, env=None, input=None, check=True):
    p = subprocess.run(['docker', *args], cwd=cwd, env=env, input=input,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if len(p.stdout) > 16 * 1024**2 or len(p.stderr) > 1024**2:
        raise Refused('COMMAND_OUTPUT_LIMIT')
    if check and p.returncode:
        raise Refused('DOCKER_COMMAND_FAILED_REDACTED')
    return p


def read_context(path, checksum):
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077 or meta.st_uid != os.getuid() or meta.st_size > 10000:
        raise Refused('PRIVATE_CONTEXT_PERMISSIONS_INVALID')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise Refused('PRIVATE_CONTEXT_HASH_CHANGED')
    values = json.loads(raw)
    if set(values) != set(FIXTURE) or any(not isinstance(v, str) for v in values.values()):
        raise Refused('PRIVATE_CONTEXT_SCOPE_CHANGED')
    return values


def prices(context):
    return {'PLAN_PRICE_' + tier: context['V79_CODEC_' + tier] for tier in ('STARTER', 'PRO', 'ENTERPRISE')}


def codec_mode(rendered, expected):
    possibilities = []
    if rendered == expected:
        possibilities.append('literal')
    if {k: v.replace('$$', '$') for k, v in rendered.items()} == expected:
        possibilities.append('doubled')
    if len(possibilities) != 1:
        raise Refused('COMPOSE_CODEC_AMBIGUOUS_OR_CHANGED')
    return possibilities[0]


def validate_probe(row, image, nonce):
    config, host = row.get('Config') or {}, row.get('HostConfig') or {}
    if ((config.get('Labels') or {}).get('v79.codec.proof') != nonce or row.get('Image') != image
            or row.get('State', {}).get('Running') or row.get('State', {}).get('StartedAt') not in (None, '', '0001-01-01T00:00:00Z', '0001-01-01T00:00:00.000000000Z')
            or host.get('NetworkMode') != 'none' or not host.get('ReadonlyRootfs')
            or config.get('Entrypoint') != ['/bin/true'] or config.get('Cmd') != ['__v79_probe_never_started__']
            or host.get('Privileged') or host.get('PortBindings') or host.get('PublishAllPorts')):
        raise Refused('SYNTHETIC_PROBE_ISOLATION_MISMATCH')
    if set(m['Destination'] for m in row.get('Mounts') or []) != {'/proof', '/data'}:
        raise Refused('SYNTHETIC_PROBE_MOUNT_SCOPE_CHANGED')


def rehearse(image, *, directory=None):
    ns = {'__name__': 'mount_contract'}
    exec(compile(MOUNT_CONTRACT_SOURCE, '<pinned-mount-contract>', 'exec'), ns)
    nonce = uuid.uuid4().hex
    stem = 'v79-codec-' + nonce
    names = [stem + '-' + phase for phase in ('legacy', 'typed', 'candidate', 'rollback')]
    volume = stem + '-volume'
    success = False
    root = Path(tempfile.mkdtemp(prefix='v79-codec-proof-', dir=directory))
    rows = []
    result = {'application_processes_started': False, 'probe_containers_started': False,
              'application_images_loaded': False, 'application_data_accessed': False,
              'live_services_changed': False, 'application_rollback_rehearsed': False,
              'release_decision': 'HOLD'}
    try:
        root.chmod(0o700)
        context = root / 'frozen-context.json'
        raw = json.dumps(FIXTURE, sort_keys=True).encode()
        with context.open('xb') as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        checksum = hashlib.sha256(raw).hexdigest()
        (root / 'proof').mkdir()
        (root / 'proof/sentinel').write_text('synthetic-no-production-data')
        sentinel_sha = hashlib.sha256((root / 'proof/sentinel').read_bytes()).hexdigest()
        meta = json.loads(run(['image', 'inspect', image]).stdout)[0]
        if meta['Id'] != image or meta['Config'].get('Volumes'):
            raise Refused('PROBE_IMAGE_IDENTITY_OR_IMPLICIT_VOLUMES_INVALID')
        run(['volume', 'create', '--label', 'v79.codec.proof=' + nonce, volume])
        args = ['create', '--name', names[0], '--label', 'v79.codec.proof=' + nonce,
                '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges:true', '--user', '1000:1000',
                '--pids-limit', '32', '--memory', '67108864', '--hostname', 'v79-codec-proof',
                '--entrypoint', '/bin/true']
        for key, value in prices(read_context(context, checksum)).items():
            args += ['--env', key + '=' + value]
        run([*args, '-v', str(root / 'proof') + ':/proof:ro,rprivate', '-v', volume + ':/data:rw,nocopy', image, '__v79_probe_never_started__'])
        row = json.loads(run(['inspect', names[0]]).stdout)[0]
        validate_probe(row, image, nonce)
        rows.append(row)
        typed_args = list(args)
        typed_args[typed_args.index('--name') + 1] = names[1]
        run([*typed_args, '--mount', 'type=bind,source=' + str(root / 'proof') + ',target=/proof,readonly,bind-propagation=rprivate,bind-create-src',
             '--mount', 'type=volume,source=' + volume + ',target=/data,volume-nocopy', image, '__v79_probe_never_started__'])
        typed_row = json.loads(run(['inspect', names[1]]).stdout)[0]
        validate_probe(typed_row, image, nonce)
        if not rows[0]['HostConfig'].get('Binds') or not typed_row['HostConfig'].get('Mounts'):
            raise Refused('BOTH_DOCKER_MOUNT_ENCODINGS_NOT_EXERCISED')
        ns['verify_host_storage'](rows[0], typed_row)
        # Each phase reconstructs context from the sealed file, never from a
        # running app or another probe. All source values above are synthetic.
        modes = []
        for phase, name in zip(('candidate', 'rollback'), names[2:]):
            saved = read_context(context, checksum)
            expected = prices(saved)
            spec = {'services': {'probe': {
                'image': image, 'container_name': name, 'network_mode': 'none',
                'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
                'user': '1000:1000', 'pids_limit': 32, 'mem_limit': 67108864,
                'hostname': 'v79-codec-proof', 'entrypoint': ['/bin/true'],
                'command': ['__v79_probe_never_started__'], 'labels': {'v79.codec.proof': nonce},
                'environment': {'PLAN_PRICE_' + tier: '${V79_CODEC_' + tier + ':?required}' for tier in ('STARTER', 'PRO', 'ENTERPRISE')},
                'volumes': [
                    {'type': 'bind', 'source': str(root / 'proof'), 'target': '/proof', 'read_only': True,
                     'bind': {'create_host_path': True, 'propagation': 'rprivate'}},
                    {'type': 'volume', 'source': 'proof', 'target': '/data', 'volume': {'nocopy': True}}]}},
                'volumes': {'proof': {'external': True, 'name': volume}}}
            path = root / (phase + '.json')
            with path.open('x') as f:
                os.fchmod(f.fileno(), 0o600)
                json.dump(spec, f)
            command = ['compose', '--project-directory', str(root), '--project-name', stem + '-' + phase, '-f', str(path)]
            environment = {**os.environ, **saved}
            model = json.loads(run([*command, 'config', '--format', 'json'], env=environment).stdout)
            modes.append(codec_mode(model['services']['probe']['environment'], expected))
            run([*command, 'create', '--no-build', '--pull', 'never', '--no-deps', 'probe'], env=environment)
            row = json.loads(run(['inspect', name]).stdout)[0]
            validate_probe(row, image, nonce)
            env = dict(v.split('=', 1) for v in row['Config']['Env'])
            if any(env.get(k) != v for k, v in expected.items()):
                raise Refused('ACTUAL_CREATED_CONTAINER_PRICE_CODEC_MISMATCH')
            ns['verify_host_storage'](rows[0], row)
            rows.append(row)
        if len(set(modes)) != 1 or hashlib.sha256((root / 'proof/sentinel').read_bytes()).hexdigest() != sentinel_sha:
            raise Refused('CODEC_OR_SYNTHETIC_SENTINEL_CHANGED')
        result.update({'status': 'PASS_STOPPED_SYNTHETIC_CODEC_AND_STORAGE_ONLY',
                       'compose_output_codec': modes[0], 'candidate_and_rollback_actual_env_match': True,
                       'host_and_storage_semantics_match': True, 'sealed_context_reused_without_running_app': True,
                       'probe_container_count': 4, 'legacy_and_typed_mount_encodings_verified': True})
        success = True
    finally:
        cleanup_errors = []
        for name in names:
            found = run(['inspect', name], check=False)
            if found.returncode:
                if b'no such' not in found.stderr.lower():
                    cleanup_errors.append('PROBE_LOOKUP_UNCERTAIN')
                continue
            row = json.loads(found.stdout)[0]
            try:
                validate_probe(row, image, nonce)
                run(['rm', row['Id']])  # no force, no volume removal; exact owned stopped ID
                absent = run(['inspect', row['Id']], check=False)
                if absent.returncode == 0 or b'no such' not in absent.stderr.lower():
                    raise Refused('PROBE_ABSENCE_UNVERIFIED')
            except Exception:
                cleanup_errors.append('OWNED_PROBE_CLEANUP_UNVERIFIED')
        try:
            found_volume = run(['volume', 'inspect', volume], check=False)
            if found_volume.returncode == 0:
                volume_row = json.loads(found_volume.stdout)[0]
                if volume_row.get('Name') != volume or volume_row.get('Labels', {}).get('v79.codec.proof') != nonce:
                    raise Refused('OWNED_VOLUME_IDENTITY_CHANGED')
                run(['volume', 'rm', volume])
                absent = run(['volume', 'inspect', volume], check=False)
                if absent.returncode == 0 or b'no such' not in absent.stderr.lower():
                    raise Refused('OWNED_VOLUME_ABSENCE_UNVERIFIED')
            elif b'no such' not in found_volume.stderr.lower():
                raise Refused('OWNED_VOLUME_LOOKUP_UNCERTAIN')
        except Exception:
            cleanup_errors.append('OWNED_VOLUME_CLEANUP_UNVERIFIED')
        # Only this function's fresh private directory is removed.
        shutil.rmtree(root)
        result['temporary_resource_cleanup_verified'] = not cleanup_errors
        if cleanup_errors:
            raise Refused('SYNTHETIC_CLEANUP_UNVERIFIED:' + stem)
    if not success:
        raise Refused('SYNTHETIC_REHEARSAL_INCOMPLETE')
    return result


def core_snapshot():
    rows = json.loads(run(['inspect', *PINS]).stdout)
    by_name = {r['Name'].lstrip('/'): r for r in rows}
    if set(by_name) != set(PINS):
        raise Refused('CORE_BASELINE_SCOPE_CHANGED')
    for name, row in by_name.items():
        if row['Image'] != PINS[name] or not row['State']['Running'] or row['State'].get('Health', {}).get('Status') != 'healthy':
            raise Refused('CORE_BASELINE_IDENTITY_OR_HEALTH_CHANGED')
    return {name: row['Id'] for name, row in by_name.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated-codec', action='store_true')
    parser.add_argument('--ci', action='store_true')
    args = parser.parse_args()
    if args.run_isolated_codec and not args.ci and socket.gethostname() == 'v79sl':
        memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(memory['MemAvailable'].split()[0]) < 512 * 1024 or shutil.disk_usage(Path.home()).free < 1024**3:
            raise Refused('PROBE_RESOURCE_HEADROOM_UNAVAILABLE')
        before = core_snapshot()
        try:
            result = rehearse(PINS['v79-tiquet-manager'], directory=Path.home())
        finally:
            if core_snapshot() != before:
                raise Refused('CORE_IDENTITY_CHANGED_DURING_SYNTHETIC_CHECK')
        result['core_container_identity_and_health_unchanged'] = True
    elif args.ci and not args.run_isolated_codec and os.environ.get('GITHUB_ACTIONS') == 'true' and socket.gethostname() != 'v79sl':
        run(['pull', 'alpine:3.24'])
        image = json.loads(run(['image', 'inspect', 'alpine:3.24']).stdout)[0]['Id']
        result = rehearse(image)
    else:
        raise Refused('EXPLICIT_ISOLATED_MODE_AND_HOST_GUARDS_REQUIRED')
    result['docker_version'] = run(['version', '--format', '{{.Server.Version}}']).stdout.decode().strip()
    result['compose_version'] = run(['compose', 'version', '--short']).stdout.decode().strip()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error) if isinstance(error, Refused) else 'SYNTHETIC_REHEARSAL_FAILED_REDACTED',
                          'release_decision': 'HOLD', 'application_rollback_rehearsed': False}))
        raise SystemExit(2)
