import { FormEvent, useEffect, useMemo, useState } from "react";
import { CalendarDays, CheckCircle2, CreditCard, Loader2, PackageCheck, RefreshCw, Search } from "lucide-react";

interface AssignableApp { id: string; name: string; shortName: string; }
interface CustomerRecord {
  id: string;
  name: string;
  lifecycle: string;
  organizationStatus: string | null;
  apps: Array<{ id: string; shortName: string; name: string; provisioningStatus: string }>;
  plan: {
    organizationId: string;
    planName: string;
    status: "active" | "trial" | "paused" | "cancelled";
    billingCycle: "monthly" | "annual" | "custom";
    appIds?: string[];
    priceXcd?: number;
    renewalDate?: string;
  } | null;
}
interface CustomerData { customers: CustomerRecord[]; invited: CustomerRecord[]; assignableApps: AssignableApp[]; }

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload as T;
}

export function PlatformPlansAdmin() {
  const [data, setData] = useState<CustomerData>({ customers: [], invited: [], assignableApps: [] });
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [planName, setPlanName] = useState("Custom");
  const [status, setStatus] = useState<"active" | "trial" | "paused" | "cancelled">("active");
  const [billingCycle, setBillingCycle] = useState<"monthly" | "annual" | "custom">("custom");
  const [priceXcd, setPriceXcd] = useState("");
  const [renewalDate, setRenewalDate] = useState("");
  const [appIds, setAppIds] = useState<string[]>([]);
  const [reason, setReason] = useState("");

  const load = async () => {
    setBusy(true);
    try {
      const next = await api<CustomerData>("/api/admin/customers");
      setData(next);
      if (selectedId && !next.customers.some(customer => customer.id === selectedId)) setSelectedId("");
    } catch (error) {
      setMessage({ type: "error", text: error instanceof Error ? error.message : "Plans could not be loaded." });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return data.customers.filter(customer =>
      !term || [customer.name, customer.plan?.planName, customer.lifecycle]
        .some(value => String(value || "").toLowerCase().includes(term))
    );
  }, [data.customers, search]);

  const selected = data.customers.find(customer => customer.id === selectedId) || null;

  useEffect(() => {
    if (!selected) return;
    setPlanName(selected.plan?.planName || "Custom");
    setStatus(selected.plan?.status || "active");
    setBillingCycle(selected.plan?.billingCycle || "custom");
    setPriceXcd(selected.plan?.priceXcd == null ? "" : String(selected.plan.priceXcd));
    setRenewalDate(selected.plan?.renewalDate || "");
    setAppIds(selected.plan?.appIds?.length ? selected.plan.appIds : selected.apps.map(app => app.id));
    setReason("");
  }, [selectedId]);

  const toggleApp = (appId: string) => {
    setAppIds(current => current.includes(appId) ? current.filter(id => id !== appId) : [...current, appId]);
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      await api(`/api/admin/customers/${encodeURIComponent(selected.id)}/plan`, {
        method: "PUT",
        body: JSON.stringify({
          planName,
          status,
          billingCycle,
          priceXcd: priceXcd === "" ? null : Number(priceXcd),
          renewalDate: renewalDate || null,
          appIds,
          reason,
        }),
      });
      setMessage({ type: "success", text: "Plan and Hub entitlements updated." });
      await load();
    } catch (error) {
      setMessage({ type: "error", text: error instanceof Error ? error.message : "Plan could not be updated." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      {message && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${message.type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
          {message.text}
        </div>
      )}

      <div className="grid xl:grid-cols-[360px_minmax(0,1fr)] gap-5">
        <section className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between gap-2">
            <div>
              <h2 className="font-bold text-slate-900">Customer plans</h2>
              <p className="text-xs text-slate-500 mt-1">{data.customers.length} accepted customer{data.customers.length === 1 ? "" : "s"}</p>
            </div>
            <button onClick={() => void load()} className="p-2 rounded-lg border border-slate-200 text-slate-500" title="Refresh"><RefreshCw className={`w-4 h-4 ${busy ? "animate-spin" : ""}`} /></button>
          </div>
          <div className="p-3 border-b border-slate-200">
            <label className="relative block">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
              <input value={search} onChange={e => setSearch(e.target.value)} className="admin-input pl-9" placeholder="Search customers" />
            </label>
          </div>
          <div className="max-h-[720px] overflow-y-auto divide-y divide-slate-100">
            {filtered.map(customer => (
              <button key={customer.id} onClick={() => setSelectedId(customer.id)}
                className={`w-full text-left p-4 hover:bg-slate-50 ${selectedId === customer.id ? "bg-cyan-50/60 border-l-2 border-cyan-500" : "border-l-2 border-transparent"}`}>
                <div className="font-semibold text-sm text-slate-900">{customer.name}</div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-400">
                  <span>{customer.plan?.planName || "Custom"}</span>
                  <span>·</span>
                  <span>{customer.apps.length} apps</span>
                </div>
              </button>
            ))}
            {!busy && filtered.length === 0 && <div className="p-8 text-center text-sm text-slate-400">No accepted customers found.</div>}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          {!selected ? (
            <div className="min-h-[420px] flex flex-col items-center justify-center text-center">
              <CreditCard className="w-10 h-10 text-slate-300" />
              <h3 className="mt-3 font-bold text-slate-800">Select a customer plan</h3>
              <p className="mt-1 text-sm text-slate-500 max-w-md">Hub owns the customer entitlement record. Product apps should consume Hub access rather than independently deciding what the customer purchased.</p>
            </div>
          ) : (
            <form onSubmit={save} className="space-y-6">
              <div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-cyan-700">Plans & entitlements</div>
                <h2 className="text-xl font-extrabold text-slate-900 mt-1">{selected.name}</h2>
                <p className="text-xs text-slate-500 mt-1">Changes here control Hub visibility and launch entitlement. Tenant-mapped apps newly enabled will require provisioning.</p>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <Field label="Plan name">
                  <input required value={planName} onChange={e => setPlanName(e.target.value)} className="admin-input" placeholder="Business" />
                </Field>
                <Field label="Plan status">
                  <select value={status} onChange={e => setStatus(e.target.value as typeof status)} className="admin-input">
                    <option value="active">Active</option>
                    <option value="trial">Trial</option>
                    <option value="paused">Paused</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </Field>
                <Field label="Billing cycle">
                  <select value={billingCycle} onChange={e => setBillingCycle(e.target.value as typeof billingCycle)} className="admin-input">
                    <option value="monthly">Monthly</option>
                    <option value="annual">Annual</option>
                    <option value="custom">Custom / agreement</option>
                  </select>
                </Field>
                <Field label="Price (EC$)">
                  <input type="number" min="0" step="0.01" value={priceXcd} onChange={e => setPriceXcd(e.target.value)} className="admin-input" placeholder="Leave blank if by agreement" />
                </Field>
                <Field label="Renewal date">
                  <div className="relative">
                    <CalendarDays className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                    <input type="date" value={renewalDate} onChange={e => setRenewalDate(e.target.value)} className="admin-input pl-9" />
                  </div>
                </Field>
                <Field label="Customer state">
                  <div className="admin-input flex items-center gap-2 bg-slate-50">
                    <CheckCircle2 className={`w-4 h-4 ${selected.organizationStatus === "active" ? "text-emerald-600" : "text-rose-600"}`} />
                    <span className="capitalize">{selected.organizationStatus || selected.lifecycle}</span>
                  </div>
                </Field>
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <PackageCheck className="w-4 h-4 text-cyan-700" />
                  <div className="text-xs font-bold text-slate-800">Enabled V79 modules</div>
                </div>
                <p className="text-[11px] text-slate-500 mt-1 mb-3">Active/trial plans grant the selected Hub entitlements. Paused/cancelled plans preserve this selection but disable live app access until reactivated.</p>
                <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2">
                  {data.assignableApps.map(app => (
                    <label key={app.id} className={`rounded-xl border p-3 cursor-pointer flex items-start gap-2 ${appIds.includes(app.id) ? "border-cyan-300 bg-cyan-50/60" : "border-slate-200 hover:bg-slate-50"}`}>
                      <input type="checkbox" checked={appIds.includes(app.id)} onChange={() => toggleApp(app.id)} />
                      <span>
                        <strong className="block text-xs text-slate-800">{app.shortName}</strong>
                        <span className="text-[10px] text-slate-400">{app.name}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <Field label="Reason for change">
                <textarea required minLength={5} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} rows={3} className="admin-input" placeholder="Example: Customer upgraded to Business plan and added Marketing." />
              </Field>

              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-[11px] leading-5 text-amber-800">
                Hub entitlement is authoritative for Hub access. External product workspaces may still retain data after an app is removed; destructive data deletion/offboarding is intentionally not performed from this screen.
              </div>

              <button type="submit" disabled={busy || reason.trim().length < 5} className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-xs font-bold text-white disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
                Save plan & entitlements
              </button>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="space-y-1.5"><span className="text-[10px] uppercase tracking-wider font-bold text-slate-500">{label}</span>{children}</label>;
}
