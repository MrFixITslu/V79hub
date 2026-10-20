#!/usr/bin/env python3
"""Print configuration presence only. No secrets, writes, OAuth consent or deployments."""
import json
import os
import subprocess


def run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def main():
    print('MODE=READ_ONLY_GOOGLE_WORKFORCE_PREFLIGHT')
    print('HOST=' + os.uname().nodename)
    result = run(['docker', 'inspect', 'v79-hub', 'v79-business-agent'])
    if result is None or result.returncode:
        print('CONTAINER_INSPECTION=UNAVAILABLE')
    else:
        for container in json.loads(result.stdout):
            print('CONTAINER=' + container['Name'].lstrip('/'))
            print('IMAGE=' + container['Image'])
            print('STATE=' + container.get('State', {}).get('Status', 'unknown'))
            print('HEALTH=' + container.get('State', {}).get('Health', {}).get('Status', 'not-configured'))
            env = dict(item.split('=', 1) for item in container['Config'].get('Env', []) if '=' in item)
            matches = [(key, value) for key, value in sorted(env.items()) if any(
                term in key.upper() for term in ['GOOGLE', 'GMAIL', 'OAUTH', 'WORKFORCE', 'COO_WORKBOARD'])]
            if not matches:
                print('GOOGLE_WORKFORCE_ENV=NO_MATCHING_KEYS')
            for key, value in matches:
                safe = value if key.endswith('_ENABLED') and value in ('0', '1', 'true', 'false') else ('PRESENT' if value else 'EMPTY')
                print(key + '=' + safe)
    timers = run(['systemctl', '--user', 'list-timers', '--all', '--no-pager', '--plain'])
    if timers is None or timers.returncode:
        print('WORKFORCE_TIMER_INSPECTION=UNAVAILABLE')
    else:
        lines = [line for line in timers.stdout.splitlines() if 'v79' in line.lower()]
        for line in lines:
            print('TIMER=' + line.strip())
        if not lines:
            print('WORKFORCE_TIMERS=NONE_LISTED')
    print('GOOGLE_ACCESS=NOT_TESTED')
    print('CONFIGURATION_PRESENCE_IS_NOT_AUTHORIZATION=YES')
    print('PRODUCTION_CHANGED=NO')


if __name__ == '__main__':
    main()

