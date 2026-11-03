import {useEffect,useState} from "react";
import {Archive,CheckCircle2,FileUp,LockKeyhole,RefreshCcw,ShieldAlert} from "lucide-react";

type Hook="package-integrity"|"ui-static-review";
type Job="ceo-daily"|"coo-daily"|"technology-review"|"marketing-review";
type SkillPackage={
 id:string;name:string;revision:number;sha256:string;files:number;unpackedBytes:number;
 entrypoints:{path:string;sha256:string;kind:string}[];skillPath:string;
 status:"quarantined"|"approved";approvedAt:string|null;approvedBy:string|null;
 hooks:Hook[];schedules:Job[];createdAt:string;
};
const HOOKS:ReadonlyArray<{id:Hook;label:string}>=[
 {id:"package-integrity",label:"Verify package integrity on access"},
 {id:"ui-static-review",label:"UI static-review policy (requires developer hook runtime)"}
];
const JOBS:ReadonlyArray<{id:Job;label:string}>=[
 {id:"ceo-daily",label:"CEO daily"},
 {id:"coo-daily",label:"COO daily"},
 {id:"technology-review",label:"Technology review"},
 {id:"marketing-review",label:"Marketing review"}
];
const apiBase="/api/agent/skills/packages";
async function api<T>(path:string,body?:object):Promise<T>{
 const response=await fetch(apiBase+path,{
  credentials:"same-origin",method:body?"POST":"GET",
  headers:body?{"content-type":"application/json"}:{},
  ...(body?{body:JSON.stringify(body)}:{})
 });
 const payload=await response.json().catch(()=>({}));
 if(!response.ok)throw Error(typeof payload.error==="string"?payload.error:"Package request rejected");
 return payload as T;
}
async function encodeZip(file:File):Promise<string>{
 if(!/\.zip$/i.test(file.name))throw Error("Only .zip packages are supported");
 if(file.size<1 || file.size>1_350_000)throw Error("Upload a skill-only ZIP, at most 1.35 MB (not a full source repository)");
 return new Promise((resolve,reject)=>{
  const reader=new FileReader();
  reader.onerror=()=>reject(Error("Could not read ZIP"));
  reader.onload=()=>{
   const value=reader.result;
   if(typeof value!=="string" || !value.startsWith("data:") || !value.includes(","))
    return reject(Error("Invalid ZIP file"));
   resolve(value.slice(value.indexOf(",")+1));
  };
  reader.readAsDataURL(file);
 });
}
export function SkillPackageManager(){
 const [packages,setPackages]=useState<SkillPackage[]>([]);
 const [drafts,setDrafts]=useState<Record<string,{hooks:Hook[];schedules:Job[]}>>({});
 const [pending,setPending]=useState(false);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [loading,setLoading]=useState(true);
 const refresh=async()=>{
  const response=await api<{packages:SkillPackage[]}>("");
  setPackages(response.packages);
  setDrafts(Object.fromEntries(response.packages.map(p=>[p.id,{hooks:p.hooks,schedules:p.schedules}])));
 };
 useEffect(()=>{let current=true;
  api<{packages:SkillPackage[]}>("").then(value=>{
   if(!current)return;
   setPackages(value.packages);
   setDrafts(Object.fromEntries(value.packages.map(p=>[p.id,{hooks:p.hooks,schedules:p.schedules}])));
  }).catch(e=>{if(current)setError(e instanceof Error?e.message:"Package library unavailable");})
   .finally(()=>{if(current)setLoading(false);});
  return()=>{current=false;};
 },[]);
 const act=async(fn:()=>Promise<void>,message:string)=>{
  if(pending)return;
  setPending(true);setError("");setNotice("");
  try{await fn();await refresh();setNotice(message);}
  catch(e){setError(e instanceof Error?e.message:"Action rejected");}
  finally{setPending(false);}
 };
 const upload=(file:File|undefined)=>{
  if(!file)return;
  void act(async()=>{
   const archive=await encodeZip(file);
   const name=file.name.replace(/\.zip$/i,"").toLowerCase()
    .replace(/[^a-z0-9._-]/g,"-").replace(/-+/g,"-").slice(0,64);
   await api("/import",{name:name.length>=3?name:"skill-"+Date.now(),archive});
  },"ZIP inspected and quarantined. Review scripts and exact SHA-256 before fresh-MFA approval.");
 };
 const setChoice=(id:string,key:"hooks"|"schedules",value:Hook|Job,checked:boolean)=>{
  setDrafts(old=>{
   const current=old[id]||{hooks:[],schedules:[]};
   const list=new Set<string>(current[key]);
   if(checked)list.add(value);else list.delete(value);
   return {...old,[id]:{...current,[key]:[...list]}};
  });
 };
 return <section className="rounded-2xl border border-slate-700 p-4 sm:p-5 space-y-4" aria-label="Executable skill packages">
  <div className="flex flex-wrap items-center justify-between gap-3">
   <div><h3 className="text-lg font-bold flex items-center gap-2"><Archive size={20}/> ZIP skill packages</h3>
    <p className="text-sm text-slate-400 mt-1">Quarantined imports, digest-pinned approval, restricted hooks and scheduled advisory assignments.</p></div>
   <button type="button" disabled={pending} onClick={()=>void act(refresh,"Package list refreshed")}
    className="rounded-lg border border-slate-700 p-2" aria-label="Refresh packages"><RefreshCcw size={18}/></button>
  </div>
  <div className="rounded-lg bg-slate-900 border border-slate-700 p-3 text-sm flex items-start gap-2">
   <ShieldAlert size={18} className="shrink-0 mt-0.5 text-amber-300"/>
   <span>ZIP files are never executed inside Hub. Approval allows a separate restricted sandbox runner to use the exact reviewed archive. Scheduled assignments pass instructions only; they cannot invoke package scripts. Imported hooks cannot grant permissions or bypass MFA.</span>
  </div>
  <label className={"inline-flex cursor-pointer items-center gap-2 min-h-11 rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold "+(pending?"opacity-40":"")}>
   <FileUp size={17}/>Import skill-only .zip
   <input className="sr-only" type="file" accept=".zip,application/zip" disabled={pending}
    onChange={e=>{upload(e.target.files?.[0]);e.target.value="";}}/>
  </label>
  <p className="text-xs text-slate-400">Maximum upload 1.35 MB compressed; 120 entries and 4 MB expanded. Exactly one SKILL.md (max 64 KB); include ADVISORY.md (max 6 KB) when the full skill is larger. No symlinks, nested archives or native binaries.</p>
  {loading&&<p className="text-sm text-slate-400">Loading packages…</p>}
  {error&&<p className="text-sm rounded-lg border border-red-800 p-3 text-red-200" role="alert">{error}</p>}
  {notice&&<p className="text-sm rounded-lg border border-emerald-800 p-3 text-emerald-200" role="status">{notice}</p>}
  {!loading&&!packages.length&&<p className="text-sm text-slate-400">No ZIP skill packages imported yet.</p>}
  {packages.map(item=>{
   const current=drafts[item.id]||{hooks:item.hooks,schedules:item.schedules};
   const changed=JSON.stringify([...current.hooks].sort())!==JSON.stringify([...item.hooks].sort()) ||
    JSON.stringify([...current.schedules].sort())!==JSON.stringify([...item.schedules].sort());
   return <div className="rounded-xl border border-slate-700 p-4 space-y-3" key={item.id}>
    <div className="flex flex-wrap justify-between gap-2">
     <div><p className="font-semibold">{item.name}</p>
      <p className="text-xs text-slate-400">{item.files} files · {item.entrypoints.length} eligible sandbox entrypoints · revision {item.revision}</p></div>
     <span className={"text-xs rounded-full px-3 py-1 border self-start "+(item.status==="approved"?"text-emerald-200 border-emerald-700":"text-amber-200 border-amber-700")}>{item.status}</span>
    </div>
    <div className="space-y-1">
     <p className="text-xs text-slate-300">SHA-256 (check before approval)</p>
     <code className="block rounded-lg bg-slate-950 text-xs p-2 break-all select-all">{item.sha256}</code>
     {item.entrypoints.length>0&&<p className="text-xs text-slate-400">Code present: {item.entrypoints.map(p=>p.path).slice(0,6).join(", ")}{item.entrypoints.length>6?" …":""}</p>}
    </div>
    {item.status==="quarantined"
     ? <button type="button" disabled={pending} className="rounded-lg bg-amber-300 text-slate-950 font-semibold px-4 py-2 text-sm"
       onClick={()=>void act(async()=>{await api("/"+item.id+"/approve",{sha256:item.sha256,expectedRevision:item.revision});},
        "Package digest approved after fresh MFA. Execution still requires an isolated runner.")}>
       <LockKeyhole size={15} className="inline mr-1"/>Approve reviewed digest (fresh MFA)
       </button>
     : <div className="space-y-3 border-t border-slate-700 pt-3">
       <div><p className="text-xs font-semibold mb-2">Built-in hook policies</p>
        <div className="grid gap-2">{HOOKS.map(option=><label key={option.id} className="flex gap-2 text-sm">
         <input type="checkbox" checked={current.hooks.includes(option.id)} disabled={pending}
          onChange={e=>setChoice(item.id,"hooks",option.id,e.target.checked)}/>{option.label}</label>)}</div></div>
       <div><p className="text-xs font-semibold mb-2">Scheduled agents (instructions only)</p>
        <div className="grid sm:grid-cols-2 gap-2">{JOBS.map(option=><label key={option.id} className="flex gap-2 text-sm">
         <input type="checkbox" checked={current.schedules.includes(option.id)} disabled={pending}
          onChange={e=>setChoice(item.id,"schedules",option.id,e.target.checked)}/>{option.label}</label>)}</div></div>
       <button type="button" disabled={pending||!changed}
        className="rounded-lg bg-cyan-300 disabled:opacity-40 text-slate-950 font-semibold px-4 py-2 text-sm"
        onClick={()=>void act(async()=>{await api("/"+item.id+"/configure",{hooks:current.hooks,schedules:current.schedules,expectedRevision:item.revision});},
         "Approved hook and scheduled guidance policy saved with fresh MFA.")}>
        <CheckCircle2 size={15} className="inline mr-1"/>Save approved policies (fresh MFA)</button>
       <button type="button" disabled={pending}
        className="ml-2 rounded-lg border border-red-700 px-4 py-2 text-sm text-red-200"
        onClick={()=>void act(async()=>{await api("/"+item.id+"/revoke",{expectedRevision:item.revision});},
          "Package approval revoked. Hooks and scheduled guidance assignments cleared.")}>
        Revoke approval (fresh MFA)</button>
      </div>}
   </div>;
  })}
 </section>;
}
