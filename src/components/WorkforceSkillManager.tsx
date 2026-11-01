import {useEffect, useState} from "react";
import {BookOpen, Check, FileUp, LockKeyhole, Plus, RotateCcw, ShieldCheck, UploadCloud} from "lucide-react";

type Worker = "ceo"|"coo"|"finance"|"strategy"|"marketing"|"customer-service"|"technical-security"|"sales";
const WORKERS:readonly {id:Worker;name:string}[] = [
  {id:"ceo",name:"CEO"}, {id:"coo",name:"COO"},
  {id:"finance",name:"Finance"}, {id:"strategy",name:"Strategy"},
  {id:"marketing",name:"Marketing"}, {id:"customer-service",name:"Customer Service"},
  {id:"technical-security",name:"Technical & Security"}, {id:"sales",name:"Sales"}
];
type Metadata = {
  id:string; name:string; revision:number; activeVersion:number|null;
  latestVersion:number; workers:Worker[]; status:"draft"|"active"|"paused"; updatedAt:string;
};
type Version = {version:number;content:string;sha256:string;createdAt:string;restoredFrom?:number};
type Detail = Metadata & {versions:Version[]};
type Audit = {at:string;action:string;id:string;revision:number;actor:string};
type Validation = {sha256:string;bytes:number;warnings:string[];result:"format-only";note:string};
const base = "/api/agent/skills";
const inputClass = "w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400";
const secondaryButton = "min-h-11 rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold hover:border-cyan-500 disabled:opacity-40";
const primaryButton = "min-h-11 rounded-xl bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-200 disabled:opacity-40";
async function callApi<T>(url:string, data?:Record<string, unknown>):Promise<T> {
  const response = await fetch(base + url, {
    method:data === undefined ? "GET" : "POST",
    credentials:"same-origin",
    headers:data === undefined ? {} : {"content-type":"application/json"},
    ...(data === undefined ? {} : {body:JSON.stringify(data)}),
  });
  let body:unknown;
  try { body = await response.json(); }
  catch { throw Error("Skill Manager returned an invalid response"); }
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? String(body.error) : "Request failed";
    throw Error(error);
  }
  return body as T;
}
export function WorkforceSkillManager() {
  const [catalog,setCatalog] = useState<Metadata[]>([]);
  const [audit,setAudit] = useState<Audit[]>([]);
  const [selected,setSelected] = useState<Detail|null>(null);
  const [name,setName] = useState("");
  const [content,setContent] = useState("");
  const [workers,setWorkers] = useState<Worker[]>([]);
  const [review,setReview] = useState<Validation|null>(null);
  const [acknowledged,setAcknowledged] = useState(false);
  const [restoreVersion,setRestoreVersion] = useState(1);
  const [message,setMessage] = useState("");
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const [loading,setLoading] = useState(true);

  const refresh = async () => {
    const response = await callApi<{skills:Metadata[];audit:Audit[]}>("/");
    setCatalog(response.skills);
    setAudit(response.audit);
  };
  const readDetail = async (id:string) => {
    const detail = await callApi<Detail>("/" + encodeURIComponent(id));
    setSelected(detail);
    setName(detail.name);
    setContent(detail.versions.at(-1)?.content || "");
    setWorkers(detail.workers);
    setRestoreVersion(detail.activeVersion || detail.latestVersion);
    setReview(null);
    setAcknowledged(false);
  };
  useEffect(() => {
    let active = true;
    callApi<{skills:Metadata[];audit:Audit[]}>("/")
      .then(data => { if(active) {setCatalog(data.skills);setAudit(data.audit);} })
      .catch(e => {if(active) setError(String(e.message || e));})
      .finally(() => {if(active) setLoading(false);});
    return () => {active=false;};
  }, []);
  const resetDraft = () => {
    setSelected(null);setName("");setContent("");setWorkers([]);
    setReview(null);setAcknowledged(false);setMessage("");setError("");
  };
  const act = async (run:()=>Promise<void>, success:string) => {
    if(busy) return;
    setBusy(true);setError("");setMessage("");
    try {await run();await refresh();setMessage(success);}
    catch(e) {setError(e instanceof Error ? e.message : "Skill Manager request failed");}
    finally {setBusy(false);}
  };
  const loadFile = async (file:File|undefined) => {
    if(!file)return;
    if(!/\.(md|txt)$/i.test(file.name)) {
      setError("Only Markdown or plain-text skills are accepted. ZIP files cannot be executed or imported.");
      return;
    }
    if(file.size > 6000) {setError("Skill exceeds the 6000-byte limit");return;}
    const text = await file.text();
    setContent(text);
    if(!name) setName(file.name.replace(/\.(md|txt)$/i,"").replace(/[-_]/g," "));
    setReview(null);setAcknowledged(false);setError("");
  };
  const validate = () => act(async () => {
    const result = await callApi<Validation>("/validate",{name,content});
    setReview(result);setAcknowledged(false);
  },"Format checked. Inspect the text and warnings before enabling it.");
  const save = () => act(async () => {
    if(selected) {
      const result = await callApi<{skill:Metadata}>("/"+selected.id+"/revise",{
        name, content, expectedRevision:selected.revision
      });
      await readDetail(result.skill.id);
    } else {
      const result = await callApi<{skill:Metadata}>("/",{name,content});
      await readDetail(result.skill.id);
    }
  },"Immutable draft version saved. Active workers are unchanged.");
  const apply = () => {
    if(!selected)return;
    act(async () => {
      await callApi("/"+selected.id+"/activate", {
        version:selected.latestVersion,workers,expectedRevision:selected.revision
      });
      await readDetail(selected.id);
    },"Worker assignment activated for local AI (when configured).");
  };
  const pause = () => {
    if(!selected)return;
    act(async () => {
      await callApi("/"+selected.id+"/pause",{expectedRevision:selected.revision});
      await readDetail(selected.id);
    },"Assignment paused. Existing built-in worker instructions remain available.");
  };
  const restore = () => {
    if(!selected)return;
    act(async () => {
      await callApi("/"+selected.id+"/restore",{
        version:restoreVersion,expectedRevision:selected.revision
      });
      await readDetail(selected.id);
    },"Historical content restored as a NEW draft; activation is still separate.");
  };
  const latest = selected?.versions.at(-1);
  const unchanged = !!selected && latest?.content === content && selected.name === name;
  const safeToActivate = selected && latest && unchanged && review?.sha256 === latest.sha256 &&
    acknowledged && workers.length > 0;
  return <div className="p-4 sm:p-7 text-slate-100 space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2 text-cyan-300 text-xs uppercase font-semibold tracking-widest"><BookOpen size={16}/> AI workforce</div>
        <h2 className="mt-1 text-2xl font-bold">Skill Library</h2>
        <p className="mt-1 text-sm text-slate-400">Create once, assign to workers, and activate only after review.</p>
      </div>
      <button type="button" onClick={resetDraft} className={primaryButton}><Plus size={16} className="inline mr-1"/>New skill</button>
    </div>
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300 rounded-xl border border-slate-800 bg-slate-900/50 p-3">
      <LockKeyhole size={16} className="text-cyan-300"/>
      Founder-only · built-in prompts remain pinned · activation requires fresh MFA · no automatic actions
    </div>
    {error && <p role="alert" className="rounded-xl border border-red-700/70 bg-red-950/40 p-3 text-sm text-red-200">{error}</p>}
    {message && <p role="status" className="rounded-xl border border-emerald-800 bg-emerald-950/40 p-3 text-sm text-emerald-200">{message}</p>}
    {loading ? <p className="text-sm text-slate-400">Loading library…</p> :
    <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="rounded-2xl border border-slate-800 bg-slate-900/40 p-3 self-start">
        <h3 className="mb-2 px-2 text-sm font-bold">Your skills ({catalog.length})</h3>
        <div className="space-y-1 max-h-[550px] overflow-y-auto">
          {catalog.map(item => <button type="button" key={item.id}
            onClick={() => act(async () => {await readDetail(item.id);},"")}
            className={"w-full rounded-xl border px-3 py-3 text-left text-sm " +
              (selected?.id===item.id?"border-cyan-500 bg-cyan-950/40":"border-transparent hover:bg-slate-800")}>
            <span className="block font-semibold break-words">{item.name}</span>
            <span className="text-xs text-slate-400">v{item.latestVersion} · {item.status} · {item.workers.length} worker(s)</span>
          </button>)}
          {!catalog.length && <p className="px-2 py-4 text-sm text-slate-400">No custom skills yet. Import a Markdown skill or paste your instructions.</p>}
        </div>
        <div className="mt-4 border-t border-slate-800 pt-3 px-2">
          <p className="font-semibold text-sm">Protected built-in skills</p>
          <p className="text-xs text-slate-400 mt-1">{WORKERS.map(w=>w.name).join(" · ")}</p>
          <p className="text-xs text-slate-500 mt-2">Add-on skills cannot replace or weaken these workers.</p>
        </div>
      </aside>
      <div className="rounded-2xl border border-slate-800 p-4 sm:p-5 space-y-5 min-w-0">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-bold">{selected ? "Edit custom skill" : "Create custom skill"}</h3>
          {selected && <span className="text-xs text-slate-400">Revision {selected.revision} · {selected.status}</span>}
        </div>
        <label className="block space-y-2">
          <span className="text-sm font-semibold">Skill name</span>
          <input className={inputClass} value={name} maxLength={80} onChange={e=>{setName(e.target.value);setReview(null);setAcknowledged(false);}} placeholder="e.g. Website Development"/>
        </label>
        <label className="block space-y-2">
          <span className="text-sm font-semibold">Instructions (Markdown)</span>
          <textarea className={inputClass+" min-h-[220px] font-mono"} value={content}
            onChange={e=>{setContent(e.target.value);setReview(null);setAcknowledged(false);}}
            placeholder="# Purpose&#10;Describe the role, review standards, safe workflow and expected output."
            aria-label="Skill instructions" />
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className={"inline-flex cursor-pointer items-center gap-2 "+secondaryButton}>
            <FileUp size={16}/> Import .md / .txt
            <input className="sr-only" type="file" accept=".md,.txt,text/plain,text/markdown"
              onChange={async e=>{await loadFile(e.target.files?.[0]);e.target.value="";}}/>
          </label>
          <span className="text-xs text-slate-400">{new TextEncoder().encode(content).length}/6000 bytes</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={busy||!name.trim()||!content.trim()} onClick={validate} className={secondaryButton}><ShieldCheck size={16} className="inline mr-2"/>Check draft</button>
          <button type="button" disabled={busy||!name.trim()||!content.trim()||unchanged} onClick={save} className={primaryButton}>{selected?"Save new version":"Save draft"}</button>
        </div>
        {review && <div className="border border-amber-800/60 rounded-xl p-3 text-sm space-y-2">
          <p className="font-semibold">Format check: {review.bytes} bytes</p>
          <p className="text-slate-400">This does not certify model behaviour or security. Review the full instructions yourself.</p>
          {review.warnings.map(w=><p key={w} className="text-amber-200">{w}</p>)}
          {!review.warnings.length && <p className="text-slate-300">No simple warning patterns detected.</p>}
          <label className="flex items-start gap-2 cursor-pointer">
            <input type="checkbox" className="mt-1" checked={acknowledged} onChange={e=>setAcknowledged(e.target.checked)}/>
            <span>I reviewed the instructions and understand they cannot grant permissions or approve actions.</span>
          </label>
        </div>}
        {selected && <div className="border-t border-slate-800 pt-5 space-y-3">
          <h3 className="font-bold">Assign to workers</h3>
          <p className="text-xs text-slate-400">Maximum 2 active custom skills per worker. These add guidance to the existing protected skill.</p>
          <div className="grid sm:grid-cols-2 gap-2">
            {WORKERS.map(worker=><label key={worker.id} className="flex gap-2 items-center rounded-xl border border-slate-800 px-3 py-2 text-sm cursor-pointer">
              <input type="checkbox" checked={workers.includes(worker.id)} onChange={e=>{
                setWorkers(old=>e.target.checked?[...old,worker.id]:old.filter(x=>x!==worker.id));
                setReview(null);setAcknowledged(false);
              }}/>
              {worker.name}
            </label>)}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy||!safeToActivate} onClick={apply} className={primaryButton}><Check size={16} className="inline mr-2"/>Activate exact version</button>
            <button type="button" disabled={busy||selected.status!=="active"} onClick={pause} className={secondaryButton}>Pause assignments</button>
          </div>
          <p className="text-xs text-slate-500">Activation or pausing requires a founder session with MFA verified within the last five minutes. Changes do not grant tools, spending or publishing access.</p>
          <div className="border-t border-slate-800 pt-4 space-y-3">
            <h3 className="font-bold">Version history and rollback</h3>
            <div className="flex flex-wrap gap-2">
              <select className={inputClass+" max-w-xs"} aria-label="Version to restore" value={restoreVersion}
                onChange={e=>setRestoreVersion(Number(e.target.value))}>
                {selected.versions.map(v=><option key={v.version} value={v.version}>Version {v.version} · {v.createdAt.slice(0,10)}</option>)}
              </select>
              <button type="button" onClick={restore} disabled={busy} className={secondaryButton}><RotateCcw size={16} className="inline mr-2"/>Restore as draft</button>
            </div>
            <p className="text-xs text-slate-400">Restoration creates a new immutable draft; workers keep their current active version until you explicitly activate another.</p>
          </div>
        </div>}
      </div>
    </div>}
    <details className="rounded-2xl border border-slate-800 px-4 py-3">
      <summary className="cursor-pointer text-sm font-semibold">Skill audit history</summary>
      <div className="mt-3 space-y-2 max-h-64 overflow-auto">
        {audit.map((item,i)=><div key={item.id+item.revision+i} className="text-xs text-slate-400">
          {item.at} · {item.action} · {catalog.find(x=>x.id===item.id)?.name||item.id} · rev {item.revision}
        </div>)}
        {!audit.length && <p className="text-xs text-slate-500">No changes recorded.</p>}
      </div>
    </details>
    <p className="text-xs text-slate-500">Text-only imports. No ZIP execution, external tool installation or automatic worker actions. Model evaluation and AI-assisted authoring remain separate acceptance work.</p>
  </div>;
}
