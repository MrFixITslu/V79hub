import { useEffect, useState } from "react";
import { ArrowRight, ClipboardCheck, RefreshCw } from "lucide-react";
import { WorkforceBriefingHistory } from "./WorkforceBriefingHistory";

type Action = { id: string; summary: string; system: string; status: string; approval?: { expiresAt?: string } | null };
type Snapshot = { jobs: Action[]; enabled: boolean; paused: boolean; checkedAt: Date };
const statuses = ["pending", "approved", "running", "succeeded", "failed", "uncertain", "rejected", "cancelled"];
const needsReview = (j: Action) => ["failed", "uncertain"].includes(j.status) ||
  (j.status === "approved" && !(Date.parse(j.approval?.expiresAt || "") > Date.now()));

// Reads the existing queue. Authorization and execution remain in their existing panels.
export function OwnerToday({ active, onTasks, onDelivery, onAsk }: {
  active: boolean; onTasks: () => void; onDelivery: () => void; onAsk: () => void;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setSnapshot(null); setError(""); setBusy(true);
    void (async () => {
      try {
        const res = await fetch("/api/agent/work-actions", { credentials: "same-origin", cache: "no-store", signal: controller.signal });
        if (!res.ok) throw Error(res.status === 401 || res.status === 403
          ? "An MFA-verified owner session is required to view actions." : "Action summary is unavailable. Open Tasks & approvals to review access or try again.");
        const data = await res.json();
        if (data?.mode !== "owner-approved-actions" || typeof data.enabled !== "boolean" || typeof data.paused !== "boolean" ||
          !Array.isArray(data.jobs) || data.jobs.length > 200 || !data.jobs.every((j: Action) => j &&
            typeof j.id === "string" && typeof j.summary === "string" && typeof j.system === "string" && statuses.includes(j.status))) {
          throw Error("The action summary could not be verified.");
        }
        if (!controller.signal.aborted) setSnapshot({ jobs: data.jobs, enabled: data.enabled, paused: data.paused, checkedAt: new Date() });
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Action summary unavailable.");
      } finally { if (!controller.signal.aborted) setBusy(false); }
    })();
    return () => controller.abort();
  }, [active, revision]);
  const jobs = snapshot?.jobs || [];
  const attention = jobs.filter(j => j.status === "pending" || needsReview(j));
  const metrics = [
    { label: "Awaiting your approval", count: jobs.filter(j => j.status === "pending").length, detail: "Review the exact action before approving." },
    { label: "Approved or running", count: jobs.filter(j => ["approved", "running"].includes(j.status) && !needsReview(j)).length, detail: "Execution and completion remain separate." },
    { label: "Needs follow-up", count: jobs.filter(needsReview).length, detail: "Failed, uncertain or expired approvals." },
  ];
  return <div className="v79-today">
    <div className="v79-area-heading"><div><p className="v79-eyebrow">YOUR DAILY FOCUS</p><h2>Decisions first. Progress next.</h2><p>A read-only snapshot of your action queue.</p></div>
      <button className="v79-secondary" disabled={busy} onClick={() => setRevision(v => v + 1)}><RefreshCw size={16} />{busy ? "Loading…" : "Refresh summary"}</button></div>
    {error && <p role="alert" className="v79-notice">{error}</p>}
    {snapshot && (!snapshot.enabled || snapshot.paused) && <p className="v79-notice">{!snapshot.enabled ? "Workforce actions are disabled." : "Workforce execution is paused."} Viewing this page does not enable or resume execution.</p>}
    <div className="v79-owner-metrics">{metrics.map(m => <button key={m.label} className="v79-owner-metric" onClick={onTasks}>
      <span>{m.label}</span><strong>{snapshot ? m.count : busy ? "…" : "—"}</strong><p>{m.detail}</p><span className="v79-inline-link">Review actions <ArrowRight size={15} /></span>
    </button>)}</div>
    <div className="v79-owner-focus-grid">
      <section className="v79-area-card"><div className="v79-area-heading"><h2>Your next decisions</h2><ClipboardCheck size={20} /></div>
        {!snapshot ? <p>{busy ? "Loading your action queue…" : "No verified action summary is available."}</p> : attention.length ? <ul className="v79-decision-list">{attention.slice(0, 4).map(j => <li key={j.id}><button onClick={onTasks}><span><strong>{j.summary}</strong><small>{j.system} · {j.status === "pending" ? "Awaiting approval" : j.status === "approved" ? "Approval expired" : j.status === "uncertain" ? "Needs reconciliation" : "Failed"}</small></span><ArrowRight size={16} /></button></li>)}</ul> : <p>No pending approvals or follow-up items in this queue snapshot. Delivery completion is tracked separately.</p>}
        <button className="v79-text-button" onClick={onTasks}>Open tasks & approvals <ArrowRight size={16} /></button>
      </section>
      <aside className="v79-area-card v79-guidance"><p className="v79-eyebrow">FROM IDEA TO ADVANTAGE</p><h2>Turn a question into a clear next step.</h2><p>Ask for a review, check the evidence, then prepare a task for approval.</p>
        <button className="v79-solid-button" onClick={onAsk}>Ask the assistant <ArrowRight size={16} /></button>
        <button className="v79-text-button" onClick={onDelivery}>Review delivery evidence <ArrowRight size={16} /></button>
      </aside>
    </div>
    <p className="v79-source-note">{snapshot ? `Queue retrieved ${snapshot.checkedAt.toLocaleString()}. Refresh to check for changes.` : "Task counts are shown only after the queue is verified."} Planning proposals have a separate review inbox in Tasks & approvals.</p>
    <div className="v79-legacy-panel v79-briefing-card"><WorkforceBriefingHistory /></div>
  </div>;
}
