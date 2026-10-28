import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

TESTS=Path(__file__).parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


finish=load('finish',TESTS.parent/'scripts/finish-website-lead-profiles.py')
fixture_module=load('binding_fixture',TESTS/'test_website_lead_binding.py')


def stopped_profiles(backend):
    verified=0
    try:
        for name,entry in backend.plan['apps'].items():
            for which in ('candidate','rollback'):
                backend.calls.append((name,which));verified+=1
    finally:backend.cleaned=True
    return {'profiles_verified':verified}


class WebsiteFinishTests(unittest.TestCase):
    def cache_fixture(self,which):
        engine,before,after,entry=fixture_module.BindingTests().fixture(which)
        entry['candidate_sha256']='c'*64;entry['rollback_sha256']='d'*64
        after['State']['StartedAt']='0001-01-01T00:00:00Z'
        # Reproduce the old helper's stored normalized capture.
        before['Config']['Env']=after['Config']['Env'].copy()
        after['Config']['Labels']['com.docker.compose.image']=entry[which+'_image']['Id']
        record={'app':'v79-hub','which':which,'engine_message':'RUNTIME_MATCHED',
            'before':before,'after':after,'entry':entry}
        plan={'apps':{'v79-hub':entry},'selinux_enabled':False}
        return engine,record,plan

    def test_both_passed_hub_receipts_revalidate_without_any_backend_or_docker(self):
        for which in ('candidate','rollback'):
            engine,record,plan=self.cache_fixture(which)
            finish.verify_cached_hub(engine,record,plan,which,fixture_module.binding.require)

    def test_changed_cached_receipt_is_not_reused(self):
        engine,record,plan=self.cache_fixture('candidate')
        record['after']['State']['Running']=True
        with self.assertRaisesRegex(ValueError,'PASSED_HUB_RECEIPT_CONFIG_CHANGED'):
            finish.verify_cached_hub(engine,record,plan,'candidate',fixture_module.binding.require)

    def test_only_website_candidate_and_rollback_are_created(self):
        backend=SimpleNamespace(plan={'apps':{'v79-hub':{},'V79website':{}}},calls=[],cleaned=False)
        function,_=finish.selected_profile_function(SimpleNamespace(stopped_profiles=stopped_profiles))
        selection=frozenset((('V79website','candidate'),('V79website','rollback')))
        self.assertEqual(function(backend,selection)['profiles_verified'],2)
        self.assertEqual(backend.calls,[('V79website','candidate'),('V79website','rollback')])
        self.assertTrue(backend.cleaned)


if __name__=='__main__':unittest.main()
