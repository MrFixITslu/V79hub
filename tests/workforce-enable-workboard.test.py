import copy,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('workboard',Path(__file__).parents[1]/'scripts/workforce-enable-workboard.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class WorkboardActivationTests(unittest.TestCase):
 def setUp(self):
  self.before={'services':{'hub':{'image':'pinned','environment':{'V79_WORKFORCE_REPORTS_ENABLED':'1'},'volumes':[{'target':'/app/data'}]},'other':{'image':'keep'}}}
  self.after=copy.deepcopy(self.before)
  self.after['services']['hub']['environment']['V79_COO_WORKBOARD_ENABLED']='1'
  self.after['services']['hub']['volumes'].append({'type':'bind','source':'/private/token','target':p.TARGET,'read_only':True,'bind':{'create_host_path':False}})
 def verify(self):p.verify_diff(self.before,self.after,'hub','/private/token')
 def test_only_flag_and_readonly_token(self):self.verify()
 def test_writable_token_rejected(self):
  self.after['services']['hub']['volumes'][-1]['read_only']=False
  with self.assertRaises(RuntimeError):self.verify()
 def test_token_substitution_rejected(self):
  self.after['services']['hub']['volumes'][-1]['source']='/another/token'
  with self.assertRaises(RuntimeError):self.verify()
 def test_reports_disable_rejected(self):
  self.after['services']['hub']['environment']['V79_WORKFORCE_REPORTS_ENABLED']='0'
  with self.assertRaises(RuntimeError):self.verify()
 def test_other_service_change_rejected(self):
  self.after['services']['other']['image']='changed'
  with self.assertRaises(RuntimeError):self.verify()
 def test_old_explicit_disabled_flag_supported(self):
  self.before['services']['hub']['environment']['V79_COO_WORKBOARD_ENABLED']='0';self.verify()
if __name__=='__main__':unittest.main()
