import ast
import copy
import importlib.util
from pathlib import Path
import subprocess
import unittest

script = Path(__file__).parents[1]/'scripts/prepare-website-lead-release.py'
spec = importlib.util.spec_from_file_location('prepare',script)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTest(unittest.TestCase):
    def inputs(self):
        row = {'Image':'sha256:prior','Config':{'Env':['EXISTING=preserved',
            'V79_HUB_EVENT_URL=http://v79-hub:3040/api/platform/events'],
            'Labels':{'com.docker.compose.service':'app'}}}
        model = {'services':{'app':{'image':'old-tag','environment':{'EXISTING':'preserved'},
            'volumes':['existing:/app/data'],'networks':['existing']},'database':{'image':'existing-db'}},
            'networks':{'existing':{'external':True}}}
        return row,model

    def test_exact_scoped_changes_and_rollback_do_not_mutate_inputs(self):
        for name in prepare.CANDIDATES:
            row,model=self.inputs(); before=copy.deepcopy(model)
            result=prepare.prepare_models(name,row,model,'existing-org','dedicated-key')
            self.assertEqual(model,before)
            self.assertEqual(result['rollback']['services']['app']['image'],'sha256:prior')
            self.assertEqual(result['rollback']['services']['app']['environment']['EXISTING'],'preserved')
            self.assertEqual(result['candidate']['services']['database'],model['services']['database'])
            self.assertEqual(result['candidate']['services']['app']['volumes'],['existing:/app/data'])
            expected=prepare.environment(row)
            actual=result['candidate']['services']['app']['environment']
            changed={k for k in expected.keys()|actual.keys() if expected.get(k)!=actual.get(k)}
            self.assertEqual(changed,set(result['approved_environment_keys']))
            if name=='V79website':self.assertEqual(actual['V79_HUB_EVENT_REPLAY_LEAD_IDS'],'2')

    def test_current_declaration_drift_and_external_endpoint_stop(self):
        row,model=self.inputs();model['services']['app']['environment']['EXISTING']='drift'
        with self.assertRaisesRegex(ValueError,'DECLARED_LIVE_ENVIRONMENT_DIFFERS'):
            prepare.prepare_models('v79-hub',row,model,'org','key')
        row,model=self.inputs();row['Config']['Env'][1]='V79_HUB_EVENT_URL=https://example.test/api/platform/events'
        with self.assertRaisesRegex(ValueError,'HUB_EVENT_ENDPOINT_NOT_INTERNAL_EXPECTED'):
            prepare.prepare_models('V79website',row,model,'org','key')

    def test_embedded_node_command_parses(self):
        tree=ast.parse(script.read_text())
        source=next(n.value.value for n in ast.walk(tree) if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='node' for t in n.targets))
        p=subprocess.run(['node','--check'],input=source,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)


if __name__=='__main__':unittest.main()
