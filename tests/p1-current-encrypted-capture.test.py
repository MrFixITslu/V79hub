"""Offline lifecycle failures + real GPG synthetic stream; no SSH/Docker."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('capture',ROOT/'scripts/p1-current-encrypted-capture.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class LifecycleTests(unittest.TestCase):
    def test_emergency_resume_validates_persisted_helper_when_invoked_via_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'v79-p1-current-capture.ABC12345';run.mkdir(mode=0o700)
            helper=run/'capture.py';helper.write_bytes(b'synthetic reviewed helper');helper.chmod(0o600)
            rows={name:{'Id':str(i)*64,'Name':'/'+name,'Image':'sha256:'+str(i)*64,'Config':{}} for i,name in enumerate(c.APPS,1)}
            record={'helper_blob':c.blob(helper.read_bytes()),'timers':[],
                    'apps':{n:{'id':row['Id'],'image':row['Image'],'runtime_sha256':hashlib.sha256(b'{}').hexdigest()} for n,row in rows.items()}}
            journal=run/'resume-journal.json';journal.write_text(json.dumps(record));journal.chmod(0o600)
            receipt=root/'release-receipt.json';receipt.write_text(json.dumps({'images':{n:row['Image'] for n,row in rows.items()}}));receipt.chmod(0o600)
            r=SimpleNamespace(inspect=lambda key:next(row for row in rows.values() if row['Id']==key),fingerprint=lambda row:row['Config'])
            with patch.object(c,'__file__','<stdin>'),patch.object(c,'RUN_RE',str(run)),patch.object(c,'ACCEPTED',root),patch.object(c,'restore') as restore:
                r.emit=lambda *a:None
                c.resume_apps(r,run,c.blob(helper.read_bytes()));restore.assert_called_once()

    def test_plan_output_contract_rejects_unbounded_or_secret_values(self):
        self.assertTrue(c.plan_safe('P1_CAPTURE_PLAN_SHA256='+'a'*64))
        self.assertTrue(c.plan_safe('CAPTURE_TIMER_1=v79-workforce-task.timer'))
        self.assertFalse(c.plan_safe('CAPTURE_TIMER_1=PRIVATE_MARKER'))
        self.assertFalse(c.plan_safe('ENV=PRIVATE_MARKER'))

    def test_pinned_utility_marker_compatibility(self):
        import ast
        path=os.environ.get('P1_TEST_UTILITY_PATH')
        if not path:
            if os.environ.get('GITHUB_ACTIONS')=='true':self.fail('CI must provide exact pinned utility')
            self.skipTest('Exact pinned utility integration required in GitHub CI')
        r=c.load_core(Path(path))
        tree=ast.parse((ROOT/'scripts/p1-current-encrypted-capture.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='emit':
                key=node.args[0].value
                self.assertTrue(r.SAFE_LINE.fullmatch(key+'=TEST'),key)
        self.assertFalse(r.SAFE_LINE.fullmatch('P1_CAPTURE_PLAN_SHA256='+'a'*64))
        self.assertTrue(c.plan_safe('P1_CAPTURE_PLAN_SHA256='+'a'*64))

    def test_early_detached_failure_closes_completion_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)/'v79-p1-current-capture.ABC12345';run.mkdir(mode=0o700)
            with patch.object(c,'__file__',str(run/'capture.py')),patch.object(c,'RUN_RE',str(run)), \
                 patch.object(sys,'argv',['capture','--server-capture',str(run),'key','--plan-sha','a'*64,'--approve-pause']), \
                 patch.object(c,'server',side_effect=c.Stop('TRUSTED_UTILITY_CHANGED')):
                with self.assertRaisesRegex(c.Stop,'TRUSTED_UTILITY_CHANGED'):c.main()
            self.assertEqual((run/'exit-code').read_text(),'1')

    def test_encryptor_spawn_failure_kills_and_reaps_started_producer(self):
        from unittest.mock import MagicMock
        producer=MagicMock();producer.poll.return_value=None
        with tempfile.TemporaryDirectory() as tmp,patch.object(c.subprocess,'Popen',side_effect=[producer,OSError('synthetic')]):
            r=SimpleNamespace(RECIPIENT='A'*40,clean_env=lambda:{})
            with self.assertRaises(OSError):c.stream(r,['synthetic'],Path(tmp)/'out.gpg',Path(tmp),30)
        producer.kill.assert_called_once();producer.wait.assert_called_once()

    def exercise(self,failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);names=(*c.APPS,*c.DBS)
            selected={n:{'Id':str(i)*64,'Image':'sha256:'+str(i)*64,'Config':{'fixture':'PRIVATE_MARKER'},'Mounts':[{'Destination':'/app/data'}]} for i,n in enumerate(names,1)}
            before=copy.deepcopy(selected);commands=[];events=[]
            receipt='F'*40;digest='a'*64;timers=['v79-workforce-task.timer']
            def call(args,**kwargs):
                commands.append(args)
                if args[:2]==['docker','stop'] and failure=='stop':raise c.Stop('INJECTED_STOP_FAILURE')
                if args[0]=='gpg' and '--fingerprint' in args:return ('fpr:::::::::'+receipt+':').encode()
                if args[0]=='gpg' and kwargs.get('output'):kwargs['output'].write(b'x'*100)
                return b''
            def encrypt(r,args,destination,keyring,timeout):
                events.append(('stream',destination.name));destination.write_bytes(b'x'*100)
                if failure=='image' and 'save' in args:raise c.Stop('INJECTED_IMAGE_FAILURE')
                if failure=='database' and 'pg_dump' in args[-1]:raise c.Stop('INJECTED_DUMP_FAILURE')
            def inspect(key,image=False):
                if image:return {'Size':1024}
                return next(copy.deepcopy(x) for x in selected.values() if x['Id']==key)
            def save(path,data):path.write_text(json.dumps(data))
            r=SimpleNamespace(RECIPIENT=receipt,call=call,inspect=inspect,
                fingerprint=lambda row:row['Config'],health=lambda name,*a,**kw:copy.deepcopy(selected[name]),
                emit=lambda k,v:events.append((k,v)),timers_idle=lambda t:None,same_others=lambda *a:None,
                sha_file=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),private_json=save)
            def collect(_):return digest,selected,before,{}, {'/public-config':b'fixture'},timers
            with patch.object(c,'collect',side_effect=collect),patch.object(c,'stream',side_effect=encrypt), \
                 patch.object(c,'config_file',return_value=b'fixture'),patch.object(c.shutil,'which',return_value='/fixture'), \
                 patch.object(c.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)):
                if failure:
                    with self.assertRaises(c.Stop):c.capture(r,run,'cHVibGljLWtleQ==',digest)
                else:c.capture(r,run,'cHVibGljLWtleQ==',digest)
            self.assertNotIn('PRIVATE_MARKER',json.dumps(events))
            if failure=='image':
                self.assertFalse(any(x[:2]==['docker','stop'] for x in commands))
                self.assertFalse(any(x[:3]==['systemctl','--user','stop'] for x in commands))
            elif failure:
                self.assertTrue(any(x[:2]==['docker','start'] for x in commands))
                self.assertIn(['systemctl','--user','start',*timers],commands)
                self.assertFalse((run/'checkpoint/manifest.json').exists())
            else:
                manifest=json.loads((run/'checkpoint/manifest.json').read_text())
                self.assertEqual(manifest['status'],'CAPTURED_NOT_RESTORE_TESTED')
                self.assertEqual(set(manifest['source_images']),set(names))
                self.assertIn(['systemctl','--user','start',*timers],commands)
            self.assertFalse(any(x[:2] in (['docker','rm'],['docker','load'],['docker','compose']) for x in commands))
            return commands,events

    def test_success_capture_has_manifest_only_after_app_resume(self):self.exercise()
    def test_image_failure_never_pauses_anything(self):self.exercise('image')
    def test_dump_failure_resumes_same_app_ids_and_timers(self):self.exercise('database')
    def test_partial_stop_failure_is_armed_for_resume(self):self.exercise('stop')

    def test_unproven_resume_holds_timers_and_reports_failure(self):
        events=[];commands=[]
        r=SimpleNamespace(inspect=lambda key:(_ for _ in ()).throw(c.Stop('INJECTED_ID_LOSS')),
                          call=lambda a,**kw:commands.append(a),emit=lambda k,v:events.append((k,v)))
        selected={c.APPS[0]:{'Id':'a'*64,'Image':'sha256:'+'b'*64}}
        with self.assertRaisesRegex(c.Stop,'APP_RESUME_NOT_PROVEN'):
            c.restore(r,selected,[c.APPS[0]],['v79-workforce-task.timer'])
        self.assertFalse(commands);self.assertIn(('PRESERVED','HELD_APP_RECOVERY_NOT_PROVEN'),events)

    def test_changed_approved_plan_stops_before_any_side_effect(self):
        r=SimpleNamespace(call=lambda *a,**kw:self.fail('unexpected mutation'))
        with patch.object(c,'collect',return_value=('a'*64,None,None,None,None,None)):
            with self.assertRaisesRegex(c.Stop,'APPROVED_PLAN_CHANGED'):c.capture(r,Path('/unused'),'','b'*64)

    def test_archive_contains_relative_private_records_only(self):
        raw=c.configuration_archive(None,{'a':{'Config':{'Env':['TEST=SYNTHETIC']}}},{},{'/public':b'fixture'})
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            self.assertEqual(set(archive.getnames()),{'runtime.json','frozen-compose.json','input-map.json','config/0'})
            self.assertTrue(all(x.mode==0o600 and x.isfile() for x in archive))

    def test_no_old_frozen_plan_reference(self):
        source=(ROOT/'scripts/p1-current-encrypted-capture.py').read_text()
        self.assertNotIn('v79-remaining-plan.by50q9w3',source)
        self.assertNotIn('continued_server_locked',source)
        self.assertTrue(c.overlap('/a','/a/b'));self.assertFalse(c.overlap('/a','/ab'))

class PlanTests(unittest.TestCase):
    def plan(self,change=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt=root/'release-receipt.json'
            rows={}
            for i,name in enumerate((*c.APPS,*c.DBS),1):
                work=root/name;work.mkdir();config=work/'compose.json';config.write_text('{}')
                image='sha256:'+str(i)*64 if name in c.APPS else c.DBS[name][0]
                env=(['V79_REQUIRE_ADMIN_MFA=1','V79_TIQUET_LAUNCH_SECRET=synthetic'] if name==c.APPS[0]
                     else ['V79_ALLOW_LEGACY_AUTH=0','V79_ENTITLEMENT_RECHECK_ENABLED=1','V79_TIQUET_LAUNCH_SECRET=synthetic'])
                destinations=['/app/data'] if name==c.APPS[0] else ['/app/data','/app/uploads'] if name==c.APPS[1] else []
                rows[name]={'Id':str(i)*64,'Name':'/'+name,'Image':image,'State':{'Running':True,'Health':{'Status':'healthy'}},
                   'Config':{'Env':env,'Labels':{'com.docker.compose.project.config_files':str(config),
                    'com.docker.compose.project.working_dir':str(work),'com.docker.compose.project':name,'com.docker.compose.service':name}},
                   'Mounts':[{'Destination':d,'Source':'/synthetic/'+name+d,'Type':'bind','RW':True} for d in destinations]}
            receipt.write_text(json.dumps({'images':{name:rows[name]['Image'] for name in c.APPS}}));receipt.chmod(0o600)
            if change:change(rows)
            commands=[]
            def call(args,**kw):
                commands.append(args)
                if args[:2]==['docker','ps']:return '\n'.join(rows).encode()
                if args[:3]==['docker','container','inspect']:return json.dumps(list(rows.values())).encode()
                if args[-1]=='--version':
                    name=next(n for n,row in rows.items() if row['Id']==args[2])
                    return ('pg_dump (PostgreSQL) '+c.DBS[name][1]+'.6').encode()
                return b''
            r=SimpleNamespace(call=call,envmap=lambda env:dict(v.split('=',1) for v in env),
                original_model=lambda *a:{},fingerprint=lambda row:row['Config'],active_timers=lambda:[])
            with patch.object(c,'ACCEPTED',root):result=c.collect(r)
            self.assertFalse(any(a[:2] in (['docker','start'],['docker','stop']) for a in commands))
            return result[0]

    def test_current_readonly_plan_is_digested(self):
        self.assertRegex(self.plan(),r'^[a-f0-9]{64}$')

    def test_true_string_is_not_mandatory_admin_mfa(self):
        def change(rows):rows[c.APPS[0]]['Config']['Env'][0]='V79_REQUIRE_ADMIN_MFA=true'
        with self.assertRaisesRegex(c.Stop,'SECURITY_FLAGS_CHANGED'):self.plan(change)

    def test_unknown_mount_and_other_writable_container_are_rejected(self):
        def unknown(rows):rows[c.APPS[0]]['Mounts'][0]['Destination']='/unexpected'
        with self.assertRaisesRegex(c.Stop,'MOUNT_SCOPE'):self.plan(unknown)
        def writer(rows):
            rows['foreign']={'Name':'/foreign','State':{'Running':True},'Mounts':[{'RW':True,'Source':rows[c.APPS[0]]['Mounts'][0]['Source']+'/nested'}]}
        with self.assertRaisesRegex(c.Stop,'OTHER_WRITER'):self.plan(writer)

class EncryptionTests(unittest.TestCase):
    def test_real_gpg_roundtrip_and_failed_producer_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            keyring=Path(tmp)/'key';keyring.mkdir(mode=0o700)
            generated=subprocess.run(['gpg','--homedir',str(keyring),'--batch','--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Synthetic CI <p1@example.test>','rsa2048','encr','0'],capture_output=True,timeout=60)
            if generated.returncode and b'No agent running' in generated.stderr and os.environ.get('GITHUB_ACTIONS')!='true':
                self.skipTest('Local runtime cannot start gpg-agent; real crypto remains required in GitHub CI')
            self.assertEqual(generated.returncode,0,'synthetic GPG key generation')
            keys=subprocess.run(['gpg','--homedir',str(keyring),'--with-colons','--list-keys'],check=True,capture_output=True).stdout.decode()
            fingerprint=next(x.split(':')[9] for x in keys.splitlines() if x.startswith('fpr:'))
            r=SimpleNamespace(RECIPIENT=fingerprint,clean_env=lambda:dict(os.environ))
            encrypted=Path(tmp)/'fixture.gpg'
            c.stream(r,[sys.executable,'-c',"print('synthetic fixture')"],encrypted,keyring,30)
            result=subprocess.run(['gpg','--homedir',str(keyring),'--batch','--decrypt',str(encrypted)],check=True,capture_output=True,timeout=30)
            self.assertEqual(result.stdout,b'synthetic fixture\n')
            with self.assertRaisesRegex(c.Stop,'ENCRYPTED_STREAM_FAILED'):
                c.stream(r,[sys.executable,'-c',"import sys;print('partial');sys.exit(1)"],Path(tmp)/'partial.gpg',keyring,30)

if __name__=='__main__':unittest.main()
