import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('prepare',Path(__file__).parents[1]/'scripts/workforce-release-prepare.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class PrepareTests(unittest.TestCase):
 def run_case(self, drift=False, bad_mount=False, other_change=False):
  with tempfile.TemporaryDirectory() as root:
   home=Path(root); reports=home/'.local/share/v79-workforce-operations/reports';reports.mkdir(parents=True,mode=0o700)
   files=[]
   for i in range(9):
    f=home/f'{i}.json';f.write_text('{}');files.append(str(f))
   cfg={'Cmd':['node','server.ts'],'Entrypoint':None,'Env':['A=1']}
   svc={'image':p.EXPECTED['v79-hub'],'command':None,'entrypoint':None,'environment':{'A':'1'},'volumes':[{'type':'bind','source':str(home/'data'),'target':'/app/data','read_only':False}]}
   baseline={'services':{'v79-hub':svc,'other':{'image':'unchanged'}}}
   live=[]
   for name,image in p.EXPECTED.items():
    live.append({'Name':'/'+name,'Image':image,'State':{'Health':{'Status':'healthy'}},'Config':copy.deepcopy(cfg),'Mounts':[]})
   hub=live[0];hub['Config']['Labels']={'com.docker.compose.project.config_files':','.join(files),'com.docker.compose.project.working_dir':root,'com.docker.compose.project':'synthetic','com.docker.compose.service':'v79-hub'}
   hub['Mounts']=[{'Destination':'/app/data','Type':'bind','Source':str(home/'data'),'RW':not bad_mount}]
   if drift:hub['Config']['Env']=['A=changed']
   calls=[]
   def command(args,cwd=None):
    calls.append(args)
    if args[:2]==['docker','inspect']:return json.dumps(live)
    if args[:3]==['docker','image','inspect']:
     return json.dumps([{'Id':args[3],'Config':{'Cmd':['node','server.ts'],'Entrypoint':None,'Env':[]}}])
    self.assertIn('config',args)
    result=copy.deepcopy(baseline)
    paths=[args[i+1] for i,x in enumerate(args) if x=='-f']
    if len(paths)==10:
     overlay=json.loads(Path(paths[-1]).read_text())['services']['v79-hub']
     result['services']['v79-hub']['image']=overlay['image']
     if 'environment' in overlay:
      result['services']['v79-hub']['environment'].update(overlay['environment'])
      result['services']['v79-hub']['volumes']+=overlay['volumes']
      if other_change:result['services']['other']['image']='unexpected'
    return json.dumps(result)
   out=io.StringIO()
   with patch.object(p.socket,'gethostname',return_value='v79sl'),patch.object(p.Path,'home',return_value=home),patch.object(p,'command',side_effect=command),patch('sys.stdout',out):
    if drift or bad_mount or other_change:
     with self.assertRaises(RuntimeError):p.main()
    else:
     p.main();self.assertIn('ROLLBACK_CONFIG_PARITY=PASS',out.getvalue());self.assertIn('PRODUCTION_DEPLOYED=NO',out.getvalue())
   self.assertFalse(any(any(x in ['up','run','start','stop','restart','rm'] for x in args) for args in calls))
 def test_prepare(self):self.run_case()
 def test_environment_drift(self):self.run_case(drift=True)
 def test_mount_drift(self):self.run_case(bad_mount=True)
 def test_other_service_change(self):self.run_case(other_change=True)

if __name__=='__main__':unittest.main()
