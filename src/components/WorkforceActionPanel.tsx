import { useEffect, useState } from "react";
import type { CooWorkItemDraft } from "./OwnerCooWorkboardPanel";

type Job = { id: string; operation: string; system: string; summary: string;
  payload: { detail?: string; commitSha?: string; manifestSha256?: string };
  digest: string; revision: number; status: string; approval: { expiresAt: string } | null;
  result: { taskId?: string; receiptSha256?: string } | null };
const systems = ["hub", "tiquet", "marketing", "ffpro", "pos", "academy", "website", "games", "sentinel", "lasertag"];
export function WorkforceActionPanel({ preparedTask, onPreparedTaskApplied }: {
  preparedTask?: CooWorkItemDraft | null;
  onPreparedTaskApplied?: () => void;
} = {}) {
  const [open, setOpen] = useState(false), [enabled, setEnabled] = useState(false), [paused, setPaused] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [operation, setOperation] = useState("create_work_item"), [system, setSystem] = useState("hub");
  const [summary, setSummary] = useState(""), [detail, setDetail] = useState("");
  const [commitSha, setCommitSha] = useState(""), [manifestSha256, setManifestSha256] = useState("");
  const request = async (suffix = "", body?: unknown) => {
    const res = await fetch("/api/agent/work-actions" + suffix, { credentials: "same-origin", cache: "no-store",
      ...(body === undefined ? {} : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Approved actions unavailable");
    return data;
  };
  const refresh = async () => {
    const data = await request();
    if (data.mode !== "owner-approved-actions" || !Array.isArray(data.jobs)) throw new Error("Unexpected action queue response");
    setEnabled(data.enabled === true); setPaused(data.paused === true); setJobs(data.jobs);
  };
  useEffect(() => { if (open) refresh().catch(e => setError(e.message)); }, [open]);
  useEffect(() => {
    if (!preparedTask) return;
    // UI prefill only. No create_work_item POST, approval or worker dispatch.
    if (!systems.includes(preparedTask.system)) return;
    setOpen(true);
    setOperation("create_work_item");
    setSystem(preparedTask.system);
    setSummary(preparedTask.summary.slice(0, 180));
    setDetail(preparedTask.detail.slice(0, 2000));
    setCommitSha(""); setManifestSha256("");
    setNotice("Draft prepared only. Review it and choose Queue for review; fresh owner MFA approval is still required.");
    onPreparedTaskApplied?.();
  }, [preparedTask, onPreparedTaskApplied]);
  const perform = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await fn(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "Action unavailable"); }
    finally { setBusy(false); }
  };
  const queue = () => perform(async () => {
    await request("", { operation, system, summary, payload: operation === "create_work_item" ? { detail } : { commitSha, manifestSha256 },
      idempotencyKey: "work-" + crypto.randomUUID() });
    setNotice("Queued for your review. Approval is still required."); setSummary(""); setDetail("");
  });
  const decide = (job: Job, decision: "approve" | "reject") => perform(async () => {
    if (decision === "approve" && !window.confirm("Approve this exact " + job.operation.replaceAll("_", " ") + " for " + job.system + "?\n\n" +
        job.summary + "\n\n" + JSON.stringify(job.payload, null, 2))) return;
    await request("/" + job.id + "/decision", { decision, expectedRevision: job.revision, digest: job.digest });
    setNotice(decision === "approve" ? "Exact action approved. Release workers can claim it; work items use the Create button." : "Action rejected.");
  });
  return <section className="border-b border-slate-800 bg-slate-900/80 px-5 py-3 text-sm">
    <button type="button" className="font-semibold text-emerald-200" aria-expanded={open} onClick={() => setOpen(!open)}>V79 team · Approved actions</button>
    {open && <div className="mt-3 space-y-3">
      <p className="text-xs text-slate-300">COO proposes and executes; CEO reviews; you approve the exact action. Release approvals expire after 15 minutes. Sign in with MFA again if the five-minute approval window has expired.</p>
      <div className="flex gap-2">
        <button disabled={busy} onClick={() => perform(async () => {})} className="rounded border border-slate-600 px-3 py-1">Refresh</button>
        {enabled && <button disabled={busy} onClick={() => perform(async () => { await request("/pause", { paused: !paused }); })}
          className="rounded border border-amber-600 px-3 py-1 text-amber-200">{paused ? "Resume queue" : "Pause new execution"}</button>}
        <span className="text-xs text-slate-400">{!enabled ? "Disabled" : paused ? "Paused" : "Owner approval required"}</span>
      </div>
      {notice && <p role="status" className="text-xs text-emerald-200">{notice}</p>}
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
      {enabled && <div className="space-y-2 rounded-lg border border-slate-700 p-3">
        <label className="block text-xs">Action<select value={operation} onChange={e => setOperation(e.target.value)} className="ml-2 rounded bg-slate-800 p-2">
          <option value="create_work_item">Create engineering work item</option><option value="validate_release">Test exact release</option>
          <option value="deploy_release">Deploy tested release</option><option value="rollback_release">Roll back exact release</option>
        </select></label>
        <label className="block text-xs">App<select value={system} onChange={e => setSystem(e.target.value)} className="ml-2 rounded bg-slate-800 p-2">{systems.map(s => <option key={s}>{s}</option>)}</select></label>
        <label className="block text-xs">Summary<input value={summary} onChange={e => setSummary(e.target.value)} maxLength={180} className="mt-1 block w-full rounded bg-slate-800 p-2" /></label>
        {operation === "create_work_item" ? <label className="block text-xs">Work to complete<textarea value={detail} onChange={e => setDetail(e.target.value)} maxLength={2000} className="mt-1 block w-full rounded bg-slate-800 p-2" /></label> : <>
          <label className="block text-xs">Reviewed commit SHA<input value={commitSha} onChange={e => setCommitSha(e.target.value)} maxLength={40} className="mt-1 block w-full rounded bg-slate-800 p-2 font-mono" /></label>
          <label className="block text-xs">Reviewed release manifest SHA-256<input value={manifestSha256} onChange={e => setManifestSha256(e.target.value)} maxLength={64} className="mt-1 block w-full rounded bg-slate-800 p-2 font-mono" /></label>
        </>}
        <button disabled={busy || summary.trim().length < 8} onClick={queue} className="rounded bg-emerald-400 px-3 py-2 font-semibold text-slate-950 disabled:opacity-40">Queue for review</button>
      </div>}
      <div className="max-h-96 space-y-2 overflow-y-auto">{jobs.map(job => <article key={job.id} className="space-y-2 rounded-lg border border-slate-700 bg-slate-950 p-3">
        <div className="flex justify-between gap-3"><strong>{job.summary}</strong><span className="text-xs text-emerald-200">{job.status}</span></div>
        <p className="text-xs text-slate-400">{job.system} · {job.operation.replaceAll("_", " ")}</p>
        <pre className="whitespace-pre-wrap break-all text-xs text-slate-300">{JSON.stringify(job.payload, null, 2)}</pre>
        {job.approval && <p className="text-xs text-amber-200">Approval expires {new Date(job.approval.expiresAt).toLocaleString()}</p>}
        {enabled && job.status === "pending" && <div className="flex gap-2"><button disabled={busy} onClick={() => decide(job, "approve")} className="rounded border border-emerald-600 px-3 py-1">Approve exact action</button>
          <button disabled={busy} onClick={() => decide(job, "reject")} className="rounded border border-slate-600 px-3 py-1">Reject</button></div>}
        {enabled && job.status === "approved" && job.operation === "create_work_item" && <button disabled={busy || paused} onClick={() => perform(async () => {
          await request("/" + job.id + "/execute", { expectedRevision: job.revision }); setNotice("Engineering work item created and assigned to COO.");
        })} className="rounded border border-emerald-600 px-3 py-1">Create approved work item</button>}
        {enabled && ["pending", "approved"].includes(job.status) && <button disabled={busy} onClick={() => perform(async () => {
          await request("/" + job.id + "/cancel", { expectedRevision: job.revision }); setNotice("Action cancelled.");
        })} className="ml-2 rounded border border-slate-600 px-3 py-1">Cancel</button>}
        {job.result && <p className="break-all text-xs text-slate-400">{job.result.taskId ? "Work item: " + job.result.taskId : "Receipt: " + job.result.receiptSha256}</p>}
      </article>)}</div>
    </div>}
  </section>;
}
