import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {execFileSync} from "node:child_process";
import {createPackageStore,inspectZipBase64} from "../server/workforce-skill-packages.mjs";

const zip=(entries)=>{
  const code=`import io,zipfile,sys,json,base64
z=io.BytesIO()
with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as f:
 for name,text in json.loads(sys.stdin.buffer.read()):f.writestr(name,text)
print(base64.b64encode(z.getvalue()).decode())`;
  return execFileSync("python3",["-c",code],{input:JSON.stringify(entries)}).toString().trim();
};

test("safe ZIP parser accepts SKILL.md and code but never executes its scripts",()=>{
  const encoded=zip([["SKILL.md","# Test skill\nSafe design guidance"],["scripts/check.py","raise RuntimeError('must not execute')"]]);
  const result=inspectZipBase64(encoded);
  assert.equal(result.files,2);
  assert.equal(result.entrypoints[0].path,"scripts/check.py");
  assert.match(result.skill,/Test skill/);
});

test("large SKILL.md requires a separate bounded ADVISORY.md",()=>{
  const full="# Full skill\n"+"Detailed design guidance. ".repeat(520);
  assert.ok(Buffer.byteLength(full)>6000);
  assert.throws(()=>inspectZipBase64(zip([["SKILL.md",full]])));
  const item=inspectZipBase64(zip([["SKILL.md",full],["ADVISORY.md","# Review-only summary"]]));
  assert.equal(item.skill,"# Review-only summary");
  assert.equal(item.files,2);
});

test("reject symlink archive member and compressed expansion bomb",()=>{
  const py=`import io,zipfile,stat,base64
b=io.BytesIO()
with zipfile.ZipFile(b,'w') as z:
 z.writestr('SKILL.md','Safe')
 info=zipfile.ZipInfo('scripts/escape.sh')
 info.create_system=3
 info.external_attr=(stat.S_IFLNK|0o777)<<16
 z.writestr(info,'/etc/passwd')
print(base64.b64encode(b.getvalue()).decode())`;
  const bad=execFileSync("python3",["-c",py]).toString().trim();
  assert.throws(()=>inspectZipBase64(bad));
  assert.throws(()=>inspectZipBase64(zip([["SKILL.md","Safe"],["big.txt","A".repeat(4_100_000)]])));
});

test("malicious and oversized packages are refused",()=>{
  for(const name of ["../SKILL.md","/SKILL.md","a/../../SKILL.md","c:\\SKILL.md","a//SKILL.md"]){
    assert.throws(()=>inspectZipBase64(zip([[name,"x"],["SKILL.md","Good"]])));
  }
  assert.throws(()=>inspectZipBase64(zip([["SKILL.md","ok"],["skill.md","collision"]])));
  assert.throws(()=>inspectZipBase64(zip([["README.md","no skill"]])));
  assert.throws(()=>inspectZipBase64("!!not-zip!!"));
});

test("import is quarantined and sealed; digest and revision approval are required",async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),"v79-package-"));
  try{
    const store=createPackageStore({directory:dir,secret:"test-package-registry-key-with-strong-separation-000001"});
    const archive=zip([["SKILL.md","# A safe test skill"],["scripts/probe.py","print('test')"]]);
    const item=await store.import({name:"test-package",archive},"owner");
    assert.equal(item.status,"quarantined");
    assert.equal(store.list().packages.length,1);
    await assert.rejects(store.approve(item.id,{sha256:"a".repeat(64),expectedRevision:1},"owner"),{status:409});
    await assert.rejects(store.configure(item.id,{hooks:[],schedules:["coo-daily"],expectedRevision:1},"owner"),{status:409});
    const approved=await store.approve(item.id,{sha256:item.sha256,expectedRevision:1},"owner");
    assert.equal(approved.status,"approved");
    assert.throws(()=>store.configure(item.id,{hooks:["exec-arbitrary"],schedules:["coo-daily"],expectedRevision:2},"owner"));
    const configured=await store.configure(item.id,{hooks:["package-integrity"],schedules:["coo-daily"],expectedRevision:2},"owner");
    assert.equal(configured.schedules[0],"coo-daily");
    const snapshot=store.scheduledSnapshot("coo-daily");
    assert.equal(snapshot.packages.length,1);
    assert.match(snapshot.packages[0].skill,/safe test/);
    assert.doesNotMatch(JSON.stringify(snapshot),/probe.py/);
    const revoked=await store.revoke(item.id,{expectedRevision:3},"owner");
    assert.equal(revoked.status,"quarantined");
    assert.equal(store.scheduledSnapshot("coo-daily").packages.length,0);
    await assert.rejects(store.revoke(item.id,{expectedRevision:4},"owner"));
    const file=path.join(dir,item.sha256+".zip");
    fs.appendFileSync(file,"tampering");
    assert.throws(()=>store.list(),/Package bytes changed/);
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
