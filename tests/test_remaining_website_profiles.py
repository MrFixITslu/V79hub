import ast
import copy
import importlib.util
import inspect
from pathlib import Path
import textwrap
from types import SimpleNamespace
import unittest

source=Path(__file__).parents[1]/'scripts/resume-website-lead-profiles.py'
spec=importlib.util.spec_from_file_location('remaining_profiles',source)
resume=importlib.util.module_from_spec(spec);spec.loader.exec_module(resume)


def stopped_profiles(backend):
    verified=0
    try:
        for name,entry in backend.plan['apps'].items():
            for which in ('candidate','rollback'):
                backend.calls.append((name,which))
                if backend.fail==(name,which):raise ValueError('simulated validation failure')
                verified+=1
    finally:
        backend.cleaned=True
    return {'profiles_verified':verified}


class SelectionTests(unittest.TestCase):
    def setup_engine(self,fail=None):
        engine=SimpleNamespace(stopped_profiles=stopped_profiles)
        backend=SimpleNamespace(plan={'apps':{'v79-hub':{},'V79website':{}}},calls=[],fail=fail,cleaned=False)
        return engine,backend

    def test_only_three_unverified_profiles_run(self):
        engine,backend=self.setup_engine()
        function,_=resume.selected_profile_function(engine)
        selected=resume.ALL-{('v79-hub','candidate')}
        result=function(backend,selected)
        self.assertEqual(result['profiles_verified'],3)
        self.assertEqual(backend.calls,[('v79-hub','rollback'),('V79website','candidate'),('V79website','rollback')])
        self.assertTrue(backend.cleaned)

    def test_validation_failure_still_runs_original_finally_cleanup(self):
        engine,backend=self.setup_engine(('v79-hub','rollback'))
        function,_=resume.selected_profile_function(engine)
        with self.assertRaises(ValueError):function(backend,resume.ALL-{('v79-hub','candidate')})
        self.assertEqual(backend.calls,[('v79-hub','rollback')]);self.assertTrue(backend.cleaned)

    def test_source_difference_is_only_selection_argument_name_and_guard(self):
        fake,_=self.setup_engine()
        fixture=Path(__file__).parent/'fixtures/release-engine-b233/paired-compose-transaction.py'
        spec=importlib.util.spec_from_file_location('real_engine',fixture)
        real=importlib.util.module_from_spec(spec);spec.loader.exec_module(real)
        for engine in (fake,real):
            _,tree=resume.selected_profile_function(engine)
            restored=copy.deepcopy(tree);fn=restored.body[0];fn.name='stopped_profiles';fn.args.args.pop()
            loops=[n for n in ast.walk(fn) if isinstance(n,ast.For) and isinstance(n.target,ast.Name)
                and n.target.id=='which']
            self.assertEqual(len(loops),1);guard=loops[0].body.pop(0)
            self.assertIsInstance(guard,ast.If);self.assertIsInstance(guard.body[0],ast.Continue)
            original=ast.parse(textwrap.dedent(inspect.getsource(engine.stopped_profiles)))
            self.assertEqual(ast.dump(restored),ast.dump(original))


if __name__=='__main__':unittest.main()
