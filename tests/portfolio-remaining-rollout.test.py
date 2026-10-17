import base64
import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
s=module('remaining_rollout','scripts/portfolio-remaining-rollout.py')
r=module('verified_rollout','scripts/portfolio-pinned-rollout.py')
p=module('verified_remaining_plan','scripts/portfolio-remaining-preflight.py')

def row(name,image):
    return {'Name':'/'+name,'Id':name+'-original','Image':image,
        'Config':{'Env':['PASSWORD=PRIVATE_MARKER'],'Cmd':['node','server.js'],'User':'node'},
        'HostConfig':{},'Mounts':[],'NetworkSettings':{'Networks':{}},
        'State':{'Running':True,'Status':'running',**({} if name=='v79-pos-worker' else {'Health':{'Status':'healthy'}})}}

class LifecycleTests(unittest.TestCase):
    def exercise(self,failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)
            before={n:row(n,pin['image_id']) for n,pin in p.PINS.items()}
            before['v79_course_builder']['Mounts']=[{'Type':'bind','Source':'PRIVATE_PATH','Destination':'/app/data','RW':True}]
            live=copy.deepcopy(before);all_before={**before,'v79-hub':row('v79-hub','sha256:'+'e'*64)}
            images={n:'sha256:'+str(i+1)*64 for i,n in enumerate(p.PINS)}
            for n in p.PINS:
                for kind in ('original','candidate'):
                    r.private_json(run/(n+'-'+kind+'.pinned.yml'),{'services':{p.PINS[n]['compose_service']:{'image':images[n] if kind=='candidate' else before[n]['Image']}}})
            plans={n:(run/(n+'-original.pinned.yml'),run/(n+'-candidate.pinned.yml')) for n in p.PINS}
            commands=[];events=[];output=[]
            def call(args,**kwargs):
                commands.append(args)
                if args[0]=='gpg' and '--fingerprint' in args:return ('fpr:::::::::'+r.RECIPIENT+':').encode()
                if args[:2]==['docker','stop']:
                    live[args[-1]]['State']['Running']=False
                    if failure=='stop' and args[-1]=='v79-pos':raise r.Stop('INJECTED_STOP_FAILURE')
                if args[:2]==['docker','start']:live[args[-1]]['State']['Running']=True
                return b''
            def encrypted(args,dest,*_):
                events.append(('capture',dest.name));commands.append(args)
                if failure=='capture' and dest.suffixes[-2:]==['.dump','.gpg']:raise r.Stop('INJECTED_CAPTURE_FAILURE')
                dest.write_bytes(b'synthetic-ciphertext'*8)
            def up(path,pin):
                name=pin['container'];candidate='-candidate.' in path.name
                if candidate:
                    self.assertTrue((run/'checkpoint/manifest.json').exists())
                    self.assertEqual(set(n for n in s.STOP_ORDER if not live[n]['State']['Running']),set(s.STOP_ORDER)-set(n for action,n in events if action=='switch'))
                live[name]['Image']=images[name] if candidate else before[name]['Image'];live[name]['State']['Running']=True
                events.append(('switch' if candidate else 'rollback',name))
                if candidate and failure==name:raise r.Stop('INJECTED_PARTIAL_SWITCH')
                if not candidate and failure=='rollback' and name=='v79-pos':raise r.Stop('INJECTED_ROLLBACK_FAILURE')
                if candidate and failure=='rollback' and name=='v79-pos-worker':raise r.Stop('INJECTED_PARTIAL_SWITCH')
            def wait(_,name,image,worker_probe=False):
                self.assertEqual(live[name]['Image'],image)
                result=copy.deepcopy(live[name])
                if failure=='runtime' and image==images[name]:result['HostConfig']['Privileged']=True
                return result
            with patch.object(s,'frozen_candidates',return_value=plans),patch.object(s,'check_plan',return_value=(before,{})),patch.object(r,'call',side_effect=call), \
                 patch.object(r,'encrypted_stream',side_effect=encrypted),patch.object(r,'active_timers',return_value=['v79-workforce-task.timer']), \
                 patch.object(r,'timers_idle'),patch.object(r,'up',side_effect=up),patch.object(s,'wait_service',side_effect=wait), \
                 patch.object(r,'same_others'),patch.object(p,'pos_migrations',return_value={'status':'PASS'}), \
                 patch.object(r,'capture_failed_startup',side_effect=lambda *args:events.append(('safe-evidence',args[1]))), \
                 patch.object(r,'emit',side_effect=lambda k,v:output.append((k,v))):
                if failure:
                    with self.assertRaises((s.Stop,r.Stop)):
                        s.checkpoint_and_switch(r,p,run,before,{},images,base64.b64encode(b'public-key').decode(),all_before)
                else:s.checkpoint_and_switch(r,p,run,before,{},images,base64.b64encode(b'public-key').decode(),all_before)
            self.assertIn(['systemctl','--user','start','v79-workforce-task.timer'],commands)
            self.assertNotIn('PRIVATE',json.dumps(output))
            if failure and failure!='rollback':
                for n in before:
                    self.assertEqual(live[n]['Image'],before[n]['Image']);self.assertTrue(live[n]['State']['Running'])
            self.assertFalse(any(cmd[:2] in (['docker','volume'],['docker','network'],['docker','system']) for cmd in commands))
            return commands,events,output

    def test_success_captures_before_switch_and_preserves_other_services(self):
        commands,events,output=self.exercise()
        self.assertIn(('RESULT','ACADEMY_POS_GAMES_DEPLOYED_WITH_WORKER_PROCESS_DB_CHECK'),output)
        self.assertIn(['docker','exec','v79-pos-redis','redis-cli','--rdb','-'],commands)
        self.assertFalse(any('migrate deploy' in ' '.join(cmd) for cmd in commands))

    def test_checkpoint_failure_restores_all_stopped_without_switch(self):
        _,events,output=self.exercise('capture')
        self.assertFalse(any(action=='switch' for action,_ in events))
        self.assertIn(('ROLLBACK','ALL_STOPPED_ORIGINALS_RESTORED'),output)

    def test_stop_failure_restores_even_partially_stopped_service(self):self.exercise('stop')

    def test_every_switch_failure_restores_changed_and_unswitched_originals(self):
        for n in s.SWITCH_ORDER:
            with self.subTest(service=n):self.exercise(n)

    def test_runtime_security_drift_forces_rollback(self):self.exercise('runtime')

    def test_genuine_rollback_failure_is_not_hidden(self):
        _,_,output=self.exercise('rollback')
        self.assertIn(('ROLLBACK','FAILED_MANUAL_RECOVERY_REQUIRED'),output)

    def test_failure_evidence_precedes_failed_candidate_replacement(self):
        _,events,_=self.exercise('v79-pos-worker')
        self.assertLess(events.index(('safe-evidence','v79-pos-worker')),events.index(('rollback','v79-pos-worker')))

class GuardTests(unittest.TestCase):
    def test_modules_reject_modified_source_before_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'core.py').write_text("raise Exception('SHOULD_NOT_EXECUTE')")
            with self.assertRaisesRegex(s.Stop,'MODULE_INTEGRITY_FAILURE'):s.load_modules(root)

    def test_exact_pinned_modules_still_match_source(self):
        for _,(path,digest) in s.MODULES.items():self.assertEqual(s.blob((ROOT/path).read_bytes()),digest)

    def test_pos_missing_or_placeholder_credentials_stop_before_build(self):
        env={'NODE_ENV':'production','GIFT_CARD_PEPPER':'secure-fixture-value','ENCRYPTION_KEY':'x'*32,
             'V79_PLATFORM_SHARED_SECRET':'x'*32,'CORS_ORIGINS':'https://pos.example.invalid','DATABASE_URL':'postgresql://fixture'}
        s.check_pos_environment({'Config':{'Env':[k+'='+v for k,v in env.items()]}})
        for key in ('GIFT_CARD_PEPPER','ENCRYPTION_KEY','V79_PLATFORM_SHARED_SECRET','CORS_ORIGINS','DATABASE_URL'):
            changed=dict(env);changed.pop(key)
            with self.assertRaises(s.Stop):s.check_pos_environment({'Config':{'Env':[k+'='+v for k,v in changed.items()]}})

    def test_unknown_inspect_error_is_not_resource_absence(self):
        with patch.object(s.subprocess,'run',return_value=type('P',(),{'returncode':1})()),patch.object(r,'call',side_effect=r.Stop('ENGINE_FAILED')):
            with self.assertRaisesRegex(r.Stop,'ENGINE_FAILED'):s.optional_container(r,'probe')

    def test_worker_probe_reads_only_actual_process_and_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);worker=root/'worker.js';worker.write_text('setInterval(()=>{},1000)')
            prisma=root/'prisma.mjs';prisma.write_text("export const prisma={$transaction:async f=>{if(process.env.DATABASE_URL!=='PRIVATE_DB_MARKER')throw Error();await f({$executeRawUnsafe:async q=>{if(q!=='SET TRANSACTION READ ONLY')throw Error()},$queryRawUnsafe:async q=>{if(q!=='SELECT 1')throw Error();return [{value:1}]}})},$disconnect:async()=>{}}")
            import os
            child=subprocess.Popen(['node',str(worker)],env={**os.environ,'DATABASE_URL':'PRIVATE_DB_MARKER'})
            try:
                code=s.WORKER_PROBE.replace('/app/apps/api/dist/lib/prisma.js',prisma.as_uri())
                result=subprocess.run(['node','-e',code],capture_output=True,timeout=15,env={k:v for k,v in os.environ.items() if k!='DATABASE_URL'})
                self.assertEqual(result.returncode,0,result.stderr.decode())
                self.assertEqual(result.stdout.strip(),b'WORKER_PROCESS_AND_READ_ONLY_DATABASE_PASS')
                self.assertNotIn(b'PRIVATE',result.stdout)
            finally:child.terminate();child.wait()


class PlanAndBuildTests(unittest.TestCase):
    def test_successful_plan_revalidation_and_runtime_drift_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=root/'plan';plan.mkdir(mode=0o700);accepted=root/'accepted';accepted.mkdir()
            baseline={n:row(n,pin['image_id']) for n,pin in p.PINS.items()}
            models={n:{'services':{p.PINS[n]['compose_service']:{'image':v['Image']}}} for n,v in baseline.items()}
            r.private_json(plan/'runtime-before.json',baseline)
            r.private_json(plan/'plan-summary.json',{'status':'PLAN_PREPARED_NOT_DEPLOYED','sources':p.SOURCES,'pins':p.PINS,
                            'pos_migrations':{'status':'PASS'},'results':{n:{'runtime_parity':'PASS'} for n in p.PINS}})
            for n in p.PINS:r.private_json(plan/(n+'-original.pinned.yml'),models[n])
            receipt={'images':{'v79-hub':'sha256:'+'a'*64,'v79-tiquet-manager':'sha256:'+'b'*64}}
            r.private_json(accepted/'release-receipt.json',receipt)
            live=copy.deepcopy(baseline)
            for n,image in {**s.DATABASES,'v79-pos-redis':s.REDIS_IMAGE,**receipt['images']}.items():live[n]=row(n,image)
            with patch.object(s,'PLAN',plan),patch.object(p,'ACCEPTED_RUN',accepted), \
                 patch.object(r,'inspect',side_effect=lambda n:copy.deepcopy(live[n])), \
                 patch.object(r,'original_model',side_effect=lambda v,pin:models[pin['container']]), \
                 patch.object(p,'pos_migrations',return_value={'status':'PASS'}):
                found,plans=s.check_plan(r,p);self.assertEqual(found,baseline);self.assertEqual(plans,models)
                live['v79-pos']['HostConfig']['Privileged']=True
                with self.assertRaisesRegex(s.Stop,'ACCEPTED_RUNTIME_CHANGED'):s.check_plan(r,p)

    def test_builds_three_sources_once_and_probes_both_pos_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);before={n:row(n,pin['image_id']) for n,pin in p.PINS.items()};events=[]
            ids={repo:'sha256:'+ch*64 for repo,ch in zip(p.SOURCES,('a','b','c'))}
            def call(args,**kwargs):
                if args[0]=='git' and 'rev-parse' in args:return p.SOURCES[Path(args[2]).name].encode()
                if args[:2]==['docker','build']:events.append(('build',args[-1]))
                return b''
            def inspect(tag,image=False):
                repo=next(repo for repo in p.SOURCES if repo.lower() in tag)
                return {'Id':ids[repo],'Config':{'User':'node','Env':[], 'Labels':{'org.opencontainers.image.revision':p.SOURCES[repo]}}}
            with patch.object(r,'call',side_effect=call),patch.object(r,'inspect',side_effect=inspect), \
                 patch.object(r,'public_checkout_modes',side_effect=lambda path:events.append(('modes',str(path)))), \
                 patch.object(s,'probe_image') as probe,patch.object(r,'emit'):
                images=s.build_images(r,p,root,before)
            self.assertEqual(images['v79-pos'],images['v79-pos-worker'])
            self.assertEqual(probe.call_count,4)
            for repo in p.SOURCES:self.assertLess(events.index(('modes',str(root/repo))),events.index(('build',str(root/repo))))

    def test_server_build_failure_never_stops_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);commands=[]
            before={n:row(n,pin['image_id']) for n,pin in p.PINS.items()}
            def call(args,**kwargs):
                commands.append(args)
                if args[:3]==['docker','compose','up']:return b'--no-deps --no-build --pull'
                if 'redis-cli' in args:return b'--rdb' if '--help' in args else b'PONG'
                if args[:2]==['docker','ps']:return b'v79-pos\n'
                if args[:2]==['docker','inspect']:return json.dumps([before['v79-pos']]).encode()
                return b''
            with patch.object(s.socket,'gethostname',return_value='v79sl'),patch.object(s.os,'getuid',return_value=1000), \
                 patch.object(s.signal,'signal'),patch.object(s.Path,'home',return_value=root), \
                 patch.object(s.shutil,'which',return_value='/fixture'), \
                 patch.object(s.shutil,'disk_usage',return_value=type('D',(),{'free':100*1024**3})()), \
                 patch.object(s,'check_plan',return_value=(before,{})),patch.object(s,'check_pos_environment'), \
                 patch.object(s,'build_images',side_effect=r.Stop('BUILD_FAILED')),patch.object(r,'call',side_effect=call),patch.object(r,'sha_file',return_value='0'*64),patch.object(r,'emit'):
                with self.assertRaisesRegex(r.Stop,'BUILD_FAILED'):s.server(root,'',r,p)
            self.assertFalse(any(cmd[:2] in (['docker','stop'],['docker','start'],['systemctl','--user']) for cmd in commands))

    def test_module_failure_still_closes_remote_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=io.StringIO()
            with patch.object(s,'RUN_RE',str(root)),patch.object(s,'__file__',str(root/'rollout.py')), \
                 patch.object(s.sys,'argv',['rollout','--server',str(root),'public']), \
                 patch.object(s,'load_modules',side_effect=s.Stop('MODULE_INTEGRITY_FAILURE')),redirect_stdout(output):
                self.assertEqual(s.main(),1)
            self.assertEqual((root/'exit-code').read_text(),'1')
            self.assertIn('MODULE_INTEGRITY_FAILURE',output.getvalue())

if __name__=='__main__':unittest.main()
