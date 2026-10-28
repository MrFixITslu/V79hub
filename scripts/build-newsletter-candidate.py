#!/usr/bin/env python3
"""Build website only and batch the new newsletter checks; never deploy."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REVISION = 'db84a4a07cf637c9115769706301814c8cb3df4b'
LIVE = {'V79website': 'sha256:2bf0b35a8b7d71b183b34fa09a08ba7fb1b3c7637448b523c1bd07f8a02fa1fb',
        'v79-hub': 'sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec'}
FOCUSED = ('tests/newsletter-production.test.ts',)


def require(ok, code):
    if not ok:
        raise ValueError(code)


def fingerprint(rows):
    # Full private runtime comparison without printing configuration values.
    records = {r['Name']: {k: r.get(k) for k in ('Id', 'Image', 'Config', 'HostConfig', 'Mounts', 'NetworkSettings')}
               | {'status': r['State']['Status'], 'started': r['State']['StartedAt']} for r in rows}
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    os.umask(0o077)
    os.environ['GIT_TERMINAL_PROMPT'] = '0'
    work = Path(tempfile.mkdtemp(prefix='v79-newsletter-candidate-', dir=Path.home()))
    log = work / 'build.log'
    stage = 'inventory'
    def run(args, *, capture=False, timeout=1200):
        with log.open('ab') as stream:
            result = subprocess.run(args, stdout=subprocess.PIPE if capture else stream,
                                    stderr=stream, timeout=timeout)
        require(result.returncode == 0, 'CANDIDATE_COMMAND_FAILED_REDACTED')
        return result.stdout if capture else None
    def snapshot():
        ids = run(['docker', 'ps', '--all', '-q'], capture=True).decode().split()
        require(bool(ids), 'CONTAINER_INVENTORY_EMPTY')
        rows = json.loads(run(['docker', 'inspect', *ids], capture=True))
        by_name = {r['Name'].lstrip('/'): r for r in rows}
        for name, image in LIVE.items():
            require(name in by_name and by_name[name]['Image'] == image
                    and by_name[name]['State']['Running']
                    and by_name[name]['State'].get('Health', {}).get('Status') == 'healthy',
                    'ACCEPTED_LIVE_PAIR_CHANGED')
        return rows
    try:
        before = snapshot()
        source = work / 'website'
        stage = 'website_source'
        print(json.dumps({'stage': stage, 'status': 'RUNNING'}), flush=True)
        run(['git', 'init', str(source)])
        run(['git', '-C', str(source), 'remote', 'add', 'origin', 'https://github.com/MrFixITslu/v79website.git'])
        run(['git', '-C', str(source), 'fetch', '--depth=1', '--no-tags', 'origin', REVISION])
        run(['git', '-C', str(source), 'checkout', '--detach', REVISION])
        require(run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture=True).decode().strip() == REVISION,
                'SOURCE_PIN_MISMATCH')
        require(not run(['git', '-C', str(source), 'status', '--porcelain'], capture=True), 'SOURCE_NOT_CLEAN')
        require('COPY --chmod=0644 package.json package-lock.json ./' in (source / 'Dockerfile').read_text(),
                'PACKAGE_PERMISSION_FIX_MISSING')
        stage = 'website_build'
        tag = 'v79website:newsletter-' + REVISION[:12]
        print(json.dumps({'stage': stage, 'status': 'RUNNING', 'hub_rebuild': False}), flush=True)
        run(['docker', 'build', '--label', 'org.opencontainers.image.revision=' + REVISION, '-t', tag, str(source)])
        image = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag], capture=True).decode().strip()
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', image), 'INVALID_BUILT_IMAGE')
        # Public source fixtures only: readable by the image user regardless of host UID.
        # Source checkout stays private, and no production file permissions change.
        command = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
                   '--tmpfs', '/tmp:rw,nosuid,noexec,size=128m', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--entrypoint', 'node']
        for relative in FOCUSED:
            file = source / relative
            file.chmod(0o644)
            command.extend(['--mount', 'type=bind,source=' + str(file) + ',target=/focused/' + relative + ',readonly'])
        command.extend([image, '--test', '/focused/tests/newsletter-production.test.ts'])
        stage = 'new_newsletter_checks'
        print(json.dumps({'stage': stage, 'status': 'RUNNING', 'previous_lead_checks_repeated': False}), flush=True)
        run(command, timeout=120)
        stage = 'closeout'
        after = snapshot()
        require(fingerprint(before) == fingerprint(after), 'LIVE_RUNTIME_CHANGED_DURING_BUILD')
        receipt = {'result': 'PASS_NEWSLETTER_CANDIDATE_BUILT_FOCUSED_ONLY',
                   'website': {'commit': REVISION, 'image': image, 'tag': tag},
                   'newsletter_checks': 'PASS', 'compiled_http_flow': 'PASS',
                   'hub_rebuilt': False, 'previous_lead_checks_repeated': False,
                   'production_container_count': len(before), 'live_runtime_unchanged': True,
                   'deployed': False, 'evidence_directory': str(work)}
        (work / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt, indent=2))
    except Exception as error:
        code = str(error)
        print(json.dumps({'result': 'STOP_NEWSLETTER_CANDIDATE', 'stage': stage,
                          'reason': code if re.fullmatch('[A-Z][A-Z0-9_]+', code) else type(error).__name__,
                          'evidence_directory': str(work), 'deployed': False}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
