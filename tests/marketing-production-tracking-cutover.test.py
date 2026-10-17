"""Image-only parity, bound recovery, and no automatic retry after a switch."""
import copy
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'scripts/marketing-production-tracking-cutover.py'
def load():
 spec=importlib.util.spec_from_file_location('tracking_cutover',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def fingerprint(value):return json.dumps(value,sort_keys=True)

class CutoverTests(unittest.TestCase):
 def test_only_two_images_can_change_in_the_resolved_compose_configuration(self):
  m=load();old={'services':{'v79-hub':{'image':'old','environment':{'key':'synthetic','publication':'1'},'volumes':['original']},'database':{'image':'untouched'}}}
  new=copy.deepcopy(old);new['services']['v79-hub']['image']='candidate';m.parity('v79-hub',old,new,'candidate')
  for key,value in [('environment',{'key':'changed','publication':'1'}),('volumes',['changed'])]:
   bad=copy.deepcopy(new);bad['services']['v79-hub'][key]=value
   with self.assertRaises(RuntimeError):m.parity('v79-hub',old,bad,'candidate')
  new['services']['database']['image']='changed'
  with self.assertRaises(RuntimeError):m.parity('v79-hub',old,new,'candidate')

 def test_runtime_normalization_accepts_only_generated_identity_bind_order_and_image_bookkeeping(self):
  m=load();m.h={'fingerprint':fingerprint,'mounts':lambda v:sorted(v['Mounts'],key=lambda x:x['Destination']),'healthy':lambda v:True}
  image={'image':'sha256:new','commit':'new-commit'};m.recovery={'EXPECTED':{'V79hub':image}}
  labels={'com.docker.compose.project':'v79-hub','com.docker.compose.service':'v79-hub','com.docker.compose.project.working_dir':'/opt/v79/hub','com.docker.compose.project.config_files':'original','com.docker.compose.config-hash':'old','com.docker.compose.image':'old','org.opencontainers.image.revision':'old','unchanged':'value'}
  old={'Id':'a'*64,'Image':'sha256:old','Config':{'Image':'sha256:old','Hostname':'a'*12,'Env':['B=2','A=1'],'User':'','Cmd':['node','server'],'Labels':labels},'HostConfig':{'Binds':['b:/b:ro','a:/a:rw'],'Memory':768},'Mounts':[{'Destination':'/b','RW':False},{'Destination':'/a','RW':True}],'NetworkSettings':{'Networks':{'original':{}}}}
  new=copy.deepcopy(old);new.update(Id='b'*64,Image=image['image']);new['Config'].update(Image=image['image'],Hostname='b'*12,Env=['A=1','B=2'])
  new['HostConfig']['Binds'].reverse();new['Mounts'].reverse();new['Config']['Labels'].update({'com.docker.compose.project.config_files':'original,overlay','com.docker.compose.config-hash':'new','com.docker.compose.image':'new','org.opencontainers.image.revision':image['commit']})
  check=lambda v:m.runtime_parity('v79-hub',old,v,None,['original'],Path('overlay'))
  check(new)
  mutations=[lambda v:v['Config']['Env'].append('UNAPPROVED=1'),lambda v:v['Config'].update(User='root'),lambda v:v['Config'].update(Cmd=['different']),lambda v:v['Config'].update(Hostname='explicit'),lambda v:v['HostConfig'].update(Memory=999),lambda v:v['HostConfig']['Binds'].append('other:/other'),lambda v:v['Mounts'][0].update(RW=False),lambda v:v['NetworkSettings']['Networks'].update(other={}),lambda v:v['Config']['Labels'].update(unchanged='changed')]
  for mutation in mutations:
   bad=copy.deepcopy(new);mutation(bad)
   with self.assertRaises(RuntimeError):check(bad)

 def evidence(self,m):
  now=datetime.datetime.now(datetime.timezone.utc).isoformat();backups={n:'cipher-'+n for n in ['hub-pg.dump.gpg','hub-data.tar.gpg','marketing-online.sqlite.gpg','marketing-files.tar.gpg','runtime-config.json.gpg']}
  receipt={'capturedAt':now,'copiedOnlineRestoreVerified':True,'copiedCandidateMigrationAndRollbackVerified':True,'signedCampaignsAndSchedulesPreserved':True,'scratchCleanupVerified':True,'liveDeploymentPerformed':False,'publicationEnabled':True,'candidates':{'exact':'images'},'encryptedBackups':backups,'plaintextHashes':{n:'clear-'+n for n in backups},'marketingBasis':{'confirmed':[]}}
  proof={'verifiedAt':now,'allFiveFullDecryptionsVerified':True,'recoveryDirectory':str(m.RECOVERY),'recoveryReceiptSha256':'bound-receipt','encryptedBackups':backups,'plaintextHashes':receipt['plaintextHashes'],'acerRecoveryCopy':'/home/firelion/v79-g3-tracking-recovery.synthetic'}
  return receipt,proof

 def test_recovery_and_offhost_proof_are_bound_to_exact_images_hashes_time_and_no_unreconciled_receipts(self):
  m=load();m.recovery={'EXPECTED':{'exact':'images'}};receipt,proof=self.evidence(m);m.verify_evidence(receipt,proof,'bound-receipt')
  for key,value in [('recoveryReceiptSha256','other'),('allFiveFullDecryptionsVerified',False),('plaintextHashes',{}),('recoveryDirectory','other')]:
   bad=copy.deepcopy(proof);bad[key]=value
   with self.assertRaises(RuntimeError):m.verify_evidence(receipt,bad,'bound-receipt')
  for change in [lambda r:r.update(scratchCleanupVerified=False),lambda r:r.update(candidates={'other':'image'}),lambda r:r['marketingBasis'].update(confirmed=[{'providerPostId':'confirmed'}]),lambda r:r.update(capturedAt=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=2)).isoformat())]:
   bad=copy.deepcopy(receipt);change(bad)
   with self.assertRaises(RuntimeError):m.verify_evidence(bad,proof,'bound-receipt')

 def test_a_failed_first_switch_records_attempt_before_command_and_never_switches_marketing_or_rolls_back(self):
  m=load();calls=[];m.manifest={'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'marketingBasis':{},'hubProtectedStateSha256':'hub','sourceHashes':{}}
  m.h={'protected_state':lambda name:'hub','inspect':lambda name:{'id':name},'healthy':lambda v:True,'stable_runtime':lambda v:v,'write_json':lambda path,value:Path(path).write_text(json.dumps(value))}
  m.recovery={'protected_equal':lambda *args:None,'basis':lambda name:{},'EXPECTED':{'V79hub':{'image':'sha256:hub'}}}
  runtime={n:{'id':n} for n in m.SPECS};stacks={n:['original'] for n in m.SPECS};resolved={n:{'services':{m.SPECS[n][2]:{}}} for n in m.SPECS};desired={n:{'candidate':n} for n in m.SPECS}
  with tempfile.TemporaryDirectory() as directory:
   m.WORK=Path(directory);overlays={n:m.WORK/(n+'.yml') for n in m.SPECS}
   def fail(args):
    self.assertTrue((m.WORK/'switch-attempted-v79-hub.json').is_file());calls.append(args);raise RuntimeError('Simulated uncertain Docker outcome')
   with patch.object(m,'resolve',side_effect=lambda name,files:desired[name]),patch.object(m,'compose_switch',side_effect=fail):
    with self.assertRaisesRegex(RuntimeError,'uncertain'):m.switch_services(runtime,stacks,resolved,desired,overlays)
   self.assertEqual(m.attempted,['v79-hub']);self.assertEqual(len(calls),1);self.assertFalse((m.WORK/'switch-attempted-v79marketing-app.json').exists());self.assertFalse((m.WORK/'deployed.json').exists())
   self.assertIn('--no-deps',calls[0]);self.assertIn('--no-build',calls[0]);self.assertEqual(calls[0][calls[0].index('--pull')+1],'never');self.assertEqual(calls[0][-1],'v79-hub')

 def test_served_asset_verification_uses_the_actual_index_and_detects_wrong_javascript(self):
  m=load()
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'dist/assets').mkdir(parents=True);(root/'dist/index.html').write_text('<script type="module" crossorigin src="/assets/index-actual.js"></script>')
   (root/'dist/assets/index-actual.js').write_text('Clear failed attempts; Publication complete; https://www.youtube.com/watch?v=; Owner-approved production')
   harness="globalThis.fetch=async url=>{const path=new URL(url).pathname;const bytes=fs.readFileSync(path==='/'?'dist/index.html':'dist'+path);return{status:200,text:async()=>bytes.toString(),arrayBuffer:async()=>process.env.CORRUPT?Buffer.from('wrong bytes'):bytes};};\n"
   # fs is bound by the original module's import; fetch executes afterward.
   for port in ('3040','3070'):
    result=subprocess.run(['node','--input-type=module','-'],input=(harness+m.UI_PROBE).encode(),cwd=root,env={'PATH':__import__('os').environ['PATH'],'PORT':port},capture_output=True)
    self.assertEqual(result.returncode,0,result.stderr.decode())
   result=subprocess.run(['node','--input-type=module','-'],input=(harness+m.UI_PROBE).encode(),cwd=root,env={'PATH':__import__('os').environ['PATH'],'PORT':'3040','CORRUPT':'1'},capture_output=True)
   self.assertNotEqual(result.returncode,0)

if __name__=='__main__':unittest.main()
