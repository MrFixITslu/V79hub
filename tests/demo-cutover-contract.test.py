#!/usr/bin/env python3
"""Ambiguous-outcome, startup and rollback failure tests; no Docker required."""
import importlib.util
import copy
import tempfile
import json
import time
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('transaction',
    Path(__file__).parents[1]/'scripts/paired-compose-transaction-demo-v2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Backend:
    def __init__(self,fail=None):
        self.plan={'apps':{'hub':{},'tiquet':{}}};self.fail=fail;self.actions=[]
        self.state={'hub':'rollback','tiquet':'rollback'}
    def protected(self):self.actions.append(('protected',))
    def check_files(self):
        if self.fail=='seal':raise m.Refused('seal')
    def eligible(self,name):
        if self.fail=='foreign':raise m.Refused('foreign')
    def journal(self,event,name=None,reason=None):
        self.actions.append((event,name) if reason is None else (event,name,reason))
        if self.fail=='journal' and event=='CANDIDATE_INTENT':raise m.Refused('disk')
    def switch(self,name,which):
        self.actions.append(('switch',name,which))
        # A failed or timed-out CLI may already have replaced the container.
        self.state[name]=which
        if self.fail==name and which=='candidate':raise m.Refused('timeout_after_side_effect')
        if self.fail=='rollback' and ((name=='tiquet' and which=='candidate')
                                      or (name=='hub' and which=='rollback')):
            raise m.Refused('failed')
        if self.fail=='missing' and which=='candidate':
            self.state[name]='absent';raise m.Refused('removed_then_create_failed')
        if self.fail=='interrupt' and name=='tiquet' and which=='candidate':raise KeyboardInterrupt()
    def healthy(self,name,which):
        self.actions.append(('healthy',name,which))
        if self.fail=='startup' and name=='tiquet' and which=='candidate':raise m.Refused('unhealthy')


class TransactionTests(unittest.TestCase):
    def test_mount_order_is_not_drift_but_source_change_is(self):
        before,_,_=self.runtime_fixture()
        before['State'].update({'Status':'running','StartedAt':'synthetic'})
        before['Mounts']=[{'Destination':'/a','Source':'/first'},
                          {'Destination':'/b','Source':'/second'}]
        after=copy.deepcopy(before);after['Mounts'].reverse()
        self.assertEqual(m.protected_fingerprint(before),m.protected_fingerprint(after))
        after['Mounts'][0]['Source']='/other'
        self.assertNotEqual(m.protected_fingerprint(before),m.protected_fingerprint(after))

    def test_production_supervision_requires_a_fresh_private_heartbeat(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);b=m.ComposeBackend(root,{'requires_supervision':True})
            with self.assertRaisesRegex(m.Refused,'SUPERVISION_LEASE_LOST'):b.supervised()
            lease=root/'supervision.json'
            lease.write_text(json.dumps({'monotonic':time.monotonic()}));lease.chmod(0o600)
            b.supervised()
            lease.write_text(json.dumps({'monotonic':time.monotonic()-31}))
            with self.assertRaisesRegex(m.Refused,'SUPERVISION_LEASE_LOST'):b.supervised()
            lease.write_text(json.dumps({'monotonic':time.monotonic()}));lease.chmod(0o644)
            with self.assertRaisesRegex(m.Refused,'SUPERVISION_LEASE_LOST'):b.supervised()

    def runtime_fixture(self):
        old_id='a'*64;new_id='b'*64
        old_image={'Id':'sha256:'+'1'*64,'Config':{'Labels':{'org.example.revision':'before'}}}
        new_image={'Id':'sha256:'+'2'*64,'Config':{'Labels':{'org.example.revision':'after'}}}
        labels={'org.example.revision':'before','v79.security':'enabled',
            'com.docker.compose.project':'fixture','com.docker.compose.service':'hub'}
        before={'Id':old_id,'Name':'/v79-hub','Image':old_image['Id'],'Config':{'Image':old_image['Id'],
            'Hostname':old_id[:12],'User':'appuser','Env':['SECRET=synthetic-only'],'Labels':labels},
            'HostConfig':{'OomKillDisable':None},'Mounts':[],
            'NetworkSettings':{'Networks':{}},'State':{'Running':False}}
        after=copy.deepcopy(before);after['Id']=new_id;after['Image']=new_image['Id']
        after['Config']['Hostname']=new_id[:12];after['Config']['Image']=new_image['Id']
        after['Config']['Labels'].update({'org.example.revision':'after',
            'com.docker.compose.project.config_files':'/private/candidate.json',
            'com.docker.compose.project.environment_file':'/dev/null',
            'com.docker.compose.image':new_image['Id'],'com.docker.compose.version':'5.6.0',
            'com.docker.compose.config-hash':'c'*64})
        after['HostConfig']['OomKillDisable']=False
        entry={'model':{'services':{'hub':{}}},'service':'hub','compose_version':'5.6.0',
            'candidate_file':'/private/candidate.json','candidate_image':new_image,
            'rollback_image':old_image}
        return before,after,entry

    def test_enabled_oom_encoding_is_equal_but_disabling_oom_is_rejected(self):
        before,after,entry=self.runtime_fixture()
        self.assertTrue(m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False))
        after['HostConfig']['OomKillDisable']=True
        with self.assertRaisesRegex(ValueError,'HOST_FIELDS_CHANGED:OomKillDisable'):
            m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False)

    def test_auth_env_process_and_unrecognized_label_changes_are_not_normalized(self):
        for kind in ('env','user','label','reserved-label'):
            before,after,entry=self.runtime_fixture()
            if kind=='env':after['Config']['Env']=['SECRET=changed-synthetic-only']
            elif kind=='user':after['Config']['User']='root'
            elif kind=='label':after['Config']['Labels']['v79.security']='disabled'
            else:after['Config']['Labels']['com.docker.compose.unknown-security-label']='disabled'
            with self.subTest(kind=kind),self.assertRaises(ValueError) as error:
                m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False)
            self.assertNotIn('synthetic-only',str(error.exception))

    def test_compose_v560_replace_label_is_exact_configured_container_name(self):
        before,after,entry=self.runtime_fixture()
        entry['model']['services']['hub']['container_name']='v79-hub'
        entry['_replaced_id']=before['Id']
        after['Config']['Labels']['com.docker.compose.replace']='v79-hub'
        self.assertTrue(m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False))
        for bad in (before['Id'],'not-v79-hub','v79-tiquet-manager',None):
            with self.subTest(replacement=bad):
                changed=copy.deepcopy(after)
                if bad is None:
                    changed['Config']['Labels'].pop('com.docker.compose.replace')
                else:
                    changed['Config']['Labels']['com.docker.compose.replace']=bad
                with self.assertRaisesRegex(m.Refused,'COMPOSE_REPLACEMENT_NAME_MISMATCH'):
                    m.runtime_matches(before,changed,entry,'candidate',selinux_enabled=False)
        invalid=copy.deepcopy(entry)
        invalid['model']['services']['hub'].pop('container_name')
        with self.assertRaisesRegex(m.Refused,'COMPOSE_REPLACEMENT_NAME_MISMATCH'):
            m.runtime_matches(before,after,invalid,'candidate',selinux_enabled=False)
        renamed=copy.deepcopy(before);renamed['Name']='/other-container'
        with self.assertRaisesRegex(m.Refused,'COMPOSE_REPLACEMENT_NAME_MISMATCH'):
            m.runtime_matches(renamed,after,entry,'candidate',selinux_enabled=False)

    def test_unexpected_replace_label_when_no_previous_container_is_rejected(self):
        before,after,entry=self.runtime_fixture()
        after['Config']['Labels']['com.docker.compose.replace']='v79-hub'
        with self.assertRaisesRegex(m.Refused,'UNEXPECTED_COMPOSE_REPLACEMENT_LABEL'):
            m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False)

    def test_compose_v238_replacement_requires_previous_exact_id(self):
        before,after,entry=self.runtime_fixture()
        entry['compose_version']='2.38.2'
        entry['_replaced_id']=before['Id']
        after['Config']['Labels']['com.docker.compose.version']='2.38.2'
        after['Config']['Labels']['com.docker.compose.replace']=before['Id']
        self.assertTrue(m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False))
        after['Config']['Labels']['com.docker.compose.replace']='v79-hub'
        with self.assertRaisesRegex(m.Refused,'COMPOSE_REPLACED_CONTAINER_ID_CHANGED'):
            m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False)

    def test_unknown_compose_version_fails_closed_when_replacing(self):
        before,after,entry=self.runtime_fixture()
        entry['compose_version']='6.0.0'
        entry['_replaced_id']=before['Id']
        after['Config']['Labels']['com.docker.compose.version']='6.0.0'
        after['Config']['Labels']['com.docker.compose.replace']='v79-hub'
        with self.assertRaisesRegex(m.Refused,'UNVERIFIED_COMPOSE_REPLACEMENT_CONTRACT'):
            m.runtime_matches(before,after,entry,'candidate',selinux_enabled=False)

    def test_durable_plan_tamper_requires_retained_external_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pin=m.seal_plan(root,{'synthetic':'original'})
            self.assertEqual(m.load_plan(root,pin),{'synthetic':'original'})
            (root/'transaction.json').write_text('{"synthetic":"modified"}')
            with self.assertRaisesRegex(m.Refused,'EXTERNAL_DIGEST_MISMATCH'):m.load_plan(root,pin)

    def test_success_still_requires_supervised_acceptance(self):
        b=Backend();result=m.deploy(b)
        self.assertEqual(b.state,dict.fromkeys(('hub','tiquet'),'candidate'))
        self.assertEqual(result['release_decision'],'HOLD')
        self.assertFalse(result['supervised_acceptance_complete'])

    def test_first_ambiguous_cli_failure_restores_touched_app(self):
        b=Backend('hub');result=m.deploy(b)
        self.assertTrue(result['candidate_deployment_failed'])
        self.assertEqual(b.state,dict.fromkeys(('hub','tiquet'),'rollback'))
        self.assertNotIn(('switch','tiquet','candidate'),b.actions)

    def test_second_failure_rolls_back_both_in_reverse_order(self):
        b=Backend('tiquet');m.deploy(b)
        self.assertEqual([a for a in b.actions if a[0]=='switch' and a[2]=='rollback'],
                         [('switch','tiquet','rollback'),('switch','hub','rollback')])

    def test_deleted_then_failed_create_is_recoverable(self):
        b=Backend('missing');m.deploy(b)
        self.assertEqual(b.state,dict.fromkeys(('hub','tiquet'),'rollback'))

    def test_health_failure_and_interrupt_restore_originals(self):
        for failure in ('startup','interrupt'):
            with self.subTest(failure=failure):
                b=Backend(failure);m.deploy(b)
                self.assertEqual(b.state,dict.fromkeys(('hub','tiquet'),'rollback'))

    def test_one_rollback_failure_preserves_both_failure_reasons(self):
        b=Backend('rollback')
        with self.assertRaisesRegex(m.Refused,'ROLLBACK_INCOMPLETE_OPERATOR_REQUIRED'):m.deploy(b)
        self.assertIn(('switch','tiquet','rollback'),b.actions)
        self.assertIn(('switch','hub','rollback'),b.actions)
        self.assertIn(('CANDIDATE_FAILED','tiquet','UNCLASSIFIED_FAILURE'),b.actions)
        self.assertIn(('ROLLBACK_FAILED','hub','UNCLASSIFIED_FAILURE'),b.actions)

    def test_demo_release_export_matches_demo_transaction_source(self):
        spec=importlib.util.spec_from_file_location('demo_release',
            Path(__file__).parents[1]/'scripts/release-hardened-pair-demo-v2.py')
        release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
        expected=(Path(__file__).parents[1]/'scripts/paired-compose-transaction-demo-v2.py').read_text()
        self.assertEqual(release.SOURCES['paired-compose-transaction.py'],expected)

    def test_journal_cannot_emit_untrusted_raw_failure_or_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=m.ComposeBackend(tmp,{'apps':{}})
            backend.journal('CANDIDATE_FAILED','v79-hub','COMPOSE_RECREATE_COMMAND_FAILED_REDACTED')
            row=json.loads((Path(tmp)/'events.jsonl').read_text().splitlines()[0])
            self.assertEqual(row['reason'],'COMPOSE_RECREATE_COMMAND_FAILED_REDACTED')
            with self.assertRaisesRegex(m.Refused,'UNSAFE_JOURNAL_FAILURE_CODE'):
                backend.journal('ROLLBACK_FAILED','v79-hub','PASSWORD=synthetic-only')
            self.assertEqual(len((Path(tmp)/'events.jsonl').read_text().splitlines()),1)

    def test_untrusted_files_foreign_image_or_unsaved_intent_stop_before_switch(self):
        for failure in ('seal','foreign','journal'):
            with self.subTest(failure=failure):
                b=Backend(failure)
                if failure=='journal':m.deploy(b)
                else:
                    with self.assertRaises(m.Refused):m.deploy(b)
                self.assertFalse(any(a[0]=='switch' for a in b.actions))

    def test_manual_rollback_needs_no_live_app_environment(self):
        b=Backend();b.state={'hub':'absent','tiquet':'candidate'}
        result=m.rollback(b,['hub','tiquet'])
        self.assertEqual(result['status'],'PASS_ORIGINAL_IMAGES_AND_RUNTIME_RESTORED')
        self.assertFalse(result['application_data_restored'])


if __name__=='__main__':unittest.main()
