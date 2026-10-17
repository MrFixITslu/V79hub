#!/usr/bin/env python3
"""Prepare private frozen plans for remaining releases; no builds or live switches."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile

ACCEPTED_RUN = Path('/home/firelion/v79-portfolio-rollout.6kvFDd5e')
HELPER_BLOB = '6a3a5bd30f4e66b3415891f654a7e142d04dbd79'
SOURCES = {'V79acaedmy': '584e07c9f5186e4aa10e87f931b2ea7194db93d4',
           'V79POS': 'e4bf7620f5e6c5cc2e3a6c12d14bb441bf15de37',
           'Gaming-Studio-J': '17bb9eadf44c4e2892cb4bb77810d3b7f957dea1'}
PINS = {
 'v79_course_builder': {'container':'v79_course_builder', 'repo':'V79acaedmy', 'compose_project':'v79-course-builder', 'compose_service':'course-builder',
   'image_id':'sha256:f9ab28a4b25fed0445a93e6f3b1548ed2706d9ec7a57176152236fa8708005d0',
   'compose_inputs':[{'path':'/home/firelion/V79-Course-Builder/docker-compose.yml','sha256':'d3816cbb32bdd9d2cb73ad0f87162e189d983a576af1d5d2488a3d01e2d1e50d'}]},
 'v79-pos': {'container':'v79-pos', 'repo':'V79POS', 'compose_project':'v79pos', 'compose_service':'api',
   'image_id':'sha256:4f864f323e8a9d1d98dd1f26caf82d9b223412115fed7cb154c2d0e0158b88f8',
   'compose_inputs':[{'path':'/home/firelion/v79pos/docker-compose.yml','sha256':'1387085157b4f25fefc799694aacbc8452097906ebfbc3894808ea359a93e264'}]},
 'v79-pos-worker': {'container':'v79-pos-worker', 'repo':'V79POS', 'compose_project':'v79pos', 'compose_service':'worker',
   'image_id':'sha256:24279f6e693a66dca8bdb47f0e0e072d00983a67e74cc5e55a87ea5ecbf5c19d',
   'compose_inputs':[{'path':'/home/firelion/v79pos/docker-compose.yml','sha256':'1387085157b4f25fefc799694aacbc8452097906ebfbc3894808ea359a93e264'}]},
 'gaming-studio-j': {'container':'gaming-studio-j', 'repo':'Gaming-Studio-J', 'compose_project':'gaming-studio-j', 'compose_service':'gaming-studio-j',
   'image_id':'sha256:4039d9ab72c0cc99c5d18c92714678a9a8e05ef26177e85bbe3d56da834b07e7',
   'compose_inputs':[{'path':'/home/firelion/Gaming-Studio-J/docker-compose.yml','sha256':'552a9c62afd66cf68cf60de0de0274129d98102ea60e03030961bf0115912a6b'}]},
}
POS_MIGRATIONS = {'20260925_baseline':'e4b31c44e021cd1986a291e3addafbb0662e29262047f6fca5aeec94660fa7d4'}
DB_IMAGE = 'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24'

class Stop(Exception): pass

def need(value, code):
    if not value: raise Stop(code)

def safe_code(error):
    trusted = isinstance(error,Stop) or type(error).__module__=='verified_rollout' and type(error).__name__=='Stop'
    if not trusted: return 'PREFLIGHT_ERROR_REDACTED'
    value = str(error)
    return value if re.fullmatch(r'[A-Z][A-Z0-9_]{0,100}',value) else 'PREFLIGHT_ERROR_REDACTED'

def load_helper():
    path = ACCEPTED_RUN/'rollout.py'
    need(path.is_file() and not path.is_symlink(), 'VERIFIED_ROLLOUT_HELPER_MISSING')
    data = path.read_bytes()
    digest = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    need(digest == HELPER_BLOB, 'ROLLOUT_HELPER_INTEGRITY_FAILURE')
    spec = importlib.util.spec_from_file_location('verified_rollout',path)
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    return helper

def migration_summary(rows):
    need(isinstance(rows,list), 'MIGRATION_METADATA_INVALID')
    seen = {}; failed = 0
    for row in rows:
        need(isinstance(row,dict) and isinstance(row.get('name'),str)
             and isinstance(row.get('finished'),bool) and isinstance(row.get('rolled_back'),bool)
             and isinstance(row.get('checksum'),str) and re.fullmatch(r'[0-9a-f]{64}',row['checksum']), 'MIGRATION_METADATA_INVALID')
        # Only active, completed entries establish applied migration acceptance.
        if row['rolled_back']:
            continue
        need(row['name'] not in seen, 'DUPLICATE_ACTIVE_MIGRATION')
        seen[row['name']] = row['checksum']
        failed += not row['finished']
    unknown = len(set(seen)-set(POS_MIGRATIONS))
    missing = sorted(set(POS_MIGRATIONS)-set(seen))
    mismatch = sum(seen[name] != digest for name,digest in POS_MIGRATIONS.items() if name in seen)
    return {'expected_migrations':len(POS_MIGRATIONS),'pending_known_migrations':missing,
            'unknown_migration_count':unknown,'checksum_mismatch_count':mismatch,'unfinished_migration_count':failed,
            'status':'PASS' if not (unknown or missing or mismatch or failed) else 'REVIEW_REQUIRED'}

def pos_migrations(helper):
    row = helper.inspect('v79-pos-db')
    need(row['Image']==DB_IMAGE and row['State'].get('Health',{}).get('Status')=='healthy', 'POS_DATABASE_IMAGE_OR_HEALTH_CHANGED')
    prefix = ['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on','v79-pos-db','sh','-c',
              'exec psql -X -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"','readonly-migrations']
    exists = helper.call([*prefix,"SELECT to_regclass('public._prisma_migrations') IS NOT NULL"]).decode().strip()
    need(exists in ('t','f'), 'MIGRATION_TABLE_QUERY_INVALID')
    if exists=='f':
        return {'status':'REVIEW_REQUIRED','migration_table':'ABSENT'}
    query = "SELECT COALESCE(json_agg(json_build_object('name',migration_name,'checksum',checksum,'finished',finished_at IS NOT NULL,'rolled_back',rolled_back_at IS NOT NULL)),'[]'::json) FROM public._prisma_migrations"
    return migration_summary(json.loads(helper.call([*prefix,query])))

def prepare(helper, directory):
    receipt = json.loads((ACCEPTED_RUN/'release-receipt.json').read_text())
    need(receipt.get('health')=='PASS_BOTH', 'LATEST_HUB_TIQUET_RECEIPT_NOT_ACCEPTED')
    for name in ('v79-hub','v79-tiquet-manager'):
        row = helper.inspect(name)
        need(row['Image']==receipt['images'][name] and row['State'].get('Health',{}).get('Status')=='healthy', 'LATEST_HUB_TIQUET_CHANGED')
    print('LATEST_HUB_TIQUET=DEPLOYED_IMAGES_HEALTHY',flush=True)
    before={name:helper.inspect(name) for name in PINS}
    helper.private_json(directory/'runtime-before.json',before)
    results = {}
    for name,pin in PINS.items():
        row=before[name]
        try:
            need(row['Image']==pin['image_id'] and row['State'].get('Running') is True, 'REMAINING_APP_IMAGE_OR_STATE_CHANGED')
            health=(row['State'].get('Health') or {}).get('Status')
            need(health=='healthy' or name=='v79-pos-worker' and health is None, 'REMAINING_APP_NOT_HEALTHY')
            model=helper.original_model(row,pin)
            path=directory/(name+'-original.pinned.yml')
            helper.private_json(path,model)
            rendered=json.loads(helper.call(helper.compose(path,pin['compose_project'],'config','--format','json')))
            service=rendered['services'][pin['compose_service']]
            need(helper.compose_runtime(service.get('environment',{}))==helper.envmap(row['Config'].get('Env')),'FROZEN_ENVIRONMENT_INTERPOLATION_DRIFT')
            helper.validate_storage_and_networks(rendered,service,row)
            results[name]={'runtime_parity':'PASS','current_health':'HEALTHY' if health=='healthy' else 'RUNNING_NO_HEALTHCHECK',
                           'worker_readiness':'NOT_PROVEN' if name=='v79-pos-worker' else 'NOT_APPLICABLE',
                           'source_commit':SOURCES[pin['repo']]}
        except Exception as error:
            results[name]={'runtime_parity':'FAIL','reason':safe_code(error)}
        print(json.dumps({'container':name,**results[name]},sort_keys=True),flush=True)
    try:
        migrations=pos_migrations(helper)
    except Exception as error:
        migrations={'status':'REVIEW_REQUIRED','reason':safe_code(error)}
    print(json.dumps({'pos_migrations':migrations},sort_keys=True),flush=True)
    # Verify preflight itself did not replace or modify any selected live runtime.
    for name,old in before.items():
        now=helper.inspect(name)
        need(now['Id']==old['Id'] and now['Image']==old['Image'] and helper.fingerprint(now)==helper.fingerprint(old), 'LIVE_RUNTIME_CHANGED_DURING_PREFLIGHT')
    complete=all(x['runtime_parity']=='PASS' for x in results.values()) and migrations['status']=='PASS'
    report={'sources':SOURCES,'pins':PINS,'results':results,'pos_migrations':migrations,
            'status':'PLAN_PREPARED_NOT_DEPLOYED' if complete else 'PLAN_REQUIRES_RECONCILIATION'}
    helper.private_json(directory/'plan-summary.json',report)
    print('LIVE_SELECTED_CONTAINERS=UNCHANGED',flush=True)
    print('PLAN_DIRECTORY='+str(directory),flush=True)
    print('REMAINING_ROLLOUT_PREFLIGHT='+('PASS_PLAN_ONLY' if complete else 'REVIEW_REQUIRED'),flush=True)
    print('REMAINING_APPS_DEPLOYED=NO',flush=True)
    print('FULL_PORTFOLIO_BACKUP=NOT_PERFORMED',flush=True)
    print('R1_CUSTOMER_RELEASE=NO_GO',flush=True)
    return 0 if complete else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:
        result=migration_summary([{'name':'PRIVATE_MARKER','checksum':'0'*64,'finished':True,'rolled_back':False}])
        need('PRIVATE_MARKER' not in json.dumps(result) and result['status']=='REVIEW_REQUIRED','REDACTION_TEST_FAILED')
        print('REMAINING_PREFLIGHT_SELF_TEST=PASS');return 0
    need(socket.gethostname()=='v79sl' and os.getuid()!=0,'RUN_ON_V79SL_NON_ROOT')
    os.umask(0o077)
    with (Path.home()/'.v79-portfolio-rollout.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Stop('OTHER_ROLLOUT_OR_DIAGNOSTIC_RUNNING')
        helper=load_helper()
        directory=Path(tempfile.mkdtemp(prefix='v79-remaining-plan.',dir=Path.home()))
        return prepare(helper,directory)

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as error:
        print('STOP='+safe_code(error));sys.exit(1)
