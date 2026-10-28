#!/usr/bin/env python3
"""Confirm package access defect, rebuild website only, isolate startup once."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

ROOT = Path('/home/firelion/v79-lead-release-2pvsb2mo')
OLD_IMAGE = 'sha256:a5ef48c1b1a4dfd29fe33b19f689adae4ca1d1ed344e2bef8b6a16c1684a848c'
REVISION = '356b09e0cb5ebdda92b5f7d80e01a4d37feacdf0'
DOCKERFILE_BLOB = 'dcfe5b39f0afd14f179dfd88d4afbc361afbc66e'
PROBE_REVISION = 'aefc035eb7c8e2b32874b65ed2247eeb55f896dc'
PROBE_SHA = 'b809d90ac15ce503bc05e757bfae568b1e175023392f2930cc6889ac18669669'
PROBE_URL = ('https://raw.githubusercontent.com/MrFixITslu/V79hub/' + PROBE_REVISION
             + '/scripts/probe-website-candidate-startup.py')

ACCESS = r"""
const fs=require('node:fs');
const p='/app/package.json',s=fs.statSync(p);let readable=true,error=null;
try{fs.accessSync(p,fs.constants.R_OK)}catch(e){readable=false;error=e.code}
console.log(JSON.stringify({mode:(s.mode&511).toString(8),uid:s.uid,gid:s.gid,readable,error}));
"""


def require(ok, code):
    if not ok:
        raise ValueError(code)


def access(run, image):
    return json.loads(run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                          '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                          '--workdir', '/', '--entrypoint', 'node', image, '-e', ACCESS],
                         capture=True))


def live(run):
    rows = json.loads(run(['docker', 'inspect', 'v79-hub', 'V79website'], capture=True))
    require(all(r['State']['Running'] and r['State'].get('Health', {}).get('Status') == 'healthy'
                for r in rows), 'ORIGINAL_APPS_MUST_BE_HEALTHY')
    return {r['Name']: {'id': r['Id'], 'image': r['Image'], 'started': r['State']['StartedAt']}
            for r in rows}


def main():
    os.umask(0o077)
    os.environ['GIT_TERMINAL_PROMPT'] = '0'
    require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.stat().st_uid == os.geteuid()
            and ROOT.stat().st_mode & 0o077 == 0, 'PRIVATE_RELEASE_DIRECTORY_REQUIRED')
    require(json.loads((ROOT / 'lead-release-state.json').read_text()).get('phase') == 'ROLLED_BACK',
            'ORIGINALS_MUST_BE_RESTORED')
    work = Path(tempfile.mkdtemp(prefix='website-permission-rebuild-', dir=ROOT))
    log = work / 'build.log'
    stage = 'confirm_package_access'

    def run(args, *, capture=False, timeout=1200):
        with log.open('ab') as stream:
            result = subprocess.run(args, stdout=subprocess.PIPE if capture else stream,
                                    stderr=stream, timeout=timeout)
        require(result.returncode == 0, 'BUILD_COMMAND_FAILED_REDACTED')
        return result.stdout if capture else None

    before = live(run)
    try:
        original_access = access(run, OLD_IMAGE)
        print(json.dumps({'stage': stage, 'old_image_package_access': original_access}), flush=True)
        require(original_access.get('readable') is False and original_access.get('error') == 'EACCES',
                'PACKAGE_ACCESS_CAUSE_NOT_CONFIRMED_NO_BUILD')
        source = work / 'website'
        stage = 'website_source'
        print(json.dumps({'stage': stage, 'status': 'RUNNING'}), flush=True)
        run(['git', 'init', str(source)])
        run(['git', '-C', str(source), 'remote', 'add', 'origin',
             'https://github.com/MrFixITslu/v79website.git'])
        run(['git', '-C', str(source), 'fetch', '--depth=1', '--no-tags', 'origin', REVISION])
        run(['git', '-C', str(source), 'checkout', '--detach', REVISION])
        require(run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture=True).decode().strip() == REVISION,
                'SOURCE_PIN_MISMATCH')
        require(run(['git', '-C', str(source), 'hash-object', 'Dockerfile'], capture=True).decode().strip()
                == DOCKERFILE_BLOB, 'DOCKERFILE_FIX_CHANGED')
        require(not run(['git', '-C', str(source), 'status', '--porcelain'], capture=True), 'SOURCE_NOT_CLEAN')
        stage = 'website_build'
        tag = 'v79website:runtime-permissions-' + REVISION[:12]
        print(json.dumps({'stage': stage, 'status': 'RUNNING', 'hub_rebuild': False}), flush=True)
        run(['docker', 'build', '--label', 'org.opencontainers.image.revision=' + REVISION,
             '-t', tag, str(source)])
        image = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag], capture=True).decode().strip()
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', image), 'INVALID_BUILT_IMAGE')
        stage = 'fixed_package_access'
        fixed_access = access(run, image)
        print(json.dumps({'stage': stage, 'new_image_package_access': fixed_access}), flush=True)
        require(fixed_access.get('readable') is True and fixed_access.get('mode') == '644',
                'FIXED_IMAGE_PACKAGE_NOT_READABLE')
        stage = 'isolated_startup'
        with urllib.request.urlopen(PROBE_URL, timeout=30) as response:
            probe_source = response.read(1_000_000)
        require(hashlib.sha256(probe_source).hexdigest() == PROBE_SHA, 'PROBE_CHECKSUM_CHANGED')
        probe_file = work / 'isolated-startup.py'
        probe_file.write_bytes(probe_source)
        spec = importlib.util.spec_from_file_location('fixed_website_startup', probe_file)
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        result = probe.main(image_override=image)
        require(result['running'] is True and result['health'] == 'healthy'
                and result['probe_removed'] and result['originals_unchanged'],
                'FIXED_IMAGE_ISOLATED_STARTUP_NOT_HEALTHY')
        require(live(run) == before, 'ORIGINAL_IDENTITIES_CHANGED')
        receipt = {'result': 'PASS_WEBSITE_REBUILT_AND_ISOLATED_STARTUP',
                   'website': {'commit': REVISION, 'image': image, 'tag': tag},
                   'old_package_access': original_access, 'new_package_access': fixed_access,
                   'isolated_startup': result, 'hub_rebuilt': False,
                   'previous_focused_tests_repeated': False, 'live_identities_unchanged': True,
                   'deployed': False, 'requires_new_image_bound_release': True,
                   'evidence_directory': str(work)}
        (work / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt, indent=2))
    except Exception as error:
        code = str(error)
        print(json.dumps({'result': 'STOP_WEBSITE_PERMISSION_REBUILD', 'stage': stage,
                          'reason': code if re.fullmatch('[A-Z][A-Z0-9_]+', code) else type(error).__name__,
                          'evidence_directory': str(work), 'deployed': False}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
