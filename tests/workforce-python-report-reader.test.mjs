import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {validatePythonBriefing,createPythonBriefingStatus} from '../server/workforce-python-report-reader.mjs';
const at = new Date('2026-10-16T23:00:22Z');
const sample = () => ({schema:1,slot:'2026-10-16-evening',checkedAt:at.toISOString(),state:'AVAILABLE',report:{evidenceCollectedAt:at.toISOString(),priority:'ATTENTION',coverage:'AVAILABLE',verifiedFindings:[{system:'hub',metric:'faults',value:1.5,severity:'attention'}],missingSources:[],noActionsExecuted:true}});
test('Python report maps only numeric evidence and allowlisted fields',()=>{
 const raw=sample();raw.secret='private';raw.report.verifiedFindings[0].secret='private';
 const result=validatePythonBriefing(raw,at.getTime());
 assert.equal(result.state,'available');assert.equal(result.report.priority,'attention');assert.equal(JSON.stringify(result).includes('private'),false);
});
test('action claims, stale source, future check, injected fields and contradictory coverage reject',()=>{
 for(const mutate of [r=>r.report.noActionsExecuted=false,r=>r.report.evidenceCollectedAt='2026-10-16T21:00:00Z',r=>r.checkedAt='2027-01-01T00:00:00Z',r=>r.report.verifiedFindings[0].metric='<script>',r=>r.report.missingSources=['hub'],r=>r.schema=2]) {
  const raw=sample();mutate(raw);assert.throws(()=>validatePythonBriefing(raw,at.getTime()));
 }
});
test('private files read without mutation; stale and unsafe files fail visibly',async()=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'v79-python-'));const file=path.join(dir,'2026-10-16-evening.json');
 try {
  const text=JSON.stringify(sample());await fs.writeFile(file,text,{mode:0o600});
  const read=createPythonBriefingStatus({directory:dir,now:()=>at});
  assert.equal((await read()).status,'report_available');assert.equal(await fs.readFile(file,'utf8'),text);
  assert.equal((await createPythonBriefingStatus({directory:dir,now:()=>new Date('2026-10-19T00:00:00Z')})()).status,'stale_or_unavailable');
  await fs.chmod(file,0o644);assert.equal((await read()).status,'unavailable');
  await fs.unlink(file);await fs.symlink('/etc/passwd',file);assert.equal((await read()).status,'unavailable');
 }finally{await fs.rm(dir,{recursive:true,force:true})}
});
