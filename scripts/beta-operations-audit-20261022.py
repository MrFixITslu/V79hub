#!/usr/bin/env python3
"""Read-only workforce closing evidence; never starts a service or invokes a worker."""
import argparse,datetime,hashlib,json,os,re,socket,stat,subprocess,sys,unittest
from pathlib import Path
PINS={'v79-hub': 'sha256:d722f357206fec938eca691c92ddfe57ece62811f62124f6fbf760258b2b6940', 'v79-tiquet-manager': 'sha256:18fc67f82ec3dc33a7b281da79d6ab8e6b17f2983f419833bd008101d5711fc3', 'v79-business-agent': 'sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b', 'v79-hub-postgres': 'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24', 'tiquet-postgres': 'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685'}
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def command(args,timeout=60):
 p=subprocess.run(args,capture_output=True,timeout=timeout);need(p.returncode==0,'READ_COMMAND_FAILED_NO_SECRET_OUTPUT');return p.stdout
def private_json(path):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode&0o077 and s.st_size<=65536,'PRIVATE_STATUS_METADATA_INVALID');data=os.read(fd,65537);need(len(data)<=65536,'STATUS_TOO_LARGE');return json.loads(data)
 finally:os.close(fd)
def unit(name):
 fields=['ActiveState','SubState','Result','ExecMainStatus','LastTriggerUSec','NextElapseUSecRealtime','ActiveEnterTimestamp','TimersCalendar']
 p=subprocess.run(['systemctl','--user','show',name,*['--property='+f for f in fields]],capture_output=True,text=True,timeout=20)
 if p.returncode:return {'metadata':'UNAVAILABLE'}
 return {k:v for line in p.stdout.splitlines() if '=' in line for k,v in [line.split('=',1)] if k in fields}
REPORT_AUDIT="import fs from 'node:fs/promises';\nimport {constants} from 'node:fs';\nimport path from 'node:path';\nimport {createHash} from 'node:crypto';\nimport {validatePythonBriefing} from './server/workforce-python-report-reader.mjs';\nimport {auditBriefingReliability} from './workforce/quality/briefing-reliability.mjs';\nimport {getWipayConfig} from './server/wipay-provider.mjs';\nconst blob=b=>createHash('sha1').update(Buffer.from('blob '+b.length+'\\0')).update(b).digest('hex');\nfor(const [file,expected] of Object.entries({'server/workforce-python-report-reader.mjs':'cb33c5517fca8cfb3a1c1a8c59645a118d7ebf32','workforce/quality/briefing-reliability.mjs':'427cc80691b860c7e560d2f6e8ba591e78d24516'}))if(blob(await fs.readFile(file))!==expected)throw Error('source-pin');\nconst now=new Date(),today=new Intl.DateTimeFormat('en-CA',{timeZone:'America/St_Lucia',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);\nconst firstDay=new Date(Date.parse(today+'T00:00:00Z')-3*86400000).toISOString().slice(0,10);\nconst root='/run/v79-workforce-reports',safe=[],verified=new Set();let complete=true,invalid=0;\nconst dir=await fs.lstat(root);if(!dir.isDirectory()||dir.isSymbolicLink()||(dir.mode&0o077))throw Error('private-report-dir');\nconst names=(await fs.readdir(root)).filter(x=>/^\\d{4}-\\d{2}-\\d{2}-(morning|evening|manual-\\d{6})\\.json$/.test(x));if(names.length>500)throw Error('inventory-limit');\nconst selected=names.filter(x=>x.slice(0,10)>=firstDay&&x.slice(0,10)<today&&/-(morning|evening)\\.json$/.test(x));\nfor(const name of selected){let h;try{\n h=await fs.open(path.join(root,name),constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);const s=await h.stat();if(!s.isFile()||s.uid!==dir.uid||(s.mode&0o077)||s.size>100000)throw Error('private-report');\n const b=Buffer.alloc(100001),{bytesRead}=await h.read(b,0,b.length,0);if(bytesRead>100000)throw Error('report-limit');\n const raw=JSON.parse(b.subarray(0,bytesRead).toString('utf8')),checked=validatePythonBriefing(raw,now.getTime());if(raw.slot+'.json'!==name)throw Error('slot-mismatch');\n safe.push({slot:raw.slot,checkedAt:new Date(raw.checkedAt).toISOString(),state:'recorded',report:{coverage:checked.report.coverage,noActionsExecuted:true}});verified.add(raw.slot);\n}catch{complete=false;invalid++}finally{await h?.close()}}\nconst reliability=auditBriefingReliability({reports:safe,firstDay,days:3,asOfUtc:now.toISOString(),verifyReport:r=>verified.has(r.slot),verifyInventory:()=>complete});\nconst wipay=getWipayConfig().environment;if(wipay!=='sandbox')throw Error('sandbox-required');\nconsole.log(JSON.stringify({wipay:'sandbox',sourcePins:'PASS',window:{firstDay,lastDay:new Date(Date.parse(today+'T00:00:00Z')-86400000).toISOString().slice(0,10),timezone:'America/St_Lucia',completedDays:3},inventory:{selectedFiles:selected.length,invalid,complete},reliability,provenance:'private-owned-files-and-schema-validation-not-cryptographic-report-signatures',reportContentPrinted:false,providerCalls:false}));\n"
def main():
 need(socket.gethostname()=='v79sl' and os.getuid()==1000,'SERVER_IDENTITY_MISMATCH')
 need(not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'),'DOCKER_OVERRIDE_DISALLOWED')
 contexts=json.loads(command(['docker','context','inspect']));need(len(contexts)==1 and contexts[0]['Endpoints']['docker']['Host'] in ('unix:///var/run/docker.sock','unix:///run/docker.sock'),'NONLOCAL_DOCKER')
 need(json.loads(command(['docker','info','--format','{{json .Name}}']))=='v79sl','DOCKER_DAEMON_MISMATCH')
 def baseline():
  objects={o['Name'].lstrip('/'):o for o in json.loads(command(['docker','inspect',*PINS]))}
  for name,pin in PINS.items():
   o=objects[name];need(o['Image']==pin and o['State']['Status']=='running' and o['State'].get('Health',{}).get('Status')=='healthy','LIVE_BASELINE_DRIFT')
  return objects
 before=baseline();hub=before['v79-hub'];mounts=[m for m in hub['Mounts'] if m['Destination']=='/run/v79-workforce-reports'];need(len(mounts)==1 and not mounts[0]['RW'],'REPORT_MOUNT_NOT_READ_ONLY')
 evidence=json.loads(command(['docker','exec','--workdir','/app','v79-hub','node','--input-type=module','-e',REPORT_AUDIT],timeout=90))
 timers={name:unit(name) for name in ['v79-g2-approved-task-worker.timer','v79-workforce-morning.timer','v79-workforce-evening.timer','v79-g2-approved-task-worker.service','v79-workforce-briefing@morning.service','v79-workforce-briefing@evening.service']}
 after=baseline();need(all(before[n]['Id']==after[n]['Id'] for n in PINS),'CONCURRENT_RELEASE_REQUIRES_REVIEW')
 live=dict(x.split('=',1) for x in hub['Config']['Env'] if '=' in x)
 active=all(timers[n].get('ActiveState')=='active' for n in timers if n.endswith('.timer'))
 signup_off=live.get('V79_SELF_SERVICE_SIGNUP')=='0'
 result={'mode':'READ_ONLY_BETA_OPERATIONS_AUDIT','checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ownerBetaDecision':'GO_INVITE_ONLY_HUB_TIQUET','paidLaunch':'DEFERRED','baseline':'PASS_5_PINNED_SERVICES_SAME_IDS','selfServiceSignupDisabled':signup_off,'timers':timers,'allThreeTimersActive':active,'evidence':evidence,'workforceSustainedReliability':'PASS_6_OF_6' if evidence['reliability']['status']=='candidate_for_owner_acceptance' and active else 'REQUIRES_REVIEW','productionChanged':False,'jobsInvoked':False,'providerCalls':False,'customerInvitationsSent':False}
 print(json.dumps(result,indent=2,sort_keys=True))

class Tests(unittest.TestCase):
 def test_pins(self):self.assertEqual(len(PINS),5);self.assertTrue(all(re.fullmatch('sha256:[a-f0-9]{64}',x) for x in PINS.values()))
 def test_status_reader_rejects_loose_permissions(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'s.json';p.write_text('{}');p.chmod(0o644)
   with self.assertRaises(Stop):private_json(p)
 def test_status_reader_rejects_symlink(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'s.json';p.write_text('{}');p.chmod(0o600);q=Path(d)/'link';q.symlink_to(p)
   with self.assertRaises(OSError):private_json(q)
 def test_status_reader_preserves_valid_private_data(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'s.json';p.write_text('{"state":"idle"}');p.chmod(0o600);self.assertEqual(private_json(p),{'state':'idle'})
 def test_no_mutation_in_node_audit(self):
  for forbidden in ('ledger.transact','getAccessToken','client.execute','writeFile','unlink','fetch('):self.assertNotIn(forbidden,REPORT_AUDIT)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');a=p.parse_args()
 if a.self_test:
  r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));sys.exit(0 if r.wasSuccessful() else 1)
 try:main()
 except BaseException as e:
  if isinstance(e,SystemExit):raise
  print('STOP='+(str(e) if isinstance(e,Stop) else 'READ_ONLY_AUDIT_FAILED_NO_SECRET_OUTPUT'));sys.exit(1)
