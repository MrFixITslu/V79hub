import { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronRight, ClipboardCheck, Plus, RefreshCcw, Search } from "lucide-react";
import type { CooWorkItemDraft } from "./OwnerCooWorkboardPanel";

type Job = { id: string; operation: string; system: string; summary: string;
  payload: { detail?: string; commitSha?: string; manifestSha256?: string; to?: string; subject?: string; body?: string; start?: string; end?: string; attendees?: string[]; eventId?: string; etag?: string; threadId?: string; messageId?: string; summary?: string };
  digest: string; revision: number; status: string; approval: { expiresAt: string } | null;
  result: { taskId?: string; receiptSha256?: string } | null };
type QueueFilter = "all" | "review" | "active" | "history";
const systems = ["hub", "tiquet", "marketing", "ffpro", "pos", "academy", "website", "games", "sentinel", "lasertag"];
const operations: Record<string, string> = { create_work_item: "Create work item", validate_release: "Test exact release", deploy_release: "Deploy tested release", rollback_release: "Roll back exact release" };
const googleOperations: Record<string,string> = {create_email_draft:'Save Gmail reply draft',create_calendar_event:'Create appointment',update_calendar_event:'Change appointment',delete_calendar_event:'Cancel appointment'};
const priority: Record<string, number> = { pending: 0, uncertain: 1, failed: 2, approved: 3, running: 4 };
function expired(job: Job) {
  return job.status === "approved" && !(Date.parse(job.approval?.expiresAt || "") > Date.now());
}
function statusLabel(job: Job) {
  if (expired(job)) return "Approval expired";
  if (job.status === "succeeded" && job.operation === "create_work_item") return "Work item created";
  return ({ pending: "Needs your approval", approved: "Approved · awaiting execution", running: "Running", succeeded: "Succeeded", failed: "Failed", uncertain: "Needs reconciliation", rejected: "Rejected", cancelled: "Cancelled" } as Record<string, string>)[job.status] || job.status;
}
function statusStyle(job: Job) {
  if (expired(job) || ["pending", "uncertain"].includes(job.status)) return "border-amber-600/50 bg-amber-400/10 text-amber-200";
  if (job.status === "failed") return "border-red-600/50 bg-red-400/10 text-red-200";
  if (job.status === "succeeded") return "border-emerald-600/50 bg-emerald-400/10 text-emerald-200";
  return "border-slate-600 bg-slate-800 text-slate-200";
}
async function request(suffix = "", body?: unknown) {
  const res = await fetch("/api/agent/work-actions" + suffix, { credentials: "same-origin", cache: "no-store",
    ...(body === undefined ? {} : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }) });
  const data = await res.json();
  if (!res.ok) throw new Error(res.status === 403 ? "Sign in with fresh owner MFA to view or change actions." : data.error || "Approved actions unavailable");
  return data;
}
export function WorkforceActionPanel({ preparedTask, onPreparedTaskApplied, embedded = false, active = true }: {
  preparedTask?: CooWorkItemDraft | null;
  onPreparedTaskApplied?: () => void;
  embedded?: boolean;
  active?: boolean;
} = {}) {
  const [open, setOpen] = useState(false), [enabled, setEnabled] = useState(false), [paused, setPaused] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false), [error, setError] = useState("");
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [notice, setNotice] = useState("");
  const [operation, setOperation] = useState("create_work_item"), [system, setSystem] = useState("hub");
  const [summary, setSummary] = useState(""), [detail, setDetail] = useState("");
  const [commitSha, setCommitSha] = useState(""), [manifestSha256, setManifestSha256] = useState("");
  const [filter, setFilter] = useState<QueueFilter>("all"), [search, setSearch] = useState("");
  const serial = useRef(0), mutation = useRef(false);
  const proposalRetry = useRef<{ signature: string; key: string } | null>(null);
  const shown = active && (embedded || open);
  const refresh = useCallback(async () => {
    const current = ++serial.current;
    setLoading(true);
    try {
      const data = await request();
      if (current !== serial.current) return;
      if (data.mode !== "owner-approved-actions" || !Array.isArray(data.jobs) || data.jobs.length > 200 ||
        !data.jobs.every((j: Job) => j && typeof j.id === "string" && typeof j.summary === "string" && typeof j.status === "string" &&
          typeof j.operation === "string" && typeof j.system === "string" && j.payload && typeof j.payload === "object" &&
          Number.isInteger(j.revision) && typeof j.digest === "string")) throw new Error("Unexpected action queue response");
      setEnabled(data.enabled === true); setPaused(data.paused === true); setJobs(data.jobs); setCheckedAt(new Date()); setError("");
    } catch (e) {
      if (current === serial.current) {
        setJobs([]); setEnabled(false); setCheckedAt(null);
        setError(e instanceof Error ? e.message : "Action queue unavailable");
      }
      throw e;
    } finally { if (current === serial.current) setLoading(false); }
  }, []);
  useEffect(() => {
    if (!shown) return;
    void refresh().catch(() => {});
    const timer = window.setInterval(() => {
      if (!mutation.current && !document.hidden) void refresh().catch(() => {});
    }, 15000);
    return () => { window.clearInterval(timer); serial.current++; };
  }, [shown, refresh]);
  useEffect(() => {
    if (!preparedTask || !systems.includes(preparedTask.system)) return;
    // UI prefill only. Queueing and exact owner approval remain separate user actions.
    setOpen(true); setOperation("create_work_item"); setSystem(preparedTask.system);
    setSummary(preparedTask.summary.slice(0, 180)); setDetail(preparedTask.detail.slice(0, 2000));
    setCommitSha(""); setManifestSha256("");
    setNotice("Draft prepared only. Review it and choose Queue for review; fresh owner MFA approval is still required.");
    onPreparedTaskApplied?.();
  }, [preparedTask, onPreparedTaskApplied]);
  const perform = async (fn: () => Promise<void>) => {
    if (mutation.current) return;
    mutation.current = true; serial.current++; setBusy(true); setError(""); setNotice("");
    try { await fn(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Action unavailable"); setJobs([]); setEnabled(false); setCheckedAt(null); }
    finally { mutation.current = false; setBusy(false); }
  };
  const queue = () => perform(async () => {
    // The server accepts one-line plain text. Review still binds the saved exact scope.
    const plain = (value: string) => value.trim().replace(/\s+/g, " ");
    const draft = { operation, system, summary: plain(summary), payload: operation === "create_work_item" ? { detail: plain(detail) } : { commitSha, manifestSha256 } };
    const signature = JSON.stringify(draft);
    if (proposalRetry.current?.signature !== signature) proposalRetry.current = { signature, key: "work-" + crypto.randomUUID() };
    await request("", { ...draft, idempotencyKey: proposalRetry.current.key });
    proposalRetry.current = null;
    setNotice("Queued for your review. Find it under Needs approval and review the exact scope.");
    setSummary(""); setDetail(""); setFilter("review"); setSearch("");
  });
  const decide = (job: Job, decision: "approve" | "reject") => {
    if (decision === "approve" && !window.confirm("Approve this exact " + job.operation.replaceAll("_", " ") + " for " + job.system + "?\n\n" + job.summary + "\n\n" + JSON.stringify(job.payload, null, 2))) return;
    void perform(async () => {
      await request("/" + encodeURIComponent(job.id) + "/decision", { decision, expectedRevision: job.revision, digest: job.digest });
      setNotice(decision === "approve" ? "Exact action approved. Track it in Active. An eligible worker must be running to execute it; refreshing this page does not execute actions." : "Action rejected.");
      setFilter(decision === "approve" ? "active" : "history");
    });
  };
  const counts = {
    all: jobs.length, review: jobs.filter(j => j.status === "pending").length,
    active: jobs.filter(j => ["approved", "running", "uncertain"].includes(j.status)).length,
    history: jobs.filter(j => !["pending", "approved", "running", "uncertain"].includes(j.status)).length,
  };
  const visibleJobs = jobs.filter(j => (filter === "all" || (filter === "review" ? j.status === "pending" : filter === "active" ? ["approved", "running", "uncertain"].includes(j.status) : !["pending", "approved", "running", "uncertain"].includes(j.status))) &&
    (j.summary + " " + j.system).toLowerCase().includes(search.trim().toLowerCase())).sort((a, b) => (priority[a.status] ?? 5) - (priority[b.status] ?? 5));
  const field = "mt-1.5 block min-h-11 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400";
  return <section aria-label="Owner-approved work" className="bg-slate-950 px-4 py-5 text-sm sm:px-6">
    {!embedded && <button type="button" className="min-h-11 font-semibold text-cyan-200" aria-expanded={open} onClick={() => setOpen(!open)}>V79 team · Approved actions</button>}
    {(embedded || open) && <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-xl font-semibold">Tasks & approvals</h2><p className="mt-1 text-sm text-slate-400">Give COO a clear task. You control exactly what is approved.</p></div>
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={busy || loading} onClick={() => void refresh().catch(() => {})} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 hover:bg-slate-800 disabled:opacity-50"><RefreshCcw className="h-4 w-4" aria-hidden="true" />{loading ? "Checking…" : "Refresh status"}</button>
          {enabled && <button type="button" disabled={busy} onClick={() => void perform(async () => { await request("/pause", { paused: !paused }); })} className="min-h-11 rounded-lg border border-amber-600/60 px-3 py-2 text-amber-200 disabled:opacity-50">{paused ? "Resume queue" : "Pause new execution"}</button>}
        </div>
      </div>
      <ol aria-label="Task workflow" className="grid gap-2 sm:grid-cols-3">
        {[{ title: "1. Describe the task", text: "Choose the app and define the outcome." }, { title: "2. Review & approve", text: "Check the exact scope. Fresh owner MFA is required." }, { title: "3. Track the result", text: "Approval, execution and delivery are separate stages." }].map(step => <li key={step.title} className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="font-medium text-slate-100">{step.title}</p><p className="mt-1 text-xs leading-5 text-slate-400">{step.text}</p></li>)}
      </ol>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
        <span>{!checkedAt ? loading ? "Checking action queue…" : "Queue status unverified" : !enabled ? "Actions disabled" : paused ? "Queue paused" : "Owner approval required"}</span>
        {checkedAt && <span>Checked {checkedAt.toLocaleTimeString()} · Refreshes every 15s while visible</span>}
      </div>
      {notice && <p role="status" className="rounded-lg border border-cyan-800 bg-cyan-950/40 p-3 text-sm text-cyan-100">{notice}</p>}
      {error && <p role="alert" className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-200">{error}</p>}
      {checkedAt && !enabled && <p className="rounded-xl border border-slate-700 p-4 text-slate-300">Task actions are disabled. You can review available history; an operator must enable actions before queueing work.</p>}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
        <form aria-label="New work item" onSubmit={e => { e.preventDefault(); if (enabled && checkedAt && !busy && summary.trim().length >= 8 && (operation !== "create_work_item" || detail.trim().length >= 8)) void queue(); }} className="rounded-2xl border border-slate-700 bg-slate-900/60 p-4 sm:p-5">
          <fieldset disabled={busy} className="min-w-0 space-y-4 disabled:opacity-60">
          <legend className="sr-only">Describe a work item for owner review</legend>
          <div><h3 className="flex items-center gap-2 text-base font-semibold"><Plus className="h-4 w-4 text-cyan-300" aria-hidden="true" />New work item</h3><p className="mt-1 text-xs leading-5 text-slate-400">Describe the assignment first. Queueing it later requires a verified owner session; opening this form changes nothing on the server.</p></div>
          {(!enabled || !checkedAt) && <p role="status" aria-live="polite" className="rounded-lg border border-amber-700/60 bg-amber-950/30 p-3 text-xs leading-5 text-amber-100">{loading ? "Checking owner-approved task access. You can prepare a draft; submitting is disabled until verification succeeds." : error ? "The owner action queue could not be verified. Drafting is available, but no task can be queued. Refresh status or sign in again with owner MFA." : checkedAt ? "Task actions are disabled on the server. You may prepare a draft, but no task can be queued." : "Waiting for verified owner action queue access. No task will be queued."}</p>}
          <label className="block text-sm font-medium">App<select value={system} onChange={e => setSystem(e.target.value)} className={field}>{systems.map(s => <option key={s}>{s}</option>)}</select></label>
          <label className="block text-sm font-medium">Task title<input value={summary} onChange={e => setSummary(e.target.value)} maxLength={180} minLength={8} required placeholder="e.g. Review Sentinel monitoring gaps" className={field} /></label>
          {operation === "create_work_item" ? <label className="block text-sm font-medium">Work to complete<textarea value={detail} onChange={e => setDetail(e.target.value)} maxLength={2000} minLength={8} required rows={5} placeholder="Describe the outcome, scope, and evidence you expect." className={field + " resize-y"} /></label> : <>
            <label className="block text-sm font-medium">Reviewed commit SHA<input required pattern="[a-f0-9]{40}" value={commitSha} onChange={e => setCommitSha(e.target.value)} maxLength={40} className={field + " font-mono"} /></label>
            <label className="block text-sm font-medium">Reviewed release manifest SHA-256<input required pattern="[a-f0-9]{64}" value={manifestSha256} onChange={e => setManifestSha256(e.target.value)} maxLength={64} className={field + " font-mono"} /></label>
          </>}
          <details className="rounded-lg border border-slate-700 p-3"><summary className="cursor-pointer text-xs text-slate-300">Advanced · release actions</summary><p className="mt-2 text-xs leading-5 text-amber-200">Use only with a reviewed release manifest and an eligible release worker. Task worker installation does not enable release execution.</p>
            <label className="mt-3 block text-xs">Action<select value={operation} onChange={e => setOperation(e.target.value)} className={field}>{Object.entries(operations).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          </details>
          {operation !== "create_work_item" && <p role="status" className="text-sm font-medium text-amber-200">You are queueing: {operations[operation]}. This is a release action.</p>}
          <button type="submit" disabled={!enabled || !checkedAt || busy || summary.trim().length < 8 || (operation === "create_work_item" && detail.trim().length < 8)} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-3 font-semibold text-slate-950 hover:bg-cyan-200 focus-visible:ring-2 focus-visible:ring-white disabled:opacity-40">Queue for review<ChevronRight className="h-4 w-4" aria-hidden="true" /></button>
          <p className="text-xs leading-5 text-slate-400">Queueing saves a proposal. You approve it separately below. Sign in with MFA again if your five-minute approval window has expired.</p>
          </fieldset>
        </form>
        <div className={enabled ? "min-w-0 space-y-3" : "min-w-0 space-y-3 xl:col-span-2"}>
          <div className="flex items-center gap-2"><ClipboardCheck className="h-4 w-4 text-cyan-300" aria-hidden="true" /><h3 className="text-base font-semibold">Action queue</h3></div>
          <div role="group" aria-label="Filter actions" className="flex flex-wrap gap-2">{([['all', 'All'], ['review', 'Needs approval'], ['active', 'Active'], ['history', 'History']] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={"min-h-10 rounded-lg border px-3 py-2 text-xs font-medium focus-visible:ring-2 focus-visible:ring-cyan-300 " + (filter === value ? "border-cyan-600 bg-cyan-300/10 text-cyan-200" : "border-slate-700 text-slate-300 hover:bg-slate-800")}>{label}{checkedAt ? ` (${counts[value]})` : ""}</button>)}</div>
          <label className="flex min-h-11 items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3"><Search className="h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" /><input type="search" aria-label="Search actions by title or app" value={search} onChange={e => setSearch(e.target.value)} placeholder="Find a task by title or app…" className="min-w-0 w-full bg-transparent py-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-cyan-300" /></label>
          {checkedAt && !visibleJobs.length && <div className="rounded-xl border border-dashed border-slate-700 p-6 text-center"><p className="font-medium text-slate-200">{jobs.length ? "No matching actions" : "No actions queued yet"}</p><p className="mt-2 text-sm text-slate-400">{jobs.length ? "Try another filter or search term." : "Describe a task, then queue it for your review."}</p></div>}
          <div className="space-y-3">{visibleJobs.map(job => <article key={job.id} aria-label={job.summary} className="space-y-3 rounded-xl border border-slate-700 bg-slate-900/50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2"><h4 className="min-w-0 break-words font-semibold">{job.summary}</h4><span className={"rounded-full border px-2.5 py-1 text-xs " + statusStyle(job)}>{statusLabel(job)}</span></div>
            <p className="text-xs text-slate-400">{job.system} · {operations[job.operation] || googleOperations[job.operation] || job.operation.replaceAll("_", " ")}</p>
            {job.payload.detail && <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-200">{job.payload.detail}</p>}
            {googleOperations[job.operation] ? <div className="space-y-2 rounded-lg border border-slate-700 p-3 text-sm">
              {job.payload.to&&<p>To: {job.payload.to}</p>}{job.payload.subject&&<p>Subject: {job.payload.subject}</p>}
              {job.payload.body&&<p className="whitespace-pre-wrap break-words">{job.payload.body}</p>}
              {job.payload.summary&&<p>{job.payload.summary}</p>}
              {job.payload.start&&job.payload.end&&<p>{new Intl.DateTimeFormat('en-LC',{timeZone:'America/St_Lucia',dateStyle:'medium',timeStyle:'short'}).format(new Date(job.payload.start))} – {new Intl.DateTimeFormat('en-LC',{timeZone:'America/St_Lucia',dateStyle:'medium',timeStyle:'short'}).format(new Date(job.payload.end))} · Saint Lucia</p>}
              {job.payload.attendees&&<p>Attendees: {job.payload.attendees.join(', ')||'Only you'}</p>}
              <p className="text-amber-200">{job.operation==='create_email_draft'?'Saves a Gmail draft. You review and send it.':'This action can notify appointment attendees.'}</p>
            </div> : job.operation !== "create_work_item" && <dl className="space-y-1 break-all text-xs text-slate-300"><dt className="text-slate-400">Reviewed commit</dt><dd className="font-mono">{job.payload.commitSha}</dd><dt className="pt-1 text-slate-400">Manifest SHA-256</dt><dd className="font-mono">{job.payload.manifestSha256}</dd></dl>}
            {job.status === "pending" && <p className="text-xs text-amber-200">Next: review the scope above, then approve or reject this exact action.</p>}
            {job.status === "approved" && <p className="text-xs text-amber-200">{expired(job) ? "Approval has expired. This action cannot execute; cancel it and queue a fresh review if still needed." : "Waiting for an eligible worker or manual execution. Approval expires " + new Date(job.approval!.expiresAt).toLocaleString() + "."}</p>}
            {job.status === "uncertain" && <p className="text-xs text-amber-200">Execution outcome is uncertain. An operator must reconcile the result before any retry.</p>}
            {job.status === "succeeded" && job.operation === "create_work_item" && <p className="flex items-start gap-2 text-xs leading-5 text-slate-300"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" aria-hidden="true" />Assigned to COO. Creation is verified; completion of the underlying work is not verified here.</p>}
            {enabled && job.status === "pending" && <div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={() => decide(job, "approve")} className="min-h-11 rounded-lg bg-emerald-300 px-3 py-2 font-semibold text-slate-950 disabled:opacity-50">Approve exact action</button><button type="button" disabled={busy} onClick={() => decide(job, "reject")} className="min-h-11 rounded-lg border border-slate-600 px-3 py-2 disabled:opacity-50">Reject</button></div>}
            {enabled && job.status === "approved" && job.operation === "create_work_item" && !expired(job) && <details className="rounded-lg border border-slate-700 p-3"><summary className="cursor-pointer text-xs text-slate-300">Manual execution option</summary><p className="mt-2 text-xs leading-5 text-slate-400">Use only if you intend to execute this approved creation manually. Leave this untouched when verifying the scheduled worker.</p><button type="button" disabled={busy || paused} onClick={() => void perform(async () => { await request("/" + encodeURIComponent(job.id) + "/execute", { expectedRevision: job.revision }); setNotice("Engineering work item created and assigned to COO. Underlying delivery remains separate."); })} className="mt-2 min-h-11 rounded-lg border border-emerald-700 px-3 py-2 text-emerald-200 disabled:opacity-50">Create approved work item</button></details>}
            {enabled && ["pending", "approved"].includes(job.status) && <button type="button" disabled={busy} onClick={() => void perform(async () => { await request("/" + encodeURIComponent(job.id) + "/cancel", { expectedRevision: job.revision }); setNotice("Action cancelled."); })} className="min-h-10 rounded-lg px-2 py-2 text-xs text-slate-400 underline underline-offset-4 hover:text-white disabled:opacity-50">Cancel action</button>}
            {job.result && <details className="text-xs text-slate-400"><summary className="cursor-pointer">Result reference</summary><p className="mt-2 break-all font-mono">{job.result.taskId ? "Work item: " + job.result.taskId : "Receipt: " + job.result.receiptSha256}</p></details>}
          </article>)}</div>
          {jobs.length === 200 && <p className="text-xs text-slate-400">Showing the latest 200 actions. Counts apply to this loaded history.</p>}
        </div>
      </div>
    </div>}
  </section>;
}

