import React, { useEffect, useMemo, useState } from "react";
import { Activity, Building2, CreditCard, RefreshCw, ShieldAlert, Users } from "lucide-react";

interface TiquetStats {
  totalAccounts: number;
  activeAccounts: number;
  suspendedAccounts: number;
  totalUsers: number;
  totalJobs: number;
  activeSubscriptions: number;
  trialSubscriptions: number;
  canceledSubscriptions: number;
  estimatedMrrUsd: number;
  newAccounts30d: number;
  generatedAt: string;
}

interface TiquetAccount {
  id: string;
  name: string;
  status: string;
  plan: string;
  createdAt?: string | null;
  suspendedAt?: string | null;
  hubOrganizationId?: string | null;
  userCount: number;
  jobCount: number;
  subscription?: {
    status?: string | null;
    plan?: string | null;
    currentPeriodEnd?: string | null;
  } | null;
}

async function tiquetAdminApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/admin/platform/tiquet${path}`, {
    ...options,
    cache: "no-store",
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.error || `Tiquet admin request failed (${response.status})`);
  return payload as T;
}

export function TiquetPlatformAdmin() {
  const [stats, setStats] = useState<TiquetStats | null>(null);
  const [accounts, setAccounts] = useState<TiquetAccount[]>([]);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{type:"success"|"error"; text:string}|null>(null);

  const flash = (text: string, type: "success" | "error" = "success") => {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 5000);
  };

  const refresh = async () => {
    setBusy("refresh");
    try {
      const [nextStats, nextAccounts] = await Promise.all([
        tiquetAdminApi<TiquetStats>("/stats"),
        tiquetAdminApi<TiquetAccount[]>("/accounts"),
      ]);
      setStats(nextStats);
      setAccounts(nextAccounts);
    } catch (error) {
      flash(error instanceof Error ? error.message : "Tiquet administration could not be loaded.", "error");
    } finally {
      setBusy("");
    }
  };

  useEffect(() => { void refresh(); }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return accounts.filter((account) => !term || [account.name, account.id, account.plan, account.status].some((value) => String(value || "").toLowerCase().includes(term)));
  }, [accounts, search]);

  return (
    <div className="space-y-5">
      {message && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${message.type === "success" ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-rose-50 border-rose-200 text-rose-800"}`}>
          {message.text}
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-bold text-slate-900">Tiquet platform administration</h2>
          <p className="text-xs text-slate-500 mt-1">Operational workspace metadata only. Customer access and plan entitlements are managed centrally from Customers and Plans & Entitlements.</p>
        </div>
        <button onClick={() => void refresh()} className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold inline-flex items-center gap-1.5">
          <RefreshCw className={`w-3.5 h-3.5 ${busy === "refresh" ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Metric icon={Building2} label="Accounts" value={stats?.totalAccounts ?? 0} />
        <Metric icon={Activity} label="Active" value={stats?.activeAccounts ?? 0} />
        <Metric icon={ShieldAlert} label="Suspended" value={stats?.suspendedAccounts ?? 0} />
        <Metric icon={Users} label="Users" value={stats?.totalUsers ?? 0} />
        <Metric icon={CreditCard} label="Active subscriptions" value={stats?.activeSubscriptions ?? 0} />
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Mini label="New accounts · 30d" value={String(stats.newAccounts30d)} />
          <Mini label="Trial subscriptions" value={String(stats.trialSubscriptions)} />
          <Mini label="Canceled subscriptions" value={String(stats.canceledSubscriptions)} />
          <Mini label="Estimated MRR" value={`US$${stats.estimatedMrrUsd.toFixed(2)}`} />
        </div>
      )}

      <section className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-slate-200">
          <input value={search} onChange={(e) => setSearch(e.target.value)} className="admin-input max-w-md" placeholder="Search Tiquet workspaces" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="p-3">Workspace</th>
                <th className="p-3">Status</th>
                <th className="p-3">Plan</th>
                <th className="p-3">Users</th>
                <th className="p-3">Jobs</th>
                <th className="p-3">Joined</th>
                <th className="p-3 text-right">Authority</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((account) => (
                <tr key={account.id} className="text-xs">
                  <td className="p-3"><div className="font-semibold text-slate-900">{account.name}</div><div className="text-[10px] text-slate-400 mt-0.5">{account.hubOrganizationId ? "Hub managed" : "Legacy/local"}</div></td>
                  <td className="p-3"><span className={`px-2 py-1 rounded-full text-[9px] font-bold ${account.status === "suspended" ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700"}`}>{account.status}</span></td>
                  <td className="p-3"><span className="px-2 py-1 rounded-full bg-indigo-50 text-indigo-700 text-[9px] font-bold">{account.plan || "trial"}</span></td>
                  <td className="p-3 text-slate-600">{account.userCount}</td>
                  <td className="p-3 text-slate-600">{account.jobCount}</td>
                  <td className="p-3 text-slate-500">{account.createdAt ? new Date(account.createdAt).toLocaleDateString() : "—"}</td>
                  <td className="p-3 text-right"><span className="text-[9px] font-semibold text-slate-400">Managed in Hub</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && <div className="p-10 text-center text-sm text-slate-400">No Tiquet workspaces found.</div>}
        </div>
      </section>
    </div>
  );
}

function Metric({ icon: Icon, label, value }: { icon: React.ComponentType<{className?:string}>; label: string; value: number }) {
  return <div className="bg-white border border-slate-200 rounded-xl p-4"><Icon className="w-4 h-4 text-cyan-600" /><div className="text-xl font-extrabold text-slate-900 mt-2">{value}</div><div className="text-[10px] text-slate-500 mt-0.5">{label}</div></div>;
}
function Mini({ label, value }: { label:string; value:string }) {
  return <div className="bg-slate-50 border border-slate-200 rounded-xl p-3"><div className="text-sm font-bold text-slate-900">{value}</div><div className="text-[10px] text-slate-500 mt-0.5">{label}</div></div>;
}
