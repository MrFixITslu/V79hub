import { useEffect, useRef, useState } from "react";
import { ArrowRight, Bot, ClipboardCheck, FileText, LayoutList, MessageSquare, Plus, Send, ShieldCheck, Wrench } from "lucide-react";
import { AgentApprovalInbox, type AgentDraftSuggestion } from "./AgentApprovalInbox";
import { SignedTiquetEvidencePanel } from "./SignedTiquetEvidencePanel";
import { ExecutiveReviewPanel } from "./ExecutiveReviewPanel";
import { WorkforceBriefingHistory } from "./WorkforceBriefingHistory";
import { MarketingProductionPanel } from "./MarketingProductionPanel";
import { WorkforceActionPanel } from "./WorkforceActionPanel";
import { OwnerCooWorkboardPanel, type CooWorkItemDraft } from "./OwnerCooWorkboardPanel";

type EvidenceMetric = { key: string; value: number };
type EvidenceRecord = {
  system: string; name: string; source: string;
  state: "available" | "stale" | "unavailable" | "unknown";
  reportedAt: string | null; connection: string; metrics: EvidenceMetric[];
};
type EvidenceLedger = { mode: "read-only"; collectedAt: string | null; records: EvidenceRecord[] };
type InvestigationFinding = {
  id: string; system: string; severity: "attention" | "watch" | "information";
  title: string; evidence: {source: string; metric: string; value: number; reportedAt: string};
  evidenceAttestation?: string;
  nextStep: string;
};
type InvestigationBrief = {
  mode: "read-only"; dataStatus: "available" | "partial" | "unavailable";
  findings: InvestigationFinding[];
  missing: {system: string; reason: "stale" | "unavailable" | "unknown"}[];
};
type Message = { role: "user" | "assistant"; text: string; specialist?: string; evidence?: EvidenceLedger; investigation?: InvestigationBrief };

const specialistPrompts = [
  { label: "Operations", prompt: "Review inventory, shipments and operational bottlenecks." },
  { label: "Growth", prompt: "Review marketing campaigns and website leads." },
  { label: "Finance", prompt: "Analyse FFPRO cashflow, revenue and expenses." },
  { label: "Customer Care", prompt: "Review Tiquet support tickets and customer issues." },
  { label: "Technology", prompt: "Review technology app health and reliability risks." },
  { label: "CombatZone", prompt: "Review CombatZone laser tag bookings and event readiness." },
];

type WorkspaceView = "agents" | "tasks" | "delivery" | "briefings" | "tools";
const workspaceViews = [
  { id: "agents", label: "Agents", icon: MessageSquare },
  { id: "tasks", label: "Tasks & approvals", icon: ClipboardCheck },
  { id: "delivery", label: "Delivery board", icon: LayoutList },
  { id: "briefings", label: "Briefings", icon: FileText },
  { id: "tools", label: "More tools", icon: Wrench },
] as const;

export function OwnerAssistant() {
  const [view, setView] = useState<WorkspaceView>("agents");
  const [visited, setVisited] = useState<Set<WorkspaceView>>(new Set(["agents"]));
  const composer = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const navigate = (next: WorkspaceView) => {
    setView(next);
    setVisited(current => new Set([...current, next]));
  };
  const prepareTask = (draft: CooWorkItemDraft) => {
    setPreparedCooWork(draft);
    navigate("tasks");
  };
  const preparePrompt = (prompt: string) => {
    setInput(prompt);
    composer.current?.focus();
  };
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "What would you like to get done? Ask for a review or recommendation here. Use Tasks & approvals to assign work to COO after your review.",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestedDraft, setSuggestedDraft] = useState<AgentDraftSuggestion | null>(null);
  const [preparedCooWork, setPreparedCooWork] = useState<CooWorkItemDraft | null>(null);

  useEffect(() => {
    if (view === "agents" && conversation.current) {
      conversation.current.scrollTop = conversation.current.scrollHeight;
    }
  }, [messages, busy, view]);

  const send = async () => {
    const message = input.trim();
    if (!message || busy) return;
    setMessages((items) => [...items, { role: "user", text: message }]);
    setInput("");
    setBusy(true);
    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await response.json();
      setMessages((items) => [
        ...items,
        { role: "assistant", text: response.ok ? data.output : data.error || "Assistant request failed.",
          specialist: response.ok ? data.specialist : undefined,
          evidence: response.ok && data.evidence?.mode === "read-only" ? data.evidence : undefined,
          investigation: response.ok && data.investigation?.mode === "read-only" ? data.investigation : undefined },
      ]);
    } catch {
      setMessages((items) => [...items, { role: "assistant", text: "Owner Assistant is unavailable." }]);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mx-auto w-full max-w-7xl p-3 sm:p-6 text-slate-100">
      <div className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-950 shadow-xl">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 bg-gradient-to-r from-cyan-950/60 to-slate-950 px-5 py-6 sm:px-7">
          <div>
            <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-cyan-300"><Bot className="h-4 w-4" aria-hidden="true" /> V79 Owner Assistant</p>
            <h1 className="text-2xl font-bold sm:text-3xl">Your owner workspace</h1>
            <p className="mt-2 text-sm text-slate-300">Plan with agents. Review decisions. Keep work moving.</p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-2 text-xs text-slate-300"><ShieldCheck className="h-4 w-4 text-cyan-300" aria-hidden="true" /> Owner access · MFA required</span>
            <button type="button" onClick={() => navigate("tasks")}
              className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-200 focus-visible:ring-2 focus-visible:ring-white">
              <Plus className="h-4 w-4" aria-hidden="true" /> New task
            </button>
          </div>
        </header>
        <nav aria-label="Owner workspace" className="flex gap-1 overflow-x-auto border-b border-slate-800 bg-slate-900/70 p-2 sm:px-5">
          {workspaceViews.map(({ id, label, icon: Icon }) => <button key={id} type="button" aria-current={view === id ? "page" : undefined}
            onClick={() => navigate(id)} aria-controls={"workspace-" + id}
            className={"inline-flex min-h-11 shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium focus-visible:ring-2 focus-visible:ring-cyan-300 sm:px-4 " +
              (view === id ? "bg-cyan-300/10 text-cyan-200 ring-1 ring-inset ring-cyan-500/30" : "text-slate-300 hover:bg-slate-800 hover:text-white")}>
            <Icon className="h-4 w-4" aria-hidden="true" />{label}
          </button>)}
        </nav>

        <section id="workspace-agents" aria-label="Agents" hidden={view !== "agents"}>
          <div className="grid lg:grid-cols-[250px_minmax(0,1fr)]">
            <aside className="border-b border-slate-800 bg-slate-900/40 p-4 lg:border-b-0 lg:border-r lg:p-5">
              <h2 className="font-semibold">Work with your team</h2>
              <p className="mt-2 hidden text-xs leading-5 text-slate-400 lg:block">Choose a starting point. Review the prompt, then send it to the assistant.</p>
              <div className="mt-3 grid grid-cols-2 gap-2 lg:mt-4 lg:grid-cols-1">
                {[
                  { name: "CEO · Direction", detail: "Priorities, tradeoffs and decisions", prompt: "Prepare a CEO review of the most important V79 priorities and decisions. Separate verified evidence from unknowns. Recommend what I should focus on next." },
                  { name: "COO · Delivery", detail: "Next steps and operational blockers", prompt: "Prepare a COO review of delivery blockers and operational next steps from available evidence. Suggest clear work items for my review; do not execute them." },
                ].map(agent => <button key={agent.name} type="button" disabled={busy} onClick={() => preparePrompt(agent.prompt)}
                  className="rounded-xl border border-slate-700 bg-slate-950 p-3 text-left hover:border-cyan-600 focus-visible:ring-2 focus-visible:ring-cyan-300 disabled:opacity-50">
                  <span className="block text-sm font-semibold text-cyan-200">{agent.name}</span><span className="mt-1 block text-xs text-slate-400">{agent.detail}</span>
                </button>)}
              </div>
              <div className="mt-5 hidden rounded-xl border border-slate-800 p-3 text-xs leading-5 text-slate-400 lg:block">
                <p className="font-medium text-slate-200">Ready to assign work?</p>
                <p className="mt-1">Create a task, review its exact scope, then approve it with MFA.</p>
                <button type="button" onClick={() => navigate("tasks")} className="mt-3 inline-flex min-h-10 items-center gap-2 text-cyan-200 hover:underline">Open tasks & approvals <ArrowRight className="h-3 w-3" aria-hidden="true" /></button>
              </div>
            </aside>
            <div className="min-w-0">
        <div className="px-5 py-3 border-b border-slate-800 bg-slate-900/50">
          <p className="text-xs text-slate-400 mb-2">Ask a specialist · drafts and recommendations only</p>
          <div className="flex flex-wrap gap-2">
            {specialistPrompts.map((specialist) => (
              <button
                type="button"
                key={specialist.label}
                disabled={busy}
                onClick={() => preparePrompt(specialist.prompt)}
                className="min-h-10 rounded-full border border-slate-700 px-3 py-1 text-xs text-cyan-200 hover:bg-slate-800 focus-visible:ring-2 focus-visible:ring-cyan-400 disabled:opacity-40"
              >
                {specialist.label}
              </button>
            ))}
          </div>
        </div>
        <div ref={conversation} role="log" aria-label="Agent conversation" aria-live="polite" aria-relevant="additions text" className="h-[48vh] min-h-72 overflow-y-auto p-4 space-y-4 bg-slate-950 sm:p-6">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`max-w-[94%] sm:max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 ${message.role === "user"
                ? "ml-auto bg-cyan-600 text-white"
                : "bg-slate-900 border border-slate-800 text-slate-200"}`}
            >
              {message.role === "assistant" && message.specialist && (
                <div className="text-xs text-cyan-300 mb-1 font-semibold">{message.specialist} · Read-only</div>
              )}
              <span className="whitespace-pre-wrap">{message.text}</span>
              {message.role === "user" && <button type="button" onClick={() => prepareTask({ sourceId: "chat", system: "hub", summary: message.text.trim().slice(0, 180), detail: message.text.trim().slice(0, 2000) })}
                className="mt-3 block min-h-10 rounded-lg border border-cyan-200/40 px-3 py-2 text-xs font-medium hover:bg-cyan-700 focus-visible:ring-2 focus-visible:ring-white">Prepare as task</button>}
              {message.role === "assistant" && message.investigation && (
                <details className="mt-3 rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2">
                  <summary className="cursor-pointer text-xs text-cyan-200">
                    Read-only operational investigation · {message.investigation.findings.length} evidence-backed observations
                  </summary>
                  <p className="mt-2 text-xs text-slate-400">
                    Only aggregate, fresh application data. Recommendations are not executed.
                    {message.investigation.dataStatus !== "available" ? " Some sources are missing or out of date." : ""}
                  </p>
                  <div className="mt-2 space-y-2">
                    {message.investigation.findings.map((finding) => (
                      <div key={finding.id} className="rounded-lg border border-slate-800 p-2 text-xs space-y-1">
                        <div className="flex flex-wrap justify-between gap-2">
                          <span className="font-medium">{finding.title}</span>
                          <span className={finding.severity === "attention" ? "text-amber-300" : "text-cyan-300"}>{finding.severity}</span>
                        </div>
                        <div className="text-slate-400">{finding.system}: {finding.evidence.metric} = {finding.evidence.value.toLocaleString()} · reported {new Date(finding.evidence.reportedAt).toLocaleString()}</div>
                        <div className="text-slate-200">Suggested review: {finding.nextStep}</div>
                        <button type="button" className="mt-2 rounded-md border border-cyan-700 px-2 py-1 text-xs text-cyan-200"
                          onClick={() => {
                            const targetSystem = finding.system === "tiquet" ? "tiquet"
                              : finding.system === "marketing" ? "marketing"
                              : finding.system === "pos" ? "pos"
                              : finding.system === "ffpro" ? "ffpro" : "hub";
                            const operation = targetSystem === "tiquet" ? "draft_support_reply"
                              : targetSystem === "marketing" ? "draft_marketing_campaign"
                              : targetSystem === "pos" ? "draft_inventory_review"
                              : targetSystem === "ffpro" ? "draft_finance_review" : "draft_operational_report";
                            setSuggestedDraft({
                              operation, targetSystem, summary: finding.title,
                              rationale: finding.nextStep,
                              // Never relabel evidence from a different app as Hub evidence.
                              evidenceRef: finding.evidenceAttestation && finding.id.startsWith(targetSystem + ":") ? finding.id : undefined,
                              evidenceAttestation: finding.evidenceAttestation && finding.id.startsWith(targetSystem + ":") ? finding.evidenceAttestation : undefined,
                              idempotencyKey: crypto.randomUUID(),
                            });
                            navigate("tools");
                          }}>Propose a review draft</button>
                      </div>
                    ))}
                    {message.investigation.findings.length === 0 && (
                      <p className="text-slate-400 text-xs">No configured aggregate review conditions met; this is not a guarantee that everything is healthy.</p>
                    )}
                    {message.investigation.missing.length > 0 && (
                      <p className="text-amber-200 text-xs">Missing or outdated: {message.investigation.missing.map(item => item.system + " (" + item.reason + ")").join(", ")}</p>
                    )}
                  </div>
                </details>
              )}
              {message.role === "assistant" && message.evidence && (
                <details className="mt-3 rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2">
                  <summary className="cursor-pointer text-xs text-cyan-200">
                    Verified data sources · {message.evidence.records.filter(record => record.state === "available").length} fresh, {message.evidence.records.filter(record => record.state !== "available").length} unverified or unavailable
                  </summary>
                  <p className="mt-2 text-xs text-slate-400">
                    Only approved aggregate metrics are shown. “Unknown” is not zero.
                  </p>
                  <div className="mt-2 space-y-2">
                    {message.evidence.records.map((record, index) => (
                      <div key={record.system + record.source + index} className="rounded-lg border border-slate-800 px-2 py-2 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium text-slate-200">{record.name}</span>
                          <span className={record.state === "available" ? "text-emerald-300" : "text-amber-300"}>{record.state}</span>
                        </div>
                        <div className="text-slate-500">{record.source.replaceAll("_", " ")} · connection: {record.connection}{record.reportedAt ? " · reported " + new Date(record.reportedAt).toLocaleString() : " · observation time unknown"}</div>
                        {record.metrics.length > 0 && (
                          <div className="mt-1 text-slate-300">{record.metrics.map(metric => metric.key + ": " + metric.value.toLocaleString()).join(" · ")}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          ))}
          {busy && <div className="text-xs text-slate-500">Working...</div>}
        </div>
        <div className="p-4 border-t border-slate-800 bg-slate-900/70 flex gap-3">
          <textarea
            ref={composer}
            aria-label="Message to your agents"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                send();
              }
            }}
            placeholder="Describe what you need help with…"
            className="min-w-0 flex-1 resize-none rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-sm outline-none focus:border-cyan-500"
            rows={2}
          />
          <button
            type="button"
            aria-label="Send message"
            onClick={send}
            disabled={busy || !input.trim()}
            className="self-end rounded-xl bg-cyan-500 text-slate-950 p-3 disabled:opacity-40"
          >
            <Send className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>
        <p className="px-4 pb-3 text-xs text-slate-400">Chat provides reviews and recommendations. Actions go through Tasks & approvals.</p>
            </div>
          </div>
        </section>

        <section id="workspace-tasks" aria-label="Tasks and approvals" hidden={view !== "tasks"}>
          {visited.has("tasks") && <WorkforceActionPanel embedded active={view === "tasks"} preparedTask={preparedCooWork} onPreparedTaskApplied={() => setPreparedCooWork(null)} />}
        </section>
        <section id="workspace-delivery" aria-label="Delivery board" hidden={view !== "delivery"}>
          {visited.has("delivery") && <><div className="px-5 pt-5"><h2 className="text-lg font-semibold">Engineering delivery board</h2><p className="mt-1 text-sm text-slate-400">Review GitHub work and prepare a task for COO. Preparing a task opens a draft for you to review.</p></div><OwnerCooWorkboardPanel embedded active={view === "delivery"} onPrepareTask={prepareTask} /></>}
        </section>
        <section id="workspace-briefings" aria-label="Briefings" hidden={view !== "briefings"}>
          {visited.has("briefings") && <><div className="px-5 pt-5"><h2 className="text-lg font-semibold">Reports & executive review</h2><p className="mt-1 text-sm text-slate-400">Read scheduled briefings or request an executive review of available evidence.</p></div><WorkforceBriefingHistory /><ExecutiveReviewPanel /></>}
        </section>
        <section id="workspace-tools" aria-label="More tools" hidden={view !== "tools"}>
          {visited.has("tools") && <><div className="px-5 py-5"><h2 className="text-lg font-semibold">Specialist tools</h2><p className="mt-1 text-sm text-slate-400">Planning proposals, Marketing production, and signed Tiquet evidence each keep their own review requirements.</p></div><AgentApprovalInbox suggested={suggestedDraft} onSuggestionHandled={() => setSuggestedDraft(null)} /><MarketingProductionPanel /><SignedTiquetEvidencePanel /></>}
        </section>
      </div>
    </div>
  );
}
