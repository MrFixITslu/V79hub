"""The UI probe must actually execute over Docker stdin before finalization."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('finalize',ROOT/'scripts/marketing-production-panel-finalize.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class FinalizeProbeTests(unittest.TestCase):
    def test_probe_forwards_stdin_and_rejects_missing_asset(self):
        tree=ast.parse(module.REMOTE_PROGRAM)
        call=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='served' for t in n.targets))
        command=ast.literal_eval(call.args[0]);self.assertEqual(command[:3],['docker','exec','-i']);self.assertEqual(command[-1],'-')
        source=ast.literal_eval(next(k.value for k in call.keywords if k.arg=='data'))
        for asset,ok in [('index-CHQuh9Xa.js',True),('different.js',False)]:
            program=("globalThis.fetch=async()=>({ok:true,text:async()=>'<script src=\"/assets/"+asset+"\"></script>'});\n").encode()+source
            result=subprocess.run(['node','--input-type=module','-'],input=program,capture_output=True)
            self.assertEqual(result.returncode==0,ok)
            self.assertEqual(b'PINNED_UI_ASSET_SERVED_PASS' in result.stdout,ok)
        # The deployment receipt must be written after the served-marker check.
        self.assertLess(module.REMOTE_PROGRAM.index("require(b'PINNED_UI_ASSET_SERVED_PASS'"),module.REMOTE_PROGRAM.index("h['write_json'](root/'deployed.json'"))


if __name__=='__main__':unittest.main()
