import { useCallback, useEffect, useState } from "react";
import { CreditCard, RefreshCw, ShieldCheck } from "lucide-react";

interface ManualOrder {
  id: string;
  organizationId: string;
  organization: string;
  description: string;
  amount: number;
  currency: string;
  status: "pending" | "paid" | "failed" | "cancelled";
  createdAt: string;
  paidAt: string | null;
  bankReference: string | null;
  verifiedByUserId: string | null;
}

export function PlatformManualPaymentsAdmin() {
  const [orders, setOrders] = useState<ManualOrder[]>([]);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [reference, setReference] = useState("");
  const [evidence, setEvidence] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [bankVerified, setBankVerified] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const response = await fetch("/api/admin/billing/manual/orders", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load bank-transfer requests.");
    setOrders(data.orders || []);
  }, []);
  useEffect(() => {
    void load().catch(err => setError(err instanceof Error ? err.message : "Could not load payments."));
  }, [load]);
  const selected = orders.find(order => order.id === selectedId && order.status === "pending");
  async function reject() {
    if (!selected || evidence.trim().length < 10) { setError("Enter a rejection reason of at least 10 characters."); return; }
    if (!window.confirm("Reject this pending invoice? This does not affect existing customer access.")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await fetch(`/api/admin/billing/manual/orders/${encodeURIComponent(selected.id)}/reject`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: evidence }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not reject invoice.");
      setMessage("Pending manual invoice marked rejected. No paid access was granted.");
      setSelectedId(""); setEvidence(""); setReference(""); setConfirmation(""); setBankVerified(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rejection failed.");
    } finally { setBusy(false); }
  }
  async function verify() {
    if (!selected) return;
    if (confirmation !== `CONFIRM ${selected.id}`) { setError("Enter the full confirmation phrase."); return; }
    if (!window.confirm("Have you independently verified received funds in the bank statement? This action grants paid access.")) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`/api/admin/billing/manual/orders/${encodeURIComponent(selected.id)}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bankReference: reference, evidenceNote: evidence,
          receivedAmount: selected.amount, bankStatementVerified: bankVerified, confirmation }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error + (data.code ? ` (${data.code})` : ""));
      setMessage(`Bank receipt confirmed for ${selected.organization}. Paid through ${new Date(data.paidThroughAt).toLocaleDateString()}.`);
      setSelectedId("");
      setReference("");
      setEvidence("");
      setConfirmation("");
      setBankVerified(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment confirmation failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2"><CreditCard className="w-5 h-5"/>Manual bank-transfer reconciliation</h2>
          <p className="mt-1 text-xs text-slate-600">Only confirm funds already received and independently verified in the bank statement. Customer payment claims never grant access. For reconciliation, complete a fresh administrator MFA sign-in within the past 15 minutes.</p>
        </div>
        <button type="button" onClick={() => void load().catch(err => setError(String(err)))} className="p-2 border rounded-lg" aria-label="Refresh manual payments"><RefreshCw className="w-4 h-4"/></button>
      </div>
      {message && <p role="status" className="text-sm text-emerald-700">{message}</p>}
      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
      <div className="grid md:grid-cols-[1fr_1fr] gap-5">
        <div className="max-h-[360px] overflow-y-auto divide-y">
          {orders.length === 0 && <p className="p-4 text-sm text-slate-500">No manual payment requests.</p>}
          {orders.map(order => (
            <button type="button" key={order.id} onClick={() => { setSelectedId(order.status === "pending" ? order.id : ""); setConfirmation(""); setReference(""); setEvidence(""); setBankVerified(false); setError(""); }}
              className={`w-full text-left p-3 hover:bg-slate-50 ${selectedId === order.id ? "bg-cyan-50" : ""}`}>
              <span className="block font-semibold text-sm text-slate-900">{order.organization}</span>
              <span className="block text-xs text-slate-600">{order.currency} {order.amount.toFixed(2)} · {order.status} · {new Date(order.createdAt).toLocaleDateString()}</span>
              <span className="block text-[10px] text-slate-500 break-all">{order.id}</span>
            </button>
          ))}
        </div>
        <div className="space-y-3">
          {selected ? (
            <>
              <div className="text-sm font-semibold text-slate-900">{selected.organization}: EC$ {selected.amount.toFixed(2)}</div>
              <p className="text-xs text-slate-600">Check the receiving bank account, exact incoming amount, transaction reference and applicable customer invoice. Do not enter bank account numbers or customer passwords.</p>
              <label className="block text-xs font-semibold text-slate-700">Verified bank transaction reference
                <input value={reference} onChange={e => setReference(e.target.value)} maxLength={100} className="admin-input mt-1" placeholder="Bank reference from received funds"/>
              </label>
              <label className="block text-xs font-semibold text-slate-700">Independent verification evidence (minimum 20 characters)
                <textarea rows={3} value={evidence} onChange={e => setEvidence(e.target.value)} maxLength={500} className="admin-input mt-1" placeholder="Verified bank statement date, payment source and invoice reconciliation; omit sensitive account numbers."/>
              </label>
              <label className="flex items-start gap-2 text-xs text-slate-700">
                <input type="checkbox" checked={bankVerified} onChange={e => setBankVerified(e.target.checked)} className="mt-0.5"/>
                I independently confirmed the funds were received and cleared in the V79 Digital bank statement, not merely claimed by the customer.
              </label>
              <label className="block text-xs font-semibold text-slate-700">Type CONFIRM followed by the exact order ID
                <input value={confirmation} onChange={e => setConfirmation(e.target.value)} className="admin-input mt-1" placeholder={`CONFIRM ${selected.id}`}/>
              </label>
              <button type="button" disabled={busy || !bankVerified || confirmation !== `CONFIRM ${selected.id}` || evidence.trim().length < 20 || reference.trim().length < 6}
                onClick={() => void verify()}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">
                <ShieldCheck className="w-4 h-4"/> {busy ? "Verifying…" : "Confirm received funds"}
              </button>
              <button type="button" disabled={busy || evidence.trim().length < 10}
                onClick={() => void reject()}
                className="ml-2 rounded-lg border border-rose-400 px-4 py-2 text-xs font-bold text-rose-700 disabled:opacity-40">
                Reject pending invoice
              </button>
            </>
          ) : <p className="text-sm text-slate-500">Select a pending invoice to reconcile. Paid orders are read-only.</p>}
        </div>
      </div>
    </section>
  );
}
