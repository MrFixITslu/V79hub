"""Only the new adapter surface; exercise the unchanged real runtime validator."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).parents[1]/'scripts'


def load(name):
    location=ROOT if name=='bind-website-lead-release' else ROOT.parent/'tests/fixtures/release-engine-b233'
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),location/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


binding=load('bind-website-lead-release')


class BindingTests(unittest.TestCase):
    def fixture(self,which='candidate'):
        engine=load('paired-compose-transaction')
        old='sha256:'+'1'*64;new='sha256:'+'2'*64;manifest='sha256:'+'3'*64
        first='a'*64;second='b'*64
        before={'Id':first,'Image':old,'Config':{'Image':old,'Hostname':first[:12],
            'User':'appuser','Env':['EXISTING=retained'],'Labels':{
                'com.docker.compose.project':'example','com.docker.compose.service':'hub'}},
            'HostConfig':{'OomKillDisable':None},'Mounts':[],
            'NetworkSettings':{'Networks':{}},'State':{'Running':False}}
        approved={'V79_WEBSITE_EVENTS_ENABLED':'1','V79_WEBSITE_EVENT_SECRET':'synthetic-secret',
            'V79_WEBSITE_ORGANIZATION_REF':'synthetic-platform-org'}
        effective={'EXISTING':'retained',**approved} if which=='candidate' else {'EXISTING':'retained'}
        pin=new if which=='candidate' else old
        after=copy.deepcopy(before);after['Id']=second;after['Image']=pin
        after['Config'].update(Image=pin,Hostname=second[:12],Env=[k+'='+v for k,v in effective.items()])
        after['Config']['Labels'].update({'com.docker.compose.project.config_files':'/private/'+which+'.json',
            'com.docker.compose.image':manifest if which=='candidate' else old,
            'com.docker.compose.version':'5.6.0','com.docker.compose.project.environment_file':'/dev/null',
            'com.docker.compose.config-hash':'c'*64})
        entry={'release_name':'v79-hub','baseline':copy.deepcopy(before),'service':'hub','compose_version':'5.6.0',
            'model':{'services':{'hub':{'container_name':'v79-hub','environment':effective}}},
            'candidate_image':{'Id':new,'Config':{'Labels':{}}},'rollback_image':{'Id':old,'Config':{'Labels':{}}},
            'candidate_file':'/private/candidate.json','rollback_file':'/private/rollback.json',
            'approved_environment':approved,'image_manifests':{old:old,new:manifest}}
        binding.install_compat(engine)
        return engine,before,after,entry

    def check(self,fixture,which='candidate'):
        engine,before,after,entry=fixture
        return engine.runtime_matches(before,after,entry,which,selinux_enabled=False)

    def test_561_candidate_and_rollback_keep_the_same_exact_runtime_contract(self):
        for which in ('candidate','rollback'):
            fixture=self.fixture(which)
            fixture[3]['compose_version']='5.6.1'
            fixture[2]['Config']['Labels']['com.docker.compose.version']='5.6.1'
            self.assertTrue(self.check(fixture,which))
        fixture=self.fixture()
        fixture[3]['compose_version']='5.6.1'
        with self.assertRaisesRegex(ValueError,'COMPOSE_BOOKKEEPING_IDENTITY_CHANGED'):
            self.check(fixture)

    def test_only_reviewed_versions_pass_and_prepared_version_must_match(self):
        for version in ('5.6.0','5.6.1','v5.6.0','v5.6.1'):
            binding.verify_compose_version(version,version)
        for version in ('5.6.2','5.6.10','5.7.0','5.6.1-custom','vv5.6.1',''):
            with self.assertRaisesRegex(ValueError,'UNREVIEWED_COMPOSE_VERSION'):
                binding.verify_compose_version(version)
        with self.assertRaisesRegex(ValueError,'PREPARED_COMPOSE_VERSION_CHANGED'):
            binding.verify_compose_version('5.6.1','5.6.0')

    def test_only_exact_approved_candidate_environment_and_image_mapping_pass(self):
        fixture=self.fixture();before=copy.deepcopy(fixture[1]);after=copy.deepcopy(fixture[2])
        self.assertTrue(self.check(fixture))
        self.assertEqual(fixture[1],before);self.assertEqual(fixture[2],after)

    def test_existing_secret_and_extra_environment_changes_fail(self):
        for key in ('EXISTING','UNAPPROVED'):
            fixture=self.fixture();fixture[2]['Config']['Env'].append(key+'=changed')
            with self.assertRaises(ValueError):self.check(fixture)

    def test_model_environment_and_allowance_scope_are_not_relaxed(self):
        fixture=self.fixture();fixture[3]['approved_environment']['EXTRA']='bad'
        with self.assertRaisesRegex(ValueError,'ALLOWANCE_SCOPE_CHANGED'):self.check(fixture)
        fixture=self.fixture();fixture[3]['model']['services']['hub']['environment']['EXISTING']='changed'
        with self.assertRaisesRegex(ValueError,'SEALED_ENVIRONMENT_CHANGED'):self.check(fixture)

    def test_foreign_actual_image_or_image_label_is_rejected(self):
        for kind in ('actual','label'):
            fixture=self.fixture()
            if kind=='actual':fixture[2]['Image']='sha256:'+'f'*64
            else:fixture[2]['Config']['Labels']['com.docker.compose.image']='sha256:'+'f'*64
            with self.assertRaises(ValueError):self.check(fixture)

    def test_host_process_and_application_label_guards_still_apply(self):
        for kind in ('privilege','user','label'):
            fixture=self.fixture()
            if kind=='privilege':fixture[2]['HostConfig']['Privileged']=True
            elif kind=='user':fixture[2]['Config']['User']='root'
            else:fixture[2]['Config']['Labels']['application.guard']='changed'
            with self.assertRaises(ValueError):self.check(fixture)

    def test_rollback_requires_original_environment_without_new_credentials(self):
        fixture=self.fixture('rollback');self.assertTrue(self.check(fixture,'rollback'))
        fixture[2]['Config']['Env'].append('V79_WEBSITE_EVENTS_ENABLED=1')
        with self.assertRaisesRegex(ValueError,'EFFECTIVE_ENVIRONMENT_CHANGED'):self.check(fixture,'rollback')

    def test_exact_compose_replacement_name_maps_only_with_previous_id_context(self):
        fixture=self.fixture();fixture[3]['_replaced_id']=fixture[1]['Id']
        fixture[2]['Config']['Labels']['com.docker.compose.replace']='v79-hub'
        self.assertTrue(self.check(fixture))
        fixture[2]['Config']['Labels']['com.docker.compose.replace']='foreign'
        with self.assertRaisesRegex(ValueError,'REPLACEMENT_NAME_CHANGED'):self.check(fixture)

    def test_all_four_protected_cores_require_running_and_healthy(self):
        from types import SimpleNamespace
        names=('v79-business-agent','v79-hub-postgres','tiquet-postgres','v79-tiquet-manager')
        rows={name:{'State':{'Running':True,'Health':{'Status':'healthy'}}} for name in names}
        backend=SimpleNamespace(plan={'protected':{name:{'Id':name} for name in names}},
            protected=lambda:None,inspect=lambda name:rows[name])
        binding.protect_core_health(backend);backend.protected()
        rows['v79-tiquet-manager']['State']['Health']['Status']='unhealthy'
        with self.assertRaisesRegex(ValueError,'PROTECTED_CORE_NOT_HEALTHY'):backend.protected()


if __name__=='__main__':unittest.main()
