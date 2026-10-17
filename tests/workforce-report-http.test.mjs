import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createOwnerBriefingReader} from '../server/workforce-briefing-route.mjs';
import {createPythonBriefingStatus} from '../server/workforce-python-report-reader.mjs';
test('HTTP reader uses private Python reports and denies unauthorized reads and all writes',async()=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'v79-http-'));
 const at=new Date('2026-10-16T23:00:22Z');
 const raw={schema:1,slot:'2026-10-16-evening',checkedAt:at.toISOString(),state:'recorded',report:{evidenceCollectedAt:at.toISOString(),coverage:'AVAILABLE',priority:'ATTENTION',verifiedFindings:[],missingSources:[],noActionsExecuted:true}};
 const file=path.join(dir,'2026-10-16-evening.json');await fs.writeFile(file,JSON.stringify(raw),{mode:0o600});
 const app=express();let enabled=false;
 // Test-only synthetic identity. Production uses ownerApprovalContext, never a header.
 app.all('/reports',createOwnerBriefingReader({ownerMfaContext:req=>req.headers['x-test-owner']==='mfa'?{owner:true}:null,enabled:()=>enabled,readStatus:createPythonBriefingStatus({directory:dir,now:()=>at})}));
 const server=await new Promise(resolve=>{const s=app.listen(0,'127.0.0.1',()=>resolve(s))});
 const url=`http://127.0.0.1:${server.address().port}/reports`;
 try{
  assert.equal((await fetch(url)).status,403);
  const headers={'x-test-owner':'mfa'};
  assert.equal((await fetch(url,{headers})).status,503);
  enabled=true;
  const res=await fetch(url,{headers});assert.equal(res.status,200);assert.equal(res.headers.get('cache-control'),'no-store');
  const body=await res.json();assert.equal(body.status,'report_available');assert.equal(body.reports.length,1);
  for(const method of ['POST','PUT','PATCH','DELETE','HEAD'])assert.equal((await fetch(url,{method,headers})).status,405);
  assert.equal((await fetch(url)).status,403);
  assert.equal(await fs.readFile(file,'utf8'),JSON.stringify(raw));
 }finally{await new Promise(resolve=>server.close(resolve));await fs.rm(dir,{recursive:true,force:true})}
});
