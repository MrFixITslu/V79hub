#!/usr/bin/env python3
"""Capture one stopped Hub candidate's label difference; no cutover CLI."""
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT=Path('/home/firelion/v79-lead-release-2pvsb2mo')
SCOPE='v79profile39e19427a15546ab'
BINDER_SHA='06be2308bee4ac1370ba285a27a7c4bb55274eb77d43044b9e990c7104dac29c'
SAFE_LABELS=frozenset(('com.docker.compose.project','com.docker.compose.service',
    'com.docker.compose.container-number','com.docker.compose.oneoff',
    'com.docker.compose.project.working_dir','org.opencontainers.image.revision',
    'org.opencontainers.image.source','org.opencontainers.image.version',
    'org.opencontainers.image.title','org.opencontainers.image.created'))


def label_report(message, before, after, entry=None):
    if not message.startswith('APPLICATION_LABELS_CHANGED:'):return []
    keys=message.split(':',1)[1].split(',')
    first=copy.deepcopy(before['Config'].get('Labels') or {});second=after['Config'].get('Labels') or {}
    if entry:
        previous=entry['rollback_image']['Config'].get('Labels') or {}
        selected=entry['candidate_image']['Config'].get('Labels') or {}
        explicit=entry['model']['services'][entry['service']].get('labels') or {}
        for key in set(previous)|set(selected):
            if key not in explicit:
                if key in selected:first[key]=selected[key]
                else:first.pop(key,None)
    result=[]
    for key in keys:
        row={'key':key} if key in SAFE_LABELS else {'key_sha256':hashlib.sha256(key.encode()).hexdigest()}
        row.update(expected_present=key in first,actual_present=key in second,
            values_equal=first.get(key)==second.get(key))
        if entry:
            if key=='com.docker.compose.project.working_dir':
                row.update(expected_matches_directory=first.get(key)==entry['directory'],
                    actual_matches_directory=second.get(key)==entry['directory'])
            if key=='com.docker.compose.oneoff':
                row.update(expected_is_false=first.get(key)=='False',actual_is_false=second.get(key)=='False')
            row.update(expected_matches_image=first.get(key)==selected.get(key),
                actual_matches_image=second.get(key)==selected.get(key),
                model_explicit=key in explicit)
        result.append(row)
    return result


def narrow(plan):
    result=copy.deepcopy(plan)
    result['protected']['V79website']=result['apps']['V79website']['baseline']
    result['apps']={'v79-hub':result['apps']['v79-hub']}
    return result


class Captured(Exception):pass


def diagnose():
    url='https://raw.githubusercontent.com/MrFixITslu/V79hub/5b42c3de48e1df4c909c73c78c64930a80b05193/scripts/bind-website-lead-release.py'
    with urllib.request.urlopen(url,timeout=30) as response:data=response.read(1_000_000)
    if hashlib.sha256(data).hexdigest()!=BINDER_SHA:raise ValueError('BINDER_DIGEST_CHANGED')
    helpers={'__name__':'binding_helpers'};exec(compile(data,url,'exec'),helpers)
    require=helpers['require'];private=helpers['private'];write=helpers['write'];run=helpers['run']
    require(not ROOT.is_symlink() and ROOT.is_dir() and ROOT.stat().st_uid==os.geteuid()
        and ROOT.stat().st_mode&0o077==0,'PRIVATE_DIRECTORY_REQUIRED')
    lock=os.open(ROOT/'binding.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not (ROOT/'binding-result.json').exists(),'BINDING_ALREADY_PASSED_NO_DIAGNOSTIC')
        require(not (ROOT/'label-diagnostic.json').exists(),'DIAGNOSTIC_ALREADY_CAPTURED')
        inputs_raw=private(ROOT/'configuration-inputs.json')
        require(hashlib.sha256(inputs_raw).hexdigest()==helpers['INPUT_SHA'],'INPUT_DIGEST_CHANGED')
        inputs=json.loads(inputs_raw)
        for name,pin in helpers['MODULES'].items():
            raw=private(ROOT/name)
            require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==pin,
                'ENGINE_MODULE_CHANGED')
        spec=importlib.util.spec_from_file_location('existing_pair_engine',ROOT/'paired-compose-transaction.py')
        engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
        plan_raw=private(ROOT/'transaction.json');plan=json.loads(plan_raw)
        require(set(plan['apps'])==set(helpers['PINS']) and plan.get('requires_supervision') is True,
            'SEALED_SCOPE_CHANGED')
        expected_protected={n:r for n,r in inputs['baseline'].items() if n not in helpers['PINS']}
        require(plan['protected']==expected_protected,'PROTECTED_PLAN_CHANGED')
        for name,entry in plan['apps'].items():
            require(entry['baseline']==inputs['baseline'][name] and entry['release_name']==name
                and entry['candidate_image']['Id']==helpers['PINS'][name][1]
                and entry['rollback_image']['Id']==entry['baseline']['Image'],'BASELINE_PLAN_CHANGED')
            for which in ('candidate','rollback'):
                path=Path(entry[which+'_file'])
                require(path.parent==ROOT,'MODEL_PATH_CHANGED')
                require(json.loads(private(path))==inputs['prepared'][name][which],'MODEL_CONTENT_CHANGED')
        require(run(['docker','compose','version','--short']).decode().strip()=='5.6.1',
            'COMPOSE_VERSION_CHANGED')
        backend=engine.ComposeBackend(ROOT,plan);helpers['protect_core_health'](backend)
        backend.protected();backend.check_files()
        for name,entry in plan['apps'].items():
            require(engine.protected_fingerprint(backend.inspect(name))==engine.protected_fingerprint(entry['baseline']),
                'TARGET_BASELINE_CHANGED')
        names=run(['docker','ps','--all','--format','{{.Names}}']).decode().splitlines()
        volumes=run(['docker','volume','ls','-q','--filter','label=v79.profile.scope='+SCOPE]).decode().splitlines()
        require(not any(n.startswith(SCOPE) for n in names) and not volumes and not (ROOT/SCOPE).exists(),
            'PREVIOUS_SCOPE_RESIDUE_REQUIRES_REVIEW')
        require(not any(p.is_dir() for p in ROOT.glob('v79profile*')),'OTHER_PROFILE_RESIDUE_REQUIRES_REVIEW')
        require(helpers['timer_states']()==plan['workforce_timers'],'WORKFORCE_TIMER_STATE_CHANGED')
        print(json.dumps({'precheck':'PASS_BASELINE_AND_PREVIOUS_CLEANUP','deployed':False}),flush=True)
        one=narrow(plan);backend=engine.ComposeBackend(ROOT,one);helpers['protect_core_health'](backend)
        original=engine.runtime_matches;captured=[]
        def capture(before,after,entry,which,**kwargs):
            require(entry['release_name']=='v79-hub' and which=='candidate','UNEXPECTED_PROBE_SCOPE')
            try:
                original(before,after,entry,which,**kwargs);message='RUNTIME_MATCHED'
            except Exception as error:message=str(error)
            record={'app':'v79-hub','which':which,'engine_message':message,
                'before':before,'after':after,'entry':entry}
            write(ROOT/'label-diagnostic.json',helpers['canonical'](record))
            prefix=message.split(':',1)[0]
            report={'phase':'CAPTURED_ONE_STOPPED_HUB_CANDIDATE',
                'reason':prefix if re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else 'REDACTED',
                'label_differences':label_report(message,before,after,entry),'deployed':False}
            captured.append(report);print(json.dumps(report),flush=True)
            raise Captured('DIAGNOSTIC_CAPTURE_COMPLETE')
        engine.runtime_matches=capture;helpers['install_compat'](engine)
        try:
            with helpers['heartbeat'](ROOT):engine.stopped_profiles(backend)
        except Captured:pass
        require(len(captured)==1,'SINGLE_CAPTURE_NOT_COMPLETED')
        backend.protected()
        for name,entry in plan['apps'].items():
            require(engine.protected_fingerprint(backend.inspect(name))==engine.protected_fingerprint(entry['baseline']),
                'POST_DIAGNOSTIC_BASELINE_CHANGED')
        require(helpers['timer_states']()==plan['workforce_timers'],'POST_DIAGNOSTIC_TIMER_STATE_CHANGED')
        require(not any(p.is_dir() for p in ROOT.glob('v79profile*')),'POST_DIAGNOSTIC_SCOPE_REMAINS')
        return {'result':'PASS_SINGLE_LABEL_CAPTURE_CLEANED','captured':captured[0],
            'baseline_preserved':True,'workforce_timers_preserved':True,'deployed':False}
    finally:os.close(lock)


if __name__=='__main__':
    try:print(json.dumps(diagnose(),indent=2))
    except Exception as error:
        prefix=str(error).split(':',1)[0]
        print(json.dumps({'result':'STOP_LABEL_DIAGNOSTIC','reason':prefix if
            re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else type(error).__name__,'deployed':False}))
        raise SystemExit(1)
