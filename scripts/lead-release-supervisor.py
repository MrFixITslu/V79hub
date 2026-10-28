#!/usr/bin/env python3
"""Durable supervisor; all container switches/rollback delegate to pinned engine."""
import argparse
import contextlib
import copy
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

ROOT=Path('/home/firelion/v79-lead-release-2pvsb2mo')
MANIFEST='44c0625680f1dfb306aaa49d51f936a08eb76d67ba1e9c2fcddfd9b6be4f368e'
ADAPTER_SHA='a1d4842cb0625e1207fb454b5510c05bd2443a245fe7f3143d7be20c660d84e7'
ADAPTER_URL='https://raw.githubusercontent.com/MrFixITslu/V79hub/2e538278eb346eedce48c77757188e74ed8793bd/scripts/bind-website-lead-release.py'
ORDER=('v79-hub','V79website')
TIMER='vision79-lead-pair-expiry.timer'
SERVICE='vision79-lead-pair-expiry.service'
WINDOW=20*60


def require(ok,code):
    if not ok:raise ValueError(code)


def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def private(path):
    st=path.lstat()
    require(path.is_file() and not path.is_symlink() and st.st_uid==os.geteuid()
        and st.st_nlink==1 and not st.st_mode&0o077,'PRIVATE_FILE_REQUIRED')
    return path.read_bytes()


def atomic(path,data):
    temporary=path.parent/('.'+path.name+'-'+str(os.getpid()))
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class State:
    def __init__(self,root):self.path=Path(root)/'lead-release-state.json'
    def read(self):
        if not self.path.exists():return None
        result=json.loads(private(self.path))
        require(result.get('manifest_sha256')==MANIFEST,'STATE_MANIFEST_CHANGED')
        return result
    def put(self,data):
        require(data.get('manifest_sha256')==MANIFEST,'STATE_MANIFEST_CHANGED')
        atomic(self.path,canon(data))


def healthy(row):
    return bool(row and row['State'].get('Running') and row['State'].get('Health',{}).get('Status')=='healthy')


def durable_backend(engine,backend,plan,state):
    original_call=backend.call;original_switch=backend.switch;original_journal=backend.journal
    def verify(name,which,row=None):
        entry=copy.deepcopy(plan['apps'][name]);row=row or backend.inspect(name)
        if which=='rollback' and row['Id']==entry['baseline']['Id']:
            require(engine.protected_fingerprint(row)==engine.protected_fingerprint(entry['baseline']),
                'ORIGINAL_BASELINE_CHANGED')
            return True
        current=state.read();context=(current or {}).get('replacements',{}).get(name,{}).get(which)
        require(isinstance(context,dict) and 'previous_id' in context,'DURABLE_REPLACEMENT_CONTEXT_MISSING')
        entry['_replaced_id']=context['previous_id']
        # The original engine keeps candidate model in entry. Verify each
        # selected runtime against its own sealed model, including rollback Env.
        selected_path=Path(entry[which+'_file']);data=private(selected_path)
        require(hashlib.sha256(data).hexdigest()==entry[which+'_sha256'],'SELECTED_MODEL_CHANGED')
        entry['model']=json.loads(data)
        expected=context.get('created_id')
        require(expected in (None,row['Id']),'REPLACEMENT_CONTAINER_ID_CHANGED')
        result=engine.runtime_matches(entry['baseline'],row,entry,which,selinux_enabled=plan['selinux_enabled'])
        if expected is None:
            context['created_id']=row['Id'];state.put(current)
        return result
    def call(args,**kwargs):
        if args[:2]==['docker','compose'] and 'up' in args:
            matches=[]
            for name,entry in plan['apps'].items():
                for which in ('candidate','rollback'):
                    expected=['docker','compose','--env-file','/dev/null','--project-directory',entry['directory'],
                        '--project-name',entry['project'],'-f',entry[which+'_file'],'up','--no-start','--no-deps',
                        '--no-build','--pull','never','--force-recreate',entry['service']]
                    if args==expected:matches.append((name,which,entry))
            require(len(matches)==1,'UNREVIEWED_COMPOSE_MUTATION')
            name,which,entry=matches[0]
            previous=entry.get('_replaced_id')
            require(previous is None or re.fullmatch('[0-9a-f]{64}',previous),'REPLACEMENT_ID_INVALID')
            current=state.read();require(current is not None,'DURABLE_STATE_MISSING')
            require(current['phase']!='ACCEPTED','ACCEPTED_RELEASE_NO_MUTATION')
            current.setdefault('replacements',{}).setdefault(name,{})[which]={
                'previous_id':previous,'created_id':None}
            state.put(current)  # durable BEFORE the original Compose call
        if args[:2]==['docker','start']:
            current=state.read() or {}
            require(current.get('phase')!='ACCEPTED','ACCEPTED_RELEASE_NO_MUTATION')
            allowed={c.get('created_id') for variants in current.get('replacements',{}).values()
                for c in variants.values()}
            require(len(args)==3 and args[2] in allowed,'START_WITHOUT_VERIFIED_DURABLE_ID')
        elif args[:2]!=['docker','compose']:
            require(args==['docker','ps','--all','--format','{{.Names}}'],'UNREVIEWED_ENGINE_COMMAND')
        else:
            require('up' in args,'UNREVIEWED_ENGINE_COMMAND')
        return original_call(args,**kwargs)
    def switch(name,which):
        if which=='rollback':
            row=backend.inspect(name,allow_missing=True)
            if healthy(row) and row['Image']==plan['apps'][name]['rollback_image']['Id']:
                try:verify(name,which,row)
                except Exception:pass
                else:return  # exact original or verified rollback: no recreate
        return original_switch(name,which)
    def journal(event,name=None):
        original_journal(event,name)
        if event in ('CANDIDATE_INTENT','ROLLBACK_INTENT','ROLLBACK_FAILED','ORIGINAL_PAIR_RESTORED'):
            current=state.read();require(current is not None,'DURABLE_STATE_MISSING')
            if event=='CANDIDATE_INTENT' and name not in current['touched']:current['touched'].append(name)
            if event=='ROLLBACK_INTENT':current['engine_rollback_started']=True
            if event=='ROLLBACK_FAILED':current['rollback_failed']=True
            if event=='ORIGINAL_PAIR_RESTORED':current['engine_rollback_complete']=True
            state.put(current)
    backend.verify=verify;backend.call=call;backend.switch=switch;backend.journal=journal
    return backend


def command(args,env=None,check=True):
    p=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
    if check:require(p.returncode==0,'SUPERVISOR_COMMAND_FAILED')
    return p


def user_env():
    return {**os.environ,'XDG_RUNTIME_DIR':'/run/user/'+str(os.geteuid()),
        'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/'+str(os.geteuid())+'/bus'}


def ctl(*args,check=True):return command(['systemctl','--user',*args],user_env(),check)


def prop(unit,key):return ctl('show',unit,'--property='+key,'--value').stdout.decode().strip()


def unit_text(deadline):
    due=datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    service=('[Unit]\nDescription=Vision79 lead-pair guarded expiry rollback\n'
        '[Service]\nType=oneshot\nRestart=no\nTimeoutStartSec=1200\n'
        'ExecStart=/usr/bin/sg docker -c "/usr/bin/python3 -B '+str(ROOT/'lead-release-supervisor.py')+' --expire"\n')
    timer=('[Unit]\nDescription=Vision79 lead-pair acceptance deadline\n'
        '[Timer]\nOnCalendar='+due+'\nPersistent=true\nAccuracySec=1s\nUnit='+SERVICE+'\n'
        '[Install]\nWantedBy=timers.target\n')
    return service,timer


def arm(deadline):
    directory=Path.home()/'.config/systemd/user'
    require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_uid==os.geteuid(),
        'USER_UNIT_DIRECTORY_UNAVAILABLE')
    require(command(['loginctl','show-user','firelion','--property=Linger','--value']).stdout.strip()==b'yes',
        'USER_MANAGER_NOT_DURABLE')
    for name in (SERVICE,TIMER):require(not (directory/name).exists(),'EXPIRY_UNIT_ALREADY_EXISTS')
    require(prop(SERVICE,'ActiveState') in ('inactive','failed'),'EXPIRY_SERVICE_BUSY')
    for name,data in zip((SERVICE,TIMER),unit_text(deadline)):
        fd=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(data);f.flush();os.fsync(f.fileno())
    ctl('daemon-reload');ctl('enable','--now',TIMER)
    require(prop(TIMER,'ActiveState')=='active' and prop(TIMER,'NextElapseUSecRealtime') not in
        ('','n/a','N/A','infinity'),'PERSISTENT_TIMER_NOT_ARMED')


def disarm():
    p=ctl('disable','--now',TIMER,check=False)
    return p.returncode==0 and prop(TIMER,'ActiveState')=='inactive'


WEBSITE_READER=r"""
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {DatabaseSync}=require('node:sqlite');
const dir=path.join(process.cwd(),'data');
const configured=String(process.env.ENCRYPTION_KEY||'').trim().replace(/^['"]|['"]$/g,'');
let key;
if(configured)key=/^[a-f0-9]{64}$/i.test(configured)?Buffer.from(configured,'hex'):crypto.createHash('sha256').update(configured).digest();
else key=Buffer.from(fs.readFileSync(path.join(dir,'.encryption_key'),'utf8').trim(),'hex');
function unseal(s){if(!s.startsWith('enc:v1:'))return s;
const b=Buffer.from(s.slice(7),'base64'),d=crypto.createDecipheriv('aes-256-gcm',key,b.subarray(0,12));
d.setAuthTag(b.subarray(12,28));return Buffer.concat([d.update(b.subarray(28)),d.final()]).toString('utf8');}
const db=new DatabaseSync(path.join(dir,'website.db'),{readOnly:true,timeout:5000});
try{const doc=db.prepare('SELECT value FROM documents WHERE name=?').get('vision79_leads.json');
if(!doc)throw Error('missing document');const rows=JSON.parse(unseal(doc.value)).filter(x=>x.id===2);
if(rows.length!==1||unseal(rows[0].company)!=='V79-TEST-20261028-A')throw Error('wrong lead');
const l=rows[0];console.log(JSON.stringify({id:l.id,hubEventId:l.hubEventId,tiquetEventId:l.tiquetEventId,
hub:l.hubEventStatus,tiquet:l.tiquetSyncStatus}));}finally{db.close();}
"""

HUB_READER=r"""
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const expected=JSON.parse(fs.readFileSync(0,'utf8'));
if(!/^[0-9a-f-]{36}$/i.test(expected.eventId))throw Error('invalid ID');
const file=path.join(process.env.DATA_DIR||'/app/data','website-lead-events',expected.eventId+'.json');
if(!fs.existsSync(file)){console.log(JSON.stringify({matched:false}));process.exit(0);}
const raw=fs.readFileSync(file),r=JSON.parse(raw),e=r.event||{};
const matched=r.state==='received'&&e.id===expected.eventId&&e.type==='lead.created'&&e.version===1&&
e.subjectId==='2'&&e.payload?.leadId===2&&e.organizationRef===expected.organization&&
e.correlationId===expected.correlationId&&/^[a-f0-9]{64}$/.test(r.digest||'');
console.log(JSON.stringify({matched,receipt_sha256:crypto.createHash('sha256').update(raw).digest('hex')}));
"""


def read_lead():
    p=command(['docker','exec','V79website','node','-e',WEBSITE_READER])
    row=json.loads(p.stdout)
    require(row.get('id')==2 and all(re.fullmatch('[0-9a-f-]{36}',row.get(k,'') or '',re.I)
        for k in ('hubEventId','tiquetEventId')),'TEST_LEAD_EVENT_IDENTITIES_INVALID')
    return row


def receipt_matches(expected,organization):
    row=read_lead()
    require((row['hubEventId'],row['tiquetEventId'])==(expected['hubEventId'],expected['tiquetEventId']),
        'ORIGINAL_LEAD_EVENT_IDENTITIES_CHANGED')
    require(row.get('tiquet')=='sent','TIQUET_ACK_CHANGED')
    require(row.get('hub') in ('disabled','pending','sent'),'HUB_DELIVERY_REJECTED_OR_INVALID_STATE')
    if row.get('hub')!='sent':return False,None
    body=canon({'eventId':row['hubEventId'],'correlationId':row['tiquetEventId'],'organization':organization})
    p=subprocess.run(['docker','exec','-i','v79-hub','node','-e',HUB_READER],input=body,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
    require(p.returncode==0,'HUB_RECEIPT_READ_FAILED');result=json.loads(p.stdout)
    return result.get('matched') is True,result.get('receipt_sha256')


def load_context(state):
    require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.stat().st_uid==os.geteuid()
        and ROOT.stat().st_mode&0o077==0,'PRIVATE_RELEASE_DIRECTORY_REQUIRED')
    require(Path(__file__).resolve()==ROOT/'lead-release-supervisor.py','INSTALLED_SUPERVISOR_REQUIRED')
    adapter=ROOT/'lead-release-compat.py'
    if not adapter.exists():
        require(state.read() is None,'ADAPTER_MISSING_DURING_RELEASE')
        with urllib.request.urlopen(ADAPTER_URL,timeout=30) as response:data=response.read(1_000_000)
        require(hashlib.sha256(data).hexdigest()==ADAPTER_SHA,'ADAPTER_DIGEST_CHANGED')
        atomic(adapter,data)
    data=private(adapter);require(hashlib.sha256(data).hexdigest()==ADAPTER_SHA,'ADAPTER_DIGEST_CHANGED')
    spec=importlib.util.spec_from_file_location('lead_compat',adapter)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    for name,pin in helper.MODULES.items():
        data=private(ROOT/name)
        require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==pin,'ENGINE_MODULE_CHANGED')
    spec=importlib.util.spec_from_file_location('existing_pair_engine',ROOT/'paired-compose-transaction.py')
    engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
    plan=engine.load_plan(ROOT,MANIFEST)
    require(set(plan['apps'])==set(ORDER),'PLAN_SCOPE_CHANGED')
    plan['apps']={name:plan['apps'][name] for name in ORDER}
    proof=json.loads(private(ROOT/'binding-result.json'))
    require(proof.get('engine_bound') is True and proof.get('profiles_verified')==4 and
        proof.get('manifest_sha256')==MANIFEST and proof.get('validation_adapter_sha256')==ADAPTER_SHA,
        'COMPLETED_CONFIGURATION_PROOF_REQUIRED')
    for name,(revision,pin) in helper.PINS.items():
        require(plan['apps'][name]['candidate_image']['Id']==pin,'CANDIDATE_IMAGE_CHANGED')
        require(plan['apps'][name]['compose_version']=='5.6.1','SEALED_COMPOSE_VERSION_CHANGED')
    helper.verify_compose_version(command(['docker','compose','version','--short']).stdout.decode().strip(),'5.6.1')
    current=state.read()
    if current:require(current['supervisor_sha256']==hashlib.sha256(private(Path(__file__))).hexdigest(),
        'INSTALLED_SUPERVISOR_CHANGED')
    helper.install_compat(engine)
    backend=engine.ComposeBackend(ROOT,plan);helper.protect_core_health(backend)
    original=backend.protected
    def protected():
        original();require(helper.timer_states()==plan['workforce_timers'],'WORKFORCE_TIMER_STATE_CHANGED')
    backend.protected=protected
    durable_backend(engine,backend,plan,state)
    return engine,backend,plan,helper


def rollback(engine,backend,state):
    current=state.read();require(current is not None,'RELEASE_STATE_MISSING')
    require(current['phase']!='ACCEPTED','ACCEPTED_RELEASE_NO_ROLLBACK')
    require(not current.get('rollback_failed'),'PREVIOUS_ROLLBACK_FAILURE_REQUIRES_REVIEW')
    names=current.get('touched',[])
    require(names==list(ORDER[:len(names)]),'DURABLE_TOUCHED_SCOPE_CHANGED')
    current['phase']='ROLLING_BACK';state.put(current)
    try:
        result=engine.rollback(backend,names)
        require(result.get('status')=='PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED','ORIGINAL_ENGINE_ROLLBACK_INCOMPLETE')
        for name in backend.plan['apps']:backend.healthy(name,'rollback')
        backend.protected()
        current=state.read();current['phase']='ROLLED_BACK';state.put(current)
        return result
    except BaseException:
        current=state.read();current['phase']='ROLLBACK_REQUIRES_OPERATOR';state.put(current);raise


def deploy(engine,backend,plan,helper,state):
    require(state.read() is None,'RELEASE_ALREADY_STARTED_NO_REPLAY')
    require(tuple(plan['apps'])==ORDER,'HUB_MUST_SWITCH_BEFORE_WEBSITE')
    backend.check_files();backend.protected()
    for name,entry in plan['apps'].items():
        row=backend.inspect(name)
        require(engine.protected_fingerprint(row)==engine.protected_fingerprint(entry['baseline']) and healthy(row),
            'PREPARED_LIVE_BASELINE_CHANGED')
        backend.eligible(name)
    expected=read_lead();require(expected['tiquet']=='sent' and expected['hub']=='disabled','TEST_LEAD_BASELINE_CHANGED')
    raw=private(ROOT/'configuration-inputs.json')
    require(hashlib.sha256(raw).hexdigest()==helper.INPUT_SHA,'CONFIGURATION_INPUT_CHANGED')
    inputs=json.loads(raw)
    for entry in plan['apps'].values():
        for which in ('candidate','rollback'):
            image=entry[which+'_image']['Id'];metadata,manifest=helper.image_metadata(image)
            require(manifest==entry['image_manifests'][image],'IMAGE_MANIFEST_MAPPING_CHANGED')
    deadline=time.time()+WINDOW
    current={'manifest_sha256':MANIFEST,'supervisor_sha256':hashlib.sha256(private(Path(__file__))).hexdigest(),
        'phase':'ARMING','deadline_epoch':deadline,'touched':[],'replacements':{},'expected_lead':expected}
    state.put(current)
    arm(deadline)
    current['phase']='DEPLOYING';state.put(current)
    try:
        with helper.heartbeat(ROOT):
            local_deadline=datetime.datetime.fromtimestamp(deadline,
                datetime.timezone(datetime.timedelta(hours=-4))).isoformat()
            print(json.dumps({'phase':'SWITCH_HUB_THEN_WEBSITE','rollback_timer_armed':True,
                'deadline_saint_lucia':local_deadline}),flush=True)
            result=engine.deploy(backend)
            require(result.get('status')=='PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING','PAIR_DEPLOYMENT_DID_NOT_COMPLETE')
            current=state.read();current['phase']='VERIFYING_LEAD_RECEIPT';state.put(current)
            until=min(time.time()+360,deadline-60)
            matched=False;receipt_hash=None;last_log=0
            while time.time()<until:
                matched,receipt_hash=receipt_matches(expected,inputs['organization'])
                if matched:break
                if time.time()-last_log>30:
                    print(json.dumps({'phase':'WAITING_FOR_EXISTING_LEAD_2_SWEEP'}),flush=True);last_log=time.time()
                time.sleep(5)
            require(matched,'MATCHING_LEAD_RECEIPT_NOT_CONFIRMED')
            for name in ORDER:backend.healthy(name,'candidate')
            backend.protected();require(time.time()<deadline-30,'ACCEPTANCE_DEADLINE_EXPIRED')
            current=state.read();current.update(phase='ACCEPTED',acceptance='MATCHED_EXISTING_OPERATOR_TEST_LEAD',
                receipt_sha256=receipt_hash,accepted_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            state.put(current)
        closed=disarm()
        return {'result':'PASS_LEAD_INTEGRATION_ACCEPTED' if closed else 'ACCEPTED_TIMER_DISARM_REVIEW',
            'lead_id':2,'website_hub_status':'sent','matching_hub_receipt':True,
            'original_event_ids_preserved':True,'tiquet_ack_preserved':True,'protected_container_count':len(plan['protected']),
            'workforce_timers_preserved':True,'rollback_timer_disabled':closed,'deployed':True,
            'commercial_launch':'UNCHANGED_SEPARATE_GATE'}
    except BaseException as error:
        current=state.read()
        if current and current['phase']=='ACCEPTED':raise
        prefix=str(error).split(':',1)[0]
        reason=prefix if re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else type(error).__name__
        try:
            if current.get('rollback_failed'):
                current['phase']='ROLLBACK_REQUIRES_OPERATOR';state.put(current)
                closed=disarm()
                return {'result':'RELEASE_REQUIRES_OPERATOR','reason':reason,
                    'rollback_timer_disabled':closed,'deployed':'UNCONFIRMED',
                    'automatic_retry':False}
            if current.get('engine_rollback_complete'):
                for name in ORDER:backend.healthy(name,'rollback')
                backend.protected();current['phase']='ROLLED_BACK';state.put(current)
            else:rollback(engine,backend,state)
            closed=disarm()
            return {'result':'RELEASE_FAILED_ORIGINALS_RESTORED','reason':reason,
                'rollback_timer_disabled':closed,'deployed':False}
        except BaseException:
            return {'result':'RELEASE_REQUIRES_OPERATOR','reason':reason,'rollback_timer_state':'UNCONFIRMED',
                'deployed':'UNCONFIRMED'}


def main():
    parser=argparse.ArgumentParser();modes=parser.add_mutually_exclusive_group(required=True)
    for name in ('deploy','expire','rollback','status'):modes.add_argument('--'+name,action='store_true')
    parser.add_argument('--accept-matching-lead',action='store_true');args=parser.parse_args()
    require(not args.deploy or args.accept_matching_lead,'EXPLICIT_MATCHING_LEAD_ACCEPTANCE_REQUIRED')
    os.umask(0o077)
    lock=os.open(ROOT/'binding.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX if args.expire else fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=State(ROOT);engine,backend,plan,helper=load_context(state)
        current=state.read()
        if args.deploy:result=deploy(engine,backend,plan,helper,state)
        elif args.status:
            rows={name:backend.inspect(name,allow_missing=True) for name in ORDER}
            result={'phase':current.get('phase') if current else 'NOT_STARTED',
                'rollback_timer':prop(TIMER,'ActiveState'),
                'live_images':{name:row.get('Image') if row else None for name,row in rows.items()},
                'live_healthy':{name:healthy(row) for name,row in rows.items()}}
        elif current and current['phase']=='ACCEPTED' and args.expire:
            result={'result':'NOOP_ACCEPTED_RELEASE'}
        elif current and current['phase']=='ROLLED_BACK' and args.expire:
            result={'result':'NOOP_ORIGINALS_ALREADY_RESTORED'}
        else:
            require(current is not None,'RELEASE_STATE_MISSING')
            if args.expire:require(time.time()>=current['deadline_epoch']-3,'EXPIRY_BEFORE_DEADLINE')
            rollback(engine,backend,state);closed=disarm()
            result={'result':'PASS_ORIGINALS_RESTORED','rollback_timer_disabled':closed,'deployed':False}
        print(json.dumps(result,indent=2))
        if result.get('result') not in ('PASS_LEAD_INTEGRATION_ACCEPTED','NOOP_ACCEPTED_RELEASE',
            'NOOP_ORIGINALS_ALREADY_RESTORED','PASS_ORIGINALS_RESTORED') and not args.status:
            raise SystemExit(1)
    finally:os.close(lock)


if __name__=='__main__':
    try:main()
    except Exception as error:
        prefix=str(error).split(':',1)[0]
        print(json.dumps({'result':'STOP_SUPERVISOR','reason':prefix if
            re.fullmatch('[A-Z][A-Z0-9_]+',prefix) else type(error).__name__}))
        raise SystemExit(1)
