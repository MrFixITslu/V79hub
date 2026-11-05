import copy,importlib.util,pathlib,unittest
path=pathlib.Path(__file__).resolve().parents[1]/'scripts/workforce-specialist-guarded-release.py'
spec=importlib.util.spec_from_file_location('release_candidate',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class GuardedRelease(unittest.TestCase):
 def pair(self):
  spec={'name':'v79-hub','old':'old-pinned-image','image':'new-pinned-image','tag':'new-pinned-tag','mounts':1,'flags':{'V79_WORKFORCE_SPECIALIST_REVIEWS_ENABLED':'1'}}
  old={'Image':spec['old'],'State':{'Status':'running','Health':{'Status':'healthy'}},
   'Config':{'Image':'old-tag','Env':['V79_REQUIRE_ADMIN_MFA=1','V79_WORKFORCE_ACTIONS_ENABLED=1','UNCHANGED_SYNTHETIC_VALUE=retained'],
    'Labels':{'org.opencontainers.image.revision':'old','com.docker.compose.project':'old-compose','brand':'V79'},'User':'1000:1000','Cmd':['node','server.ts'],'Entrypoint':['docker-entrypoint.sh'],'WorkingDir':'/app','Healthcheck':{'Test':['CMD','health']}},
   'HostConfig':{'RestartPolicy':{'Name':'unless-stopped'},'Privileged':False,'ReadonlyRootfs':True,'CapDrop':['ALL'],'PortBindings':{'3040/tcp':[{'HostIp':'127.0.0.1','HostPort':'3040'}]}},
   'Mounts':[{'Type':'bind','Source':'/synthetic/persistent','Destination':'/app/data','RW':True}],
   'NetworkSettings':{'Networks':{'proxy_network':{'Aliases':['v79-hub']}}}}
  new=m.expected_runtime(old,spec);new['Image']=spec['image'];new['State']={'Status':'created'}
  return old,new,spec
 def test_only_exact_feature_flag_source_label_and_image_may_change(self):
  old,new,spec=self.pair();before=copy.deepcopy(old);m.assert_parity(old,new,spec);self.assertEqual(old,before)
  self.assertIn('V79_REQUIRE_ADMIN_MFA=1',new['Config']['Env']);self.assertIn('UNCHANGED_SYNTHETIC_VALUE=retained',new['Config']['Env'])
 def test_rejects_unapproved_environment_authority(self):
  old,new,spec=self.pair();spec['flags']['V79_REQUIRE_ADMIN_MFA']='0'
  with self.assertRaises(RuntimeError):m.expected_runtime(old,spec)
 def test_all_process_and_security_drift_rejected(self):
  cases=[lambda n:n['Config']['Env'].append('UNAPPROVED_SETTING=1'),lambda n:n['Config'].update(User='root'),lambda n:n['Config'].update(Cmd=['shell']),lambda n:n['Config'].update(Entrypoint=['shell']),lambda n:n['Config']['Labels'].update(brand='foreign'),lambda n:n['HostConfig'].update(Privileged=True),lambda n:n['HostConfig'].update(ReadonlyRootfs=False),lambda n:n['HostConfig'].update(CapDrop=[]),lambda n:n['HostConfig']['PortBindings']['3040/tcp'][0].update(HostIp='0.0.0.0'),lambda n:n['HostConfig']['RestartPolicy'].update(Name='no')]
  for change in cases:
   with self.subTest(change=change):
    old,new,spec=self.pair();change(new)
    with self.assertRaises(RuntimeError):m.assert_parity(old,new,spec)
 def test_mount_network_alias_image_and_running_stage_drift_rejected(self):
  for change in [lambda n:n['Mounts'][0].update(Source='/wrong/data'),lambda n:n['Mounts'][0].update(RW=False),lambda n:n['NetworkSettings'].update(Networks={}),lambda n:n['NetworkSettings']['Networks']['proxy_network'].update(Aliases=['wrong-name']),lambda n:n.update(Image='wrong-image'),lambda n:n['State'].update(Status='running')]:
   with self.subTest(change=change):
    old,new,spec=self.pair();change(new)
    with self.assertRaises(RuntimeError):m.assert_parity(old,new,spec)
 def test_docker_oom_default_normalization_preserves_oom_protection(self):
  old,new,spec=self.pair();old['HostConfig']['OomKillDisable']=None;new['HostConfig']['OomKillDisable']=False
  m.assert_parity(old,new,spec)
  new['HostConfig']['OomKillDisable']=True
  with self.assertRaises(RuntimeError):m.assert_parity(old,new,spec)
 def test_unhealthy_or_unpinned_baseline_rejected(self):
  for change in [lambda o:o.update(Image='drifted'),lambda o:o['State'].update(Status='exited'),lambda o:o['State']['Health'].update(Status='unhealthy')]:
   old,new,spec=self.pair();change(old)
   with self.assertRaises(RuntimeError):m.assert_parity(old,new,spec)
if __name__=='__main__':unittest.main()
