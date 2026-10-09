import { useEffect, useState } from "react";
import { ClipboardCheck, RotateCw } from "lucide-react";

export type AgentDraftSuggestion = {
  operation: "draft_support_reply" | "draft_marketing_campaign" | "draft_inventory_review" |
    "draft_finance_review" | "draft_operational_report";
  targetSystem: "tiquet" | "marketing" | "pos" | "ffpro" | "hub";
  summary: string;
  rationale: string;
  evidenceRef?: string;
  evidenceAttestation?: string;
  idempotencyKey: string;
};

type InboxProposal = {
  id: string; operation: string; targetSystem: string; summary: string; rationale: string;
  evidenceRef: string | null; evidenceVerification: "unverified" | "proxy_attested"; status: "pending" | "approved" | "rejected" | "expired";
  revision: number; createdAt: string; expiresAt: string; executionStatus: "disabled";
};

export function AgentApprovalInbox({ suggested, onSuggestionHandled }: {
  suggested: AgentDraftSuggestion | null;
  onSuggestionHandled: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [supervisedEnabled, setSupervisedEnabled] = useState(false);
  const [proposals, setProposals] = useState<InboxProposal[]>([]);
  const [totalProposals, setTotalProposals] = useState(0);
  const [nextOffset, setNextOffset] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = async () => {
    const response = await fetch("/api/agent/proposals", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error(response.status === 403 ? "Owner-only access required." : "Approval inbox is unavailable.");
    const data = await response.json();
    if (data.executionEnabled !== false || !Array.isArray(data.proposals)) throw new Error("Unexpected approval inbox mode.");
    setProposals(data.proposals);
    setSupervisedEnabled(data.supervisedMarketingDraftsEnabled === true);
    setNextOffset(data.proposals.length);
    setTotalProposals(Number.isSafeInteger(data.totalProposals) ? data.totalProposals : data.proposals.length);
  };

  useEffect(() => {
    if (!open) return;
    let active = true;
    fetch("/api/agent/proposals", { credentials: "same-origin", cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Approval inbox is unavailable.");
        return response.json();
      })
      .then(data => {
        if (!active) return;
        const next = Array.isArray(data.proposals) && data.executionEnabled === false ? data.proposals : [];
        setProposals(next);
        setSupervisedEnabled(data.supervisedMarketingDraftsEnabled === true);
        setNextOffset(next.length);
        setTotalProposals(Number.isSafeInteger(data.totalProposals) ? data.totalProposals : next.length);
      })
      .catch(() => { if (active) setError("Could not load proposals."); });
    return () => { active = false; };
  }, [open]);

  useEffect(() => {
    if (suggested) setOpen(true);
  }, [suggested]);

  const loadMore = async () => {
    if (busy || loadingMore || nextOffset >= totalProposals) return;
    setLoadingMore(true); setError("");
    try {
      const response = await fetch(`/api/agent/proposals?offset=${nextOffset}`, {
        credentials: "same-origin", cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load proposal history.");
      const body = await response.json();
      if (body.executionEnabled !== false || !Array.isArray(body.proposals) || body.offset !== nextOffset) {
        throw new Error("Unexpected approval history response.");
      }
      setProposals(current => {
        const ids = new Set(current.map(item => item.id));
        return [...current, ...body.proposals.filter((item: InboxProposal) => !ids.has(item.id))];
      });
      setNextOffset(nextOffset + body.proposals.length);
      setTotalProposals(Number.isSafeInteger(body.totalProposals) ? body.totalProposals : totalProposals);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load proposal history.");
    } finally { setLoadingMore(false); }
  };

  const queue = async () => {
    if (!suggested || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch("/api/agent/proposals", {
        method: "POST", credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(suggested),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Could not create proposal.");
      await refresh();
      setNotice("Draft added to the approval inbox. No action was executed.");
      onSuggestionHandled();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create proposal.");
    } finally { setBusy(false); }
  };

  const decide = async (proposal: InboxProposal, decision: "approve" | "reject") => {
    if (busy || proposal.status !== "pending") return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/agent/proposals/${encodeURIComponent(proposal.id)}/decision`, {
        method: "POST", credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expectedRevision: proposal.revision, decision }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Could not record decision.");
      await refresh();
      setNotice(decision === "approve" ? "Approved for planning only. Execution remains disabled." : "Proposal rejected; no action executed.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not record decision.");
    } finally { setBusy(false); }
  };

  const copyReviewedBrief = async (proposal: InboxProposal) => {
    if (busy || proposal.status !== "approved") return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/agent/proposals/${encodeURIComponent(proposal.id)}/handoff`,
        { credentials: "same-origin", cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not prepare reviewed brief.");
      if (data.executionEnabled !== false || data.handoff?.mode !== "manual-handoff" ||
          data.handoff?.externalDraftCreated !== false || typeof data.handoff?.text !== "string") {
        throw new Error("Unexpected handoff response.");
      }
      await navigator.clipboard.writeText(data.handoff.text);
      setNotice("Internal brief copied. Paste into " + proposal.targetSystem +
        " and review before use. No message sent or campaign published.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to copy reviewed brief.");
    } finally { setBusy(false); }
  };

  const createMarketingDraft = async (proposal: InboxProposal) => {
    if (busy || proposal.status !== "approved" || proposal.targetSystem !== "marketing") return;
    if (!window.confirm("Create an INTERNAL Marketing draft from this approved plan? This will not publish, schedule, or send anything.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(
        `/api/agent/proposals/${encodeURIComponent(proposal.id)}/marketing-draft`, {
          method: "POST", credentials: "same-origin",
          headers: { "content-type": "application/json" },
          body: "{}",
        });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Draft creation unavailable.");
      if (body.draftCreated !== true || body.executionEnabled !== false ||
          body.sent !== false || body.published !== false || body.scheduled !== false) {
        throw new Error("Unexpected supervised draft receipt.");
      }
      setNotice(body.duplicate
        ? "This proposal already has an internal Marketing draft. Nothing was sent or published."
        : "Internal Marketing draft created. Open Marketing > Growth > Internal Agent Drafts to review it.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create internal Marketing draft.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border-b border-slate-800 bg-slate-900/80 px-5 py-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <button type="button" className="flex items-center gap-2 font-semibold text-cyan-200"
          aria-expanded={open} onClick={() => setOpen(value => !value)}>
          <ClipboardCheck className="h-4 w-4" /> Owner approval inbox
          <span className="text-xs text-slate-400">({proposals.filter(p => p.status === "pending").length} pending)</span>
        </button>
        {open && <button type="button" disabled={busy} className="rounded border border-slate-600 p-1 text-slate-300"
          aria-label="Refresh approvals" onClick={() => { setError(""); refresh().catch(() => setError("Could not refresh proposals.")); }}>
          <RotateCw className="h-4 w-4" />
        </button>}
      </div>
      {open && <div className="mt-3 space-y-3">
        <p className="text-xs text-amber-200">Decision-only beta. Approvals are recorded for planning; no emails, payments, tickets, campaigns or other actions will execute.</p>
        {suggested && <div className="rounded-xl border border-cyan-700 bg-slate-950 p-3 space-y-2">
          <div className="text-xs text-slate-400">Suggested from read-only findings · {suggested.evidenceAttestation ? "short-lived Hub receipt attached" : "no attested evidence receipt"}</div>
          <p className="font-semibold text-slate-100">{suggested.summary}</p>
          <p className="text-xs text-slate-300">{suggested.rationale}</p>
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={queue}
              className="rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50">Add draft for review</button>
            <button type="button" disabled={busy} onClick={onSuggestionHandled}
              className="rounded-lg border border-slate-600 px-3 py-2 text-xs">Discard</button>
          </div>
        </div>}
        {notice && <p role="status" className="text-xs text-emerald-300">{notice}</p>}
        {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
        {totalProposals > proposals.length && <p className="text-xs text-amber-200">Showing {proposals.length} of {totalProposals} proposals. Pending proposals appear first.</p>}
        {proposals.length === 0 && <p className="text-xs text-slate-400">No proposals recorded yet.</p>}
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {proposals.map(proposal => (
            <article key={proposal.id} className="rounded-xl border border-slate-700 bg-slate-950 p-3">
              <div className="flex justify-between gap-3">
                <strong className="text-sm text-slate-100">{proposal.summary}</strong>
                <span className="text-xs text-cyan-300">{proposal.status}</span>
              </div>
              <p className="mt-1 text-xs text-slate-300">{proposal.rationale}</p>
              <p className="mt-1 text-xs text-amber-200">{proposal.evidenceVerification === "proxy_attested" ? "Matched an available read-only ledger metric during this owner session; source has not been independently reverified." : "Unverified evidence — review source manually."}</p>
              <p className="mt-1 text-xs text-slate-500">{proposal.targetSystem} · {proposal.operation.replaceAll("_", " ")} · Expires {new Date(proposal.expiresAt).toLocaleString()}</p>
              {proposal.status === "pending" &&
                <div className="mt-2 flex gap-2">
                  <button type="button" disabled={busy} onClick={() => decide(proposal, "approve")}
                    className="rounded-lg border border-emerald-700 px-3 py-1.5 text-xs text-emerald-200 disabled:opacity-40">Approve plan only</button>
                  <button type="button" disabled={busy} onClick={() => decide(proposal, "reject")}
                    className="rounded-lg border border-slate-600 px-3 py-1.5 text-xs disabled:opacity-40">Reject</button>
                </div>}
              {proposal.status === "approved" &&
                (proposal.targetSystem === "tiquet" || proposal.targetSystem === "marketing") &&
                <button type="button" disabled={busy} onClick={() => copyReviewedBrief(proposal)}
                  className="mt-2 rounded-lg border border-cyan-700 px-3 py-1.5 text-xs text-cyan-200 disabled:opacity-40">
                  Copy internal planning brief
                </button>}
              {supervisedEnabled && proposal.status === "approved" && proposal.targetSystem === "marketing" &&
                proposal.operation === "draft_marketing_campaign" &&
                <button type="button" disabled={busy}
                  onClick={() => createMarketingDraft(proposal)}
                  className="ml-2 mt-2 rounded-lg border border-emerald-700 px-3 py-1.5 text-xs text-emerald-200 disabled:opacity-40">
                  Create internal Marketing draft (confirm)
                </button>}
              <p className="mt-1 text-xs text-slate-500">Execution: disabled</p>
            </article>
          ))}
        </div>
        {nextOffset < totalProposals && <button type="button" disabled={busy || loadingMore}
          className="rounded border border-slate-600 px-3 py-1.5 text-xs text-cyan-200 disabled:opacity-40"
          onClick={loadMore}>{loadingMore ? "Loading history..." : "Load older proposals"}</button>}
      </div>}
    </section>
  );
}
