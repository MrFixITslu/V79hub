#!/usr/bin/env python3
"""Build the tested Hub UI correction and inspect logo metadata; never deploy."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import tempfile

COMMIT = '8d82b21a4defe47a3d377a57dcd648b3c9818fea'
TREE = '7a6f5e5835f1e141bb4197060da634cd6c2cefcc'
BASE_COMMIT = 'c42f671f4ccd4b268f6701989cceba0ba27b5dbd'
HUB_IMAGE = 'sha256:4a2320ad18549adf42fa60d9a1d06d2c124dba0db2f80b85a1a9cf0fc27dabb1'
MARKETING_IMAGE = 'sha256:e34d3c22f325c7fef78bc79bf96aa3386c10a45a7d2fd3e4e5081d39e9d4e0e8'
NODE_BASE = 'public.ecr.aws/docker/library/node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402'
NAMES = ('v79-hub', 'v79marketing-app', 'v79-business-agent', 'v79-hub-postgres', 'v79-tiquet-manager', 'tiquet-postgres')
TAG = 'v79-hub-g3-ui:' + COMMIT[:12]
LOGO_PROBE = r'''
const Database=require('better-sqlite3'),crypto=require('node:crypto');
const canonical=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const businessId='44289786-2583-4bf1-9db2-99eca95dfd96';
const db=new Database(process.env.DATABASE_PATH||'/app/data/v79_marketing.sqlite',{readonly:true,fileMustExist:true});
try{
 db.pragma('query_only=ON');
 const row=db.prepare('SELECT envelope FROM marketing_production_state WHERE business_id=?').get(businessId);
 if(!row)throw Error('No production ledger');
 const {state,hmac}=JSON.parse(row.envelope);
 const computed=crypto.createHmac('sha256',process.env.V79_MARKETING_PRODUCTION_AUDIT_KEY).update('v79-marketing-production-v1\n'+businessId+'\n'+canonical(state)).digest('hex');
 if(!/^[a-f0-9]{64}$/.test(hmac)||!crypto.timingSafeEqual(Buffer.from(computed),Buffer.from(hmac)))throw Error('Ledger integrity');
 console.log(JSON.stringify({signedLedgerVerified:true,configRevision:state.configRevision,approvedBrandHasLogo:!!state.brand?.logoPng,
  packages:state.jobs.slice(-5).map(j=>({id:j.id,status:j.status,renderedBrandHasLogo:j.bundle?!!j.bundle.brand?.logoPng:null,
  originalLogoWarning:j.bundle?.review?.warnings?.some(w=>w.includes('original brand logo'))||false}))}));
}finally{db.close();}
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(args, *, cwd=None, visible=False, timeout=60, data=None):
    result = subprocess.run(args, cwd=cwd, input=data, capture_output=not visible, timeout=timeout)
    require(result.returncode == 0, 'Command failed; sensitive output withheld')
    return result.stdout


def snapshot():
    records = {}
    for name in NAMES:
        meta = json.loads(run(['docker', 'inspect', name]))[0]
        require(meta['State'].get('Running') and meta['State'].get('Health', {}).get('Status') == 'healthy', 'Service is not healthy: ' + name)
        records[name] = {'id': meta['Id'], 'image': meta['Image'], 'startedAt': meta['State']['StartedAt'],
                         'runtimeSha256': hashlib.sha256(json.dumps({k: meta[k] for k in ('Config', 'HostConfig', 'Mounts')}, sort_keys=True).encode()).hexdigest()}
        if name in ('v79-hub', 'v79marketing-app'):
            expected = HUB_IMAGE if name == 'v79-hub' else MARKETING_IMAGE
            require(meta['Image'] == expected, 'Accepted G3 image differs: ' + name)
            env = dict(item.split('=', 1) for item in meta['Config']['Env'])
            require(env.get('V79_MARKETING_PRODUCTION_ENABLED') == '1', 'Generation flag differs: ' + name)
            if name == 'v79marketing-app':
                require(env.get('V79_MARKETING_PRODUCTION_PUBLISH_ENABLED') == '0', 'Publication must remain disabled')
    return records


def verify_ui_scope(old_package, new_package, old_lock, new_lock, changed):
    allowed = {'src/components/MarketingProductionPanel.tsx', 'package.json', 'package-lock.json'}
    require(all(p in allowed or p.startswith(('tests/', 'docs/', 'scripts/')) for p in changed), 'Candidate changes exceed reviewed Hub UI and operational/test scope')
    require(old_package['dependencies'] == new_package['dependencies'], 'Runtime dependency declarations changed')
    def runtime_packages(lock):
        return {name: value for name, value in lock['packages'].items() if name and not value.get('dev') and not value.get('devOptional')}
    require(runtime_packages(old_lock) == runtime_packages(new_lock), 'Runtime dependency lock entries changed')


def readable_source(checkout):
    for directory, dirs, files in os.walk(checkout, followlinks=False):
        dirs[:] = [name for name in dirs if name != '.git']
        Path(directory).chmod(0o755)
        for name in dirs + files:
            path = Path(directory) / name
            require(not path.is_symlink(), 'Unexpected source symlink')
            if path.is_file():
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)


def main():
    os.umask(0o077)
    require(socket.gethostname().split('.')[0] == 'v79sl' and os.getuid() == 1000 and pwd.getpwuid(os.getuid()).pw_name == 'firelion', 'Run as firelion on v79sl')
    before = snapshot()
    print('STAGE=read-only-signed-logo-diagnostic', flush=True)
    diagnostic = json.loads(run(['docker', 'exec', '-i', 'v79marketing-app', 'node', '--input-type=commonjs', '-'], data=LOGO_PROBE.encode()))
    print('LOGO_DIAGNOSTIC=' + json.dumps(diagnostic, separators=(',', ':')), flush=True)
    require(shutil.disk_usage('/home/firelion').free > 4 * 1024**3, 'Insufficient build space')
    root = Path(tempfile.mkdtemp(prefix='v79-g3-ui-build-', dir='/home/firelion'))
    print('BUILD_DIRECTORY=' + str(root), flush=True)
    checkout = root / 'V79hub'
    checkout.mkdir()
    run(['git', 'init', '--quiet', str(checkout)])
    for sha in (COMMIT, BASE_COMMIT):
        run(['git', '-C', str(checkout), 'fetch', '--depth', '1', 'https://github.com/MrFixITslu/V79hub.git', sha], timeout=180)
    run(['git', '-C', str(checkout), 'checkout', '--quiet', '--detach', COMMIT])
    require(run(['git', '-C', str(checkout), 'rev-parse', 'HEAD']).decode().strip() == COMMIT and
            run(['git', '-C', str(checkout), 'rev-parse', 'HEAD^{tree}']).decode().strip() == TREE, 'Candidate commit/tree mismatch')
    changed = run(['git', '-C', str(checkout), 'diff', '--name-only', BASE_COMMIT, COMMIT]).decode().splitlines()
    old = lambda file: json.loads(run(['git', '-C', str(checkout), 'show', BASE_COMMIT + ':' + file]))
    verify_ui_scope(old('package.json'), json.loads((checkout/'package.json').read_text()), old('package-lock.json'),
                    json.loads((checkout/'package-lock.json').read_text()), changed)
    print('UI_ONLY_SOURCE_AND_UNCHANGED_RUNTIME_DEPENDENCIES_PASS', flush=True)
    readable_source(checkout)
    print('STAGE=build-pinned-hub-ui-candidate', flush=True)
    run(['docker', 'build', '--build-arg', 'NODE_BASE=' + NODE_BASE, '--label', 'org.opencontainers.image.revision=' + COMMIT,
         '--tag', TAG, str(checkout)], visible=True, timeout=1800)
    image = json.loads(run(['docker', 'image', 'inspect', TAG]))[0]
    require(image['Config']['Labels'].get('org.opencontainers.image.revision') == COMMIT, 'Candidate image revision mismatch')
    print('STAGE=isolated-ui-and-approval-boundary-tests', flush=True)
    run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--user', 'node', '--cap-drop', 'ALL',
         '--security-opt', 'no-new-privileges', '--memory', '768m', '--cpus', '2', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
         '--env', 'NODE_OPTIONS=--import=./tests/isolated-env.mjs', '--entrypoint', 'node', image['Id'], '--test',
         'tests/marketing-production-panel.test.mjs', 'tests/marketing-production-routes.test.mjs',
         'tests/workforce-action-routes.test.mjs', 'tests/workforce-actions.test.mjs'], visible=True, timeout=180)
    require(snapshot() == before, 'Live runtime changed during build; inspect before proceeding')
    receipt = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'deploymentPerformed': False,
               'candidate': {'commit': COMMIT, 'tree': TREE, 'image': image['Id'], 'tag': TAG},
               'liveRuntime': before, 'logoDiagnostic': diagnostic, 'sourceScopeVerified': True, 'isolatedTestsPassed': True}
    (root/'ui-build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('HUB_UI_CANDIDATE_BUILD_AND_ISOLATED_TESTS_PASS')
    print('CANDIDATE_IMAGE=' + image['Id'])
    print('BUILD_RECEIPT=' + str(root/'ui-build-receipt.json'))
    print('LIVE_CONTAINERS_UNCHANGED_PUBLICATION_DISABLED')
    print('HUB_UI_DEPLOYMENT_STILL_REQUIRED')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('STOP: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__))
        print('NO_LIVE_RECREATION_ATTEMPTED')
        raise SystemExit(1)
