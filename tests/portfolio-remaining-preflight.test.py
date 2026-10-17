import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('remaining',root/'scripts/portfolio-remaining-preflight.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
spec=importlib.util.spec_from_file_location('rollout',root/'scripts/portfolio-pinned-rollout.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def migration(**change):
    name,digest=next(iter(p.POS_MIGRATIONS.items()))
    value={'name':name,'checksum':digest,'finished':True,'rolled_back':False};value.update(change);return value

class MigrationTests(unittest.TestCase):
    def test_unexpected_uppercase_exception_is_not_forwarded(self):
        self.assertEqual(p.safe_code(RuntimeError('PRIVATE_CREDENTIAL')), 'PREFLIGHT_ERROR_REDACTED')

    def test_exact_history_passes(self):
        self.assertEqual(p.migration_summary([migration()])['status'],'PASS')

    def test_pending_unknown_changed_or_unfinished_require_review(self):
        for rows in ([],[migration(name='PRIVATE_CUSTOMER')],[migration(checksum='0'*64)],[migration(finished=False)]):
            result=p.migration_summary(rows)
            self.assertEqual(result['status'],'REVIEW_REQUIRED')
            self.assertNotIn('PRIVATE',json.dumps(result))

    def test_rolled_back_attempts_do_not_hide_completed_attempt_or_pending(self):
        self.assertEqual(p.migration_summary([migration(),migration(rolled_back=True)])['status'],'PASS')
        self.assertEqual(p.migration_summary([migration(rolled_back=True),migration()])['status'],'PASS')
        self.assertEqual(p.migration_summary([migration(rolled_back=True)])['status'],'REVIEW_REQUIRED')

    def test_duplicate_active_history_or_bad_shape_is_rejected(self):
        for value in ([migration(),migration()],[migration(checksum='PRIVATE')],{},[migration(finished='yes')]):
            with self.assertRaises(p.Stop): p.migration_summary(value)

    def test_changed_helper_is_never_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp);(stage/'rollout.py').write_text("raise RuntimeError('SHOULD_NOT_EXECUTE')")
            with patch.object(p,'ACCEPTED_RUN',stage):
                with self.assertRaisesRegex(p.Stop,'ROLLOUT_HELPER_INTEGRITY_FAILURE'): p.load_helper()

class LifecycleTests(unittest.TestCase):
    def exercise(self,failed=None):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp);plan=stage/'plan';plan.mkdir(mode=0o700)
            receipt={'health':'PASS_BOTH','images':{'v79-hub':'sha256:'+'1'*64,'v79-tiquet-manager':'sha256:'+'2'*64}}
            (stage/'release-receipt.json').write_text(json.dumps(receipt))
            rows={n:{'Id':n,'Image':pin['image_id'],'State':{'Running':True,'Health':{'Status':'healthy'}},
                     'Config':{'Env':['PASSWORD=PRIVATE_CREDENTIAL']},'HostConfig':{},'Mounts':[],
                     'NetworkSettings':{'Networks':{}}} for n,pin in p.PINS.items()}
            rows['v79-pos-worker']['State'].pop('Health')
            for n,image in receipt['images'].items(): rows[n]={'Image':image,'State':{'Health':{'Status':'healthy'}}}
            rows['v79-pos-db']={'Image':p.DB_IMAGE,'State':{'Health':{'Status':'healthy'}}}
            commands=[];written=[]
            def inspect(name): return copy.deepcopy(rows[name])
            def model(row,pin):
                if failed==pin['container']:raise r.Stop('RENDERED_ENV_DIFFERS_FROM_RUNNING')
                return {'services':{pin['compose_service']:{'environment':r.compose_literal(r.envmap(row['Config']['Env']))}}}
            def call(args):
                commands.append(args)
                if args[:2]==['docker','compose']:
                    return Path(args[args.index('-f')+1]).read_bytes()
                self.assertEqual(args[:3],['docker','exec','-e'])
                self.assertIn('default_transaction_read_only=on',args[3])
                self.assertTrue(args[-1].startswith('SELECT '))
                if 'to_regclass' in args[-1]:return b't\n'
                return json.dumps([migration()]).encode()
            helper=SimpleNamespace(inspect=inspect,private_json=r.private_json,original_model=model,
                 call=call,compose=r.compose,compose_runtime=r.compose_runtime,envmap=r.envmap,
                 validate_storage_and_networks=lambda *args:None,fingerprint=r.fingerprint)
            output=io.StringIO()
            with patch.object(p,'ACCEPTED_RUN',stage),redirect_stdout(output):
                code=p.prepare(helper,plan)
            summary=json.loads((plan/'plan-summary.json').read_text())
            self.assertNotIn('PRIVATE',output.getvalue()+json.dumps(summary))
            self.assertEqual((plan/'runtime-before.json').stat().st_mode&0o777,0o600)
            self.assertTrue(all(args[:2] in (['docker','exec'],['docker','compose']) for args in commands))
            return code,output.getvalue(),summary

    def test_success_prepares_only_private_plans_and_readonly_queries(self):
        code,output,summary=self.exercise()
        self.assertEqual(code,0)
        self.assertIn('PASS_PLAN_ONLY',output)
        self.assertEqual(summary['results']['v79-pos-worker']['worker_readiness'],'NOT_PROVEN')
        self.assertIn('REMAINING_APPS_DEPLOYED=NO',output)

    def test_one_parity_failure_does_not_hide_other_app_results(self):
        code,output,summary=self.exercise('v79-pos')
        self.assertEqual(code,1)
        self.assertEqual(summary['results']['v79-pos']['runtime_parity'],'FAIL')
        self.assertEqual(summary['results']['gaming-studio-j']['runtime_parity'],'PASS')
        self.assertIn('REVIEW_REQUIRED',output)

if __name__=='__main__':unittest.main()
