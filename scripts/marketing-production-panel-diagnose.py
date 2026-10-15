#!/usr/bin/env python3
"""Read-only stage diagnostics; no deployment, configuration changes or retries."""
import hashlib
import json
import urllib.request

COMMIT = '9fa271d7cb9ef676105f051abe0c09bd1b177275'
EXPECTED = '4f33569fe8051a78a7c276e52d5346402a822e20a25a93270c23bb61190fabb9'


def main():
    url = 'https://raw.githubusercontent.com/MrFixITslu/V79hub/' + COMMIT + '/scripts/marketing-production-panel-cutover.py'
    with urllib.request.urlopen(url, timeout=30) as response:
        code = response.read(1048577)
    if hashlib.sha256(code).hexdigest() != EXPECTED:
        raise RuntimeError('Pinned diagnostic support integrity mismatch')
    ns = {'__name__': 'read_only_ui_diagnostic'}
    exec(compile(code, '<verified-read-only-support>', 'exec'), ns)
    builder, support = [ns['load_helper'](spec) for spec in ns['HELPERS']]
    ns['helper'] = support
    checks = [
        ('live-container-snapshot', builder['snapshot']),
        ('candidate-image-inspection', lambda: support['run'](['docker', 'image', 'inspect', ns['IMAGE']])),
        ('original-compose-resolution', lambda: ns['resolve'](ns['FILES'])),
        ('hub-protected-state-read', lambda: support['protected_state']('v79-hub-postgres')),
        ('marketing-protected-state-read', lambda: support['sqlite_state']('v79marketing-app')),
        ('signed-campaign-idle-check', ns['semantic_marketing']),
    ]
    for label, check in checks:
        try:
            check()
            print('READ_ONLY_CHECK_PASS=' + label, flush=True)
        except Exception as exc:
            print('READ_ONLY_CHECK_FAIL=' + label + '; error_type=' + type(exc).__name__, flush=True)
    original = 'configRevision:state.configRevision,'
    replacement = (original + 'automaticDrafts:state.plan?.automaticDrafts,paused:state.paused,'
                   "queuedPackages:state.jobs.filter(j=>j.status==='queued').length,"
                   "generatingPackages:state.jobs.filter(j=>j.status==='generating').length,"
                   "runningDeliveries:state.jobs.flatMap(j=>j.deliveries).filter(d=>d.status==='running').length,"
                   'lastAutomaticAt:state.lastAutomaticAt,cadenceDays:state.plan?.cadenceDays,')
    probe = builder['LOGO_PROBE']
    if probe.count(original) != 1:
        raise RuntimeError('Reviewed read-only probe differs')
    try:
        result = json.loads(support['run'](['docker', 'exec', '-i', 'v79marketing-app', 'node', '--input-type=commonjs', '-'], data=probe.replace(original, replacement).encode()))
        print('SIGNED_PRODUCTION_METADATA=' + json.dumps(result, separators=(',', ':')))
    except Exception as exc:
        print('SIGNED_PRODUCTION_METADATA_FAILED=' + type(exc).__name__)
    print('CUTOVER_DIRECTORY_EXISTS=' + str(ns['WORK'].exists()).lower())
    print('LIVE_SWITCH_MARKER_EXISTS=' + str((ns['WORK']/'switch-attempted.json').exists()).lower())
    print('READ_ONLY_DIAGNOSTIC_COMPLETE_NO_DEPLOYMENT_ATTEMPTED')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('STOP: read-only diagnostic failed; error_type=' + type(exc).__name__)
        raise SystemExit(1)
