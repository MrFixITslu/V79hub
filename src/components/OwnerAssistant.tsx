import { useState } from "react";
import { Bot, Send, ShieldCheck } from "lucide-react";

type Message = { role: "user" | "assistant"; text: string; specialist?: string };

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
        { role: "assistant", text: response.ok ? data.output : data.error || "Assistant request failed.", specialist: response.ok ? data.specialist : undefined },
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
