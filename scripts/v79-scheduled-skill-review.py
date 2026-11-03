#!/usr/bin/env python3
"""Bounded post-briefing skill advisory. Does not alter verified CEO/COO evidence.

Only owner-approved, digest-pinned SKILL.md text is delivered to the existing
local model using the current token-protected, read-only agent API. ZIP scripts
and hooks are never run from this scheduled workflow.
"""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

BASE=Path.home()/'.local/share/v79-workforce-operations'
REPORTS=BASE/'reports'
JOBS={'morning':('coo-daily','coo'),'evening':('ceo-daily','ceo')}
ZONE=ZoneInfo('America/St_Lucia')
SCRIPT=r"""
import fs from 'node:fs';
import {createHash} from 'node:crypto';
const output=(o)=>console.log(JSON.stringify(o));
try {
 const job=process.env.V79_SCHEDULED_JOB_ID;
 const role=process.env.V79_SCHEDULED_ROLE;
 if(!['coo-daily','ceo-daily'].includes(job) || !['coo','ceo'].includes(role))throw Error('INVALID_JOB');
 const token=fs.readFileSync('/run/secrets/v79-workforce-token','utf8').trim();
 const apiToken=String(process.env.V79_AGENT_API_TOKEN||'').trim()||
   fs.readFileSync('/run/secrets/v79-agent-token','utf8').trim();
 if(token.length<32||apiToken.length<32)throw Error('WORKER_CREDENTIAL_UNAVAILABLE');
 const guidance=await fetch('http://127.0.0.1:3040/internal/workforce/skill-guidance/'+job,{
  headers:{'x-v79-workforce-token':token},redirect:'error',signal:AbortSignal.timeout(7000)});
 if(!guidance.ok)throw Error('GUIDANCE_UNAVAILABLE');
 const b=await guidance.text();
 if(Buffer.byteLength(b)>30000)throw Error('GUIDANCE_TOO_LARGE');
 const data=JSON.parse(b);
 if(data.job!==job||data.source!=='owner-approved-guidance-only'||!Array.isArray(data.packages)||data.packages.length>2)
   throw Error('GUIDANCE_CONTRACT_INVALID');
 const packages=data.packages.map(p=>{
  if(!/^pkg-[0-9a-f]{16}$/.test(p.id)||!/^[a-f0-9]{64}$/.test(p.sha256)||
      typeof p.skill!=='string'||Buffer.byteLength(p.skill)>6000||
      typeof p.name!=='string'||p.name.length>80)throw Error('GUIDANCE_CONTENT_INVALID');
  return {id:'skill-'+p.sha256.slice(0,16),name:p.name,version:1,
    content:p.skill,sha256:createHash('sha256').update(p.skill).digest('hex'),
    packageId:p.id,archiveSha256:p.sha256};
 });
 if(!packages.length){output({state:'no-approved-assignments',job,role,packages:[]});}
 else{
  const ownerEmail=String(process.env.V79_HUB_ADMIN_EMAIL||'').trim().toLowerCase();
  if(ownerEmail!=='vision79slu@gmail.com')throw Error('OWNER_MISMATCH');
  const identity=JSON.parse(fs.readFileSync('/app/data/pos-identity.json','utf8'));
  const context={userId:identity.ownerUserId,email:ownerEmail,organizationId:identity.organizationId,
   organizationName:'V79 Digital',
   allowedSystems:['hub','website','lasertag','marketing','pos','tiquet','ffpro','academy','games'],
   ownerAgent:true,hubAdmin:true};
  const roles=['ceo','coo','finance','strategy','marketing','customer-service','technical-security','sales'];
  const managedSkills=Object.fromEntries(roles.map(x=>[x,[]]));
  managedSkills[role]=packages.map(({packageId,archiveSha256,...g})=>g);
  const message=role.toUpperCase()+': Provide a concise owner-review-only quality and improvement checklist for current V79 work. '+
   'Use only verified business snapshot facts. Identify unknowns and do not claim actions, permissions, deployments or approvals.';
  const response=await fetch('http://v79-business-agent:3055/api/agent/chat',{
   method:'POST',redirect:'error',signal:AbortSignal.timeout(24000),
   headers:{'x-v79-agent-token':apiToken,'content-type':'application/json'},
   body:JSON.stringify({message,context,managedSkills})});
  if(!response.ok)throw Error('AGENT_ADVISORY_UNAVAILABLE');
  const raw=await response.text();
  if(Buffer.byteLength(raw)>130000)throw Error('AGENT_RESPONSE_OVERSIZE');
  const result=JSON.parse(raw);
  if(result.mode!=='read-only'||result.roleId!==role||
     !['ollama'].includes(result.modelProvider)||typeof result.output!=='string'||
      result.output.length>6000)throw Error('AGENT_ADVISORY_CONTRACT_INVALID');
  const expected=managedSkills[role].map(p=>p.id+'@v1');
  const applied=result.managedSkillVersionsApplied;
  const accepted=result.advisoryOutcome==='accepted' &&
    Array.isArray(applied) && JSON.stringify(applied)===JSON.stringify(expected);
  output({state:accepted?'accepted-review':'not-applied',
    job,role,packages:packages.map(p=>({id:p.id,sha256:p.sha256,archiveSha256:p.archiveSha256})),
    modelReview:accepted?result.output.slice(0,4000):'',
    responseMode:String(result.responseMode||'').slice(0,80)});
 }
}catch(e){output({state:'unavailable',reason:String(e?.message||'error').replace(/[^A-Z_]/g,'').slice(0,80)});process.exitCode=1;}
"""

def main():
 if len(sys.argv)!=2 or sys.argv[1] not in JOBS:raise ValueError('Specify morning or evening')
 slot=sys.argv[1]
 job,role=JOBS[slot]
 current=dt.datetime.now(dt.timezone.utc)
 if current.astimezone(ZONE).hour < (8 if slot=='morning' else 19):
  raise ValueError('Scheduled slot not reached')
 if not REPORTS.is_dir() or REPORTS.is_symlink() or REPORTS.stat().st_mode&0o077:
  raise ValueError('Unsafe reporting directory')
 target=REPORTS/(f'skill-review-{current.astimezone(ZONE):%Y-%m-%d}-{slot}.json')
 if target.exists() or target.is_symlink():
  print('SKILL_REVIEW=ALREADY_RECORDED');return
 # Re-use the existing healthy, token-protected Hub execution environment.
 command=['docker','exec','-i','-e','V79_SCHEDULED_JOB_ID='+job,
          '-e','V79_SCHEDULED_ROLE='+role,'v79-hub','node','--input-type=module','-']
 result=subprocess.run(command,input=SCRIPT,capture_output=True,text=True,timeout=35)
 if result.returncode or len(result.stdout)>30000:raise ValueError('Scheduled guidance request failed')
 doc=json.loads(result.stdout)
 if doc.get('job')!=job or doc.get('role')!=role or doc.get('state') not in (
   'accepted-review','not-applied','no-approved-assignments'):
  raise ValueError('Scheduled advisory envelope rejected')
 envelope={'schema':1,'slot':slot,'recordedAt':current.isoformat(),
           'source':'local-read-only-advisory','verifiedBusinessFacts':False,
           'noActionsExecuted':True,'review':doc}
 tmp=target.with_suffix('.tmp')
 if tmp.exists() or tmp.is_symlink():raise ValueError('Unclean previous temporary output')
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'w') as f:
   json.dump(envelope,f,separators=(',',':'));f.flush();os.fsync(f.fileno())
  os.replace(tmp,target)
 finally:
  if tmp.exists():tmp.unlink()
 print('SKILL_REVIEW='+doc['state'].upper())
 print('SCHEDULED_JOB='+job)
 print('ZIP_CODE_EXECUTED=NO')

if __name__=='__main__':
 try:main()
 except Exception as e:
  print('SKILL_REVIEW=UNAVAILABLE '+type(e).__name__)
  sys.exit(1)
