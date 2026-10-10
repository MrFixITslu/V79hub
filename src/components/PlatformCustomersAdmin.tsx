import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Building2, CheckCircle2, Clipboard, Loader2, Mail, PackageCheck,
  RefreshCw, Search, Send, ShieldAlert, UserRound, Users, XCircle,
} from "lucide-react";

interface AssignableApp {
  id: string;
  name: string;
  shortName: string;
}

interface CustomerApp {
  id: string;
  name: string;
  shortName: string;
  provisioningStatus: string;
}

interface CustomerPlan {
  organizationId: string;
  planName: string;
  status: string;
  billingCycle: string;
  priceXcd?: number;
  renewalDate?: string;
}

interface CustomerRecord {
  id: string;
  name: string;
  slug: string;
  lifecycle: "invited" | "provisioning" | "active" | "suspended";
  organizationStatus: "active" | "suspended" | null;
  owner: {
    id: string | null;
    name: string;
    email: string;
    lastLogin: string | null;
    mfaEnabled: boolean;
  } | null;
  memberCount: number;
  apps: CustomerApp[];
  plan: CustomerPlan | null;
  invitation: {
    id: string;
    status: string;
    email: string;
    createdAt: string;
    acceptedAt: string | null;
    expiresAt: string;
  } | null;
  createdAt: string;
  lastActivityAt: string;
}

interface CustomerData {
  customers: CustomerRecord[];
  invited: CustomerRecord[];
  assignableApps: AssignableApp[];
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok && response.status !== 207) {
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  return payload as T;
}

const lifecycleStyle: Record<string, string> = {
  invited: "bg-blue-50 border-blue-200 text-blue-700",
  provisioning: "bg-amber-50 border-amber-200 text-amber-700",
  active: "bg-emerald-50 border-emerald-200 text-emerald-700",
  suspended: "bg-rose-50 border-rose-200 text-rose-700",
};

export function PlatformCustomersAdmin() {
  const [data, setData] = useState<CustomerData>({ customers: [], invited: [], assignableApps: [] });
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [lifecycle, setLifecycle] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [organizationName, setOrganizationName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [expiresInHours, setExpiresInHours] = useState(72);
  const [inviteAppIds, setInviteAppIds] = useState<string[]>([]);
  const [createdUrl, setCreatedUrl] = useState("");

  const [statusReason, setStatusReason] = useState("");
  const [confirmName, setConfirmName] = useState("");

  const flash = (text: string, type: "success" | "error" = "success") => {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 6000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api<CustomerData>("/api/admin/customers");
      setData(next);
      const all = [...next.invited, ...next.customers];
      if (selectedId && !all.some(customer => customer.id === selectedId)) setSelectedId("");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Customers could not be loaded.", "error");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => { void load(); }, [load]);

  const allCustomers = useMemo(() => [...data.invited, ...data.customers], [data]);
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return allCustomers.filter(customer => {
      const matchLifecycle = lifecycle === "all" || customer.lifecycle === lifecycle;
      const matchSearch = !term || [
        customer.name,
        customer.slug,
        customer.owner?.email,
        customer.owner?.name,
        customer.plan?.planName,
      ].some(value => String(value || "").toLowerCase().includes(term));
      return matchLifecycle && matchSearch;
    });
  }, [allCustomers, search, lifecycle]);

  const selected = allCustomers.find(customer => customer.id === selectedId) || null;

  const createInvitation = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("invite");
    setCreatedUrl("");
    try {
      const result = await api<{ inviteUrl: string }>("/api/admin/onboarding/invitations", {
        method: "POST",
        body: JSON.stringify({
          organizationName,
          email: ownerEmail,
          expiresInHours,
          appIds: inviteAppIds,
        }),
      });
      setCreatedUrl(result.inviteUrl);
      setOrganizationName("");
      setOwnerEmail("");
      setInviteAppIds([]);
      flash("Secure owner invitation created.");
      await load();
    } catch (error) {
      flash(error instanceof Error ? error.message : "Invitation could not be created.", "error");
    } finally {
      setBusy("");
    }
  };

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(createdUrl);
      flash("Invitation link copied.");
    } catch {
      flash("Copy failed. Select and copy the invitation link manually.", "error");
    }
  };

  const provisionSelected = async (customer: CustomerRecord) => {
    const pendingIds = customer.apps
      .filter(app => ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"].includes(app.id))
      .filter(app => app.provisioningStatus !== "active")
      .map(app => app.id);
    if (pendingIds.length === 0) {
      flash("All tenant-mapped apps are already provisioned.");
      return;
    }
    if (!window.confirm(`Provision ${pendingIds.length} selected app(s) for ${customer.name}? Existing active mappings will be skipped.`)) return;
    setBusy("provision:" + customer.id);
    try {
      const result = await api<{ success: boolean; results: Array<{ product: string; status: string; error?: string }> }>(
        `/api/admin/customers/${encodeURIComponent(customer.id)}/provision`,
        { method: "POST", body: JSON.stringify({ appIds: pendingIds }) },
      );
      const failures = result.results.filter(item => item.status === "failed");
      if (failures.length) {
        flash(`Provisioning completed with ${failures.length} failure(s): ${failures.map(item => item.product + ": " + (item.error || "failed")).join("; ")}`, "error");
      } else {
        flash("Selected apps provisioned successfully.");
      }
      await load();
    } catch (error) {
      flash(error instanceof Error ? error.message : "Provisioning failed.", "error");
    } finally {
      setBusy("");
    }
  };

  const changeCustomerStatus = async (customer: CustomerRecord) => {
    const nextStatus = customer.organizationStatus === "suspended" ? "active" : "suspended";
    if (confirmName !== customer.name || statusReason.trim().length < 5) {
      flash("Type the exact business name and provide a reason before changing customer status.", "error");
      return;
    }
    setBusy("status:" + customer.id);
    try {
      await api(`/api/admin/customers/${encodeURIComponent(customer.id)}/status`, {
        method: "POST",
        body: JSON.stringify({
          status: nextStatus,
          reason: statusReason.trim(),
          confirmName: confirmName.trim(),
        }),
      });
      flash(nextStatus === "suspended" ? "Customer suspended and active Hub sessions revoked." : "Customer reactivated.");
      setStatusReason("");
      setConfirmName("");
      await load();
    } catch (error) {
      flash(error instanceof Error ? error.message : "Customer status could not be changed.", "error");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-5">
      {message && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${message.type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
          {message.text}
        </div>
      )}

      <div className="grid xl:grid-cols-[1.2fr_.8fr] gap-5">
        <section className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div className="p-4 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div>
              <h2 className="font-bold text-slate-900">Customers</h2>
              <p className="text-xs text-slate-500 mt-1">One lifecycle view for invited, provisioning, active and suspended businesses.</p>
            </div>
            <button onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
          <div className="p-4 border-b border-slate-200 grid sm:grid-cols-[1fr_180px] gap-2">
            <label className="relative">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
              <input value={search} onChange={e => setSearch(e.target.value)} className="admin-input pl-9" placeholder="Search business, owner or plan" />
            </label>
            <select value={lifecycle} onChange={e => setLifecycle(e.target.value)} className="admin-input">
              <option value="all">All lifecycle states</option>
              <option value="invited">Invited</option>
              <option value="provisioning">Provisioning</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>
          <div className="divide-y divide-slate-100 max-h-[720px] overflow-y-auto">
            {filtered.map(customer => (
              <button
                key={customer.id}
                onClick={() => { setSelectedId(customer.id); setStatusReason(""); setConfirmName(""); }}
                className={`w-full p-4 text-left hover:bg-slate-50 transition-colors ${selectedId === customer.id ? "bg-cyan-50/60 border-l-2 border-cyan-500" : "border-l-2 border-transparent"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-semibold text-sm text-slate-900 truncate">{customer.name}</div>
                    <div className="text-[11px] text-slate-500 mt-1 truncate">{customer.owner?.email || customer.invitation?.email || "Owner not registered"}</div>
                  </div>
                  <span className={`shrink-0 rounded-full border px-2 py-1 text-[9px] font-black uppercase tracking-wide ${lifecycleStyle[customer.lifecycle] || lifecycleStyle.invited}`}>
                    {customer.lifecycle}
                  </span>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[10px] text-slate-400">
                  <span>{customer.apps.length} app{customer.apps.length === 1 ? "" : "s"}</span>
                  <span>{customer.memberCount} user{customer.memberCount === 1 ? "" : "s"}</span>
                  <span>{customer.plan?.planName || "Plan pending"}</span>
                </div>
              </button>
            ))}
            {!loading && filtered.length === 0 && <div className="p-8 text-center text-sm text-slate-400">No customers match these filters.</div>}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 min-h-[420px]">
          {!selected ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-8">
              <Building2 className="w-10 h-10 text-slate-300" />
              <h3 className="mt-3 font-bold text-slate-800">Select a customer</h3>
              <p className="mt-1 text-sm text-slate-500">Open one business to review its owner, apps, plan and lifecycle controls.</p>
            </div>
          ) : (
            <div className="space-y-5">
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Customer record</div>
                    <h3 className="text-xl font-extrabold text-slate-900 mt-1">{selected.name}</h3>
                    <div className="text-xs text-slate-400 mt-1">{selected.slug}</div>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-[9px] font-black uppercase tracking-wide ${lifecycleStyle[selected.lifecycle] || lifecycleStyle.invited}`}>{selected.lifecycle}</span>
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-3">
                <Info icon={UserRound} label="Owner" value={selected.owner?.name || "Awaiting acceptance"} detail={selected.owner?.email || selected.invitation?.email || "—"} />
                <Info icon={Users} label="Users" value={String(selected.memberCount)} detail={selected.owner?.mfaEnabled ? "Owner MFA enabled" : "Owner MFA not enabled"} />
                <Info icon={PackageCheck} label="Plan" value={selected.plan?.planName || "Pending"} detail={selected.plan ? `${selected.plan.status} · ${selected.plan.billingCycle}` : "Created after acceptance"} />
                <Info icon={Mail} label="Last activity" value={new Date(selected.lastActivityAt).toLocaleDateString()} detail={new Date(selected.lastActivityAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} />
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold mb-2">Enabled apps</div>
                <div className="space-y-2">
                  {selected.apps.length ? selected.apps.map(app => (
                    <div key={app.id} className="rounded-xl border border-slate-200 px-3 py-2.5 flex items-center justify-between gap-3">
                      <div>
                        <div className="text-xs font-semibold text-slate-800">{app.shortName}</div>
                        <div className="text-[10px] text-slate-400">{app.name}</div>
                      </div>
                      <span className={`text-[9px] font-bold ${app.provisioningStatus === "active" || app.provisioningStatus === "not_required" ? "text-emerald-700" : app.provisioningStatus === "disabled" ? "text-slate-400" : "text-amber-700"}`}>
                        {app.provisioningStatus.replaceAll("_", " ")}
                      </span>
                    </div>
                  )) : <div className="text-xs text-slate-400">No apps assigned.</div>}
                </div>
              </div>

              {selected.lifecycle !== "invited" && (
                <button
                  onClick={() => void provisionSelected(selected)}
                  disabled={busy === "provision:" + selected.id || selected.organizationStatus === "suspended"}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-xs font-bold text-white disabled:opacity-40"
                >
                  {busy === "provision:" + selected.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <PackageCheck className="w-4 h-4" />}
                  Provision selected apps
                </button>
              )}

              {selected.lifecycle !== "invited" && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50/60 p-4">
                  <div className="flex items-start gap-2">
                    <ShieldAlert className="w-4 h-4 text-rose-600 mt-0.5" />
                    <div>
                      <div className="text-xs font-bold text-rose-800">{selected.organizationStatus === "suspended" ? "Reactivate customer" : "Suspend customer"}</div>
                      <div className="text-[10px] text-rose-700/70 mt-1">High-impact action. Type the exact business name and record a reason. Suspension revokes active Hub sessions.</div>
                    </div>
                  </div>
                  <input value={confirmName} onChange={e => setConfirmName(e.target.value)} className="admin-input mt-3" placeholder={selected.name} />
                  <textarea value={statusReason} onChange={e => setStatusReason(e.target.value)} className="admin-input mt-2" rows={2} placeholder="Reason for this status change" />
                  <button
                    onClick={() => void changeCustomerStatus(selected)}
                    disabled={busy === "status:" + selected.id}
                    className={`mt-3 inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold disabled:opacity-50 ${selected.organizationStatus === "suspended" ? "bg-emerald-700 text-white" : "border border-rose-300 text-rose-700"}`}
                  >
                    {busy === "status:" + selected.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : selected.organizationStatus === "suspended" ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                    {selected.organizationStatus === "suspended" ? "Reactivate" : "Suspend"}
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-start gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-cyan-50 border border-cyan-200 flex items-center justify-center"><Send className="w-4 h-4 text-cyan-700" /></div>
          <div>
            <h2 className="font-bold text-slate-900">Invite a new business owner</h2>
            <p className="text-xs text-slate-500 mt-1">Choose the Hub modules the customer is entitled to before sending the one-time owner invitation.</p>
          </div>
        </div>
        <form onSubmit={createInvitation} className="space-y-4">
          <div className="grid md:grid-cols-[1fr_1fr_160px] gap-3">
            <input required value={organizationName} onChange={e => setOrganizationName(e.target.value)} className="admin-input" placeholder="Business name" />
            <input required type="email" value={ownerEmail} onChange={e => setOwnerEmail(e.target.value)} className="admin-input" placeholder="Owner email" />
            <input required type="number" min={1} max={168} value={expiresInHours} onChange={e => setExpiresInHours(Number(e.target.value))} className="admin-input" aria-label="Invitation expiry in hours" />
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-2">
            {data.assignableApps.map(app => (
              <label key={app.id} className="rounded-xl border border-slate-200 p-3 cursor-pointer hover:bg-slate-50 flex items-start gap-2">
                <input type="checkbox" checked={inviteAppIds.includes(app.id)} onChange={() => setInviteAppIds(current => current.includes(app.id) ? current.filter(id => id !== app.id) : [...current, app.id])} />
                <span className="text-xs"><strong className="block text-slate-800">{app.shortName}</strong><span className="text-[10px] text-slate-400">{app.name}</span></span>
              </label>
            ))}
          </div>
          <button type="submit" disabled={busy === "invite"} className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-xs font-bold text-white disabled:opacity-50">
            {busy === "invite" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Create secure invitation
          </button>
        </form>

        {createdUrl && (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <div className="text-[10px] uppercase tracking-wider font-bold text-emerald-700">Copy this invitation now</div>
            <div className="mt-2 flex flex-col sm:flex-row gap-2">
              <input readOnly value={createdUrl} onFocus={event => event.currentTarget.select()} className="admin-input flex-1 font-mono text-[10px]" />
              <button onClick={() => void copyInvite()} className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white"><Clipboard className="w-3.5 h-3.5" /> Copy</button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function Info({ icon: Icon, label, value, detail }: { icon: typeof Building2; label: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <Icon className="w-4 h-4 text-cyan-700" />
      <div className="mt-2 text-[9px] uppercase tracking-wider font-bold text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-bold text-slate-900 truncate">{value}</div>
      <div className="mt-0.5 text-[10px] text-slate-400 truncate">{detail}</div>
    </div>
  );
}
