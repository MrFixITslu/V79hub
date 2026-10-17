"""Copied recovery guards: signed approvals, idle windows and owned isolation."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'scripts/marketing-production-tracking-recovery.py'
def load():
 spec=importlib.util.spec_from_file_location('tracking_recovery',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class TrackingRecoveryTests(unittest.TestCase):
 def test_signed_idle_guard_preserves_future_approvals_and_rejects_active_uncertain_or_due_work(self):
  m=load()
  harness=r"""
const assert=require('node:assert/strict'),crypto=require('node:crypto'),vm=require('node:vm'),key='s'.repeat(64),org='44289786-2583-4bf1-9db2-99eca95dfd96',now=Date.parse('2026-10-15T09:30:00Z');
const canonical=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
let tamper=false,state={ownerHubUserId:'102ad8ce-df0b-4767-a3e2-b715ddbfee84',paused:false,plan:{automaticDrafts:false,cadenceDays:7},seenRequests:[{id:'nonce'}],jobs:[{id:'job',status:'awaiting_owner',deliveries:[{id:'approved',status:'approved',scheduledAt:new Date(now+86400000).toISOString()}]}]},out=[],closed=false;
const original=structuredClone(state);
class DB{pragma(v){return v==='integrity_check'?'ok':undefined;}defaultSafeIntegers(){}exec(){}prepare(sql){return{all(){
 if(sql.startsWith('SELECT name'))return[{name:'businesses'},{name:'marketing_production_state'}];
 if(sql.startsWith('SELECT business_id'))return[{business_id:org,envelope:JSON.stringify({state,hmac:tamper?'0'.repeat(64):crypto.createHmac('sha256',key).update('v79-marketing-production-v1\n'+org+'\n'+canonical(state)).digest('hex')})}];
 return [{id:'private-customer',secret:'synthetic-never-display',amount:7n}];}};}close(){closed=true;}}
const run=()=>{out=[];closed=false;vm.runInNewContext(PROBE,{require:n=>n==='better-sqlite3'?DB:require(n),process:{env:{V79_MARKETING_PRODUCTION_AUDIT_KEY:key}},Buffer,Date:class extends Date{static now(){return now;}},console:{log(v){out.push(v);}}});};
run();assert.deepEqual(state,original);assert.ok(closed);assert.equal(out.length,1);assert.ok(!out[0].includes('synthetic-never-display'));assert.ok(!out[0].includes('private-customer'));
const result=JSON.parse(out[0]);assert.equal(result.counts.deliveries.approved,1);assert.match(result.signedLedgerSha256,/^[a-f0-9]{64}$/);
for(const change of [s=>s.jobs[0].status='queued',s=>s.jobs[0].status='generating',s=>s.jobs[0].deliveries[0].status='running',s=>s.jobs[0].deliveries[0].status='uncertain',s=>s.jobs[0].deliveries[0].scheduledAt=new Date(now+1800000).toISOString(),s=>s.jobs[0].deliveries[0].scheduledAt='invalid',s=>{s.plan.automaticDrafts=true;s.lastAutomaticAt=null;},s=>s.ownerHubUserId='other-owner']){
 state=structuredClone(original);change(state);assert.throws(run);assert.ok(closed);assert.deepEqual(out,[]);}
state=structuredClone(original);tamper=true;assert.throws(run,/Signed ledger integrity/);assert.deepEqual(out,[]);
"""
  result=subprocess.run(['node','--input-type=commonjs','-'],input=('const PROBE='+json.dumps(m.BASIS)+';'+harness).encode(),capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr.decode())

 def test_only_the_empty_additive_schema_can_differ_after_copied_startup(self):
  m=load();before={'protectedTables':{'users':'original','posts':'original'},'signedLedgerSha256':'signed-original','trackingLinksSha256':'empty','trackingLinksCount':0,'hasTrackingSchema':False}
  after={**before,'hasTrackingSchema':True};m.protected_equal(before,after,True)
  for key in ('protectedTables','signedLedgerSha256','trackingLinksSha256','trackingLinksCount'):
   bad=copy.deepcopy(after);bad[key]='changed'
   with self.assertRaises(RuntimeError):m.protected_equal(before,bad,True)
  with self.assertRaises(RuntimeError):m.protected_equal(before,before,True)

 def test_scratch_uses_no_host_data_mounts_or_ports_and_does_not_reach_live_hub(self):
  m=load();calls=[];baseline={'protectedTables':{},'signedLedgerSha256':'same','trackingLinksSha256':'empty','trackingLinksCount':0,'hasTrackingSchema':False}
  with tempfile.TemporaryDirectory() as directory:
   m.ram=Path(directory)
   def run(args,data=None,**kwargs):
    calls.append((args,data))
    if args[:2]==['docker','create']:
     self.assertEqual(args[args.index('--network')+1],'none');self.assertEqual(args[args.index('--user')+1],'node');self.assertIn('--read-only',args);self.assertNotIn('--mount',args);self.assertNotIn('-v',args);self.assertNotIn('-p',args);self.assertNotIn('original-key',' '.join(args))
     env=Path(args[args.index('--env-file')+1]);self.assertEqual(env.stat().st_mode&0o777,0o600);text=env.read_text();self.assertIn('V79_HUB_INTERNAL_URL=http://127.0.0.1:1',text);self.assertIn('V79_ENTITLEMENT_RECHECK_ENABLED=1',text);self.assertIn('V79_MARKETING_PRODUCTION_AUDIT_KEY=original-key',text)
    if data and b"r.ok?'READY'" in data:return b'READY'
    if data and b'COPIED_AUTH_AND_PRIVATE_DRAFT_PASS' in data:return b'COPIED_AUTH_AND_PRIVATE_DRAFT_PASS'
    return b''
   m.h={'run':run,'env_map':lambda xs:dict(v.split('=',1) for v in xs),'inspect':lambda name:{'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'PortBindings':{}},'Config':{'User':'node'},'Mounts':[{'Type':'tmpfs'}]}}
   runtime={'v79marketing-app':{'Config':{'Env':['V79_MARKETING_PRODUCTION_AUDIT_KEY=original-key','V79_HUB_INTERNAL_URL=http://live-hub:3040']}}}
   with patch.object(m,'basis',return_value={**baseline,'hasTrackingSchema':True}):name,_=m.scratch('sha256:immutable','candidate',b'synthetic-sqlite',b'synthetic-tar',baseline,runtime)
   self.assertTrue(name.startswith('v79-tracking-candidate-'));self.assertEqual(len([c for c,d in calls if c[:2]==['docker','create']]),1)
   self.assertFalse(any('compose' in c or 'restart' in c for c,d in calls));self.assertEqual([d for c,d in calls if d in (b'synthetic-sqlite',b'synthetic-tar')],[b'synthetic-sqlite',b'synthetic-tar'])

 def test_cleanup_only_removes_the_exact_owned_scratch_container(self):
  m=load();meta={'Config':{'Labels':{m.LABEL:m.NONCE}},'State':{'Status':'running'}}
  present=subprocess.CompletedProcess([],0,stdout=json.dumps([meta]).encode(),stderr=b'')
  absent=subprocess.CompletedProcess([],1,stdout=b'',stderr=b'Error: No such object: scratch')
  with patch.object(m.subprocess,'run',side_effect=[present,absent]),patch.object(m.subprocess,'Popen') as start:
   m.cleanup_one('scratch');self.assertEqual(start.call_args.args[0],['docker','rm','--force','scratch'])
  meta['Config']['Labels'][m.LABEL]='another-attempt'
  for result in [subprocess.CompletedProcess([],0,stdout=json.dumps([meta]).encode(),stderr=b''),subprocess.CompletedProcess([],1,stdout=b'',stderr=b'daemon unavailable')]:
   with patch.object(m.subprocess,'run',return_value=result),patch.object(m.subprocess,'Popen') as start:
    with self.assertRaises(RuntimeError):m.cleanup_one('scratch')
    start.assert_not_called()

 def test_slow_removal_waits_for_absence_and_never_reissues_a_pending_request(self):
  for already_removing in (False,True):
   m=load();meta={'Config':{'Labels':{m.LABEL:m.NONCE}},'State':{'Status':'removing' if already_removing else 'running'}}
   present=lambda:subprocess.CompletedProcess([],0,stdout=json.dumps([meta]).encode(),stderr=b'')
   first=present();meta['State']['Status']='removing'
   absent=subprocess.CompletedProcess([],1,stdout=b'',stderr=b'No such object: scratch')
   with patch.object(m.subprocess,'run',side_effect=[first,present(),present(),absent]),patch.object(m.subprocess,'Popen') as start,patch.object(m.time,'sleep'),patch.object(m.time,'monotonic',side_effect=[0,0,90,150]):
    start.return_value.poll.return_value=None
    m.cleanup_one('scratch');self.assertEqual(start.call_count,0 if already_removing else 1)

 def test_pending_removal_timeout_cannot_start_the_next_phase_or_duplicate_removal(self):
  m=load();meta={'Config':{'Labels':{m.LABEL:m.NONCE}},'State':{'Status':'removing'}}
  present=subprocess.CompletedProcess([],0,stdout=json.dumps([meta]).encode(),stderr=b'')
  with patch.object(m.subprocess,'run',return_value=present),patch.object(m.subprocess,'Popen') as start,patch.object(m.time,'monotonic',side_effect=[0,0,301]):
   with self.assertRaisesRegex(RuntimeError,'five minutes'):m.cleanup_one('scratch')
   with self.assertRaisesRegex(RuntimeError,'remains uncertain'):m.cleanup_one('scratch')
   start.assert_not_called()

if __name__=='__main__':unittest.main()
