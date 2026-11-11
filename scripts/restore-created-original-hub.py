#!/usr/bin/env python3
"""Start only the verified never-started original Hub after incomplete rollback."""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import sys
import time

ROOT=Path('/home/firelion/.v79-hardened-pair-releases/pair-20261025T204350Z-7a93ff4e6be0')
HELPER_SHA='71eccaba9831836c67807ea00a6a79067f97a146b951407dd69c8063f7d12d13'
PLAN_SHA='347a83d8b4334e37fd25f532b128f574096ade178db4f72703fabe5ae53b42a8'


class Refused(ValueError):pass


def need(value,reason):
    if not value:raise Refused(reason)


def checked_entry(transaction,plan,row,*,before_start):
    entry=copy.deepcopy(plan['apps']['v79-hub'])
    need(row['Image']==entry['rollback_image']['Id']==entry['baseline']['Image'],'ORIGINAL_HUB_IMAGE_REQUIRED')
    need(row['Name']=='/v79-hub' and row['Id']!=entry['baseline']['Id'],'EXACT_RECREATED_HUB_REQUIRED')
    if before_start:
        need(row['State'].get('Status')=='created' and not row['State'].get('Running')
             and str(row['State'].get('StartedAt','')).startswith('0001')
             and row.get('RestartCount',0)==0,'NEVER_STARTED_CREATED_HUB_REQUIRED')
    replacement=(row['Config'].get('Labels') or {}).get('com.docker.compose.replace')
    need(replacement is None or isinstance(replacement,str),
         'UNEXPECTED_REPLACEMENT_BOOKKEEPING_TYPE')
    # This transient Compose label is not independent evidence of the replaced
    # container. It alone is excluded from identity proof; all effective runtime,
    # image, process, environment, security, data mounts and other labels remain
    # checked against the sealed original profile by unchanged comparison code.
    entry['_replaced_id']=replacement
    transaction.runtime_matches(entry['baseline'],row,entry,'rollback',selinux_enabled=plan['selinux_enabled'])
    return entry


def expected_failure(original):
    need(json.loads(original.private_file(ROOT/'outcome.json'))=={
        'reason':'ROLLBACK_INCOMPLETE_OPERATOR_REQUIRED','release_decision':'HOLD','status':'BLOCKED'},
        'EXPECTED_FAILED_ROLLBACK_RECEIPT_REQUIRED')
    need(original.private_file(ROOT/'exit-code').strip()==b'0','FAILED_WORKER_NOT_CONFIRMED_EXITED')
    events=[json.loads(line) for line in original.private_file(ROOT/'events.jsonl').splitlines()]
    need([(e.get('event'),e.get('app')) for e in events]==[
        ('TIMERS_PAUSE_INTENT',None),('CANDIDATE_INTENT','v79-hub'),('CANDIDATE_FAILED','v79-hub'),
        ('ROLLBACK_INTENT','v79-hub'),('ROLLBACK_FAILED','v79-hub'),('ROLLBACK_INCOMPLETE',None),
        ('TIMERS_HELD_OPERATOR_REVIEW_REQUIRED',None)],'FAILED_ATTEMPT_JOURNAL_CHANGED')


def health_script(port,path,expected):
    # HTTP stays inside this exact container's network namespace. No proxy,
    # credentials, external requests, environment dump or host-port assumption.
    url='http://127.0.0.1:'+str(port)+path
    return """const http=require('node:http');
const req=http.get(URL_VALUE,res=>{let raw='';res.on('data',part=>{raw+=part;if(raw.length>65536)req.destroy();});
res.on('end',()=>{let status;try{status=JSON.parse(raw).status;}catch{}
const ok=res.statusCode===200&&status===STATUS_VALUE;
console.log(JSON.stringify({http:res.statusCode,status:ok?status:'UNEXPECTED'}));process.exit(ok?0:2);});});
req.setTimeout(6000,()=>req.destroy());req.on('error',()=>{console.log(JSON.stringify({status:'UNAVAILABLE'}));process.exit(2);});
""".replace('URL_VALUE',json.dumps(url)).replace('STATUS_VALUE',json.dumps(expected))


def internal_health_pair(original,backend,plan):
    proof={}
    for name,port,path,expected in (
        ('v79-hub',3040,'/api/health','ok'),
        ('v79-tiquet-manager',3050,'/health','healthy')):
        row=backend.inspect(name)
        need(row['Image']==plan['apps'][name]['rollback_image']['Id']
             and row['State'].get('Running') and row['State'].get('Health',{}).get('Status')=='healthy',
             'ORIGINAL_HEALTHY_IMAGE_REQUIRED_FOR_INTERNAL_HTTP')
        need(str(port)+'/tcp' in (row['Config'].get('ExposedPorts') or {}),'EXPECTED_INTERNAL_PORT_NOT_DECLARED')
        print('RECOVERY=CHECKING_INTERNAL_HTTP_'+name,flush=True)
        try:raw=original.call(['docker','exec',row['Id'],'node','-e',health_script(port,path,expected)])
        except Exception:raise Refused('INTERNAL_HTTP_CHECK_FAILED_'+name.upper().replace('-','_')) from None
        result=json.loads(raw)
        need(result=={'http':200,'status':expected},'INTERNAL_HTTP_STATUS_MISMATCH')
        need(backend.inspect(name)['Id']==row['Id'],'CONTAINER_CHANGED_DURING_INTERNAL_HTTP_CHECK')
        proof[name]={'container_id':row['Id'],'http':200,'status':expected,'scope':'CONTAINER_LOOPBACK'}
    return proof


def restore(helper,*,finish_running=False):
    args=argparse.Namespace(attempt=str(ROOT),helper_sha256=HELPER_SHA,server_rollback=True,plan_sha256=PLAN_SHA)
    _,original,transaction,plan,backend=helper.validate(args)
    result={'status':'BLOCKED','release_decision':'HOLD','hub_start_requested':False,
        'containers_recreated':False,'application_data_restored':False,'images_loaded':False,
        'replacement_label_independently_verified':False}
    with original.release_lock():
        try:
            expected_failure(original);backend.check_files();backend.protected()
            def tiquet_unchanged():
                row=backend.inspect('v79-tiquet-manager')
                need(transaction.protected_fingerprint(row)==transaction.protected_fingerprint(
                    plan['apps']['v79-tiquet-manager']['baseline'])
                    and row['State'].get('Health',{}).get('Status')=='healthy','UNTOUCHED_TIQUET_CHANGED')
            tiquet_unchanged()
            for timer in original.TIMERS:
                need(original.call(['systemctl','--user','show',timer,'--value','-p','ActiveState']).decode().strip()=='inactive',
                     'EXPECTED_HELD_TIMER_STATE_CHANGED')
            row=backend.inspect('v79-hub')
            if finish_running:
                need(row['State'].get('Running') and row['State'].get('Health',{}).get('Status')=='healthy',
                     'RUNNING_HEALTHY_ORIGINAL_HUB_REQUIRED')
            checked_entry(transaction,plan,row,before_start=not finish_running)
            target=row['Id'];fingerprint=transaction.protected_fingerprint(row)
            need(transaction.protected_fingerprint(backend.inspect(target))==fingerprint,'HUB_CHANGED_BEFORE_START')
            backend.protected();tiquet_unchanged()
            if not finish_running:
                print('RECOVERY=STARTING_VERIFIED_EXISTING_ORIGINAL_HUB_ONLY',flush=True)
                result['hub_start_requested']=True
                original.call(['docker','start',target])
            deadline=time.monotonic()+180
            while True:
                current=backend.inspect(target)
                need(current['Id']==target and current['Image']==row['Image'],'STARTED_HUB_IDENTITY_CHANGED')
                if current['State'].get('Health',{}).get('Status')=='healthy' and current['State'].get('Running'):break
                need(current['State'].get('Status') not in ('exited','dead','removing'),'ORIGINAL_HUB_STARTUP_FAILED')
                need(time.monotonic()<deadline,'ORIGINAL_HUB_HEALTH_TIMEOUT')
                time.sleep(2)
            checked_entry(transaction,plan,current,before_start=False)
            backend.protected();tiquet_unchanged()
            http_proof=internal_health_pair(original,backend,plan)
            print('RECOVERY=ORIGINAL_HUB_AND_BOTH_INTERNAL_HTTP_HEALTH_CHECKS_PASS',flush=True)
            original.timers_resume()
            backend.protected();tiquet_unchanged()
            result.update(status='PASS_ORIGINAL_SERVICES_HEALTHY_TIMERS_RESUMED',hub_container_id=target,
                hub_image=current['Image'],hub_health='healthy',internal_http_health_pair=True,
                internal_http_proof=http_proof,host_port_changes_made=False,
                tiquet_unchanged=True,protected_services_unchanged=True,timers_resumed=True,
                original_runtime_checks=True)
        except BaseException as error:
            result['reason']=original.safe_reason(error)
            # A failed later check never stops a restored Hub or restarts other
            # applications. Record the actual state without config/secret data.
            try:
                row=backend.inspect('v79-hub',allow_missing=True)
                result['hub_observed_state']=None if row is None else row['State'].get('Status')
                result['hub_observed_health']=None if row is None else row['State'].get('Health',{}).get('Status')
            except Exception:result['hub_observed_state']='READ_UNAVAILABLE'
        receipt=ROOT/('original-hub-start-recovery-'+secrets.token_hex(6)+'.json')
        result['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        original.write_new(receipt,result)
        print('RECOVERY_RECEIPT='+str(receipt),flush=True)
        print(json.dumps(result,indent=2),flush=True)
        return result


def main():
    sys.dont_write_bytecode=True
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finish-running',action='store_true')
    mode=parser.parse_args()
    path=ROOT/'continue-frozen-metadata-pair.py'
    need(not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==HELPER_SHA,'HELPER_CHECKSUM_CHANGED')
    spec=importlib.util.spec_from_file_location('verified_recovery_helper',path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return restore(helper,finish_running=mode.finish_running)


if __name__=='__main__':
    try:result=main()
    except BaseException as error:
        reason=str(error)
        print(json.dumps({'status':'BLOCKED','reason':reason if re.fullmatch('[A-Z][A-Za-z0-9_:,.]{0,500}',reason)
                         else 'RECOVERY_BLOCKED_REDACTED','release_decision':'HOLD'}),flush=True)
        raise SystemExit(2)
    raise SystemExit(0 if result['status'].startswith('PASS_') else 2)
