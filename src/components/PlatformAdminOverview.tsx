import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, Activity, AlertTriangle, Building2, CheckCircle2, CreditCard,
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

export function countMetric(value: unknown): number | "—" {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : "—";
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
      { label: "Tenants", value: countMetric(m.totalTenants) },
      { label: "Active", value: countMetric(m.activeTenants) },
      { label: "Sales", value: countMetric(m.completedSales) },
      { label: "Open POs", value: countMetric(m.openPurchaseOrders) },
    ],
  },
  {
    id: "ffpro",
    name: "FFPRO",
    description: "Finance account adoption and service activity",
    icon: Wallet,
    metric: (m) => [
      { label: "Accounts", value: countMetric(m.totalAccounts) },
      { label: "Hub managed", value: countMetric(m.hubManagedAccounts) },
      { label: "Active 30d", value: countMetric(m.activeAccounts30d) },
      { label: "Saved profiles", value: countMetric(m.accountsWithSavedData) },
    ],
  },
  {
    id: "tiquet",
    name: "V79 Tiquet",
    description: "Service workspaces, users and subscriptions",
    icon: Headphones,
    metric: (m) => [
      { label: "Accounts", value: countMetric(m.totalAccounts) },
      { label: "Active", value: countMetric(m.activeAccounts) },
      { label: "Users", value: countMetric(m.totalUsers) },
      { label: "Jobs", value: countMetric(m.totalJobs) },
    ],
  },
  {
    id: "marketing",
    name: "V79 Marketing",
    description: "Marketing workspaces, campaigns and subscriptions",
    icon: Megaphone,
    metric: (m) => [
      { label: "Businesses", value: countMetric(m.totalBusinesses) },
      { label: "Users", value: countMetric(m.totalUsers) },
      { label: "Campaigns", value: countMetric(m.totalCampaigns) },
      { label: "Subscriptions", value: countMetric(m.activeSubscriptions) },
    ],
  },
  {
    id: "academy",
    name: "V79 Academy",
    description: "Course catalogue, learners and memberships",
    icon: GraduationCap,
    metric: (m) => [
      { label: "Courses", value: countMetric(m.totalCourses) },
      { label: "Published", value: countMetric(m.publishedCourses) },
      { label: "Learners", value: countMetric(m.totalLearners) },
      { label: "Memberships", value: countMetric(m.activeMemberships) },
    ],
  },
];

export function PlatformAdminOverview({ onOpen, onCustomers }: { onOpen: (product: Product) => void; onCustomers: () => void }) {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const request = useRef<AbortController | null>(null);
  const refresh = async () => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/admin/platform/overview", { cache: "no-store", signal: controller.signal });
      const payload = await response.json().catch(() => null);
      if (controller.signal.aborted) return;
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) setData(null);
        throw new Error(response.status === 401 || response.status === 403 ? "Sign in with an authorized platform administrator session." : payload?.error || `Platform overview failed (${response.status})`);
      }
      if (!payload || typeof payload !== "object" || !payload.hub || typeof payload.hub !== "object" || Array.isArray(payload.hub) ||
        !payload.apps || typeof payload.apps !== "object" || Array.isArray(payload.apps) || !Number.isFinite(Date.parse(payload.generatedAt))) {
        throw new Error("Platform statistics could not be verified.");
      }
      setData(payload); setNow(Date.now());
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Platform overview could not be loaded.");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  };
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => { request.current?.abort(); window.clearInterval(timer); };
  }, []);
  const age = data ? now - Date.parse(data.generatedAt) : 0;
  const stale = !!data && (!!error || age > 5 * 60 * 1000 || age < -60000);
  const availableCount = productConfig.filter(p => data?.apps?.[p.id]?.status === "ok").length;

  const issues = useMemo(() => {
    if (!data) return [] as Array<{ product: Product | "customers"; title: string; detail: string; severity: "error" | "warning" }>;
    const result: Array<{ product: Product | "customers"; title: string; detail: string; severity: "error" | "warning" }> = [];
    if ((data.hub?.provisioningCustomers || 0) > 0) {
      result.push({
        product: "customers",
        title: "Customers awaiting provisioning",
        detail: `${data.hub.provisioningCustomers} customer workspace(s) still have tenant-mapped apps pending.`,
        severity: "warning",
      });
    }

    for (const product of productConfig) {
      const item = data.apps?.[product.id];
      if (!item || item.status !== "ok") {
        result.push({ product: product.id, title: `${product.name} statistics unavailable`, detail: item?.error || "Platform statistics could not be retrieved.", severity: "error" });
      }
    }

    const pos = data.apps?.pos?.status === "ok" ? data.apps.pos.metrics || {} : {};
    if (Number(pos.inactiveTenants || 0) > 0) {
      result.push({ product: "pos", title: "Inactive POS tenants", detail: `${pos.inactiveTenants} tenant(s) are currently inactive.`, severity: "warning" });
    }

    const tiquet = data.apps?.tiquet?.status === "ok" ? data.apps.tiquet.metrics || {} : {};
    if (Number(tiquet.suspendedAccounts || 0) > 0) {
      result.push({ product: "tiquet", title: "Suspended Tiquet workspaces", detail: `${tiquet.suspendedAccounts} workspace(s) are suspended.`, severity: "warning" });
    }

    return result;
  }, [data]);

  return (
    <div className="v79-admin-overview">
      {error && <div role="alert" className="v79-notice">{error}</div>}
      {stale && <div role="status" className="v79-notice">Stale snapshot · these figures do not describe verified current conditions. Refresh to retrieve new statistics.</div>}
      <div className="v79-area-heading">
        <div><p className="v79-eyebrow">OPERATIONS AT A GLANCE</p><h2>Platform overview</h2><p>Customer lifecycle and application statistics. Statistics availability is not a service health check.</p></div>
        <button onClick={() => void refresh()} disabled={busy} className="v79-secondary"><RefreshCw size={16} className={busy ? "animate-spin" : ""} />{busy ? "Refreshing…" : "Refresh"}</button>
      </div>
      <section className="v79-admin-metrics" aria-label="Customer and statistics summary">
        <Summary icon={Building2} label="Customers" value={busy && !data ? "…" : String(countMetric(data?.hub?.customers))} />
        <Summary icon={CheckCircle2} label="Not suspended" value={busy && !data ? "…" : String(countMetric(data?.hub?.activeCustomers))} />
        <Summary icon={AlertTriangle} label="Provisioning" value={busy && !data ? "…" : String(countMetric(data?.hub?.provisioningCustomers))} />
        <Summary icon={CreditCard} label="Pending invites" value={busy && !data ? "…" : String(countMetric(data?.hub?.pendingInvitations))} />
        <Summary icon={Activity} label={stale ? "Statistics · stale snapshot" : "Statistics responses"} value={!data ? busy ? "…" : "—" : `${availableCount}/${productConfig.length}`} />
      </section>
      <section className="v79-area-card v79-admin-attention" aria-label="Attention needed">
        <div className="v79-area-heading"><div><h2>Attention needed</h2><p>{stale ? "Signals from the retained snapshot; current status is unverified." : "Review provisioning and application statistics that need a closer look."}</p></div><AlertTriangle size={20} /></div>
        {issues.length ? <div className="v79-admin-issues">{issues.map((issue, index) => <button key={issue.product + index} onClick={() => issue.product === "customers" ? onCustomers() : onOpen(issue.product)}>
          <span className="v79-issue-dot" data-severity={issue.severity} /><span><strong>{issue.title}</strong><small>{issue.detail}</small></span><ArrowRight size={17} />
        </button>)}</div> : <p className="v79-source-note">{!data ? "No verified snapshot is available yet." : "No configured attention signals in this snapshot. This does not establish service health."}</p>}
      </section>
      <div className="v79-area-heading"><div><h2>Your applications</h2><p>Open an application to manage its customers and configuration. Missing counts are shown as —.</p></div></div>
      <div className="v79-admin-app-grid">
        {productConfig.map(product => {
          const item = data?.apps?.[product.id];
          const available = item?.status === "ok";
          const Icon = product.icon;
          const metrics = product.metric(available ? item?.metrics || {} : {});
          const partial = available && metrics.some(m => m.value === "—");
          const status = !data ? busy ? "Loading" : "Not loaded" : stale ? "Stale snapshot" : busy ? "Refreshing" : !available ? "Statistics unavailable" : partial ? "Partial statistics" : "Statistics available";
          return <button key={product.id} onClick={() => onOpen(product.id)} className="v79-admin-app" data-product={product.id}>
            <div className="v79-card-top"><span className="v79-product-icon"><Icon className="w-5 h-5" /></span><span className="v79-data-status" data-state={stale || partial ? "warning" : !available ? "unknown" : "available"}>{status}</span></div>
            <h3>{product.name}</h3><p>{product.description}</p>
            <dl>{metrics.map(metric => <div key={metric.label}><dt>{metric.label}</dt><dd>{typeof metric.value === "number" ? metric.value.toLocaleString() : metric.value}</dd></div>)}</dl>
            <span className="v79-admin-app-footer">Manage application <ArrowRight size={16} /></span>
          </button>;
        })}
      </div>
      <p className="v79-source-note">Snapshot generated {data?.generatedAt ? new Date(data.generatedAt).toLocaleString() : "—"}. Snapshots older than five minutes are marked stale. “Not suspended” includes customers still provisioning.</p>
    </div>
  );
}

function Summary({ icon: Icon, label, value }: { icon: React.ComponentType<{className?:string}>; label:string; value:string }) {
  return <div className="v79-admin-metric"><Icon className="w-5 h-5" /><strong>{value}</strong><span>{label}</span></div>;
}
