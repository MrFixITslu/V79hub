#!/usr/bin/env python3
"""Finish only unverified stopped profiles, using original engine safety body."""
import ast
import copy
import fcntl
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import textwrap
import urllib.request

ROOT=Path('/home/firelion/v79-lead-release-2pvsb2mo')
ALL=frozenset((name,which) for name in ('v79-hub','V79website') for which in ('candidate','rollback'))


def selected_profile_function(engine):
    # The sole body change is a filter BEFORE any selected profile operation.
    # The original creation, validation, ownership and finally cleanup stay intact.
    tree=ast.parse(textwrap.dedent(inspect.getsource(engine.stopped_profiles)))
    function=tree.body[0]
    if not isinstance(function,ast.FunctionDef) or function.name!='stopped_profiles':
        raise ValueError('UNEXPECTED_PROFILE_SOURCE')
    loops=[n for n in ast.walk(function) if isinstance(n,ast.For)
        and isinstance(n.target,ast.Name) and n.target.id=='which'
        and isinstance(n.iter,ast.Tuple)
        and [getattr(e,'value',None) for e in n.iter.elts]==['candidate','rollback']]
    if len(loops)!=1:raise ValueError('PROFILE_SELECTOR_INSERTION_NOT_UNIQUE')
    guard=ast.parse('if (name, which) not in selection:\n    continue').body[0]
    loops[0].body.insert(0,guard)
    function.name='selected_profiles';function.args.args.append(ast.arg(arg='selection'))
    ast.fix_missing_locations(tree)
    namespace=dict(engine.__dict__)
    exec(compile(tree,'<original-stopped-profiles-with-selection>','exec'),namespace)
    return namespace['selected_profiles'],tree


def load_pinned(url,expected):
    with urllib.request.urlopen(url,timeout=30) as response:data=response.read(1_000_000)
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('HELPER_DIGEST_CHANGED')
    namespace={'__name__':'pinned_helpers'};exec(compile(data,url,'exec'),namespace)
    return namespace


def resume():
    binder=load_pinned('https://raw.githubusercontent.com/MrFixITslu/V79hub/5b42c3de48e1df4c909c73c78c64930a80b05193/scripts/bind-website-lead-release.py',
        '06be2308bee4ac1370ba285a27a7c4bb55274eb77d43044b9e990c7104dac29c')
    diagnostic=load_pinned('https://raw.githubusercontent.com/MrFixITslu/V79hub/7f7c9579a78540e1815ad6d73644a312b427df08/scripts/diagnose-website-lead-label.py',
        '4402326c7717d84c5e4dc1e12ad0ed0967f8a570c1742f21c36eda8c9b863aeb')
    require=binder['require'];private=binder['private'];write=binder['write'];run=binder['run']
    require(not ROOT.is_symlink() and ROOT.is_dir() and ROOT.stat().st_uid==os.geteuid()
        and ROOT.stat().st_mode&0o077==0,'PRIVATE_DIRECTORY_REQUIRED')
    lock=os.open(ROOT/'binding.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not (ROOT/'binding-result.json').exists(),'BINDING_ALREADY_PASSED')
        # One attempt only; a partial failure receipt must be reviewed before retry.
        require(not (ROOT/'remaining-profile-result.json').exists(),'REMAINING_PROFILE_ATTEMPT_ALREADY_RECORDED')
        data=private(ROOT/'configuration-inputs.json')
        require(hashlib.sha256(data).hexdigest()==binder['INPUT_SHA'],'INPUT_DIGEST_CHANGED')
        inputs=json.loads(data)
        for name,pin in binder['MODULES'].items():
            data=private(ROOT/name)
            require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==pin,'ENGINE_MODULE_CHANGED')
        spec=importlib.util.spec_from_file_location('existing_engine',ROOT/'paired-compose-transaction.py')
        engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
        raw=private(ROOT/'transaction.json');manifest=hashlib.sha256(raw).hexdigest();plan=json.loads(raw)
        require(set(plan['apps'])==set(binder['PINS']) and plan.get('requires_supervision') is True,'PLAN_SCOPE_CHANGED')
        require(plan['protected']=={n:r for n,r in inputs['baseline'].items() if n not in binder['PINS']},
            'PROTECTED_PLAN_CHANGED')
        for name,entry in plan['apps'].items():
            require(entry['baseline']==inputs['baseline'][name] and entry['release_name']==name
                and entry['candidate_image']['Id']==binder['PINS'][name][1]
                and entry['rollback_image']['Id']==entry['baseline']['Image'],'BASELINE_PLAN_CHANGED')
            for which in ('candidate','rollback'):
                file=Path(entry[which+'_file']);require(file.parent==ROOT,'MODEL_PATH_CHANGED')
                require(json.loads(private(file))==inputs['prepared'][name][which],'MODEL_CONTENT_CHANGED')
        require(run(['docker','compose','version','--short']).decode().strip()=='5.6.1','COMPOSE_VERSION_CHANGED')
        backend=engine.ComposeBackend(ROOT,plan);binder['protect_core_health'](backend)
        def preservation():
            backend.protected();backend.check_files()
            for name,entry in plan['apps'].items():
                require(engine.protected_fingerprint(backend.inspect(name))==engine.protected_fingerprint(entry['baseline']),
                    'TARGET_BASELINE_CHANGED')
            require(binder['timer_states']()==plan['workforce_timers'],'WORKFORCE_TIMER_STATE_CHANGED')
            require(not any(p.is_dir() for p in ROOT.glob('v79profile*')),'PROFILE_DIRECTORY_REMAINS')
        preservation()
        for scope in ('v79profile39e19427a15546ab','v79profile824340c6a157439d'):
            require(not run(['docker','volume','ls','-q','--filter','label=v79.profile.scope='+scope]).strip(),
                'PREVIOUS_PROFILE_VOLUME_REMAINS')
        prior_raw=private(ROOT/'label-diagnostic.json');prior=json.loads(prior_raw)
        require(prior.get('app')=='v79-hub' and prior.get('which')=='candidate'
            and prior.get('engine_message')=='RUNTIME_MATCHED','PASSED_HUB_RECEIPT_REQUIRED')
        entry=prior['entry']
        require(entry['candidate_image']['Id']==binder['PINS']['v79-hub'][1]
            and prior['after']['Image']==entry['candidate_image']['Id']
            and not prior['after']['State'].get('Running')
            and str(prior['after']['State'].get('StartedAt','0001')).startswith('0001'),
            'PASSED_RECEIPT_IMAGE_OR_STATE_CHANGED')
        # Revalidate the stored normalized receipt with the ORIGINAL validator.
        # No Docker resource is recreated for this already-passed profile.
        engine.runtime_matches(prior['before'],prior['after'],entry,'candidate',selinux_enabled=plan['selinux_enabled'])
        require(entry['approved_environment']==plan['apps']['v79-hub']['approved_environment']
            and entry['candidate_sha256']==plan['apps']['v79-hub']['candidate_sha256'],'PASSED_RECEIPT_CONFIG_CHANGED')
        selection=ALL-{('v79-hub','candidate')}
        # Explicit order is independent of canonical JSON object ordering.
        plan['apps']={name:plan['apps'][name] for name in ('v79-hub','V79website')}
        captured=[];original=engine.runtime_matches
        def report(before,after,entry,which,**kwargs):
            name=entry['release_name'];require((name,which) in selection,'PASSED_PROFILE_MUST_NOT_RECREATE')
            failure=None
            try:original(before,after,entry,which,**kwargs);message='RUNTIME_MATCHED'
            except Exception as error:failure=error;message=str(error)
            write(ROOT/(name+'.'+which+'.profile-capture.json'),binder['canonical']({
                'app':name,'which':which,'engine_message':message,'before':before,'after':after,'entry':entry}))
            display=copy.deepcopy(entry);display['candidate_image']=entry[which+'_image']
            prefix=message.split(':',1)[0]
            summary={'app':name,'which':which,'reason':prefix if re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else 'REDACTED',
                'label_differences':diagnostic['label_report'](message,before,after,display)}
            captured.append(summary);print(json.dumps({'profile':summary}),flush=True)
            if failure:raise failure
            return True
        engine.runtime_matches=report;binder['install_compat'](engine)
        proof_function,_=selected_profile_function(engine)
        failure=None;proof=None
        print(json.dumps({'reused_profile':'v79-hub/candidate','new_profiles':3,'deployed':False}),flush=True)
        try:
            with binder['heartbeat'](ROOT):proof=proof_function(backend,selection)
        except Exception as error:failure=error
        preservation()
        result={'result':'PASS_REMAINING_PROFILES' if failure is None else 'STOP_REMAINING_PROFILES',
            'profiles':captured,'reused_profiles':1,'baseline_preserved':True,'workforce_timers_preserved':True,
            'temporary_cleanup_verified':True,'manifest_sha256':manifest,'deployed':False}
        write(ROOT/'remaining-profile-result.json',binder['canonical'](result))
        if failure:
            prefix=str(failure).split(':',1)[0]
            result['reason']=prefix if re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else type(failure).__name__
            return result
        require(proof.get('profiles_verified')==3 and len(captured)==3 and
            {(r['app'],r['which']) for r in captured}==selection,'REMAINING_PROFILE_COUNT_CHANGED')
        result.update(result='PASS_BOUND_ENGINE_AND_NEW_CONFIGURATION_PROFILES',engine_bound=True,
            profiles_verified=4,new_profiles_verified=3,directory=str(ROOT),protected_container_count=len(plan['protected']))
        write(ROOT/'binding-result.json',binder['canonical'](result))
        return result
    finally:os.close(lock)


if __name__=='__main__':
    try:
        result=resume();print(json.dumps(result,indent=2))
        if result['result'].startswith('STOP'):raise SystemExit(1)
    except Exception as error:
        prefix=str(error).split(':',1)[0]
        print(json.dumps({'result':'STOP_REMAINING_PROFILES','reason':prefix if
            re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else type(error).__name__,'deployed':False}))
        raise SystemExit(1)
