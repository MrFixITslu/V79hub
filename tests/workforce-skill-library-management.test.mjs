import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import express from 'express';
import {createPackageStore} from '../server/workforce-skill-packages.mjs';
import {createSkillRegistry} from '../server/workforce-skill-registry.mjs';
import {workforceSkillRouter} from '../server/workforce-skill-routes.mjs';

function archive(text){
  const script=`import io,zipfile,base64,sys
b=io.BytesIO()
with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('SKILL.md',sys.stdin.read())
 z.writestr('scripts/never_execute.py','raise RuntimeError("UNSAFE EXECUTION")')
print(base64.b64encode(b.getvalue()).decode())`;
  return execFileSync('python3',['-c',script],{input:text}).toString().trim();
}
const key='v79-protected-skill-test-key-long-enough-00001';
const fresh=()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'v79-manage-test-'));
  const registry=createSkillRegistry({file:path.join(dir,'skills.json'),secret:key});
  const packages=createPackageStore({directory:path.join(dir,'packages'),secret:key});
  return {dir,registry,packages};
};

test('edit as immutable ZIP replacement, MFA promotion, archive and recover without script execution',async()=>{
 const {dir,registry,packages}=fresh();
 try{
  const imported=await packages.import({name:'website-studio',archive:archive('# First Website Studio')},'owner');
  assert.equal(imported.version,1);
  const approved=await packages.approve(imported.id,{sha256:imported.sha256,expectedRevision:1},'owner');
  const configured=await packages.configure(imported.id,{hooks:['package-integrity'],schedules:['technology-review'],expectedRevision:approved.revision},'owner');
  const oldBytes=packages.download(imported.id);
  const update=await packages.stageRevision(imported.id,{archive:archive('# Revised Website Studio'),expectedRevision:configured.revision},'owner');
  assert.equal(update.status,'quarantined');assert.equal(update.version,2);assert.equal(update.supersedesId,imported.id);
  assert.equal(packages.scheduledSnapshot('technology-review').packages[0].sha256,imported.sha256);
  assert.deepEqual(packages.download(imported.id),oldBytes);
  await assert.rejects(packages.stageRevision(imported.id,{archive:archive('# Third version'),expectedRevision:configured.revision},'owner'),{status:409});
  await assert.rejects(packages.promote(update.id,{expectedRevision:1,expectedParentRevision:configured.revision},'owner'),{status:409});
  const child=await packages.approve(update.id,{sha256:update.sha256,expectedRevision:update.revision},'owner');
  await assert.rejects(packages.configure(update.id,{hooks:[],schedules:['technology-review'],expectedRevision:child.revision},'owner'),{status:409});
  await assert.rejects(packages.promote(update.id,{expectedRevision:child.revision,expectedParentRevision:1},'owner'),{status:409});
  const promoted=await packages.promote(update.id,{expectedRevision:child.revision,expectedParentRevision:configured.revision},'owner');
  assert.equal(promoted.status,'approved');assert.deepEqual(promoted.hooks,['package-integrity']);
  assert.deepEqual(promoted.schedules,['technology-review']);assert.ok(promoted.promotedAt);
  const old=packages.read(imported.id);assert.equal(old.archived,true);assert.equal(old.status,'quarantined');
  assert.equal(packages.scheduledSnapshot('technology-review').packages.length,1);
  assert.equal(packages.scheduledSnapshot('technology-review').packages[0].sha256,update.sha256);
  await assert.rejects(packages.approve(imported.id,{sha256:old.sha256,expectedRevision:old.revision},'owner'),{status:409});
  const archived=await packages.archive(update.id,{expectedRevision:promoted.revision},'owner');
  assert.equal(archived.archived,true);assert.equal(packages.scheduledSnapshot('technology-review').packages.length,0);
  const restored=await packages.unarchive(update.id,{expectedRevision:archived.revision},'owner');
  assert.equal(restored.status,'quarantined');assert.equal(restored.archived,false);
  assert.deepEqual(restored.schedules,[]);
  assert.equal(createHash('sha256').update(packages.download(update.id)).digest('hex'),update.sha256);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});

test('preserves production 10 KB advisory allowance without permitting oversized guidance',async()=> {
 const {inspectZipBase64}=await import('../server/workforce-skill-packages.mjs');
 const zip=(bytes)=>execFileSync('python3',['-c',`import io,zipfile,base64,sys
b=io.BytesIO()
with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('SKILL.md','# Full skill\n'+'x'*11000)
 z.writestr('ADVISORY.md',sys.stdin.read())
print(base64.b64encode(b.getvalue()).decode())`],{input:'Reviewed guidance '.repeat(bytes)}).toString().trim();
 const accepted=inspectZipBase64(zip(350));
 assert.match(accepted.skill,/Reviewed guidance/);
 assert.throws(()=>inspectZipBase64(zip(750)));
});

test('custom skills archive disables role safely, retains immutable versions, and restores inactive',async()=>{
 const {dir,registry}=fresh();
 try{
  const saved=await registry.create({name:'Website Studio',content:'# First\nRules'},'owner');
  const active=await registry.activate(saved.id,1,['marketing'],1,'owner');
  assert.equal(registry.assignedSkills().marketing.length,1);
  await assert.rejects(registry.archive(saved.id,1,'owner'),{status:409});
  const archived=await registry.archive(saved.id,active.revision,'owner');
  assert.equal(archived.status,'archived');assert.equal(archived.archived,true);
  assert.equal(registry.assignedSkills().marketing.length,0);
  assert.equal(registry.get(saved.id).versions.length,1);
  await assert.rejects(registry.activate(saved.id,1,['marketing'],archived.revision,'owner'),{status:409});
  await assert.rejects(registry.revise(saved.id,{name:'New',content:'# New'},archived.revision,'owner'),{status:409});
  const restored=await registry.unarchive(saved.id,archived.revision,'owner');
  assert.equal(restored.status,'paused');assert.equal(restored.archived,false);
  assert.equal(registry.assignedSkills().marketing.length,0);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});

test('management HTTP routes fail closed without founder MFA, same origin, or current revision',async()=>{
 const {dir,registry,packages}=fresh();
 const app=express();app.use(express.json({limit:'2mb'}));
 app.use('/skills',workforceSkillRouter({registry,packages,enabled:()=>true,
  ownerContext:req=>req.get('x-owner')==='yes'?{userId:'owner'}:null,
  freshOwnerContext:req=>req.get('x-fresh')==='yes'?{userId:'owner'}:null,
  sameOrigin:req=>req.get('origin')==='http://allowed.local'}));
 const server=app.listen(0,'127.0.0.1');
 try{
  await new Promise(resolve=>server.once('listening',resolve));
  const base='http://127.0.0.1:'+server.address().port;
  const request=async(endpoint,method='GET',payload,headers={})=>{
   const res=await fetch(base+endpoint,{method,
    headers:{'x-owner':'yes',origin:'http://allowed.local',...(payload?{'content-type':'application/json'}:{}),...headers},
    ...(payload?{body:JSON.stringify(payload)}:{})});
   if(endpoint.endsWith('/download') && res.ok)return {status:res.status,bytes:Buffer.from(await res.arrayBuffer())};
   return {status:res.status,json:await res.json()};
  };
  const packageCreated=await request('/skills/packages/import','POST',{name:'full-website',archive:archive('# Original')});
  const pid=packageCreated.json.package.id;
  assert.equal((await request('/skills/packages/'+pid+'/download','GET',undefined,{'x-owner':'no'})).status,403);
  const downloaded=await request('/skills/packages/'+pid+'/download');
  assert.equal(downloaded.status,200);
  assert.equal(downloaded.bytes.toString('base64'),packages.download(pid).toString('base64'));
  for(const headers of [{}, {'x-fresh':'yes',origin:'https://wrong.local'},{'x-fresh':'yes','x-owner':'no'}]){
   assert.equal((await request('/skills/packages/'+pid+'/archive','POST',{expectedRevision:1},headers)).status,403);
  }
  const good=await request('/skills/packages/'+pid+'/archive','POST',{expectedRevision:1},{'x-fresh':'yes'});
  assert.equal(good.status,200);assert.equal(good.json.package.archived,true);
  assert.equal((await request('/skills/packages/'+pid+'/unarchive','POST',{expectedRevision:1},{'x-fresh':'yes'})).status,409);
  const original=await request('/skills/packages/'+pid+'/unarchive','POST',{expectedRevision:2},{'x-fresh':'yes'});
  assert.equal(original.status,200);assert.equal(original.json.package.archived,false);
  const txt=await request('/skills','POST',{name:'Custom guide',content:'Useful details'});
  const tid=txt.json.skill.id;
  assert.equal((await request('/skills/'+tid+'/archive','POST',{expectedRevision:1})).status,403);
  assert.equal((await request('/skills/'+tid+'/archive','POST',{expectedRevision:1},{'x-fresh':'yes'})).status,200);
  assert.equal((await request('/skills/'+tid+'/unarchive','POST',{expectedRevision:2},{'x-fresh':'yes'})).status,200);
 }finally{await new Promise(resolve=>server.close(resolve));fs.rmSync(dir,{recursive:true,force:true});}
});
