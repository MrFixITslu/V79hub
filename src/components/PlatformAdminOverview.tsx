import React, { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, Building2, CheckCircle2, CreditCard,
  GraduationCap, Headphones, Megaphone, RefreshCw, ShoppingCart, Wallet,
} from "lucide-react";

type Product = "pos" | "ffpro" | "tiquet" | "marketing" | "academy";

interface ProductResult {
  status: "ok" | "error";
  httpStatus: number;
  metrics: Record<string, any> | null;
  error?: string | null;
}

interface OverviewResponse {
  generatedAt: string;
  hub: {
    customers: number;
    activeCustomers: number;
    suspendedCustomers: number;
    pendingInvitations: number;
    provisioningCustomers: number;
  };
  apps: Record<Product, ProductResult>;
}

const productConfig: Array<{
  id: Product;
  name: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  metric: (m: Record<string, any>) => Array<{ label: string; value: number | string }>;
}> = [
  {
    id: "pos",
    name: "V79 POS",
    description: "Commerce tenants, locations and purchasing activity",
    icon: ShoppingCart,
    metric: (m) => [
      { label: "Tenants", value: Number(m.totalTenants || 0) },
      { label: "Active", value: Number(m.activeTenants || 0) },
      { label: "Sales", value: Number(m.completedSales || 0) },
      { label: "Open POs", value: Number(m.openPurchaseOrders || 0) },
    ],
  },
  {
    id: "ffpro",
    name: "FFPRO",
    description: "Finance account adoption and service activity",
    icon: Wallet,
    metric: (m) => [
      { label: "Accounts", value: Number(m.totalAccounts || 0) },
      { label: "Hub managed", value: Number(m.hubManagedAccounts || 0) },
      { label: "Active 30d", value: Number(m.activeAccounts30d || 0) },
      { label: "Saved profiles", value: Number(m.accountsWithSavedData || 0) },
    ],
  },
  {
    id: "tiquet",
    name: "V79 Tiquet",
    description: "Service workspaces, users and subscriptions",
    icon: Headphones,
    metric: (m) => [
      { label: "Accounts", value: Number(m.totalAccounts || 0) },
      { label: "Active", value: Number(m.activeAccounts || 0) },
      { label: "Users", value: Number(m.totalUsers || 0) },
      { label: "Jobs", value: Number(m.totalJobs || 0) },
    ],
  },
  {
    id: "marketing",
    name: "V79 Marketing",
    description: "Marketing workspaces, campaigns and subscriptions",
    icon: Megaphone,
    metric: (m) => [
      { label: "Businesses", value: Number(m.totalBusinesses || 0) },
      { label: "Users", value: Number(m.totalUsers || 0) },
      { label: "Campaigns", value: Number(m.totalCampaigns || 0) },
      { label: "Subscriptions", value: Number(m.activeSubscriptions || 0) },
    ],
  },
  {
    id: "academy",
    name: "V79 Academy",
    description: "Course catalogue, learners and memberships",
    icon: GraduationCap,
    metric: (m) => [
      { label: "Courses", value: Number(m.totalCourses || 0) },
      { label: "Published", value: Number(m.publishedCourses || 0) },
      { label: "Learners", value: Number(m.totalLearners || 0) },
      { label: "Memberships", value: Number(m.activeMemberships || 0) },
    ],
  },
];

export function PlatformAdminOverview({ onOpen }: { onOpen: (product: Product) => void }) {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  const refresh = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/platform/overview", { cache: "no-store" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.error || `Platform overview failed (${response.status})`);
      setData(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Platform overview could not be loaded.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { void refresh(); }, []);

  const onlineCount = productConfig.filter((product) => data?.apps?.[product.id]?.status === "ok").length;

  const issues = useMemo(() => {
    if (!data) return [] as Array<{ product: Product; title: string; detail: string; severity: "error" | "warning" }>;
    const result: Array<{ product: Product; title: string; detail: string; severity: "error" | "warning" }> = [];
    if ((data.hub?.provisioningCustomers || 0) > 0) {
      result.push({
        product: "pos",
        title: "Customers awaiting provisioning",
        detail: `${data.hub.provisioningCustomers} customer workspace(s) still have tenant-mapped apps pending.`,
        severity: "warning",
      });
    }

    for (const product of productConfig) {
      const item = data.apps?.[product.id];
      if (!item || item.status !== "ok") {
        result.push({ product: product.id, title: `${product.name} unavailable`, detail: item?.error || "Platform statistics could not be retrieved.", severity: "error" });
      }
    }

    const pos = data.apps?.pos?.metrics || {};
    if (Number(pos.inactiveTenants || 0) > 0) {
      result.push({ product: "pos", title: "Inactive POS tenants", detail: `${pos.inactiveTenants} tenant(s) are currently inactive.`, severity: "warning" });
    }

    const tiquet = data.apps?.tiquet?.metrics || {};
    if (Number(tiquet.suspendedAccounts || 0) > 0) {
      result.push({ product: "tiquet", title: "Suspended Tiquet workspaces", detail: `${tiquet.suspendedAccounts} workspace(s) are suspended.`, severity: "warning" });
    }

    return result;
  }, [data]);

  return (
    <div className="space-y-5">
      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 text-rose-800 px-4 py-3 text-sm">{error}</div>}

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h2 className="font-bold text-slate-900">Platform operations overview</h2>
          <p className="text-xs text-slate-500 mt-1">Customer lifecycle, provisioning workload and real service health. Private customer and learner content is not exposed here.</p>
        </div>
        <button onClick={() => void refresh()} className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold inline-flex items-center gap-1.5 self-start md:self-auto">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
        <Summary icon={Building2} label="Customers" value={busy && !data ? "…" : String(data?.hub?.customers ?? 0)} />
        <Summary icon={CheckCircle2} label="Active" value={busy && !data ? "…" : String(data?.hub?.activeCustomers ?? 0)} />
        <Summary icon={AlertTriangle} label="Provisioning" value={busy && !data ? "…" : String(data?.hub?.provisioningCustomers ?? 0)} />
        <Summary icon={CreditCard} label="Pending invites" value={busy && !data ? "…" : String(data?.hub?.pendingInvitations ?? 0)} />
        <Summary icon={Activity} label="Core services healthy" value={busy && !data ? "…" : `${onlineCount}/5`} />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {productConfig.map((product) => {
          const item = data?.apps?.[product.id];
          const healthy = item?.status === "ok";
          const Icon = product.icon;
          const metrics = product.metric(item?.metrics || {});
          return (
            <button
              key={product.id}
              onClick={() => onOpen(product.id)}
              className="text-left bg-white border border-slate-200 rounded-2xl p-5 hover:border-cyan-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-slate-950 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-cyan-400" />
                  </div>
                  <div>
                    <div className="font-bold text-slate-900">{product.name}</div>
                    <div className="text-[11px] text-slate-500 mt-0.5">{product.description}</div>
                  </div>
                </div>
                <span className={`px-2 py-1 rounded-full border text-[9px] font-bold ${healthy ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-rose-50 border-rose-200 text-rose-700"}`}>
                  {healthy ? "Healthy" : busy && !item ? "Loading" : "Needs attention"}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-2 mt-4">
                {metrics.map((metric) => (
                  <div key={metric.label} className="rounded-xl bg-slate-50 border border-slate-100 p-2.5 min-w-0">
                    <div className="text-sm font-bold text-slate-900 truncate">{metric.value}</div>
                    <div className="text-[9px] text-slate-400 mt-0.5 truncate">{metric.label}</div>
                  </div>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      <section className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-slate-200">
          <h3 className="font-bold text-sm text-slate-900">Attention needed</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">Operational signals that may require platform-administrator review.</p>
        </div>
        {issues.length ? (
          <div className="divide-y divide-slate-100">
            {issues.map((issue, index) => (
              <button key={issue.product + index} onClick={() => onOpen(issue.product)} className="w-full text-left p-4 hover:bg-slate-50 flex items-start gap-3">
                <AlertTriangle className={`w-4 h-4 mt-0.5 ${issue.severity === "error" ? "text-rose-600" : "text-amber-600"}`} />
                <div>
                  <div className="text-xs font-bold text-slate-900">{issue.title}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{issue.detail}</div>
                </div>
              </button>
            ))}
          </div>
        ) : !data ? (
          <div className="p-5 text-sm text-slate-500">Platform status has not been loaded yet.</div>
        ) : (
          <div className="p-5 flex items-center gap-3 text-sm text-emerald-700 bg-emerald-50/40">
            <CheckCircle2 className="w-4 h-4" />
            No platform-level issues are currently being surfaced.
          </div>
        )}
      </section>

      <div className="text-[10px] text-slate-400">
        Last refreshed {data?.generatedAt ? new Date(data.generatedAt).toLocaleString() : "—"}.
      </div>
    </div>
  );
}

function Summary({ icon: Icon, label, value }: { icon: React.ComponentType<{className?:string}>; label:string; value:string }) {
  return <div className="bg-slate-950 text-white rounded-xl p-4 border border-slate-800"><Icon className="w-4 h-4 text-cyan-400" /><div className="text-xl font-extrabold mt-2">{value}</div><div className="text-[10px] text-slate-400 mt-0.5">{label}</div></div>;
}
