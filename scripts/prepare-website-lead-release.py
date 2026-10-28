#!/usr/bin/env python3
"""Prepare private configuration inputs only. No live files or Docker mutations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile

CANDIDATES = {
    'v79-hub': ('2e5f872914bb85f98651ce00a4a90b1880e44076',
        'sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec'),
    'V79website': ('43de17780357e776c86a7f8898168a50fa5e2820',
        'sha256:a5ef48c1b1a4dfd29fe33b19f689adae4ca1d1ed344e2bef8b6a16c1684a848c'),
}


def require(ok, code):
    if not ok:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def environment(row):
    pairs = [s.split('=',1) for s in row['Config']['Env'] or []]
    require(all(len(p) == 2 for p in pairs) and len(dict(pairs)) == len(pairs), 'INVALID_ENVIRONMENT')
    return dict(pairs)


def prepare_models(name, row, model, organization, secret):
    labels = row['Config'].get('Labels') or {}
    service = labels.get('com.docker.compose.service')
    require(service in model.get('services',{}), 'COMPOSE_SERVICE_UNAVAILABLE')
    live = environment(row)
    declared = model['services'][service].get('environment') or {}
    require(isinstance(declared,dict) and all(v is not None and str(v) == live.get(k)
        for k,v in declared.items()), 'DECLARED_LIVE_ENVIRONMENT_DIFFERS')
    changes = ({'V79_WEBSITE_EVENTS_ENABLED':'1','V79_WEBSITE_EVENT_SECRET':secret,
        'V79_WEBSITE_ORGANIZATION_REF':organization} if name == 'v79-hub' else
        {'V79_HUB_EVENT_SECRET':secret,'V79_HUB_ORGANIZATION_REF':organization,
         'V79_HUB_EVENT_REPLAY_LEAD_IDS':'2'})
    if name == 'V79website':
        from urllib.parse import urlparse
        endpoint = urlparse(live.get('V79_HUB_EVENT_URL',''))
        require(endpoint.scheme in ('http','https') and endpoint.hostname == 'v79-hub'
            and endpoint.port == 3040 and endpoint.path == '/api/platform/events'
            and not endpoint.username and not endpoint.password and not endpoint.query
            and not endpoint.fragment, 'HUB_EVENT_ENDPOINT_NOT_INTERNAL_EXPECTED')
    rollback = copy.deepcopy(model)
    rollback['services'][service]['image'] = row['Image']
    # Preserve exact observed effective environment, including image defaults.
    rollback['services'][service]['environment'] = dict(live)
    candidate = copy.deepcopy(rollback)
    candidate['services'][service]['image'] = CANDIDATES[name][1]
    candidate['services'][service]['environment'].update(changes)
    require(set(candidate['services']) == set(model['services']), 'SERVICE_SCOPE_CHANGED')
    return {'service':service,'candidate':candidate,'rollback':rollback,
        'approved_environment_keys':sorted(changes)}


def main():
    os.umask(0o077)
    root = None
    def run(args):
        p = subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
        require(p.returncode == 0, 'READ_ONLY_COMMAND_FAILED')
        return p.stdout
    try:
        ids = run(['docker','ps','--all','-q']).decode().split()
        rows = json.loads(run(['docker','inspect',*ids]))
        by_name = {r['Name'].lstrip('/'):r for r in rows}
        for name,(revision,image) in CANDIDATES.items():
            require(name in by_name, 'TARGET_CONTAINER_UNAVAILABLE')
            row = by_name[name]
            require(row['State'].get('Running') and row['State'].get('Health',{}).get('Status') == 'healthy',
                'TARGET_NOT_HEALTHY')
            selected = json.loads(run(['docker','image','inspect',image]))[0]
            require(selected['Id'] == image and selected.get('Os') == 'linux'
                and selected.get('Architecture') == 'amd64' and
                (selected['Config'].get('Labels') or {}).get('org.opencontainers.image.revision') == revision,
                'CANDIDATE_PIN_MISMATCH')
        hub = by_name['v79-hub']
        node = """const fs=require('fs'),p=require('path');
const e=process.env;
if(e.V79_HUB_ADMIN_EMAIL!=='vision79slu@gmail.com'||e.V79_REQUIRE_ADMIN_MFA!=='1')process.exit(2);
const x=JSON.parse(fs.readFileSync(p.join(e.DATA_DIR||'/app/data','pos-identity.json'),'utf8'));
if(!x.ownerUserId||typeof x.organizationId!=='string')process.exit(3);
console.log(JSON.stringify({organizationId:x.organizationId}));"""
        identity = json.loads(run(['docker','exec',hub['Id'],'node','-e',node]))
        organization = identity['organizationId']
        require(re.fullmatch(r'[0-9a-fA-F-]{36}',organization) is not None, 'PLATFORM_ORGANIZATION_INVALID')
        secret = secrets.token_hex(32)
        prepared = {}
        for name in CANDIDATES:
            row = by_name[name]
            labels = row['Config'].get('Labels') or {}
            directory = labels.get('com.docker.compose.project.working_dir','')
            project = labels.get('com.docker.compose.project','')
            files = labels.get('com.docker.compose.project.config_files','').split(',')
            envfiles = labels.get('com.docker.compose.project.environment_file','')
            require(directory.startswith('/') and project and files and all(p.startswith('/') for p in files),
                'COMPOSE_PROVENANCE_MISSING')
            require(all(Path(p).is_file() for p in files), 'COMPOSE_INPUT_MISSING')
            args = ['docker','compose','--project-directory',directory,'--project-name',project]
            for p in envfiles.split(',') if envfiles else []:
                require(p.startswith('/') and Path(p).exists(), 'COMPOSE_ENVIRONMENT_INPUT_MISSING')
                args += ['--env-file',p]
            for p in files:
                args += ['-f',p]
            model = json.loads(run([*args,'config','--format','json']))
            prepared[name] = {**prepare_models(name,row,model,organization,secret),
                'directory':directory,'project':project,'ordered_files':files,
                'compose_version':run(['docker','compose','version','--short']).decode().strip()}
        # Recheck identities/config after collection. Do not bless a moving baseline.
        current = json.loads(run(['docker','inspect',*[r['Id'] for r in rows]]))
        fields = ('Id','Image','Config','HostConfig','Mounts')
        require(all({k:r.get(k) for k in fields} == {k:c.get(k) for k in fields}
                    for r,c in zip(rows,current)), 'BASELINE_CHANGED_DURING_PREPARATION')
        require(all(r['NetworkSettings'].get('Networks') == c['NetworkSettings'].get('Networks')
            and (r['State']['Status'],r['State'].get('StartedAt')) ==
                (c['State']['Status'],c['State'].get('StartedAt')) for r,c in zip(rows,current)),
            'BASELINE_CHANGED_DURING_PREPARATION')
        root = Path(tempfile.mkdtemp(prefix='v79-lead-release-',dir=Path.home()))
        baseline = {r['Name'].lstrip('/'):r for r in rows}
        payload = {'schema':'v79-website-lead-configuration-inputs-v1','baseline':baseline,
            'prepared':prepared,'organization':organization,'credential':secret,
            'selected_lead_id':2,'engine_bound':False,'deployed':False}
        raw = json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
        fd = os.open(root/'configuration-inputs.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        fd = os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        print(json.dumps({'result':'PASS_RELEASE_CONFIGURATION_PREPARED_ONLY',
            'directory':str(root),'inputs_sha256':hashlib.sha256(raw).hexdigest(),
            'selected_lead_id':2,'candidate_images':{n:p[1] for n,p in CANDIDATES.items()},
            'approved_environment_keys':{n:p['approved_environment_keys'] for n,p in prepared.items()},
            'protected_container_count':len(rows)-2,'engine_bound':False,'deployed':False},indent=2))
    except Exception as error:
        reason = str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z_]+',str(error)) else type(error).__name__
        print(json.dumps({'result':'STOP','reason':reason,'deployed':False}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
