import copy,hashlib,importlib.util,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('cutover',Path(__file__).parents[1]/'scripts/workforce-disabled-cutover.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class CutoverTests(unittest.TestCase):
 def case(self,drift=False,wrong_image=False):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);files=[];hashes={}
   for i in range(9):
    file=root/f'{i}.json';file.write_text('{}');files.append(str(file));hashes[str(file)]=hashlib.sha256(b'{}').hexdigest()
   report=str(root/'.local/share/v79-workforce-operations/reports')
   mounts=[{'type':'bind','source':str(root/'data'),'target':'/app/data','read_only':False}]
   svc={'image':p.OLD,'environment':{'A':'1'},'volumes':mounts}
   baseline={'services':{'v79-hub':svc,'other':{'image':'unchanged'}}}
   overlay={'services':{'v79-hub':{'image':p.NEW if not wrong_image else 'wrong','environment':{'V79_WORKFORCE_REPORTS_ENABLED':'1'},'volumes':[{'type':'bind','source':report,'target':'/run/v79-workforce-reports','read_only':True}]}}}
   (root/'candidate.json').write_text(json.dumps(overlay));(root/'rollback.json').write_text(json.dumps({'services':{'v79-hub':{'image':p.OLD}}}))
   images={'v79-hub':p.OLD,'v79-business-agent':'agent','v79-tiquet-manager':'tiquet'}
   plan={'candidateImage':p.NEW,'currentImages':images,'orderedComposeFiles':files,'composeSha256':hashes,'workingDirectory':directory,'project':'test','service':'v79-hub','candidateOverlay':str(root/'candidate.json'),'rollbackOverlay':str(root/'rollback.json')}
   (root/'release-plan.json').write_text(json.dumps(plan))
   live=[]
   for name,image in images.items():live.append({'Id':name+'-id','Name':'/'+name,'Image':image,'State':{'Health':{'Status':'healthy'}},'Config':{'Env':['A=1'],'Labels':{'com.docker.compose.project.config_files':','.join(files)}},'Mounts':[]})
   hub=live[0];hub['Mounts']=[{'Type':'bind','Source':str(root/'data'),'Destination':'/app/data','RW':True}]
   if drift:hub['Config']['Env']=['A=changed']
   mutated=False;calls=[]
   def run(args,cwd=None,timeout=None):
    nonlocal mutated
    calls.append(args)
    if args[:2]==['docker','inspect']:
     rows=copy.deepcopy(live)
     if mutated:
      rows[0]['Image']=p.NEW;rows[0]['Config']['Env']+=['V79_WORKFORCE_REPORTS_ENABLED=0'];rows[0]['Mounts']+=[{'Type':'bind','Source':report,'Destination':'/run/v79-workforce-reports','RW':False}]
     return json.dumps([r for r in rows if r['Name'].lstrip('/') in [x.lstrip('/') for x in args[2:]]])
    if args[:3]==['docker','image','inspect']:return json.dumps([{'Id':args[3],'Config':{'Env':[]}}])
    if 'config' in args:
     result=copy.deepcopy(baseline);paths=[args[i+1] for i,x in enumerate(args) if x=='-f']
     if len(paths)==10:
      ov=json.loads(Path(paths[-1]).read_text())['services']['v79-hub'];result['services']['v79-hub']['image']=ov['image']
      if 'environment' in ov:result['services']['v79-hub']['environment'].update(ov['environment']);result['services']['v79-hub']['volumes']+=ov['volumes']
     return json.dumps(result)
    if 'up' in args:mutated=True;return ''
    raise AssertionError(args)
   with patch.object(p,'PLAN',root/'release-plan.json'),patch.object(p.socket,'gethostname',return_value='v79sl'),patch.object(p.Path,'home',return_value=root),patch.object(p,'run',side_effect=run),patch('sys.stdout',io.StringIO()):
    if drift or wrong_image:
     with self.assertRaises(RuntimeError):p.main()
     self.assertFalse(mutated)
    else:
     p.main();self.assertTrue(mutated);self.assertTrue((root/'disabled-cutover-success.json').exists())
     self.assertEqual(sum('up' in call for call in calls),1)
     up=next(call for call in calls if 'up' in call);self.assertEqual(up[-1],'v79-hub');self.assertIn('--no-deps',up)
 def test_one_hub_cutover_disabled(self):self.case()
 def test_environment_drift_blocks_mutation(self):self.case(drift=True)
 def test_wrong_overlay_image_blocks_mutation(self):self.case(wrong_image=True)
if __name__=='__main__':unittest.main()
