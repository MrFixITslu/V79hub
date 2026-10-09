import { useState } from "react";
import { Bot, Send, ShieldCheck } from "lucide-react";
import { AgentApprovalInbox, type AgentDraftSuggestion } from "./AgentApprovalInbox";

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

export function OwnerAssistant() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Vision79 Owner Assistant is ready in read-only mode. Ask about Hub Admin, app health, operations, customers, finance, growth, or CombatZone.",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestedDraft, setSuggestedDraft] = useState<AgentDraftSuggestion | null>(null);

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
    <div className="p-6 max-w-5xl w-full mx-auto">
      <div className="rounded-3xl bg-slate-950 text-white border border-slate-800 overflow-hidden shadow-xl">
        <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/15 flex items-center justify-center">
              <Bot className="w-5 h-5 text-cyan-300" />
            </div>
            <div>
              <h1 className="font-bold">Vision79 Owner Assistant</h1>
              <p className="text-xs text-slate-400">Private business operations assistant</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-emerald-300">
            <ShieldCheck className="w-4 h-4" />
            Owner only · Read-only
          </div>
        </div>

        <AgentApprovalInbox suggested={suggestedDraft} onSuggestionHandled={() => setSuggestedDraft(null)} />
        <div className="px-5 py-3 border-b border-slate-800 bg-slate-900/50">
          <p className="text-xs text-slate-400 mb-2">Ask a specialist · drafts and recommendations only</p>
          <div className="flex flex-wrap gap-2">
            {specialistPrompts.map((specialist) => (
              <button
                type="button"
                key={specialist.label}
                disabled={busy}
                onClick={() => setInput(specialist.prompt)}
                className="rounded-full border border-slate-700 px-3 py-1 text-xs text-cyan-200 hover:bg-slate-800 focus-visible:ring-2 focus-visible:ring-cyan-400 disabled:opacity-40"
              >
                {specialist.label}
              </button>
            ))}
          </div>
        </div>
        <div className="h-[56vh] overflow-y-auto p-6 space-y-4 bg-slate-950">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 ${message.role === "user"
                ? "ml-auto bg-cyan-600 text-white"
                : "bg-slate-900 border border-slate-800 text-slate-200"}`}
            >
              {message.role === "assistant" && message.specialist && (
                <div className="text-xs text-cyan-300 mb-1 font-semibold">{message.specialist} · Read-only</div>
              )}
              <span className="whitespace-pre-wrap">{message.text}</span>
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
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
            placeholder="Ask your Vision79 assistant..."
            className="flex-1 resize-none rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-sm outline-none focus:border-cyan-500"
            rows={2}
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="self-end rounded-xl bg-cyan-500 text-slate-950 p-3 disabled:opacity-40"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
