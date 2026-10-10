import React, { useEffect, useMemo, useState } from "react";
import { Activity, Building2, Boxes, MapPin, RefreshCw, ShoppingCart, Users, Wifi } from "lucide-react";

interface PosStats {
  totalTenants: number;
  activeTenants: number;
  inactiveTenants: number;
  activeMemberships: number;
  activeLocations: number;
  products: number;
  completedSales: number;
  openPurchaseOrders: number;
  generatedAt: string;
}

interface PosTenant {
  id: string;
  name: string;
  slug: string;
  currency: string;
  timezone: string;
  active: boolean;
  offlineSalesEnabled: boolean;
  createdAt: string;
  memberCount: number;
  locationCount: number;
  productCount: number;
  completedSales: number;
  openPurchaseOrders: number;
}

async function posAdminApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/admin/platform/pos${path}`, {
    ...options,
    cache: "no-store",
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.error || `POS admin request failed (${response.status})`);
  return payload as T;
}

export function POSPlatformAdmin() {
  const [stats, setStats] = useState<PosStats | null>(null);
  const [tenants, setTenants] = useState<PosTenant[]>([]);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const flash = (text: string, type: "success" | "error" = "success") => {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 5000);
  };

  const refresh = async () => {
    setBusy("refresh");
    try {
      const [nextStats, nextTenants] = await Promise.all([
        posAdminApi<PosStats>("/stats"),
        posAdminApi<PosTenant[]>("/tenants"),
      ]);
      setStats(nextStats);
      setTenants(nextTenants);
    } catch (error) {
      flash(error instanceof Error ? error.message : "POS administration could not be loaded.", "error");
    } finally {
      setBusy("");
    }
  };

  useEffect(() => { void refresh(); }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return tenants.filter((tenant) =>
      !term || [tenant.name, tenant.slug, tenant.currency, tenant.timezone]
        .some((value) => String(value || "").toLowerCase().includes(term))
    );
  }, [tenants, search]);

  const setOfflineSales = async (tenant: PosTenant, enabled: boolean) => {
    setBusy(tenant.id);
    try {
      await posAdminApi(`/tenants/${encodeURIComponent(tenant.id)}/offline-sales/${enabled ? "enabled" : "disabled"}`, { method: "PUT" });
      await refresh();
      flash(enabled ? "Offline sales enabled." : "Offline sales disabled.");
    } catch (error) {
      flash(error instanceof Error ? error.message : "Offline-sales setting could not be changed.", "error");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-5">
      {message && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${message.type === "success" ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-rose-50 border-rose-200 text-rose-800"}`}>
          {message.text}
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-bold text-slate-900">POS platform administration</h2>
          <p className="text-xs text-slate-500 mt-1">Operational tenant metadata and POS-specific settings only. Customer access is managed centrally from Hub Customers and Plans & Entitlements.</p>
        </div>
        <button onClick={() => void refresh()} className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold inline-flex items-center gap-1.5">
          <RefreshCw className={`w-3.5 h-3.5 ${busy === "refresh" ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-3">
        <Metric icon={Building2} label="Tenants" value={stats?.totalTenants ?? 0} />
        <Metric icon={Activity} label="Active" value={stats?.activeTenants ?? 0} />
        <Metric icon={Users} label="Members" value={stats?.activeMemberships ?? 0} />
        <Metric icon={MapPin} label="Locations" value={stats?.activeLocations ?? 0} />
        <Metric icon={Boxes} label="Products" value={stats?.products ?? 0} />
        <Metric icon={ShoppingCart} label="Sales" value={stats?.completedSales ?? 0} />
        <Metric icon={Boxes} label="Open POs" value={stats?.openPurchaseOrders ?? 0} />
        <Metric icon={Building2} label="Inactive" value={stats?.inactiveTenants ?? 0} />
      </div>

      <section className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-slate-200">
          <input value={search} onChange={(e) => setSearch(e.target.value)} className="admin-input max-w-md" placeholder="Search POS tenants" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1100px] text-left">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="p-3">Tenant</th><th className="p-3">Status</th><th className="p-3">Members</th>
                <th className="p-3">Locations</th><th className="p-3">Products</th><th className="p-3">Sales</th>
                <th className="p-3">Open POs</th><th className="p-3">Offline Sales</th><th className="p-3 text-right">Authority</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((tenant) => (
                <tr key={tenant.id} className="text-xs">
                  <td className="p-3"><div className="font-semibold text-slate-900">{tenant.name}</div><div className="text-[10px] text-slate-400 mt-0.5">{tenant.slug} · {tenant.currency}</div></td>
                  <td className="p-3"><span className={`px-2 py-1 rounded-full text-[9px] font-bold ${tenant.active ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{tenant.active ? "active" : "inactive"}</span></td>
                  <td className="p-3 text-slate-600">{tenant.memberCount}</td>
                  <td className="p-3 text-slate-600">{tenant.locationCount}</td>
                  <td className="p-3 text-slate-600">{tenant.productCount}</td>
                  <td className="p-3 text-slate-600">{tenant.completedSales}</td>
                  <td className="p-3 text-slate-600">{tenant.openPurchaseOrders}</td>
                  <td className="p-3"><button disabled={busy === tenant.id} onClick={() => void setOfflineSales(tenant, !tenant.offlineSalesEnabled)} className={`px-2.5 py-1.5 rounded-lg border text-[10px] font-semibold ${tenant.offlineSalesEnabled ? "border-cyan-200 bg-cyan-50 text-cyan-700" : "border-slate-200 text-slate-600"}`}><Wifi className="inline w-3 h-3 mr-1" />{tenant.offlineSalesEnabled ? "Enabled" : "Disabled"}</button></td>
                  <td className="p-3 text-right"><span className="text-[9px] font-semibold text-slate-400">Managed in Hub</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && <div className="p-10 text-center text-sm text-slate-400">No POS tenants found.</div>}
        </div>
      </section>
    </div>
  );
}

function Metric({ icon: Icon, label, value }: { icon: React.ComponentType<{className?:string}>; label:string; value:number }) {
  return <div className="bg-white border border-slate-200 rounded-xl p-4"><Icon className="w-4 h-4 text-purple-600" /><div className="text-xl font-extrabold text-slate-900 mt-2">{value}</div><div className="text-[10px] text-slate-500 mt-0.5">{label}</div></div>;
}
