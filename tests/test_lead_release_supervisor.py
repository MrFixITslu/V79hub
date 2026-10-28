import contextlib
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TESTS=Path(__file__).parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


s=load('lead_supervisor',TESTS.parent/'scripts/lead-release-supervisor.py')
fixtures=load('runtime_fixture',TESTS/'test_website_lead_binding.py')


class DurableTests(unittest.TestCase):
    def setup_context(self,directory,which='candidate'):
        engine,before,after,entry=fixtures.BindingTests().fixture(which)
        root=Path(directory);entry['directory']=str(root)
        models={}
        for selected in ('candidate','rollback'):
            model=copy.deepcopy(entry['model'])
            model['services']['hub']['environment']={'EXISTING':'retained',
                **(entry['approved_environment'] if selected=='candidate' else {})}
            file=root/(selected+'.json');data=s.canon(model);file.write_bytes(data);file.chmod(0o600)
            entry[selected+'_file']=str(file);entry[selected+'_sha256']=hashlib.sha256(data).hexdigest()
            models[selected]=model
        # Real backend stores candidate model even when verifying rollback.
        entry['model']=models['candidate']
        after['Config']['Labels']['com.docker.compose.project.config_files']=entry[which+'_file']
        after['Config']['Labels']['com.docker.compose.replace']='v79-hub'
        state=s.State(root);state.put({'manifest_sha256':s.MANIFEST,'phase':'DEPLOYING','touched':['v79-hub'],
            'replacements':{'v79-hub':{which:{'previous_id':before['Id'],'created_id':None}}}})
        backend=SimpleNamespace(plan={'apps':{'v79-hub':entry},'selinux_enabled':False},
            inspect=lambda name,**kwargs:after,call=lambda *a,**k:b'',
            switch=lambda *a:None,journal=lambda *a:None)
        s.durable_backend(engine,backend,backend.plan,state)
        return engine,before,after,entry,state,backend

    def test_actual_rollback_validator_uses_rollback_environment(self):
        with tempfile.TemporaryDirectory() as d:
            _,_,after,_,state,backend=self.setup_context(d,'rollback')
            self.assertTrue(backend.verify('v79-hub','rollback',after))
            self.assertEqual(state.read()['replacements']['v79-hub']['rollback']['created_id'],after['Id'])
            after['Config']['Env'].append('V79_WEBSITE_EVENTS_ENABLED=1')
            with self.assertRaisesRegex(ValueError,'EFFECTIVE_ENVIRONMENT_CHANGED'):
                backend.verify('v79-hub','rollback',after)

    def test_replacement_context_is_durable_before_failed_compose_command(self):
        with tempfile.TemporaryDirectory() as d:
            engine,_,_,entry,state,_=self.setup_context(d)
            entry['_replaced_id']='d'*64
            def fail_call(args,**kwargs):
                self.assertEqual(state.read()['replacements']['v79-hub']['candidate']['previous_id'],'d'*64)
                raise RuntimeError('simulated ambiguous CLI failure')
            backend=SimpleNamespace(call=fail_call,switch=lambda *a:None,verify=lambda *a:None,
                journal=lambda *a:None,inspect=lambda *a,**k:None)
            s.durable_backend(engine,backend,{'apps':{'v79-hub':entry},'selinux_enabled':False},state)
            args=['docker','compose','--env-file','/dev/null','--project-directory',entry['directory'],
                '--project-name',entry['project'],'-f',entry['candidate_file'],'up','--no-start','--no-deps',
                '--no-build','--pull','never','--force-recreate',entry['service']]
            with self.assertRaises(RuntimeError):backend.call(args)
            self.assertEqual(state.read()['replacements']['v79-hub']['candidate']['previous_id'],'d'*64)

    def test_fresh_process_validates_same_candidate_id_and_rejects_foreign_id(self):
        with tempfile.TemporaryDirectory() as d:
            _,_,after,entry,state,backend=self.setup_context(d)
            backend.verify('v79-hub','candidate',after)
            code=r'''
import importlib.util,json,sys
from types import SimpleNamespace
from pathlib import Path
data=json.load(sys.stdin)
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
s=load('supervisor',data['supervisor'])
b=load('binding_fixture',data['fixture'])
engine,_,_,_=b.BindingTests().fixture()
after=data['after'];entry=data['entry']
backend=SimpleNamespace(call=lambda *a,**k:None,switch=lambda *a:None,journal=lambda *a:None,inspect=lambda *a,**k:after)
s.durable_backend(engine,backend,{'apps':{'v79-hub':entry},'selinux_enabled':False},s.State(data['root']))
try:backend.verify('v79-hub','candidate',after);print('PASS')
except ValueError as e:print(str(e));sys.exit(3)
'''
            data={'supervisor':str(TESTS.parent/'scripts/lead-release-supervisor.py'),
                'fixture':str(TESTS/'test_website_lead_binding.py'),'after':after,'entry':entry,'root':d}
            p=subprocess.run(['python3','-c',code],input=json.dumps(data),text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'PASS')
            data['after']=copy.deepcopy(after);data['after']['Id']='f'*64
            p=subprocess.run(['python3','-c',code],input=json.dumps(data),text=True,capture_output=True)
            self.assertEqual(p.returncode,3);self.assertIn('REPLACEMENT_CONTAINER_ID_CHANGED',p.stdout)

    def test_verified_original_rollback_is_not_recreated(self):
        with tempfile.TemporaryDirectory() as d:
            engine,before,_,entry,state,_=self.setup_context(d)
            before['State'].update(Running=True,Status='running',StartedAt='original',Health={'Status':'healthy'})
            entry['baseline']=copy.deepcopy(before);switches=[]
            backend=SimpleNamespace(call=lambda *a,**k:None,switch=lambda *a:switches.append(a),
                journal=lambda *a:None,inspect=lambda *a,**k:before)
            s.durable_backend(engine,backend,{'apps':{'v79-hub':entry},'selinux_enabled':False},state)
            backend.switch('v79-hub','rollback');self.assertEqual(switches,[])

    def test_fresh_process_runs_original_rollback_with_durable_replacement_and_selected_model(self):
        with tempfile.TemporaryDirectory() as d:
            _,_,candidate,entry,state,_=self.setup_context(d)
            _,_,rollback_row,_=fixtures.BindingTests().fixture('rollback')
            candidate['State'].update(Running=True,Status='running',StartedAt='candidate',Health={'Status':'healthy'})
            rollback_row['Id']='c'*64;rollback_row['Config']['Hostname']='c'*12
            rollback_row['Config']['Labels'].update({'com.docker.compose.project.config_files':entry['rollback_file'],
                'com.docker.compose.replace':'v79-hub'})
            rollback_row['State'].update(Status='created',StartedAt='0001-01-01T00:00:00Z')
            code=r'''
import importlib.util,json,sys
data=json.load(sys.stdin)
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
s=load('supervisor',data['supervisor']);b=load('binding_fixture',data['fixture'])
engine,_,_,_=b.BindingTests().fixture()
plan={'apps':{'v79-hub':data['entry']},'protected':{},'selinux_enabled':False}
class Backend(engine.ComposeBackend):
 def __init__(self):super().__init__(data['root'],plan);self.row=data['candidate']
 def inspect(self,*args,**kwargs):return self.row
 def protected(self):pass
 def call(self,args,**kwargs):
  if args[:2]==['docker','compose']:self.row=data['rollback']
  elif args[:2]==['docker','start']:
   self.row['State'].update(Running=True,Status='running',StartedAt='restored',Health={'Status':'healthy'})
  else:raise ValueError('unexpected command')
  return b''
backend=Backend();state=s.State(data['root']);s.durable_backend(engine,backend,plan,state)
s.rollback(engine,backend,state)
current=state.read();print(json.dumps({'phase':current['phase'],'image':backend.row['Image'],
 'previous':current['replacements']['v79-hub']['rollback']['previous_id']}))
'''
            data={'supervisor':str(TESTS.parent/'scripts/lead-release-supervisor.py'),
                'fixture':str(TESTS/'test_website_lead_binding.py'),'candidate':candidate,'rollback':rollback_row,
                'entry':entry,'root':d}
            p=subprocess.run(['python3','-c',code],input=json.dumps(data),text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            result=json.loads(p.stdout);self.assertEqual(result['phase'],'ROLLED_BACK')
            self.assertEqual(result['image'],entry['rollback_image']['Id']);self.assertEqual(result['previous'],candidate['Id'])

    def test_accepted_release_cannot_roll_back(self):
        with tempfile.TemporaryDirectory() as d:
            state=s.State(d);state.put({'manifest_sha256':s.MANIFEST,'phase':'ACCEPTED'})
            called=[]
            with self.assertRaisesRegex(ValueError,'ACCEPTED_RELEASE_NO_ROLLBACK'):
                s.rollback(SimpleNamespace(rollback=lambda *a:called.append(a)),None,state)
            self.assertEqual(called,[])

    def test_unreviewed_engine_command_cannot_delete_a_container(self):
        with tempfile.TemporaryDirectory() as d:
            *_,backend=self.setup_context(d)
            with self.assertRaisesRegex(ValueError,'UNREVIEWED_ENGINE_COMMAND'):
                backend.call(['docker','rm','unrelated'])

    def test_start_requires_verified_durable_container_id(self):
        with tempfile.TemporaryDirectory() as d:
            *_,backend=self.setup_context(d)
            with self.assertRaisesRegex(ValueError,'START_WITHOUT_VERIFIED_DURABLE_ID'):
                backend.call(['docker','start','unknown'])

    def test_even_a_known_container_cannot_start_after_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            _,_,after,_,state,backend=self.setup_context(d)
            backend.verify('v79-hub','candidate',after)
            current=state.read();current['phase']='ACCEPTED';state.put(current)
            with self.assertRaisesRegex(ValueError,'ACCEPTED_RELEASE_NO_MUTATION'):
                backend.call(['docker','start',after['Id']])

    def test_persistent_expiry_has_no_restart_loop(self):
        service,timer=s.unit_text(1793200000)
        self.assertIn('Restart=no',service);self.assertIn('--expire',service)
        self.assertIn('Persistent=true',timer);self.assertNotIn('Restart=on-failure',service)


class ControllerTests(unittest.TestCase):
    def exercise(self,receipt_error=False,reported_rollback=None,candidate_reason=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=s.State(root);calls=[]
            installed=root/'lead-release-supervisor.py';installed.write_text('synthetic controller');installed.chmod(0o600)
            inputs=s.canon({'organization':'synthetic-org'});file=root/'configuration-inputs.json';file.write_bytes(inputs);file.chmod(0o600)
            row={'State':{'Running':True,'Health':{'Status':'healthy'}}}
            plan={'apps':{n:{'baseline':copy.deepcopy(row),
                'candidate_image':{'Id':n+'-new'},'rollback_image':{'Id':n+'-old'},
                'image_manifests':{n+'-new':'new-manifest',n+'-old':'old-manifest'}} for n in s.ORDER},'protected':{'db':{}}}
            backend=SimpleNamespace(plan=plan,check_files=lambda:None,protected=lambda:None,inspect=lambda name:row,
                eligible=lambda name:None,healthy=lambda *a:None)
            def engine_deploy(b):
                calls.append('deploy');current=state.read();current['touched']=list(s.ORDER);state.put(current)
                if reported_rollback:
                    current['rollback_failed' if reported_rollback=='failed' else 'engine_rollback_complete']=True
                    state.put(current)
                    if reported_rollback=='failed':raise ValueError('ROLLBACK_INCOMPLETE_OPERATOR_REQUIRED')
                    return {'status':'PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED',
                        **({'candidate_failure_reason':candidate_reason} if candidate_reason else {})}
                return {'status':'PASS_DEPLOYED_HEALTHY_ACCEPTANCE_PENDING'}
            def engine_rollback(b,names):
                calls.append(('rollback',names));return {'status':'PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED'}
            engine=SimpleNamespace(protected_fingerprint=lambda r:r,deploy=engine_deploy,rollback=engine_rollback)
            helper=SimpleNamespace(INPUT_SHA=hashlib.sha256(inputs).hexdigest(),heartbeat=lambda r:contextlib.nullcontext(),
                image_metadata=lambda image:({},'new-manifest' if image.endswith('-new') else 'old-manifest'))
            def arming(deadline):
                self.assertEqual(state.read()['phase'],'ARMING');calls.append('arm')
            def match(*args):
                if receipt_error:raise ValueError('ORIGINAL_LEAD_EVENT_IDENTITIES_CHANGED')
                calls.append('receipt');return True,'e'*64
            with patch.object(s,'ROOT',root),patch.object(s,'__file__',str(installed)),\
                 patch.object(s,'read_lead',return_value={'id':2,'hub':'disabled','tiquet':'sent'}),\
                 patch.object(s,'arm',side_effect=arming),patch.object(s,'receipt_matches',side_effect=match),\
                 patch.object(s,'disarm',side_effect=lambda:calls.append('disarm') or True):
                result=s.deploy(engine,backend,plan,helper,state)
            return result,calls,state.read()

    def test_receipt_acceptance_only_after_timer_arming_and_engine_deploy(self):
        result,calls,state=self.exercise()
        self.assertEqual(calls,['arm','deploy','receipt','disarm'])
        self.assertEqual(result['result'],'PASS_LEAD_INTEGRATION_ACCEPTED');self.assertEqual(state['phase'],'ACCEPTED')

    def test_receipt_mismatch_uses_original_engine_rollback_and_never_accepts(self):
        result,calls,state=self.exercise(True)
        self.assertEqual(result['result'],'RELEASE_FAILED_ORIGINALS_RESTORED')
        self.assertIn(('rollback',list(s.ORDER)),calls);self.assertEqual(state['phase'],'ROLLED_BACK')

    def test_original_engine_rollback_failure_is_not_blindly_retried(self):
        result,calls,state=self.exercise(reported_rollback='failed')
        self.assertEqual(result['result'],'RELEASE_REQUIRES_OPERATOR')
        self.assertFalse(result['automatic_retry'])
        self.assertFalse(any(isinstance(c,tuple) and c[0]=='rollback' for c in calls))
        self.assertEqual(state['phase'],'ROLLBACK_REQUIRES_OPERATOR')

    def test_completed_engine_rollback_is_not_run_again(self):
        result,calls,state=self.exercise(reported_rollback='complete')
        self.assertEqual(result['result'],'RELEASE_FAILED_ORIGINALS_RESTORED')
        self.assertFalse(any(isinstance(c,tuple) and c[0]=='rollback' for c in calls))
        self.assertEqual(state['phase'],'ROLLED_BACK')

    def test_wrong_deployment_order_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            state=s.State(directory);plan={'apps':{name:{} for name in reversed(s.ORDER)}}
            with self.assertRaisesRegex(ValueError,'HUB_MUST_SWITCH_BEFORE_WEBSITE'):
                s.deploy(None,None,plan,None,state)

    def test_engine_failure_reason_survives_completed_rollback(self):
        result,calls,state=self.exercise(reported_rollback='complete',candidate_reason='SELECTED_APP_HEALTH_TIMEOUT')
        self.assertEqual(result['reason'],'SELECTED_APP_HEALTH_TIMEOUT')
        self.assertEqual(state['candidate_failure_reason'],'SELECTED_APP_HEALTH_TIMEOUT')
        self.assertFalse(any(isinstance(c,tuple) and c[0]=='rollback' for c in calls))

    def test_changed_event_id_is_rejected_before_hub_receipt_read(self):
        expected={'hubEventId':'a','tiquetEventId':'b'}
        with patch.object(s,'read_lead',return_value={'hubEventId':'changed','tiquetEventId':'b','tiquet':'sent'}):
            with self.assertRaisesRegex(ValueError,'ORIGINAL_LEAD_EVENT_IDENTITIES_CHANGED'):
                s.receipt_matches(expected,'org')


class ReaderTests(unittest.TestCase):
    def test_encrypted_website_document_read_is_read_only_and_returns_no_pii(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize=r'''
const fs=require('fs'),p=require('path'),c=require('crypto'),{DatabaseSync}=require('node:sqlite');
fs.mkdirSync('data');const key=Buffer.from(process.env.ENCRYPTION_KEY,'hex');
function seal(s){const iv=c.randomBytes(12),x=c.createCipheriv('aes-256-gcm',key,iv),b=Buffer.concat([x.update(s),x.final()]);
return 'enc:v1:'+Buffer.concat([iv,x.getAuthTag(),b]).toString('base64');}
const rows=[{id:2,company:seal('V79-TEST-20261028-A'),hubEventId:'11111111-1111-4111-8111-111111111111',
tiquetEventId:'22222222-2222-4222-8222-222222222222',hubEventStatus:'disabled',tiquetSyncStatus:'sent'}];
const db=new DatabaseSync('data/website.db');db.exec('CREATE TABLE documents(name TEXT PRIMARY KEY,value TEXT NOT NULL)');
db.prepare('INSERT INTO documents VALUES(?,?)').run('vision79_leads.json',seal(JSON.stringify(rows)));db.close();
'''
            env={**os.environ,'ENCRYPTION_KEY':'12'*32}
            subprocess.run(['node','-e',initialize],cwd=directory,env=env,capture_output=True,check=True)
            file=Path(directory)/'data/website.db';before=file.read_bytes()
            p=subprocess.run(['node','-e',s.WEBSITE_READER],cwd=directory,env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);result=json.loads(p.stdout)
            self.assertEqual(result['id'],2);self.assertEqual(result['tiquet'],'sent')
            self.assertNotIn('company',p.stdout);self.assertEqual(file.read_bytes(),before)

    def test_hub_receipt_requires_exact_tenant_subject_and_correlation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'website-lead-events').mkdir()
            event='11111111-1111-4111-8111-111111111111';correlation='22222222-2222-4222-8222-222222222222'
            record={'state':'received','digest':'a'*64,'event':{'id':event,'type':'lead.created','version':1,
                'subjectId':'2','payload':{'leadId':2},'organizationRef':'test-org','correlationId':correlation}}
            (root/'website-lead-events'/(event+'.json')).write_text(json.dumps(record))
            for organization,expected in [('test-org',True),('wrong-org',False)]:
                data={'eventId':event,'correlationId':correlation,'organization':organization}
                p=subprocess.run(['node','-e',s.HUB_READER],input=json.dumps(data),text=True,capture_output=True,
                    env={**os.environ,'DATA_DIR':directory})
                self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['matched'],expected)


if __name__=='__main__':unittest.main()
