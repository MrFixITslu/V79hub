import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import {execFileSync} from "node:child_process";

// ZIPs contain untrusted files. Import never extracts or runs anything in Hub.
// Only a separately approved host sandbox may execute a selected entrypoint.
const MAX_ZIP = 1_500_000;
const SHA = /^[a-f0-9]{64}$/;
const KEY = /^[a-z0-9][a-z0-9._-]{2,63}$/;
const JOBS = Object.freeze(["ceo-daily", "coo-daily", "technology-review", "marketing-review"]);
const HOOKS = Object.freeze(["ui-static-review", "package-integrity"]);
const nowIso = () => new Date().toISOString();
const sha = b => crypto.createHash("sha256").update(b).digest("hex");
const fail = (message, status=400) => Object.assign(new Error(message), {status});
const exact = (x, fields) => x && typeof x==="object" && !Array.isArray(x) &&
  Object.keys(x).sort().join("|") === [...fields].sort().join("|");

// The Python inspector checks container entries and decompresses only within
// strict limits. It returns metadata and the skill text; it never writes files.
const INSPECT = String.raw`
import sys,io,json,zipfile,re,stat,hashlib,posixpath
data=sys.stdin.buffer.read(1500001)
if len(data)>1500000: raise ValueError("Archive too large")
if not zipfile.is_zipfile(io.BytesIO(data)): raise ValueError("Invalid ZIP")
with zipfile.ZipFile(io.BytesIO(data)) as z:
 infos=z.infolist()
 if len(infos)>120 or not infos: raise ValueError("Archive entry limit")
 seen=set(); total=0; found=[]
 for i in infos:
  name=i.filename
  if not isinstance(name,str) or len(name)>220 or not name or "\\\\" in name or "\\x00" in name or name.startswith("/") or re.match(r"^[A-Za-z]:",name): raise ValueError("Unsafe entry name")
  parts=name.rstrip("/").split("/")
  if any(p in ("",".","..") for p in parts) or any(not re.fullmatch(r"[A-Za-z0-9_.@-]{1,100}",p) for p in parts): raise ValueError("Unsafe archive path")
  k=name.rstrip("/").casefold()
  if k in seen: raise ValueError("Duplicate archive entries")
  seen.add(k)
  mode=(i.external_attr>>16)&0o170000
  if mode not in (0,stat.S_IFREG,stat.S_IFDIR) or i.flag_bits & 1: raise ValueError("Unsupported link, special file or encryption")
  if i.file_size>1300000 or i.compress_size>1500000: raise ValueError("Oversized entry")
  total+=i.file_size
  if total>4000000: raise ValueError("Expansion limit")
  if i.is_dir(): continue
  if name.lower().endswith((".zip",".tar",".gz",".7z",".exe",".dll",".so",".dylib",".pyc")): raise ValueError("Nested archive or native binary refused")
  with z.open(i) as f: raw=f.read(1300001)
  if len(raw)!=i.file_size: raise ValueError("ZIP size mismatch")
  found.append((name,raw))
 candidates=[(n,r) for n,r in found if n.endswith("/SKILL.md") or n=="SKILL.md"]
 if len(candidates)!=1: raise ValueError("Exactly one SKILL.md is required")
 n,b=candidates[0]
 if len(b)>64000 or not b.strip():raise ValueError("SKILL.md must be 1-64000 bytes")
 b.decode("utf-8")
 advisory=[r for name,r in found if name=="ADVISORY.md"]
 if len(advisory)>1:raise ValueError("Duplicate advisory")
 guidance=advisory[0] if advisory else b
 if len(guidance)>10000 or not guidance.strip():
  raise ValueError("ADVISORY.md of 1-10000 bytes required for large skills")
 skill=guidance.decode("utf-8")
 scripts=[{"path":n,"sha256":hashlib.sha256(raw).hexdigest(),"kind":n.rsplit(".",1)[-1]} for n,raw in found if n.startswith("scripts/") and n.endswith((".py",".js",".sh"))]
 print(json.dumps({"skill":skill,"skillPath":n,"files":len(found),"unpackedBytes":total,"entrypoints":scripts},ensure_ascii=True))
`;

export function inspectZipBase64(value) {
  if (typeof value !== "string" || !/^[A-Za-z0-9+/]+={0,2}$/.test(value) ||
      value.length > Math.ceil(MAX_ZIP/3)*4 || value.length%4!==0) throw fail("ZIP data is missing or too large");
  const bytes=Buffer.from(value,"base64");
  if (!bytes.length || bytes.length>MAX_ZIP || bytes.toString("base64")!==value) throw fail("Invalid ZIP encoding");
  let parsed;
  try {
    const output=execFileSync("python3",["-c",INSPECT],{
      input:bytes,timeout:5000,maxBuffer:30000,stdio:["pipe","pipe","pipe"]
    });
    parsed=JSON.parse(output.toString("utf8"));
  } catch { throw fail("ZIP rejected: unsafe, malformed, or exceeds import limits"); }
  return {bytes, hash:sha(bytes), ...parsed};
}

export function createPackageStore({directory,secret}) {
  if (!path.isAbsolute(directory) || typeof secret!=="string" || Buffer.byteLength(secret)<32)
    throw Error("Absolute package directory and independent registry secret required");
  const root=path.resolve(directory);
  const dataFile=path.join(root,"packages.json");
  const lockDir=dataFile+".lock";
  const sign=state=>crypto.createHmac("sha256",secret).update("v79-packages-v1\0"+JSON.stringify(state)).digest("hex");
  const fresh=()=>({schema:1,revision:0,packages:[],audit:[]});
  const load=()=>{
    let fd;
    try { fd=fs.openSync(dataFile,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW); }
    catch(e){ if(e.code==="ENOENT")return fresh();throw e; }
    try{
      if(fs.fstatSync(fd).size>1500000)throw fail("Package index oversized",503);
      const envelope=JSON.parse(fs.readFileSync(fd,"utf8"));
      if(!envelope?.state || !SHA.test(envelope.mac||"") || !Number.isSafeInteger(envelope.state.revision))throw fail("Invalid package index",503);
      const a=Buffer.from(sign(envelope.state),"hex"),b=Buffer.from(envelope.mac,"hex");
      if(!crypto.timingSafeEqual(a,b))throw fail("Package index integrity failed",503);
      const state=envelope.state;
      if(state.schema!==1 || !Array.isArray(state.packages) || !Array.isArray(state.audit) || state.packages.length>100)throw fail("Package index schema mismatch",503);
      return state;
    } catch(e){ if(e instanceof SyntaxError)throw fail("Package index unreadable",503);throw e; }
    finally{fs.closeSync(fd);}
  };
  const store=state=>{
    const tmp=path.join(root,".packages-"+crypto.randomBytes(10).toString("hex"));
    const fd=fs.openSync(tmp,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
    try{fs.writeFileSync(fd,JSON.stringify({state,mac:sign(state)}));fs.fsyncSync(fd);}
    finally{fs.closeSync(fd);}
    fs.renameSync(tmp,dataFile);
    const dirfd=fs.openSync(root,fs.constants.O_RDONLY);
    try{fs.fsyncSync(dirfd);}finally{fs.closeSync(dirfd);}
  };
  let queue=Promise.resolve();
  const mutate=callback=>{
    const pending=queue.catch(()=>{}).then(()=>{
      fs.mkdirSync(root,{recursive:true,mode:0o700});
      fs.mkdirSync(lockDir,{mode:0o700});
      try{
        const state=load();const result=callback(state);state.revision++;
        store(state);return result;
      } finally {fs.rmdirSync(lockDir);}
    });
    queue=pending;return pending;
  };
  const find=(state,id)=>{
    const item=state.packages.find(v=>v.id===id);
    if(!item)throw fail("Package not found",404);
    return item;
  };
  const publicItem=item=>({
    id:item.id,name:item.name,revision:item.revision,sha256:item.sha256,files:item.files,
    unpackedBytes:item.unpackedBytes,entrypoints:item.entrypoints,skillPath:item.skillPath,
    status:item.status,approvedAt:item.approvedAt,approvedBy:item.approvedBy,
    hooks:item.hooks,schedules:item.schedules,createdAt:item.createdAt,
    archived:item.archived === true,version:item.version||1,supersedesId:item.supersedesId||null,
    promotedAt:item.promotedAt||null,
  });
  const audit=(state,action,item,actor)=>{
    state.audit.push({at:nowIso(),action,id:item.id,actor,revision:item.revision,sha256:item.sha256});
    if(state.audit.length>500)state.audit=state.audit.slice(-500);
  };
  const verifiedArchive=item=>{
    const candidate=path.join(root,item.sha256+".zip");
    const fd=fs.openSync(candidate,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
    try{
      const s=fs.fstatSync(fd);
      if(!s.isFile() || s.size>MAX_ZIP || s.size<1)throw fail("Archive size mismatch",503);
      const bytes=fs.readFileSync(fd);
      if(sha(bytes)!==item.sha256)throw fail("Package bytes changed",503);
      return bytes;
    }finally{fs.closeSync(fd);}
  };
  return Object.freeze({
    list(){
      const state=load();
      for(const item of state.packages) verifiedArchive(item);
      return {packages:state.packages.map(publicItem),audit:state.audit.slice(-60).reverse(),runtime:"quarantined-until-approved"};
    },
    read(id){
      const item=find(load(),id);verifiedArchive(item);
      return {...publicItem(item),skill:item.skill};
    },
    download(id){
      const item=find(load(),id);return verifiedArchive(item);
    },
    import(input,actor){
      if(!exact(input,["name","archive"]))throw fail("Expected package name and base64 ZIP only");
      if(typeof input.name!=="string" || !KEY.test(input.name))throw fail("Package name must be 3-64 lowercase letters, digits, dashes or dots");
      const inspection=inspectZipBase64(input.archive);
      if(!inspection.skill || Buffer.byteLength(inspection.skill)>10000)throw fail("Invalid SKILL.md");
      return mutate(state=>{
        const same=state.packages.find(i=>i.sha256===inspection.hash);
        if(same)throw fail("Exact package already imported",409);
        if(state.packages.length>=100)throw fail("Package library is full",409);
        const file=path.join(root,inspection.hash+".zip");
        const fd=fs.openSync(file,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
        try{fs.writeFileSync(fd,inspection.bytes);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
        const item={id:"pkg-"+crypto.randomBytes(8).toString("hex"),name:input.name,sha256:inspection.hash,
          files:inspection.files,unpackedBytes:inspection.unpackedBytes,entrypoints:inspection.entrypoints,
          skillPath:inspection.skillPath,skill:inspection.skill,revision:1,status:"quarantined",createdAt:nowIso(),
          approvedAt:null,approvedBy:null,hooks:[],schedules:[]};
        state.packages.push(item);audit(state,"import-quarantine",item,actor);
        return publicItem(item);
      });
    },
    stageRevision(id,input,actor){
      if(!exact(input,["archive","expectedRevision"]))throw fail("Provide reviewed replacement ZIP and current revision");
      const inspection=inspectZipBase64(input.archive);
      if(!inspection.skill || Buffer.byteLength(inspection.skill)>10000)throw fail("Invalid replacement guidance");
      return mutate(state=>{
        const parent=find(state,id);verifiedArchive(parent);
        if(parent.archived)throw fail("Restore the original package before staging a revision",409);
        if(parent.status!=="approved" || (parent.supersedesId && !parent.promotedAt))throw fail("Only the current approved version may be replaced",409);
        if(parent.revision!==input.expectedRevision)throw fail("Stale package revision",409);
        if(state.packages.length>=100)throw fail("Package library is full",409);
        if(state.packages.some(p=>p.sha256===inspection.hash))throw fail("Package bytes already imported",409);
        if(state.packages.some(p=>p.supersedesId===id && !p.archived))throw fail("An unarchived replacement is already staged for this version",409);
        const version=(parent.version||1)+1;
        if(version>30)throw fail("Package version limit reached",409);
        const file=path.join(root,inspection.hash+".zip");
        const fd=fs.openSync(file,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
        try{fs.writeFileSync(fd,inspection.bytes);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
        const item={id:"pkg-"+crypto.randomBytes(8).toString("hex"),name:parent.name,
          sha256:inspection.hash,files:inspection.files,unpackedBytes:inspection.unpackedBytes,
          entrypoints:inspection.entrypoints,skillPath:inspection.skillPath,skill:inspection.skill,
          supersedesId:id,version,revision:1,status:"quarantined",createdAt:nowIso(),
          approvedAt:null,approvedBy:null,hooks:[],schedules:[],archived:false};
        state.packages.push(item);audit(state,"stage-replacement-quarantine",item,actor);
        return publicItem(item);
      });
    },
    approve(id,input,actor){
      if(!exact(input,["sha256","expectedRevision"]) || !SHA.test(input.sha256))throw fail("Invalid approval");
      return mutate(state=>{
        const item=find(state,id);
        if(item.revision!==input.expectedRevision || item.sha256!==input.sha256)throw fail("Package version/digest drift",409);
        verifiedArchive(item);
        if(item.archived)throw fail("Archived package must be restored first",409);
        if(item.status!=="quarantined")throw fail("Package is not quarantined",409);
        item.status="approved";item.approvedBy=actor;item.approvedAt=nowIso();item.revision++;
        audit(state,"approve-execution-eligibility",item,actor);
        return publicItem(item);
      });
    },
    revoke(id,input,actor){
      if(!exact(input,["expectedRevision"]))throw fail("Invalid revocation");
      return mutate(state=>{
        const item=find(state,id);verifiedArchive(item);
        if(item.revision!==input.expectedRevision)throw fail("Stale package revision",409);
        if(item.archived)throw fail("Archived package cannot be revoked again",409);
        if(item.status!=="approved")throw fail("Package is not approved",409);
        item.status="quarantined";item.approvedBy=null;item.approvedAt=null;
        item.hooks=[];item.schedules=[];item.revision++;
        audit(state,"revoke-and-disable",item,actor);
        return publicItem(item);
      });
    },
    promote(id,input,actor){
      if(!exact(input,["expectedRevision","expectedParentRevision"]))throw fail("Invalid promotion confirmation");
      return mutate(state=>{
        const item=find(state,id), parent=item.supersedesId?find(state,item.supersedesId):null;
        if(!parent)throw fail("Package is not a staged replacement",409);
        verifiedArchive(item);verifiedArchive(parent);
        if(item.revision!==input.expectedRevision || parent.revision!==input.expectedParentRevision)
          throw fail("Package version/revision drift",409);
        if(item.archived||parent.archived || item.status!=="approved" || parent.status!=="approved")
          throw fail("Both package versions must be approved and unarchived",409);
        if(item.promotedAt)throw fail("Replacement already promoted",409);
        if(item.hooks.length || item.schedules.length)throw fail("Staged revision has unreviewed assignments",409);
        for(const job of parent.schedules){
          const others=state.packages.filter(p=>p.id!==id && p.id!==parent.id && p.status==="approved" && !p.archived && p.schedules.includes(job));
          if(others.length>=2)throw fail("Scheduled agent already has two assigned skills: "+job,409);
        }
        item.hooks=[...parent.hooks];item.schedules=[...parent.schedules];item.promotedAt=nowIso();item.revision++;
        audit(state,"promote-reviewed-replacement",item,actor);
        parent.status="quarantined";parent.archived=true;parent.hooks=[];parent.schedules=[];
        parent.approvedBy=null;parent.approvedAt=null;parent.revision++;
        audit(state,"archive-superseded-version",parent,actor);
        return publicItem(item);
      });
    },
    archive(id,input,actor){
      if(!exact(input,["expectedRevision"]))throw fail("Invalid archive request");
      return mutate(state=>{
        const item=find(state,id);verifiedArchive(item);
        if(item.revision!==input.expectedRevision)throw fail("Stale package revision",409);
        if(item.archived)throw fail("Package already archived",409);
        item.archived=true;item.status="quarantined";item.approvedBy=null;item.approvedAt=null;
        item.hooks=[];item.schedules=[];item.revision++;
        audit(state,"archive-revoke-and-disable",item,actor);
        return publicItem(item);
      });
    },
    unarchive(id,input,actor){
      if(!exact(input,["expectedRevision"]))throw fail("Invalid restoration request");
      return mutate(state=>{
        const item=find(state,id);verifiedArchive(item);
        if(item.revision!==input.expectedRevision)throw fail("Stale package revision",409);
        if(!item.archived)throw fail("Package not archived",409);
        item.archived=false;item.status="quarantined";item.hooks=[];item.schedules=[];item.revision++;
        item.approvedBy=null;item.approvedAt=null;
        audit(state,"restore-archived-to-quarantine",item,actor);
        return publicItem(item);
      });
    },
    configure(id,input,actor){
      if(!exact(input,["hooks","schedules","expectedRevision"]))throw fail("Invalid schedule/hook configuration");
      if(!Array.isArray(input.hooks) || !Array.isArray(input.schedules) ||
          input.hooks.length>HOOKS.length || input.schedules.length>JOBS.length ||
          new Set(input.hooks).size!==input.hooks.length || new Set(input.schedules).size!==input.schedules.length ||
          !input.hooks.every(x=>HOOKS.includes(x)) || !input.schedules.every(x=>JOBS.includes(x)))
        throw fail("Unknown hook or scheduled agent");
      return mutate(state=>{
        const item=find(state,id);verifiedArchive(item);
        if(item.revision!==input.expectedRevision)throw fail("Stale package revision",409);
        if(item.archived)throw fail("Restore archived package before configuring",409);
        if(item.status!=="approved")throw fail("Approve the digest before assigning hooks or schedules",409);
        if(item.supersedesId && !item.promotedAt)throw fail("Promote the reviewed revision before changing scheduled assignments",409);
        for(const job of input.schedules){
          const others=state.packages.filter(x=>x.id!==id && x.status==="approved" && !x.archived && x.schedules.includes(job));
          if(others.length>=2)throw fail("Scheduled agent already has two assigned skills: "+job,409);
        }
        item.hooks=[...input.hooks];item.schedules=[...input.schedules];item.revision++;
        audit(state,"configure-approved-guidance",item,actor);
        return publicItem(item);
      });
    },
    scheduledSnapshot(job){
      if(!JOBS.includes(job))throw fail("Unknown scheduled job");
      const items=load().packages.filter(x=>x.status==="approved" && !x.archived && x.schedules.includes(job));
      for(const i of items)verifiedArchive(i);
      return {job,source:"owner-approved-guidance-only",packages:items.map(i=>({
        id:i.id,name:i.name,sha256:i.sha256,skill:i.skill
      }))};
    }
  });
}
