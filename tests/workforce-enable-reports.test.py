import copy,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('enable',Path(__file__).parents[1]/'scripts/workforce-enable-reports.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class ActivationTests(unittest.TestCase):
 def setUp(self):
  self.before={'services':{'v79-hub':{'image':'exact-image','environment':{'V79_WORKFORCE_REPORTS_ENABLED':'0','MFA':'1'},'volumes':[{'target':'/app/data'}]},'other':{'image':'untouched'}}}
  self.after=copy.deepcopy(self.before);self.after['services']['v79-hub']['environment']['V79_WORKFORCE_REPORTS_ENABLED']='1'
 def test_only_report_flag(self):p.verify_flag_only(self.before,self.after,'v79-hub');self.assertEqual(self.after['services']['v79-hub']['environment']['V79_WORKFORCE_REPORTS_ENABLED'],'1')
 def test_image_change_rejected(self):
  self.after['services']['v79-hub']['image']='another'
  with self.assertRaises(RuntimeError):p.verify_flag_only(self.before,self.after,'v79-hub')
 def test_mfa_change_rejected(self):
  self.after['services']['v79-hub']['environment']['MFA']='0'
  with self.assertRaises(RuntimeError):p.verify_flag_only(self.before,self.after,'v79-hub')
 def test_mount_change_rejected(self):
  self.after['services']['v79-hub']['volumes']=[]
  with self.assertRaises(RuntimeError):p.verify_flag_only(self.before,self.after,'v79-hub')
 def test_other_service_change_rejected(self):
  self.after['services']['other']['image']='another'
  with self.assertRaises(RuntimeError):p.verify_flag_only(self.before,self.after,'v79-hub')
if __name__=='__main__':unittest.main()
