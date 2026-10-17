#!/usr/bin/env python3
"""Owner-authorized Hub/Tiquet image rollout. Run on Acer; remote work survives SSH loss.
Private runtime/config data is never logged. Checkpoints are encrypted to the R1 key.
Image rollback is automatic; database/file restore is deliberately never automatic.
"""
import argparse
import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

HOST = 'firelion@v79sl'
RECIPIENT = '484CF39CE37A02884497AD9C41A17102D2842ECE'
SOURCES = {'v79-hub': ('V79hub', 'c2681be42ad0dd68dbabebabb206273a9ea6c817'),
           'v79-tiquet-manager': ('V79Tiquet', '7da53ebb71530366168bd72a7efd52b57d34a23c')}
PINNED = {'v79-hub': {'container': 'v79-hub', 'compose_project': 'v79-hub', 'compose_service': 'v79-hub', 'image_id': 'sha256:d0dfba263dbfec8a08e6c46995c2172daf234206fe8d0f6484bb98b938cd3c65', 'compose_inputs': [{'path': '/opt/v79/hub/docker-compose.yml', 'sha256': '186175ec20d10f817a9468b305fed86a6b0b4ae7cd380659e574df95ef688261'}, {'path': '/opt/v79/hub/releases/wipay-return-585f701.pinned.yml', 'sha256': '8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74'}, {'path': '/home/firelion/.v79-g12-pinned-cutover-49318a690822/candidate-v4.yml', 'sha256': 'fddb7d2a6934dfa65a5ce05358ca71a6769eebdff8c7def760eb070adac2b4c5'}, {'path': '/home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-disabled.yml', 'sha256': '44e177b5c5cd8138ea42139bd6cbd5d82452a2a83585db88ef4f50e74519bd34'}, {'path': '/home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-enabled.yml', 'sha256': '51cb2fb1629f1900a363aed090a1066d27f1ed2b97a63372b951d85bcd07591f'}, {'path': '/home/firelion/v79-g3-recovery-20261014T220437Z-bp9zg67v/g3-hub-disabled.yml', 'sha256': 'cfac41db973d8f99b9e3675389988cef9e009d5dc9cdae39d07dc0a900eb7bda'}, {'path': '/home/firelion/v79-g3-cutover-c42f671f4ccd-b7934c03f0e3-v2/generation-only-v1/enable-v79-hub.yml', 'sha256': 'c532df563e257d2077705d48b39f0071d5fed88fcb2e9ca2874c46cba4b125c5'}, {'path': '/home/firelion/v79-g3-ui-cutover-8d82b21a4def-v3/ui-image.yml', 'sha256': '108845250715cfb91c8db538cfafc34e189ff938fc0a56a4cbb724e8f883f168'}, {'path': '/home/firelion/v79-g3-tracking-cutover-v1/v79-hub-image.yml', 'sha256': '50e68e1f530e3cfac48111d2947e4ce2059e4795a4bfcd2388efd4e668d8020a'}, {'path': '/home/firelion/v79-workforce-release-plan.dhc2pyxi/reports-disabled.compose.json', 'sha256': 'd79b99f9b0c9d7e4cd88d49bdddf37a9e841f69f398590a0b8529b8143fdb48c'}, {'path': '/home/firelion/v79-workforce-release-plan.dhc2pyxi/reports-enable-flag.compose.json', 'sha256': 'fad2932985052a31d8ecfc9a9ba64575f5835917766515e434e25814f83dc133'}, {'path': '/home/firelion/v79-workforce-release-plan.dhc2pyxi/workboard-enabled.compose.json', 'sha256': '31f94cb30d6ce0b6be4df7d02baf0616f09c8e728eec7021b8d44671eac95e79'}, {'path': '/home/firelion/v79-owner-workspace.0m350lg4/ui-image.compose.json', 'sha256': '8eda5018b4fcb591640492f6c44f8d63c446cff6ffa61aac985de19277933ff8'}]}, 'v79-tiquet-manager': {'container': 'v79-tiquet-manager', 'compose_project': 'v79tiquet', 'compose_service': 'v79-tiquet-manager', 'image_id': 'sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42', 'compose_inputs': [{'path': '/home/firelion/v79-p1-tiquet-live-release-v6-20261016/live-candidate-effective.json', 'sha256': '69d950dd3699d4dd64f013e53e64021306b4111f6d1a013dd06d2d1feb24db77'}]}}
IMAGE = re.compile(r'sha256:[0-9a-f]{64}\Z')
SAFE_LINE = re.compile(r'(?:PHASE|RESULT|STOP|CHECKPOINT|DEPLOYED|ROLLBACK|PRESERVED|CUSTOMER_RELEASE|DATA_RESTORE|OFFHOST_CHECKPOINT)=[A-Za-z0-9_./:-]+\Z')

class Stop(Exception):
    pass

def need(ok, code):
    if not ok:
        raise Stop(code)

def emit(key, value):
    line = key + '=' + str(value)
    need(SAFE_LINE.fullmatch(line), 'INVALID_OUTPUT')
    print(line, flush=True)

def call(args, *, cwd=None, data=None, timeout=90, output=None):
    # Never forward stderr: Docker/Git/Compose may include environment or credentials.
    p = subprocess.run(args, cwd=cwd, input=data, stdout=output or subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=timeout, env=clean_env())
    need(p.returncode == 0, 'COMMAND_FAILED_' + Path(args[0]).name.upper().replace('-', '_'))
    return p.stdout

def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(('COMPOSE_', 'DOCKER_', 'GIT_'))}

def inspect(name, image=False):
    rows = json.loads(call(['docker', 'image' if image else 'container', 'inspect', name]))
    need(len(rows) == 1, 'INSPECT_AMBIGUOUS')
    return rows[0]

def envmap(values):
    result = {}
    for value in values or []:
        k, sep, v = value.partition('=')
        need(sep and k not in result, 'AMBIGUOUS_ENVIRONMENT')
        result[k] = v
    return result

def normalized_host(host):
    result = copy.deepcopy(host)
    targets = []
    binds = result.get('Binds')
    if isinstance(binds, list):
        parsed = [value.split(':') for value in binds if isinstance(value, str)]
        if len(parsed) == len(binds) and all(len(v) in (2, 3) and v[1].startswith('/') for v in parsed):
            targets.extend(v[1] for v in parsed)
            result['Binds'] = sorted(binds)
    mounts = result.get('Mounts')
    if isinstance(mounts, list) and all(isinstance(m, dict) and isinstance(m.get('Target'), str)
                                        and m['Target'].startswith('/') for m in mounts):
        targets.extend(m['Target'] for m in mounts)
        result['Mounts'] = sorted(mounts, key=lambda m: json.dumps(m, sort_keys=True))
    need(len(targets) == len(set(targets)), 'AMBIGUOUS_MOUNT_DESTINATIONS')
    return result

def fingerprint(row):
    config = row['Config']
    # Deliberately ignore image/Compose labels, creation time and assigned IPs only.
    fields = ('Cmd', 'Entrypoint', 'User', 'WorkingDir', 'ExposedPorts', 'Healthcheck',
              'StopSignal', 'StopTimeout', 'Tty', 'OpenStdin', 'StdinOnce', 'Volumes')
    return {'config': {k: config.get(k) for k in fields},
            'env': envmap(config.get('Env')),
            'host': normalized_host(row['HostConfig']),
            'mounts': sorted([{k: m.get(k) for k in ('Type', 'Source', 'Destination', 'RW', 'Propagation')}
                              for m in row['Mounts']], key=lambda m: m['Destination']),
            'networks': sorted(row['NetworkSettings']['Networks'])}

def sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def private_json(path, data):
    with path.open('x', encoding='utf8') as f:
        json.dump(data, f, sort_keys=True)
    path.chmod(0o600)

def compose(model, project, *args):
    return ['docker', 'compose', '--project-name', project, '-f', str(model), *args]

def validate_storage_and_networks(model, service, row):
    actual = {m['Destination']: m for m in row['Mounts']}
    desired = service.get('volumes') or []
    need(len(desired) == len(actual), 'RENDERED_MOUNT_COUNT_DIFFERS')
    for mount in desired:
        need(isinstance(mount, dict) and mount.get('target') in actual, 'RENDERED_MOUNT_TARGET_DIFFERS')
        live = actual[mount['target']]
        need(mount['type'] == live['Type'] and
             bool(live['RW']) == (not mount.get('read_only', False)), 'RENDERED_MOUNT_ACCESS_DIFFERS')
        if mount['type'] == 'bind':
            need(mount['source'] == live['Source'], 'RENDERED_BIND_SOURCE_DIFFERS')
        elif mount['type'] == 'volume':
            definition = model.get('volumes', {}).get(mount['source'], {})
            need(definition.get('name') == live.get('Name'), 'RENDERED_VOLUME_NAME_DIFFERS')
        else:
            raise Stop('UNREVIEWED_MOUNT_TYPE')
    networks = service.get('networks') or {}
    need(isinstance(networks, dict), 'RENDERED_NETWORK_FORMAT_UNEXPECTED')
    expected = {model['networks'][alias]['name'] for alias in networks}
    need(expected == set(row['NetworkSettings']['Networks']), 'RENDERED_NETWORKS_DIFFER')

def compose_runtime(value):
    # Compose config (including JSON) re-escapes dollars for a subsequent load.
    if isinstance(value, str):
        return value.replace('$$', '$')
    if isinstance(value, list):
        return [compose_runtime(v) for v in value]
    if isinstance(value, dict):
        return {k: compose_runtime(v) for k, v in value.items()}
    return value

def compose_literal(value):
    # These values come from container inspect, not Compose's serialized model.
    # A literal dollar must survive the frozen model's next interpolation pass.
    if isinstance(value, str):
        return value.replace('$', '$$')
    if isinstance(value, list):
        return [compose_literal(v) for v in value]
    if isinstance(value, dict):
        return {k: compose_literal(v) for k, v in value.items()}
    return value

def original_model(row, pin):
    labels = row['Config']['Labels']
    paths = labels['com.docker.compose.project.config_files'].split(',')
    need(paths == [x['path'] for x in pin['compose_inputs']], 'COMPOSE_ORDER_DRIFT')
    for entry in pin['compose_inputs']:
        path = Path(entry['path'])
        need(path.is_file() and not path.is_symlink(), 'COMPOSE_FILE_UNSAFE')
        need(hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], 'COMPOSE_HASH_DRIFT')
    args = ['docker', 'compose', '--project-name', pin['compose_project'],
            '--project-directory', labels['com.docker.compose.project.working_dir']]
    for path in paths:
        args += ['-f', path]
    model = json.loads(call([*args, 'config', '--format', 'json']))
    service = model['services'][pin['compose_service']]
    need(service.get('container_name') == pin['container'], 'SERVICE_NAME_DRIFT')
    need(not service.get('ports') and not row['HostConfig'].get('PortBindings'), 'PUBLISHED_PORTS_UNEXPECTED')
    validate_storage_and_networks(model, service, row)
    old = inspect(row['Image'], image=True)['Config']
    expected = envmap(old.get('Env'))
    expected.update({k: compose_runtime(str(v)) for k, v in service.get('environment', {}).items()})
    need(expected == envmap(row['Config'].get('Env')), 'RENDERED_ENV_DIFFERS_FROM_RUNNING')
    # Freeze the complete observed environment, including image defaults.
    # Explicit runtime fields prevent a new image changing execution/user/health defaults.
    service['environment'] = compose_literal(envmap(row['Config'].get('Env')))
    for field, key in [('command', 'Cmd'), ('entrypoint', 'Entrypoint'), ('user', 'User'),
                       ('working_dir', 'WorkingDir')]:
        value = row['Config'].get(key)
        if value is not None and value != '':
            service[field] = compose_literal(value)
    service['image'] = row['Image']
    service.pop('build', None)
    service.pop('pull_policy', None)
    # Rendered model retains all networks/volumes and sibling definitions, but up
    # always targets just this service with --no-deps --no-build --pull never.
    return model

def health(name, image, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        row = inspect(name)
        if row['State'].get('Status') in ('exited', 'dead'):
            raise Stop('APPLICATION_EXITED')
        if row['Image'] == image and row['State'].get('Health', {}).get('Status') == 'healthy':
            return row
        time.sleep(3)
    raise Stop('APPLICATION_HEALTH_TIMEOUT')

def encrypted_stream(args, dest, gnupg):
    # plaintext goes through OS pipes only, not a temporary file or logging buffer.
    with dest.open('xb') as out:
        reader = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=clean_env())
        encryptor = subprocess.Popen(['gpg', '--homedir', str(gnupg), '--batch', '--quiet',
                     '--trust-model', 'always', '--encrypt', '--recipient', RECIPIENT],
                     stdin=reader.stdout, stdout=out, stderr=subprocess.DEVNULL, env=clean_env())
        reader.stdout.close()
        try:
            code = encryptor.wait(timeout=1200)
            need(reader.wait(timeout=30) == 0 and code == 0, 'CHECKPOINT_STREAM_FAILED')
        finally:
            for child in (reader, encryptor):
                if child.poll() is None:
                    child.kill()
                child.wait()
    need(dest.stat().st_size > 64, 'CHECKPOINT_EMPTY')

def same_others(before, apps):
    current = json.loads(call(['docker', 'inspect', *sorted(before)]))
    for row in current:
        name = row['Name'].lstrip('/')
        if name not in apps:
            need(row['Id'] == before[name]['Id'] and row['Image'] == before[name]['Image']
                 and row['State']['Status'] == before[name]['State']['Status'], 'OTHER_CONTAINER_CHANGED')

def active_timers():
    text = call(['systemctl', '--user', 'list-units', '--type=timer', '--state=active',
                 '--no-legend', '--plain']).decode()
    timers = []
    for line in text.splitlines():
        name = line.split()[0]
        if re.fullmatch(r'v79[-A-Za-z0-9@_.]+\.timer', name) and re.search(r'(workforce|release|task)', name):
            timers.append(name)
    timers_idle(timers)
    return timers

def timers_idle(timers):
    for timer in timers:
        state = call(['systemctl', '--user', 'show', '--property=ActiveState', '--value',
                      timer[:-6] + '.service']).decode().strip()
        need(state not in ('active', 'activating', 'reloading'), 'SCHEDULED_WORK_CURRENTLY_RUNNING')

def up(path, pin):
    call(compose(path, pin['compose_project'], 'up', '-d', '--no-deps', '--no-build',
                 '--pull', 'never', pin['compose_service']), timeout=240)

def server(run, key, continuation=None):
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Stop('TERMINATION_REQUESTED')))
    need(socket.gethostname() == 'v79sl' and os.getuid() != 0, 'WRONG_SERVER_OR_ROOT')
    os.umask(0o077)
    with (Path.home() / '.v79-portfolio-rollout.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('ANOTHER_ROLLOUT_RUNNING')
        if continuation is not None:
            return continued_server_locked(run, *continuation)
        return server_locked(run, key)

def server_locked(run, key):
    for tool in ('docker', 'git', 'gpg'):
        need(shutil.which(tool), 'DEPENDENCY_MISSING')
    call(['docker', 'compose', 'version'])
    # These flags are tested by Compose's parser before any application is stopped.
    help_text = call(['docker', 'compose', 'up', '--help']).decode()
    need(all(x in help_text for x in ('--no-deps', '--no-build', '--pull')), 'COMPOSE_OPTIONS_UNSUPPORTED')
    memory = {x.split(':')[0]: int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines()}
    need(memory['MemAvailable'] >= 1500 * 1024, 'BUILD_MEMORY_INSUFFICIENT')
    need(shutil.disk_usage(run).free >= 15 * 1024**3, 'DISK_SPACE_INSUFFICIENT')
    names = call(['docker', 'ps', '-a', '--format', '{{.Names}}']).decode().splitlines()
    before = {r['Name'].lstrip('/'): r for r in json.loads(call(['docker', 'inspect', *names]))}
    private_json(run / 'runtime-before.json', before)
    plans = {}
    emit('PHASE', 'VERIFY_EXACT_RUNNING_RELEASE_AND_COMPOSE')
    for name, pin in PINNED.items():
        row = before[name]
        need(row['Image'] == pin['image_id'] and row['State'].get('Health', {}).get('Status') == 'healthy', 'LIVE_RELEASE_DRIFT')
        labels = row['Config']['Labels']
        need(labels['com.docker.compose.project'] == pin['compose_project'] and
             labels['com.docker.compose.service'] == pin['compose_service'], 'COMPOSE_IDENTITY_DRIFT')
        plans[name] = original_model(row, pin)
        private_json(run / (name + '-original.compose.json'), plans[name])
    henv = envmap(before['v79-hub']['Config']['Env'])
    tenv = envmap(before['v79-tiquet-manager']['Config']['Env'])
    need(henv.get('V79_REQUIRE_ADMIN_MFA') in ('1', 'true') and
         tenv.get('V79_ALLOW_LEGACY_AUTH') == '0' and
         tenv.get('V79_ENTITLEMENT_RECHECK_ENABLED') == '1', 'SECURITY_FLAGS_DRIFT')
    need(henv.get('V79_TIQUET_LAUNCH_SECRET') and
         henv['V79_TIQUET_LAUNCH_SECRET'] == tenv.get('V79_TIQUET_LAUNCH_SECRET'), 'SSO_SECRET_MISMATCH')
    gnupg = run / 'gnupg'
    gnupg.mkdir(mode=0o700)
    call(['gpg', '--homedir', str(gnupg), '--batch', '--import'], data=base64.b64decode(key, validate=True))
    keys = call(['gpg', '--homedir', str(gnupg), '--batch', '--with-colons', '--fingerprint', RECIPIENT]).decode()
    need('fpr:::::::::' + RECIPIENT + ':' in keys, 'RECOVERY_KEY_MISMATCH')
    candidates = {}
    for name, (repo, sha) in SOURCES.items():
        emit('PHASE', 'BUILD_' + name.replace('-', '_').upper())
        stage = run / repo
        call(['git', 'init', '-q', str(stage)])
        call(['git', '-C', str(stage), 'fetch', '--depth', '1', '--no-tags',
              'https://github.com/MrFixITslu/' + repo + '.git', sha], timeout=300)
        need(call(['git', '-C', str(stage), 'rev-parse', 'FETCH_HEAD']).decode().strip() == sha, 'SOURCE_PIN_FAILED')
        call(['git', '-C', str(stage), 'checkout', '--detach', '-q', sha])
        tag = 'v79-portfolio/' + repo.lower() + ':' + sha
        # Single build at a time; production images are not retagged or pruned.
        call(['docker', 'build', '--label', 'org.opencontainers.image.revision=' + sha,
              '--tag', tag, str(stage)], timeout=2400)
        image = inspect(tag, image=True)
        need(IMAGE.fullmatch(image['Id']), 'CANDIDATE_IMAGE_INVALID')
        need(not image['Config'].get('Volumes'), 'CANDIDATE_UNEXPECTED_IMAGE_VOLUMES')
        old_config = before[name]['Config']
        for field in ('User', 'Entrypoint', 'Cmd', 'WorkingDir'):
            if not old_config.get(field):
                need(not image['Config'].get(field), 'CANDIDATE_NEW_EXECUTION_DEFAULT')
        need(set(envmap(image['Config'].get('Env'))) <= set(envmap(old_config.get('Env'))), 'CANDIDATE_NEW_ENVIRONMENT_DEFAULT')
        candidates[name] = image['Id']
        candidate = copy.deepcopy(plans[name])
        candidate['services'][PINNED[name]['compose_service']]['image'] = image['Id']
        # Only the selected service image may differ in the frozen full model.
        original = copy.deepcopy(candidate)
        original['services'][PINNED[name]['compose_service']]['image'] = before[name]['Image']
        need(original == plans[name], 'NON_IMAGE_CONFIGURATION_CHANGE')
        path = run / (name + '-candidate.compose.json')
        private_json(path, candidate)
        rendered = json.loads(call(compose(path, PINNED[name]['compose_project'], 'config', '--format', 'json')))
        actual_env = rendered['services'][PINNED[name]['compose_service']].get('environment', {})
        need(compose_runtime(actual_env) == envmap(before[name]['Config'].get('Env')), 'FROZEN_ENVIRONMENT_INTERPOLATION_DRIFT')
    same_others(before, set())
    # Re-check all files and running configuration after potentially long builds.
    for name, pin in PINNED.items():
        need(original_model(inspect(name), pin) == plans[name], 'CONFIG_CHANGED_DURING_BUILD')
    checkpoint = run / 'checkpoint'
    checkpoint.mkdir(mode=0o700)
    # Retain the exact original images locally AND encrypted as a recovery artifact.
    encrypted_stream(['docker', 'image', 'save', *[before[n]['Image'] for n in PINNED]],
                     checkpoint / 'original-app-images.tar.gpg', gnupg)
    stopped = []
    changed = []
    success = False
    timers = active_timers()
    try:
        if timers:
            call(['systemctl', '--user', 'stop', *timers])
            timers_idle(timers)
        emit('PHASE', 'QUIESCE_HUB_AND_TIQUET_FOR_ENCRYPTED_CHECKPOINT')
        for name in PINNED:
            stopped.append(name)  # arm recovery before invoking a mutating command
            call(['docker', 'stop', '--time', '60', name], timeout=90)
        for db in ('v79-hub-postgres', 'tiquet-postgres'):
            encrypted_stream(['docker', 'exec', db, 'sh', '-c',
                              'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
                             checkpoint / (db + '.dump.gpg'), gnupg)
        for name, row in before.items():
            if name not in PINNED:
                continue
            for index, mount in enumerate(row['Mounts']):
                encrypted_stream(['docker', 'cp', name + ':' + mount['Destination'], '-'],
                                 checkpoint / (name + '-mount-' + str(index) + '.tar.gpg'), gnupg)
        encrypted_stream(['tar', '-C', str(run), '-cf', '-', 'runtime-before.json',
                          *[name + '-original.compose.json' for name in PINNED]],
                         checkpoint / 'runtime-and-config.tar.gpg', gnupg)
        files = [{'name': p.name, 'sha256': sha_file(p), 'bytes': p.stat().st_size}
                 for p in sorted(checkpoint.iterdir())]
        private_json(checkpoint / 'manifest.json', {'files': files, 'status': 'CAPTURED_NOT_RESTORE_TESTED',
                     'source_images': {n: before[n]['Image'] for n in PINNED}, 'candidates': candidates})
        emit('CHECKPOINT', 'ENCRYPTED_LOCAL_COMPLETE_NOT_RESTORE_TESTED')
        for name, pin in PINNED.items():
            emit('PHASE', 'SWITCH_' + name.replace('-', '_').upper())
            changed.append(name)
            up(run / (name + '-candidate.compose.json'), pin)
            row = health(name, candidates[name])
            need(fingerprint(row) == fingerprint(before[name]), 'RUNTIME_CONFIGURATION_CHANGED')
            emit('DEPLOYED', name + '_HEALTHY')
        same_others(before, set(PINNED))
        private_json(run / 'release-receipt.json', {'images': candidates, 'sources': SOURCES,
                     'health': 'PASS_BOTH', 'security_acceptance': 'NOT_PERFORMED'})
        success = True
        emit('PRESERVED', 'OTHER_CONTAINERS_AND_ORIGINAL_COMPOSE_FILES')
        emit('RESULT', 'BOTH_APPS_DEPLOYED_HEALTHY')
    finally:
        if not success:
            emit('PHASE', 'RESTORE_ORIGINAL_APP_IMAGES')
            failed = False
            for name in reversed(stopped):
                try:
                    if name in changed:
                        up(run / (name + '-original.compose.json'), PINNED[name])
                    else:
                        call(['docker', 'start', name])
                    row = health(name, before[name]['Image'])
                    need(fingerprint(row) == fingerprint(before[name]), 'ROLLBACK_CONFIG_CHANGED')
                except Exception:
                    failed = True
            emit('ROLLBACK', 'FAILED_MANUAL_RECOVERY_REQUIRED' if failed else 'ORIGINAL_IMAGES_HEALTHY')
            emit('DATA_RESTORE', 'NOT_AUTOMATIC_IMAGE_ROLLBACK_ONLY')
        emit('CUSTOMER_RELEASE', 'NO_GO')
        if timers:
            call(['systemctl', '--user', 'start', *timers])
            emit('PRESERVED', 'ORIGINALLY_ACTIVE_USER_TIMERS_RESUMED')

SSH = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=12', HOST]

def remote(args, **kwargs):
    return call([*SSH, shlex.join(args)], **kwargs)

def acer():
    need(socket.gethostname() != 'v79sl' and os.getuid() != 0, 'RUN_ON_NON_ROOT_ACER')
    key = call(['gpg', '--batch', '--export', RECIPIENT])
    need(key, 'ACER_RECOVERY_PUBLIC_KEY_UNAVAILABLE')
    # A detached worker keeps checkpoint/rollback alive if the Acer connection drops.
    directory = remote(['mktemp', '-d', '/home/firelion/v79-portfolio-rollout.XXXXXXXX']).decode().strip()
    need(re.fullmatch(r'/home/firelion/v79-portfolio-rollout\.[A-Za-z0-9]{8}', directory), 'REMOTE_DIRECTORY_INVALID')
    script = Path(directory) / 'rollout.py'
    command = 'umask 077; cat > ' + shlex.quote(str(script))
    call([*SSH, command], data=Path(__file__).read_bytes())
    launch = shlex.join(['python3', '-u', str(script), '--server', directory, base64.b64encode(key).decode()])
    remote_shell = 'nohup ' + launch + ' > ' + shlex.quote(directory + '/progress.log') + ' 2>&1 < /dev/null &'
    call([*SSH, remote_shell])
    emit('CHECKPOINT', directory)
    return monitor(directory)

def monitor(directory, copy_checkpoint=True):
    seen = 0
    deadline = time.monotonic() + 10800
    heartbeat = time.monotonic()
    while True:
        need(time.monotonic() < deadline, 'MONITOR_TIMEOUT_USE_RESUME_REMOTE_MAY_CONTINUE')
        text = remote(['cat', directory + '/progress.log']).decode('utf8', 'replace')
        lines = text.splitlines()
        if text and not text.endswith('\n'):
            lines = lines[:-1]
        for line in lines[seen:]:
            if SAFE_LINE.fullmatch(line):
                print(line, flush=True)
        seen = len(lines)
        code = remote(['sh', '-c', 'if test -f "$1/exit-code"; then cat "$1/exit-code"; fi', 'poll', directory]).decode().strip()
        if code:
            need(code in ('0', '1'), 'REMOTE_STATUS_INVALID')
            if not copy_checkpoint:
                emit('OFFHOST_CHECKPOINT', 'PREVIOUSLY_VERIFIED_SET_RETAINED')
                need(code == '0', 'REMOTE_ROLLOUT_FAILED_SEE_SAFE_STATUS')
                return
            # Early preflight/build failure has no checkpoint and never stopped apps.
            complete = remote(['sh', '-c', 'test -f "$1/checkpoint/manifest.json" && echo yes || echo no', 'check', directory]).decode().strip()
            if complete != 'yes':
                emit('CHECKPOINT', 'NOT_CREATED_PREDEPLOY_OR_CAPTURE_STOP')
                raise Stop('REMOTE_ROLLOUT_FAILED_SEE_SAFE_STATUS')
            # Copy encrypted checkpoint even after an unsuccessful rollout.
            base = Path.home() / 'V79-Portfolio-Checkpoints'
            base.mkdir(mode=0o700, exist_ok=True)
            need(base.is_dir() and not base.is_symlink() and base.stat().st_uid == os.getuid(), 'LOCAL_CHECKPOINT_DIRECTORY_UNSAFE')
            base.chmod(0o700)
            local = Path(tempfile.mkdtemp(prefix=Path(directory).name + '-', dir=base))
            call(['scp', '-q', '-r', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                  HOST + ':' + directory + '/checkpoint', str(local)], timeout=1200)
            manifest = json.loads((local / 'checkpoint/manifest.json').read_text())
            for f in manifest['files']:
                path = local / 'checkpoint' / f['name']
                need(path.is_file() and sha_file(path) == f['sha256'], 'OFFHOST_CIPHERTEXT_MISMATCH')
                # Validate encryption end to end without placing plaintext on disk.
                call(['gpg', '--batch', '--quiet', '--decrypt', str(path)], output=subprocess.DEVNULL, timeout=1200)
            emit('CHECKPOINT', str(local))
            emit('OFFHOST_CHECKPOINT', 'HASH_AND_FULL_DECRYPT_PASS_NOT_RESTORE_TESTED')
            need(code == '0', 'REMOTE_ROLLOUT_FAILED_SEE_SAFE_STATUS')
            return
        if time.monotonic() - heartbeat >= 55:
            emit('PHASE', 'REMOTE_WORKER_RUNNING')
            heartbeat = time.monotonic()
        time.sleep(5)

# Continuation is deliberately limited to the failed run diagnosed by the founder.
FAILED_RUN = Path('/home/firelion/v79-portfolio-rollout.W8DQrYJI')
VERIFIED_CHECKPOINT = Path.home() / 'V79-Portfolio-Checkpoints/v79-portfolio-rollout.W8DQrYJI-6_p2qopr/checkpoint'

def continuation_proof(checkpoint):
    import io
    import tarfile
    manifest = json.loads((checkpoint / 'manifest.json').read_text())
    artifact = checkpoint / 'runtime-and-config.tar.gpg'
    entry = next(x for x in manifest['files'] if x['name'] == artifact.name)
    need(sha_file(artifact) == entry['sha256'], 'OFFHOST_CONFIG_CIPHERTEXT_CHANGED')
    plaintext = call(['gpg', '--batch', '--quiet', '--decrypt', str(artifact)], timeout=90)
    need(len(plaintext) <= 8 * 1024**2, 'CONFIG_ARCHIVE_TOO_LARGE')
    expected = {'runtime-before.json', *[n + '-original.compose.json' for n in PINNED]}
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode='r:') as archive:
        for member in archive:
            need(member.isfile() and member.name in expected and member.name not in hashes
                 and member.size <= 4 * 1024**2, 'CONFIG_ARCHIVE_UNEXPECTED_MEMBER')
            hashes[member.name] = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
    need(set(hashes) == expected, 'CONFIG_ARCHIVE_INCOMPLETE')
    need(manifest['source_images'] == {n: p['image_id'] for n, p in PINNED.items()}, 'CHECKPOINT_SOURCE_IMAGES_CHANGED')
    need(set(manifest['candidates']) == set(PINNED)
         and all(IMAGE.fullmatch(x) for x in manifest['candidates'].values()), 'CHECKPOINT_CANDIDATES_INVALID')
    return {'files': hashes, 'manifest_sha256': sha_file(checkpoint / 'manifest.json'),
            'candidates': manifest['candidates']}

def check_original_inputs():
    for pin in PINNED.values():
        for entry in pin['compose_inputs']:
            path = Path(entry['path'])
            need(path.is_file() and not path.is_symlink() and sha_file(path) == entry['sha256'],
                 'ORIGINAL_COMPOSE_INPUT_CHANGED')

def continued_server_locked(run, old, proof):
    need(old == FAILED_RUN and old.is_dir() and not old.is_symlink(), 'CONTINUATION_RUN_INVALID')
    need((old / 'exit-code').read_text().strip() == '1', 'PREVIOUS_RUN_NOT_FAILED_COMPLETE')
    expected_files = {'runtime-before.json', *[n + '-original.compose.json' for n in PINNED]}
    need(set(proof['files']) == expected_files, 'CHECKPOINT_PROOF_INCOMPLETE')
    for name, digest in proof['files'].items():
        path = old / name
        need(path.is_file() and not path.is_symlink() and sha_file(path) == digest, 'SAVED_CONFIG_INTEGRITY_CHANGED')
    manifest_path = old / 'checkpoint/manifest.json'
    need(sha_file(manifest_path) == proof['manifest_sha256'], 'SAVED_MANIFEST_CHANGED')
    manifest = json.loads(manifest_path.read_text())
    need(manifest['candidates'] == proof['candidates'] and set(proof['candidates']) == set(PINNED),
         'CANDIDATE_PROOF_CHANGED')
    need(manifest['source_images'] == {n: p['image_id'] for n, p in PINNED.items()}, 'SOURCE_IMAGES_CHANGED')
    baseline = json.loads((old / 'runtime-before.json').read_text())
    check_original_inputs()
    emit('PHASE', 'VERIFY_RESTORED_ORIGINALS_AND_CACHED_CANDIDATES')
    before = {n: inspect(n) for n in baseline}
    plans = {}
    for name, pin in PINNED.items():
        row = before[name]
        need(row['Image'] == pin['image_id'] and row['State'].get('Health', {}).get('Status') == 'healthy',
             'ORIGINAL_APP_NOT_HEALTHY')
        need(fingerprint(row) == fingerprint(baseline[name]), 'ORIGINAL_RUNTIME_DRIFT')
        candidate_id = proof['candidates'][name]
        need(IMAGE.fullmatch(candidate_id), 'CANDIDATE_ID_INVALID')
        image = inspect(candidate_id, image=True)
        need(image['Id'] == candidate_id and
             image['Config'].get('Labels', {}).get('org.opencontainers.image.revision') == SOURCES[name][1],
             'CACHED_CANDIDATE_SOURCE_MISMATCH')
        model = json.loads((old / (name + '-original.compose.json')).read_text())
        service = model['services'][pin['compose_service']]
        need(service['image'] == pin['image_id'], 'ORIGINAL_MODEL_IMAGE_CHANGED')
        original_path = run / (name + '-original.pinned.yml')
        private_json(original_path, model)
        service['image'] = candidate_id
        candidate_path = run / (name + '-candidate.pinned.yml')
        private_json(candidate_path, model)
        rendered = json.loads(call(compose(candidate_path, pin['compose_project'], 'config', '--format', 'json')))
        selected = rendered['services'][pin['compose_service']]
        need(compose_runtime(selected.get('environment', {})) == envmap(row['Config'].get('Env')),
             'FROZEN_ENVIRONMENT_INTERPOLATION_DRIFT')
        validate_storage_and_networks(rendered, selected, row)
        plans[name] = (original_path, candidate_path)
    same_others(baseline, set(PINNED))
    private_json(run / 'runtime-before.json', before)
    private_json(run / 'checkpoint-reference.json', {'prior_run': str(old), 'scope': 'PRE_FIRST_ATTEMPT_NOT_NEW_SNAPSHOT',
                                                  'manifest_sha256': proof['manifest_sha256']})
    emit('CHECKPOINT', 'REUSE_VERIFIED_PRE_FIRST_ATTEMPT_SET_NO_NEW_SNAPSHOT')
    changed = []
    timers = active_timers()
    success = False
    try:
        if timers:
            call(['systemctl', '--user', 'stop', *timers])
            timers_idle(timers)
        for name, pin in PINNED.items():
            # Arm rollback before up. No builds, captures, imports or data restores.
            emit('PHASE', 'SWITCH_' + name.replace('-', '_').upper())
            changed.append(name)
            up(plans[name][1], pin)
            current = health(name, proof['candidates'][name])
            need(fingerprint(current) == fingerprint(before[name]), 'RUNTIME_CONFIGURATION_CHANGED')
            emit('DEPLOYED', name + '_HEALTHY_CONFIGURATION_PRESERVED')
        same_others(before, set(PINNED))
        private_json(run / 'release-receipt.json', {'images': proof['candidates'], 'sources': SOURCES,
                     'checkpoint': 'PRE_FIRST_ATTEMPT_REUSED', 'health': 'PASS_BOTH',
                     'security_acceptance': 'NOT_PERFORMED'})
        success = True
        emit('RESULT', 'BOTH_APPS_DEPLOYED_HEALTHY')
    finally:
        if not success:
            failed = False
            for name in reversed(changed):
                try:
                    up(plans[name][0], PINNED[name])
                    current = health(name, before[name]['Image'])
                    need(fingerprint(current) == fingerprint(before[name]), 'ROLLBACK_CONFIG_CHANGED')
                    emit('ROLLBACK', name + '_ORIGINAL_HEALTHY_CONFIGURATION_PRESERVED')
                except Exception:
                    failed = True
                    emit('ROLLBACK', name + '_NOT_PROVEN_MANUAL_REVIEW_REQUIRED')
            emit('ROLLBACK', 'FAILED_MANUAL_RECOVERY_REQUIRED' if failed else 'ORIGINAL_IMAGES_HEALTHY')
            emit('DATA_RESTORE', 'NOT_AUTOMATIC_IMAGE_ROLLBACK_ONLY')
        emit('CUSTOMER_RELEASE', 'NO_GO')
        if timers:
            call(['systemctl', '--user', 'start', *timers])
            emit('PRESERVED', 'ORIGINALLY_ACTIVE_USER_TIMERS_RESUMED')

def acer_continue():
    need(socket.gethostname() != 'v79sl' and os.getuid() != 0, 'RUN_ON_NON_ROOT_ACER')
    proof = continuation_proof(VERIFIED_CHECKPOINT)
    encoded = base64.b64encode(json.dumps(proof).encode()).decode()
    directory = remote(['mktemp', '-d', '/home/firelion/v79-portfolio-rollout.XXXXXXXX']).decode().strip()
    need(re.fullmatch(r'/home/firelion/v79-portfolio-rollout\.[A-Za-z0-9]{8}', directory), 'REMOTE_DIRECTORY_INVALID')
    script = Path(directory) / 'rollout.py'
    call([*SSH, 'umask 077; cat > ' + shlex.quote(str(script))], data=Path(__file__).read_bytes())
    launch = shlex.join(['python3', '-u', str(script), '--server-continue', directory, str(FAILED_RUN), encoded])
    call([*SSH, 'nohup ' + launch + ' > ' + shlex.quote(directory + '/progress.log') + ' 2>&1 < /dev/null &'])
    emit('CHECKPOINT', directory)
    monitor(directory, copy_checkpoint=False)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', nargs=2, metavar=('DIRECTORY', 'PUBLIC_KEY_BASE64'))
    parser.add_argument('--continue-run', action='store_true', help='Continue the specifically diagnosed failed run with cached candidates and its existing verified checkpoint')
    parser.add_argument('--server-continue', nargs=3, metavar=('DIRECTORY', 'OLD_DIRECTORY', 'PROOF_BASE64'))
    parser.add_argument('--resume', help='Monitor an existing remote run; never start another deployment')
    args = parser.parse_args()
    if args.continue_run:
        need(not args.server and not args.server_continue and not args.resume, 'CONFLICTING_MODES')
        acer_continue()
        return 0
    if args.resume:
        need(not args.server and not args.server_continue and re.fullmatch(r'/home/firelion/v79-portfolio-rollout\.[A-Za-z0-9]{8}', args.resume), 'RESUME_DIRECTORY_INVALID')
        copy_checkpoint = remote(['sh', '-c', 'if test -f "$1/checkpoint-reference.json"; then echo no; else echo yes; fi', 'resume', args.resume]).decode().strip() != 'no'
        monitor(args.resume, copy_checkpoint=copy_checkpoint)
        return 0
    if args.server or args.server_continue:
        need(not (args.server and args.server_continue), 'CONFLICTING_MODES')
        options = args.server or args.server_continue
        run = Path(options[0])
        need(run == Path(__file__).resolve().parent and run.parent == Path('/home/firelion'), 'REMOTE_PATH_INVALID')
        code = 1
        try:
            if args.server_continue:
                proof = json.loads(base64.b64decode(options[2], validate=True))
                server(run, '', (Path(options[1]), proof))
            else:
                server(run, options[1])
            code = 0
        except BaseException as error:
            emit('STOP', str(error) if isinstance(error, Stop) and re.fullmatch('[A-Z0-9_]+', str(error)) else 'REMOTE_ERROR_REDACTED')
        finally:
            (run / 'exit-code').write_text(str(code))
        return code
    acer()
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Stop as error:
        emit('STOP', str(error))
        sys.exit(1)
    except KeyboardInterrupt:
        emit('STOP', 'ACER_DISCONNECTED_REMOTE_WORKER_CONTINUES')
        sys.exit(1)
    except Exception:
        emit('STOP', 'LOCAL_ERROR_REDACTED_REMOTE_WORKER_MAY_CONTINUE')
        sys.exit(1)
