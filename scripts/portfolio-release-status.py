#!/usr/bin/env python3
"""Read-only V79 release metadata. Never output inspect environment or raw errors."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys

TARGET=re.compile(r'(v79|tiquet|fire.finance|ffpro|gaming|lasertag|course|sentinel)',re.I)
def project(row):
    config=row.get('Config') or {}; labels=config.get('Labels') or {}
    state=row.get('State') or {}; raw_health=state.get('Health') or {}
    image=row.get('Image',''); image=image if re.fullmatch(r'sha256:[0-9a-f]{64}',image) else 'UNKNOWN'
    name=row.get('Name','').lstrip('/')
    status=state.get('Status'); health=raw_health.get('Status')
    sha=labels.get('org.opencontainers.image.revision','')
    return {'container':name,'state':status if status in ('running','exited','created','paused','dead','restarting','removing') else 'UNKNOWN',
        'health':health if health in ('healthy','unhealthy','starting') else 'NO_HEALTHCHECK',
        'image_id':image,'image_revision_label':sha if re.fullmatch(r'[0-9a-f]{40}',sha) else 'UNKNOWN',
        'compose_project':labels.get('com.docker.compose.project','UNKNOWN'),
        'compose_service':labels.get('com.docker.compose.service','UNKNOWN'),
        'mount_count':len(row.get('Mounts') or [])}
def run(args):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=40)
    if result.returncode: raise RuntimeError('DOCKER_METADATA_READ_FAILED')
    return result.stdout.decode()
def receipt(row):
    labels=(row.get('Config') or {}).get('Labels') or {}
    root=labels.get('com.docker.compose.project.working_dir','')
    result={'deployed_source_receipt':'UNKNOWN','compose_inputs':[]}
    if root.startswith('/'):
        path=Path(root)/'.deployed_sha'
        if path.is_file() and not path.is_symlink() and path.stat().st_size<=100:
            raw=path.read_text().strip()
            if re.fullmatch(r'[0-9a-f]{40}',raw): result['deployed_source_receipt']=raw
    files=labels.get('com.docker.compose.project.config_files','').split(',')
    for name in files:
        path=Path(name)
        if name and path.is_absolute() and path.is_file() and not path.is_symlink():
            result['compose_inputs'].append({'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return result
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--self-test',action='store_true'); args=parser.parse_args()
    if args.self_test:
        row={'Name':'/v79-synthetic','Image':'sha256:'+'1'*64,'Config':{'Env':['PASSWORD=PRIVATE_SENTINEL'],'Labels':{}},'State':{'Status':'running','Error':'PRIVATE_SENTINEL','Health':{'Status':'healthy','Log':[{'Output':'PRIVATE_SENTINEL'}]}},'Mounts':[{'Source':'PRIVATE_SENTINEL'}]}
        out=json.dumps(project(row)); assert 'PRIVATE_SENTINEL' not in out
        assert project(row)['health']=='healthy'
        assert project({'Name':'/v79-test','State':{'Status':'invented'}})['state']=='UNKNOWN'
        print('PORTFOLIO_RELEASE_METADATA_SELF_TEST=PASS');return
    if socket.gethostname()!='v79sl': raise RuntimeError('RUN_ON_V79SL_ONLY')
    names=[x for x in run(['docker','ps','-a','--format','{{.Names}}']).splitlines() if TARGET.search(x)]
    if not names: raise RuntimeError('NO_V79_CONTAINERS_FOUND')
    rows=json.loads(run(['docker','inspect',*names]))
    for row in rows:
        out=project(row); out.update(receipt(row)); print(json.dumps(out,sort_keys=True))
    print('PORTFOLIO_RELEASE_METADATA=READ_ONLY_COMPLETE')
    print('SOURCE_RECEIPT_IS_NOT_IMAGE_PROVENANCE=YES')
    print('FULL_BACKUP_AND_SECURITY_TESTS=NOT_PERFORMED')
if __name__=='__main__':
    try: main()
    except Exception:
        print('STOP=PORTFOLIO_METADATA_UNAVAILABLE_REDACTED');sys.exit(1)
