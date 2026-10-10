import { useId, useState } from "react";

type TicketChoice = { id: string; title: string; status: string };

type Props = {
  proposalId: string;
  disabled?: boolean;
};

// Intentionally not mounted until the signed, MFA-verified Hub endpoints pass
// security testing and their independent feature flag is enabled.
export function SupervisedTiquetTicketPicker({ proposalId, disabled = false }: Props) {
  const inputId = useId();
  const [opened, setOpened] = useState(false);
  const [tickets, setTickets] = useState<TicketChoice[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadTickets = async () => {
    if (busy || disabled) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(
        `/api/agent/proposals/${encodeURIComponent(proposalId)}/tiquet-tickets`, {
          credentials: "same-origin", cache: "no-store",
        });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Ticket selection is unavailable.");
      if (data.executionEnabled !== false ||
          !Array.isArray(data.tickets) || data.tickets.length > 50 ||
          data.tickets.some((ticket: TicketChoice) =>
            !ticket || typeof ticket.id !== "string" ||
            !/^[A-Za-z0-9._:@-]{1,180}$/.test(ticket.id) ||
            typeof ticket.title !== "string" || ticket.title.length > 160 ||
            typeof ticket.status !== "string" || ticket.status.length > 48)) {
        throw new Error("Unexpected ticket list.");
      }
      setTickets(data.tickets);
      setSelectedJobId("");
      setOpened(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to list Tiquet tickets.");
    } finally { setBusy(false); }
  };

  const createDraft = async () => {
    if (busy || disabled || !tickets.some(ticket => ticket.id === selectedJobId)) return;
    const ticket = tickets.find(item => item.id === selectedJobId);
    if (!ticket) return;
    if (!window.confirm(
      `Create an INTERNAL, unsent Tiquet draft for "${ticket.title}"?\n\n` +
      "The draft remains private. No email, customer message, notification, or payment will be sent."
    )) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(
        `/api/agent/proposals/${encodeURIComponent(proposalId)}/tiquet-draft`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ jobId: selectedJobId }),
        });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Tiquet rejected the draft.");
      if (data.draftCreated !== true || data.jobId !== selectedJobId ||
          data.executionEnabled !== false || data.sent !== false ||
          data.scheduled !== false || data.published !== false ||
          typeof data.draftId !== "string" || !data.draftId) {
        throw new Error("Unexpected Tiquet draft receipt.");
      }
      setNotice(data.duplicate
        ? "This approved plan already has an internal draft. Nothing was sent."
        : "Internal Tiquet draft created. Open the selected ticket to review it before sending.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create Tiquet draft.");
    } finally { setBusy(false); }
  };

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-slate-700 p-2">
      <button type="button" disabled={disabled || busy} onClick={loadTickets}
        className="rounded-lg border border-cyan-700 px-3 py-1.5 text-xs text-cyan-200 disabled:opacity-40">
        {busy ? "Checking tickets..." : "Choose ticket for internal Tiquet draft"}
      </button>
      {opened && (
        <div className="space-y-2">
          <label htmlFor={inputId} className="block text-xs text-slate-300">
            Select an existing ticket in your organisation
          </label>
          <select id={inputId} value={selectedJobId}
            onChange={event => { setSelectedJobId(event.target.value); setNotice(""); }}
            disabled={busy || disabled}
            className="w-full rounded border border-slate-600 bg-slate-950 p-2 text-xs text-slate-100">
            <option value="">Choose a ticket...</option>
            {tickets.map(ticket => (
              <option value={ticket.id} key={ticket.id}>
                {ticket.title} ({ticket.status})
              </option>
            ))}
          </select>
          {tickets.length === 0 && <p className="text-xs text-amber-200">
            No eligible Tiquet tickets were returned.
          </p>}
          <p className="text-xs text-amber-200">
            Creating a draft requires another confirmation. Sending remains a separate manual action.
          </p>
          <button type="button" disabled={disabled || busy || !selectedJobId}
            onClick={createDraft}
            className="rounded-lg border border-emerald-700 px-3 py-1.5 text-xs text-emerald-200 disabled:opacity-40">
            Create internal draft (confirm)
          </button>
        </div>
      )}
      {notice && <p role="status" className="text-xs text-emerald-300">{notice}</p>}
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
    </div>
  );
}
