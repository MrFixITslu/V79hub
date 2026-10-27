#!/usr/bin/env python3
"""Read-only workforce activation evidence. No schedules, data or services changed."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

CONTAINERS = ('v79-hub', 'v79-business-agent', 'v79-hub-postgres', 'v79-tiquet-manager', 'tiquet-postgres')
TIMERS = ('v79-workforce-morning.timer', 'v79-workforce-evening.timer', 'v79-g2-approved-task-worker.timer')
SERVICES = ('v79-workforce-briefing@morning.service', 'v79-workforce-briefing@evening.service', 'v79-g2-approved-task-worker.service')
FLAGS = ('V79_WORKFORCE_ACTIONS_ENABLED', 'V79_WORKFORCE_REPORTS_ENABLED', 'V79_COO_WORKBOARD_ENABLED', 'V79_GOOGLE_WORKFORCE_ENABLED')
NODE_AUDIT = r"""
import fs from 'node:fs';
import crypto from 'node:crypto';
const paths=['server/workforce-actions.mjs','server/workforce-action-routes.mjs','server/workforce-action-store.mjs','server/workforce-delivery.mjs','server/workforce-briefing-route.mjs','server/workforce-python-report-reader.mjs','server/owner-coo-workboard.mjs'];
const out={modules:{},ledger:{state:'unavailable'},reports:{state:'unavailable'}};
for(const p of paths){try{out.modules[p]=crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')}catch{out.modules[p]=null}}
try{
 const {createWorkActionStore}=await import('./server/workforce-action-store.mjs');
 const key=process.env.V79_WORKFORCE_AUDIT_KEY||'';
 if(key.length>=32){const ledger=createWorkActionStore({file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',secret:key,backend:process.env.V79_HUB_STORE_BACKEND||'json',databaseUrl:process.env.DATABASE_URL||''});
 try{const s=await ledger.read();const statuses=['pending','approved','running','succeeded','failed','uncertain','rejected','cancelled'];out.ledger={state:'installed_ledger_read',paused:s.paused,jobs:s.jobs.length,tasks:s.tasks.length,statuses:Object.fromEntries(statuses.map(k=>[k,s.jobs.filter(j=>j.status===k).length]))}}finally{await ledger.close()}}
}catch{}
try{
 const {createPythonBriefingStatus}=await import('./server/workforce-python-report-reader.mjs');
 const directory='/run/v79-workforce-reports';
 const s=await createPythonBriefingStatus({directory})();
 out.reports={state:s.status,count:s.reports.length,latestAt:s.reports[0]?.ranAt||null};
}catch{}
console.log(JSON.stringify(out));
"""

def run(args, timeout=20):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('UNAVAILABLE')
    return p.stdout


def inspect_containers():
    result = {}
    for name in CONTAINERS:
        try:
            info = json.loads(run(['docker', 'inspect', name]))[0]
            env = dict(v.split('=', 1) for v in info.get('Config', {}).get('Env', []) if '=' in v)
            row = {'id': info['Id'], 'image': info['Image'], 'running': info['State']['Running'],
                   'health': info['State'].get('Health', {}).get('Status', 'not_configured')}
            if name == 'v79-hub':
                row['flags'] = {k: 'enabled' if env.get(k) == '1' else 'disabled' for k in FLAGS}
                # File source paths and contents are never returned.
                row['worker_token_mount_readonly'] = any(m.get('Destination') == env.get('V79_WORKFORCE_TOKEN_FILE', '/run/secrets/v79-workforce-token') and m.get('RW') is False for m in info.get('Mounts', []))
                row['report_mount_readonly'] = any(m.get('Destination') == '/run/v79-workforce-reports' and m.get('RW') is False for m in info.get('Mounts', []))
            result[name] = row
        except Exception:
            result[name] = {'state': 'unavailable'}
    return result


def unit_status(name):
    allowed = ('LoadState', 'ActiveState', 'UnitFileState', 'Result', 'ExecMainStatus', 'LastTriggerUSec', 'NextElapseUSecRealtime')
    try:
        raw = run(['systemctl', '--user', 'show', name, '--no-pager'] + ['--property=' + p for p in allowed])
        return {k: v for line in raw.splitlines() if '=' in line for k, v in [line.split('=', 1)] if k in allowed}
    except Exception:
        return {'state': 'unavailable'}


def worker_status(home):
    root = home / '.local/share/v79-approved-task-worker'
    # Presence of any latch, including broken symlink, requires reconciliation.
    latch = os.path.lexists(root / 'uncertain.json')
    result = {'uncertainty_latch': latch, 'last_result': 'unavailable', 'status_age_seconds': None}
    p = root / 'status.json'
    try:
        st = p.lstat()
        if p.is_symlink() or not p.is_file() or st.st_mode & 0o077 or st.st_size > 4096:
            return result
        raw = json.loads(p.read_text())
        if raw.get('operation') == 'create_work_item' and raw.get('state') in ('idle', 'succeeded'):
            result['last_result'] = raw['state']
            result['status_age_seconds'] = max(0, round(datetime.datetime.now().timestamp() - st.st_mtime))
    except Exception:
        pass
    return result


def main():
    if socket.gethostname() != 'v79sl' or os.getuid() == 0:
        sys.exit('STOP=RUN_AS_FIRELION_ON_V79SL')
    context = json.loads(run(['docker', 'context', 'inspect']))
    if len(context) != 1 or context[0].get('Endpoints', {}).get('docker', {}).get('Host') not in ('unix:///var/run/docker.sock', 'unix:///run/docker.sock'):
        sys.exit('STOP=LOCAL_DOCKER_CONTEXT_REQUIRED')
    out = {'schema': 1, 'mode': 'read-only', 'checkedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'production_changes': False, 'activation_performed': False,
           'containers': inspect_containers(), 'units': {n: unit_status(n) for n in TIMERS + SERVICES},
           'worker': worker_status(Path.home()), 'runtime': {'state': 'unavailable'}}
    try:
        out['linger'] = run(['loginctl', 'show-user', str(os.getuid()), '--property=Linger', '--value']).strip() == 'yes'
    except Exception:
        out['linger'] = None
    try:
        raw = run(['docker', 'exec', '-w', '/app', 'v79-hub', 'node', '--input-type=module', '-e', NODE_AUDIT], timeout=30)
        out['runtime'] = json.loads(raw)
    except Exception:
        pass
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.exit('PREFLIGHT=UNAVAILABLE_NO_CHANGES')
