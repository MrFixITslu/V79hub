import copy,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('ui_update',Path(__file__).resolve().parents[1]/'scripts/workforce-owner-workspace-update.py')
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)
class RolloutGuards(unittest.TestCase):
 def setUp(self):
  self.config={'services':{'hub':{'image':'sha256:before','environment':{'FLAG':'1'},'volumes':[{'type':'bind','source':'/private','target':'/run/reports','read_only':True}]},'tiquet':{'image':'sha256:other'}},'networks':{'private':{'internal':True}}}
 def test_image_only_change_passes_without_mutating_original(self):
  target=copy.deepcopy(self.config);target['services']['hub']['image']='sha256:after'
  update.image_only(self.config,target,'hub','sha256:after')
  self.assertEqual(target['services']['hub']['image'],'sha256:after');self.assertEqual(self.config['services']['hub']['image'],'sha256:before')
 def test_environment_mount_other_service_and_network_changes_reject(self):
  for mutate in [lambda c:c['services']['hub']['environment'].update(FLAG='0'),lambda c:c['services']['hub']['volumes'][0].update(read_only=False),lambda c:c['services']['tiquet'].update(image='sha256:new'),lambda c:c['networks']['private'].update(internal=False)]:
   with self.subTest(mutate=mutate):
    target=copy.deepcopy(self.config);target['services']['hub']['image']='sha256:after';mutate(target)
    with self.assertRaises(RuntimeError):update.image_only(self.config,target,'hub','sha256:after')
 def test_runtime_preserves_settings_even_if_env_or_mount_order_changes(self):
  before={'Config':{'Env':['FLAG=1','OTHER=2'],'Cmd':['node','server.ts'],'User':'0'},'HostConfig':{'PortBindings':{'3040/tcp':[{'HostIp':'127.0.0.1','HostPort':'3040'}]},'ReadonlyRootfs':True},'Mounts':[{'Type':'bind','Source':'/private','Destination':'/reports','RW':False}]}
  after=copy.deepcopy(before);after['Config']['Env'].reverse();update.runtime_same(before,after)
  for mutate in [lambda r:r['Config'].update(User='1000'),lambda r:r['HostConfig'].update(ReadonlyRootfs=False),lambda r:r['Mounts'][0].update(RW=True),lambda r:r['Config'].update(Env=['FLAG=0','OTHER=2'])]:
   changed=copy.deepcopy(after);mutate(changed)
   with self.assertRaises(RuntimeError):update.runtime_same(before,changed)
if __name__=='__main__':unittest.main()
