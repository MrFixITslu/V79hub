#!/usr/bin/env python3
"""Read-only diagnosis of the 17 October rollout; prints no configuration values."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
import subprocess
import sys

RUN = Path('/home/firelion/v79-portfolio-rollout.W8DQrYJI')
BLOB = 'ee80c9a9d45bf897580776d5f005bd2b83f0e680'

def delta(before, after, path='runtime'):
    out = []
    if before == after:
        return out
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            # Keys may be attacker-controlled; never print arbitrary key text.
            label = key if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,100}', key) else 'REDACTED_KEY'
            child = path + '.' + label
            if key not in before or key not in after:
                out.append({'field': child, 'kind': 'KEY_SET_CHANGED'})
            else:
                out.extend(delta(before[key], after[key], child))
    elif isinstance(before, list) and isinstance(after, list):
        canonical = lambda values: sorted(json.dumps(v, sort_keys=True) for v in values)
        kind = 'ORDER_ONLY' if canonical(before) == canonical(after) else 'LIST_CONTENT_CHANGED'
        out.append({'field': path, 'kind': kind})
    else:
        out.append({'field': path, 'kind': 'VALUE_CHANGED'})
    return out

def report(name, original, current, candidate, fingerprint):
    state = current.get('State', {})
    status = state.get('Status', '')
    health = state.get('Health', {}).get('Status', '')
    image = current.get('Image', '')
    return {'container': name, 'state': status if status in ('running', 'exited', 'created', 'restarting', 'dead', 'paused') else 'UNKNOWN',
            'health': health if health in ('healthy', 'unhealthy', 'starting') else 'NO_HEALTHCHECK',
            'image': image if re.fullmatch(r'sha256:[a-f0-9]{64}', image) else 'UNKNOWN',
            'image_set': 'ORIGINAL' if image == original['Image'] else 'CANDIDATE' if image == candidate else 'OTHER',
            'original_container_id_retained': original.get('Id') == current.get('Id'),
            'runtime_differences': delta(fingerprint(original), fingerprint(current))}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        result = delta({'host': {'Binds': ['PRIVATE_MARKER_A', 'PRIVATE_MARKER_B']}, 'env': {'PASSWORD': 'PRIVATE_MARKER'}},
                       {'host': {'Binds': ['PRIVATE_MARKER_B', 'PRIVATE_MARKER_A']}, 'env': {'PASSWORD': 'PRIVATE_CHANGED'}})
        assert {'field': 'runtime.host.Binds', 'kind': 'ORDER_ONLY'} in result
        assert {'field': 'runtime.env.PASSWORD', 'kind': 'VALUE_CHANGED'} in result
        assert 'PRIVATE_' not in json.dumps(result)
        assert delta({'x': [1, 2]}, {'x': [1, 3]})[0]['kind'] == 'LIST_CONTENT_CHANGED'
        assert delta({'x': 1}, {'x': 1}) == []
        print('ROLLOUT_DIAGNOSTIC_SELF_TEST=PASS')
        return
    if socket.gethostname() != 'v79sl':
        raise RuntimeError('WRONG_HOST')
    source = (RUN / 'rollout.py').read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if actual != BLOB:
        raise RuntimeError('HELPER_INTEGRITY_CHANGED')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('verified_rollout', RUN / 'rollout.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    before = json.loads((RUN / 'runtime-before.json').read_text())
    manifest = json.loads((RUN / 'checkpoint/manifest.json').read_text())
    names = ('v79-hub', 'v79-tiquet-manager', 'v79-hub-postgres', 'tiquet-postgres', 'v79-business-agent')
    p = subprocess.run(['docker', 'container', 'inspect', *names], stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=30)
    if p.returncode:
        raise RuntimeError('CONTAINER_INSPECT_FAILED')
    rows = {x['Name'].lstrip('/'): x for x in json.loads(p.stdout)}
    for name in names:
        print(json.dumps(report(name, before[name], rows[name], manifest['candidates'].get(name), helper.fingerprint), sort_keys=True))
    code = (RUN / 'exit-code').read_text().strip()
    print('WORKER_EXIT_CODE=' + (code if code in ('0', '1') else 'UNKNOWN'))
    print('ROLLOUT_DIAGNOSTIC=READ_ONLY_COMPLETE')
    print('R1_CUSTOMER_RELEASE=NO_GO')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('STOP=ROLLOUT_DIAGNOSTIC_FAILED_REDACTED')
        sys.exit(1)
