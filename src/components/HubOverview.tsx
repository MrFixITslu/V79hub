import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CreditCard,
  GraduationCap,
  Headphones,
  Megaphone,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";
import "../workspace.css";
import { EcosystemApp, User, ViewState } from "../types";
import { appLaunchUrl } from "../lib/appLaunch";
import { countMetric, percentMetric, moneyMetric, numericMetric, summaryCurrency, openJobsMetric, hasUsableSummary, connectionCopy } from "../lib/dashboardTruth";

type ProductKey = "pos" | "ffpro" | "tiquet" | "marketing" | "academy";
type ProductStatus = "ok" | "needs_setup" | "unavailable" | "misconfigured" | "restricted" | "not_enabled" | "not_configured";

interface ProductSummary {
  status: ProductStatus;
  httpStatus?: number;
  metrics?: Record<string, any>;
  generatedAt?: string | null;
  sourceReportedAt?: string | null;
  error?: string | null;
}

interface DashboardSummary {
  generatedAt: string;
  apps: Record<ProductKey, ProductSummary>;
}

interface HubOverviewProps {
  ecosystemApps: EcosystemApp[];
  onNavigate: (view: ViewState) => void;
  user: User;
  organizationName?: string;
}

const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

const appCards: Array<{
  key: ProductKey;
  id: string;
  shortName: string;
  title: string;
  category: string;
  fallback: string;
  icon: typeof Wallet;
  iconClass: string;
  accent: string;
  accentSoft: string;
  border: string;
  description: string;
  metrics: (m: Record<string, any>) => Array<{ label: string; value: string }>;
}> = [
  {
    key: "tiquet",
    id: "app-tiquet",
    shortName: "Tiquet",
    title: "V79 Digital Tiquet",
    category: "Service operations",
    fallback: "https://tiquet.v79sl.com",
    icon: Headphones,
    iconClass: "text-[#62c7ff]",
    accent: "#0A86FF",
    accentSoft: "from-[#0A86FF]/24 to-[#0A86FF]/5",
    border: "hover:border-[#0A86FF]/65",
    description: "Customers, tickets, service delivery and team activity.",
    metrics: (m) => [
      { label: "Jobs", value: countMetric(m.jobs) },
      { label: "Clients", value: countMetric(m.clients) },
      { label: "Team", value: countMetric(m.teamMembers) },
    ],
  },
  {
    key: "ffpro",
    id: "app-ffpro",
    shortName: "FFPRO",
    title: "FFPRO by V79",
    category: "Financial intelligence",
    fallback: "https://ffpro.v79sl.com",
    icon: Wallet,
    iconClass: "text-[#a78bfa]",
    accent: "#8b5cf6",
    accentSoft: "from-[#8b5cf6]/24 to-[#8b5cf6]/5",
    border: "hover:border-[#8b5cf6]/65",
    description: "Cash flow, budgets, goals and business financial visibility.",
    metrics: (m) => [
      { label: "MTD net", value: moneyMetric(m.currentMonthNet, m) },
      { label: "Income", value: moneyMetric(m.currentMonthIncome, m) },
      { label: "Transactions", value: countMetric(m.transactionCount) },
    ],
  },
  {
    key: "marketing",
    id: "app-marketing",
    shortName: "Marketing",
    title: "V79 Digital Marketing",
    category: "Growth engine",
    fallback: "https://marketing.v79sl.com",
    icon: Megaphone,
    iconClass: "text-[#ff9a3d]",
    accent: "#FF7A00",
    accentSoft: "from-[#FF7A00]/24 to-[#FF7A00]/5",
    border: "hover:border-[#FF7A00]/65",
    description: "Campaigns, customer pipeline, content and marketing analytics.",
    metrics: (m) => [
      { label: "Campaigns", value: countMetric(m.activeCampaigns) },
      { label: "Customers", value: countMetric(m.customers) },
      { label: "AI credits", value: countMetric(m.aiCreditsRemaining) },
    ],
  },
  {
    key: "academy",
    id: "app-academy",
    shortName: "Academy",
    title: "V79 Digital Academy",
    category: "Learning and capability",
    fallback: "https://academy.v79sl.com/",
    icon: GraduationCap,
    iconClass: "text-[#52e6c2]",
    accent: "#10B981",
    accentSoft: "from-[#10B981]/24 to-[#10B981]/5",
    border: "hover:border-[#10B981]/65",
    description: "Learning progress, course access and certifications.",
    metrics: (m) => [
      { label: "Enrolled", value: countMetric(m.enrolledCourses) },
      { label: "Progress", value: percentMetric(m.overallProgressPercent) },
      { label: "Certificates", value: countMetric(m.certificates) },
    ],
  },
  {
    key: "pos",
    id: "app-v79pos",
    shortName: "V79 POS",
    title: "V79 Digital POS",
    category: "Commerce",
    fallback: "https://pos.v79sl.com",
    icon: CreditCard,
    iconClass: "text-[#ff6b72]",
    accent: "#EF4444",
    accentSoft: "from-[#EF4444]/24 to-[#EF4444]/5",
    border: "hover:border-[#EF4444]/65",
    description: "Sales, stock, purchasing and register operations.",
    metrics: (m) => [
      { label: "30d revenue", value: moneyMetric(m.revenue30d, m) },
      { label: "30d sales", value: countMetric(m.sales30d) },
      { label: "Open POs", value: countMetric(m.openPurchaseOrders) },
    ],
  },
];

function statusMeta(summary?: ProductSummary) {
  if (!summary) return { label: "Unknown", dot: "bg-slate-500", text: "text-slate-400", score: 0 };
  if (summary.status === "ok" && hasUsableSummary(summary)) return { label: "Data available", dot: "bg-emerald-400", text: "text-emerald-300", score: 100 };
  if (summary.status === "ok") return { label: "No metrics", dot: "bg-slate-500", text: "text-slate-400", score: 0 };
  if (summary.status === "restricted") return { label: "Restricted", dot: "bg-slate-400", text: "text-slate-300", score: 55 };
  if (summary.status === "not_enabled") return { label: "Not enabled", dot: "bg-slate-600", text: "text-slate-500", score: 15 };
  if (summary.status === "not_configured") return { label: "Not connected", dot: "bg-slate-500", text: "text-slate-400", score: 30 };
  if (summary.status === "needs_setup") return { label: "Ready to activate", dot: "bg-amber-400", text: "text-amber-300", score: 70 };
  if (summary.status === "misconfigured") return { label: "Needs attention", dot: "bg-amber-400", text: "text-amber-300", score: 45 };
  return { label: "Unavailable", dot: "bg-rose-400", text: "text-rose-300", score: 20 };
}

export function HubOverview({
  ecosystemApps,
  onNavigate,
  user,
  organizationName = "V79 Digital",
}: HubOverviewProps) {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const activeRequest = useRef<AbortController | null>(null);

  const loadDashboard = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    try {
      const response = await fetch("/api/dashboard/summary", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Dashboard data unavailable");
      const data = await response.json();
      if (controller.signal.aborted || activeRequest.current !== controller) return;
      setDashboard(data);
      setLoadError("");
    } catch {
      if (controller.signal.aborted || activeRequest.current !== controller) return;
      setDashboard(null); // A failed refresh must not display an old result as live.
      setLoadError("Current dashboard data is unavailable. Try refreshing.");
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === "hidden") {
        activeRequest.current?.abort();
        return;
      }
      void loadDashboard();
    };
    refreshWhenVisible();
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "hidden") void loadDashboard();
    }, 60000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      activeRequest.current?.abort();
    };
  }, [loadDashboard]);

  const appFor = (id: string, shortName: string) =>
    ecosystemApps.find((app) => app.id === id || app.shortName === shortName);
  const visibleAppCards = appCards.filter((card) => Boolean(appFor(card.id, card.shortName)));
  const visibleKeys = new Set(visibleAppCards.map((card) => card.key));

  const summaries = dashboard?.apps;
  const ffpro = summaries?.ffpro?.metrics || {};
  const tiquet = summaries?.tiquet?.metrics || {};
  const marketing = summaries?.marketing?.metrics || {};
  const academy = summaries?.academy?.metrics || {};
  const pos = summaries?.pos?.metrics || {};
  const availableSummaryCount = visibleAppCards.filter((card) => hasUsableSummary(summaries?.[card.key])).length;

  const openJobs = useMemo(() => openJobsMetric(tiquet.jobsByStatus), [tiquet.jobsByStatus]);

  const actions = useMemo(() => {
    const result: Array<{ title: string; detail: string; key: ProductKey }> = [];
    if (summaries?.ffpro?.status === "ok" && numericMetric(ffpro.currentMonthNet) !== null && Number(ffpro.currentMonthNet) < 0) {
      result.push({
        title: "Monthly cash flow needs attention",
        detail: summaryCurrency(ffpro)
          ? `Expenses exceed income by ${moneyMetric(Math.abs(Number(ffpro.currentMonthNet)), ffpro)} this month.`
          : "Expenses exceed income this month; source currency is unavailable.",
        key: "ffpro",
      });
    }
    if (summaries?.tiquet?.status === "ok" && openJobs !== null && openJobs > 0) {
      result.push({
        title: `${whole.format(openJobs)} open service job${openJobs === 1 ? "" : "s"}`,
        detail: "Review ownership and service deadlines in V79 Digital Tiquet.",
        key: "tiquet",
      });
    }
    if (summaries?.marketing?.status === "ok" && numericMetric(marketing.activeCampaigns) === 0) {
      result.push({
        title: "No active marketing campaign",
        detail: "Marketing is connected, but there is no active campaign right now.",
        key: "marketing",
      });
    }
    if (summaries?.pos?.status === "ok" && numericMetric(pos.openPurchaseOrders) !== null && Number(pos.openPurchaseOrders) > 0) {
      result.push({
        title: "Purchase orders require follow-up",
        detail: `${countMetric(pos.openPurchaseOrders)} POS purchase order(s) are still open.`,
        key: "pos",
      });
    }
    return result.slice(0, 5);
  }, [
    summaries,
    ffpro.currentMonthNet,
    openJobs,
    marketing.activeCampaigns,
    pos.openPurchaseOrders,
  ]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const lastUpdated = dashboard?.generatedAt
    ? new Date(dashboard.generatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "-";
  const attentionLabel = loadError
    ? "Dashboard update failed"
    : !dashboard
      ? "Checking app signals"
      : visibleAppCards.length === 0
        ? "No enabled applications"
      : actions.length === 0
        ? "No new action alerts"
        : `${actions.length} item${actions.length === 1 ? "" : "s"} need attention`;

  const metricCards = [
    {
      key: "pos",
      label: "Sales · last 30 days",
      value: summaries?.pos?.status === "ok" ? moneyMetric(pos.revenue30d, pos) : "—",
      detail: summaries?.pos?.status === "ok"
        ? (summaryCurrency(pos) ? `${countMetric(pos.sales30d)} completed sales · ${summaryCurrency(pos)}` : "POS currency not reported")
        : "Awaiting POS data",
      icon: CreditCard,
      color: "text-[#ff6b72]",
      glow: "from-[#EF4444]/20 to-transparent",
    },
    {
      key: "ffpro",
      label: "Net cash flow · this month",
      value: summaries?.ffpro?.status === "ok" ? moneyMetric(ffpro.currentMonthNet, ffpro) : "—",
      detail: summaries?.ffpro?.status === "ok" ? `${countMetric(ffpro.transactionCount)} transactions this period${summaryCurrency(ffpro) ? "" : " · currency unknown"}` : "Awaiting finance data",
      icon: Wallet,
      color: "text-[#a78bfa]",
      glow: "from-[#8b5cf6]/22 to-transparent",
    },
    {
      key: "tiquet",
      label: "Open service jobs",
      value: summaries?.tiquet?.status === "ok" && openJobs !== null ? whole.format(openJobs) : "—",
      detail: summaries?.tiquet?.status === "ok" ? `Current workload · ${countMetric(tiquet.clients)} clients` : "Awaiting service data",
      icon: Headphones,
      color: "text-[#62c7ff]",
      glow: "from-[#0A86FF]/22 to-transparent",
    },
    {
      key: "marketing",
      label: "Active campaigns",
      value: summaries?.marketing?.status === "ok" ? countMetric(marketing.activeCampaigns) : "—",
      detail: summaries?.marketing?.status === "ok" ? `Current activity · ${countMetric(marketing.customers)} customers` : "Awaiting marketing data",
      icon: Megaphone,
      color: "text-[#ff9a3d]",
      glow: "from-[#FF7A00]/22 to-transparent",
    },
  ] as const;
  const visibleMetricCards = metricCards.filter((metric) => visibleKeys.has(metric.key));

  return (
    <div className="v79-workspace">
      <div className="v79-dashboard hub-dashboard">
        <section className="v79-hero" aria-labelledby="workspace-welcome">
          <div className="v79-hero-copy">
            <div className="v79-eyebrow"><Sparkles size={16} aria-hidden="true" /> VISION79 BUSINESS WORKSPACE</div>
            <h1 id="workspace-welcome">{greeting}{user.fullName ? `, ${user.fullName.trim().split(/\s+/)[0]}` : ""}.</h1>
            <p>Your business, one command centre.</p>
            <div className="v79-hero-actions">
              <button type="button" onClick={() => onNavigate("connections")} className="v79-primary">Explore my apps <ArrowUpRight size={18} /></button>
              <span>{organizationName}</span>
            </div>
          </div>
          <aside className="v79-focus" aria-label="Workspace activity summary">
            <div className="v79-eyebrow"><span className="v79-focus-dot" /> TODAY’S FOCUS</div>
            <h2>{attentionLabel}</h2>
            <p>From available app reports. Missing data is never an all-clear.</p>
            <div className="v79-focus-footer">
              <span>Hub checked <strong>{lastUpdated}</strong></span>
              <button type="button" onClick={() => void loadDashboard()} aria-label="Refresh dashboard" title="Refresh dashboard" className="v79-refresh">
                <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
              </button>
            </div>
          </aside>
        </section>

        {loadError && <div className="v79-error" role="alert"><AlertTriangle size={20} />{loadError}</div>}

        <section className="v79-apps" aria-labelledby="workspace-apps">
          <div className="v79-section-heading">
            <div><div className="v79-eyebrow">YOUR CONNECTED TOOLS</div><h2 id="workspace-apps">Your workspace apps</h2><p>Everything you need to move your business forward.</p></div>
            <button onClick={() => onNavigate("connections")} className="v79-text-button">Manage apps <ArrowUpRight size={17} /></button>
          </div>
          <div className="v79-app-grid">
            {visibleAppCards.map((card) => {
              const app = appFor(card.id, card.shortName);
              const summary = summaries?.[card.key];
              const meta = statusMeta(summary);
              const metrics = card.metrics(summary?.metrics || {}).slice(0, 2);
              const launchUrl = appLaunchUrl(app, card.fallback);
              const Icon = card.icon;
              return (
                <a key={card.key} href={launchUrl || undefined} target={launchUrl ? "_blank" : undefined}
                  rel={launchUrl ? "noopener noreferrer" : undefined} aria-disabled={!launchUrl}
                  className="v79-app-card" data-product={card.key}>
                  <div className="v79-card-top"><span className="v79-product-icon"><Icon size={23} /></span><span className="v79-status" data-status={meta.label === "No metrics" ? "unknown" : summary?.status || "unknown"}><span />{meta.label}</span></div>
                  <div className="v79-card-title"><h3>{card.shortName}</h3><span>{card.category}</span></div>
                  <p className="v79-card-description">{card.description}</p>
                  <dl className="v79-card-metrics">{metrics.map((metric) => <div key={metric.label}><dt>{metric.label}</dt><dd data-long={metric.value.length > 8} title={metric.value}>{summary?.status === "ok" ? metric.value : "—"}</dd></div>)}</dl>
                  <div className="v79-card-source" title={summary?.sourceReportedAt || "Source timestamp unavailable"}>
                    {summary?.sourceReportedAt && Number.isFinite(Date.parse(summary.sourceReportedAt))
                      ? `Product reported ${new Date(summary.sourceReportedAt).toLocaleDateString()}` : "Product source timestamp unavailable"}
                  </div>
                  <div className="v79-card-footer"><span>{launchUrl ? "Ready to open" : app?.accessMessage || "Setup pending"}</span><span className="v79-open">{launchUrl ? "Open app" : "Unavailable"}<ArrowUpRight size={17} /></span></div>
                </a>
              );
            })}
          </div>
          {visibleAppCards.length === 0 && <div className="v79-empty"><Activity size={24} /><h3>No enabled applications</h3><p>Your workspace apps will appear here when access is enabled.</p></div>}
        </section>

        <section className="v79-performance" aria-labelledby="workspace-performance">
          <div className="v79-section-heading"><div><h2 id="workspace-performance">Performance overview</h2><p>Connected product metrics, with their own reporting periods.</p></div><span className="v79-section-note"><Activity size={16} />{availableSummaryCount} of {visibleAppCards.length} sources reporting</span></div>
          <div className="v79-kpi-grid">{visibleMetricCards.map((metric) => {
            const Icon = metric.icon;
            const summary = summaries?.[metric.key];
            const meta = statusMeta(summary);
            return <article key={metric.key} className="v79-kpi" data-product={metric.key}>
              <div className="v79-kpi-top"><span className="v79-product-icon"><Icon size={19} /></span><span className="v79-status" data-status={meta.label === "No metrics" ? "unknown" : summary?.status || "unknown"}><span />{meta.label}</span></div>
              <h3>{metric.label}</h3><div className="v79-kpi-value" data-long={metric.value.length > 8} title={metric.value}>{metric.value}</div><p>{metric.detail}</p>
            </article>;
          })}</div>
        </section>

        <div className="v79-bottom-grid">
          <section className="v79-attention" aria-labelledby="workspace-attention">
            <div className="v79-section-heading"><div><h2 id="workspace-attention">Needs your attention</h2><p>A clearer view of what to do next.</p></div><span className="v79-count">{actions.length}</span></div>
            <div className="v79-action-list">{actions.length ? actions.map((action) => {
              const card = appCards.find((item) => item.key === action.key)!;
              const Icon = card.icon;
              const launchUrl = appLaunchUrl(appFor(card.id, card.shortName), card.fallback);
              const actionText = action.key === "ffpro" ? "Review cash flow" : action.key === "tiquet" ? "Review service jobs" : action.key === "pos" ? "Review purchase orders" : action.key === "marketing" ? "Open marketing" : "Review in app";
              return <div key={action.title} className="v79-action" data-product={card.key}><span className="v79-product-icon"><Icon size={20} /></span><div><h3>{action.title}</h3><p>{action.detail}</p>{launchUrl && <a href={launchUrl} target="_blank" rel="noopener noreferrer">{actionText}<ArrowUpRight size={15} /></a>}</div></div>;
            }) : <div className="v79-empty" role="status">
              {!dashboard || loadError || availableSummaryCount === 0 ? <Activity size={24} /> : <CheckCircle2 size={24} />}
              <h3>{!dashboard || loadError || availableSummaryCount === 0 ? "No verified action insights available" : "No action alerts reported by available sources"}</h3>
              <p>Only connected apps with available data contribute alerts. Check your apps for complete activity.</p>
            </div>}</div>
          </section>
          <section className="v79-availability" aria-labelledby="workspace-availability">
            <span className="v79-availability-icon"><ShieldCheck size={25} /></span><div className="v79-eyebrow">WORKSPACE VISIBILITY</div><h2 id="workspace-availability">Application data availability</h2>
            <p>{connectionCopy(visibleAppCards.length, availableSummaryCount, Boolean(dashboard), Boolean(loadError))}</p>
            {user.platformOperator && <div className="v79-source-list">{visibleAppCards.map((card) => {
              const meta = statusMeta(summaries?.[card.key]);
              return <div key={card.key}><span>{card.shortName}</span><span className="v79-status" data-status={meta.label === "No metrics" ? "unknown" : summaries?.[card.key]?.status || "unknown"}><span />{meta.label}</span></div>;
            })}</div>}
          </section>
        </div>
        <footer className="v79-footer"><strong>Vision79 <span>From Idea to Advantage.</span></strong><span>Private data stays in each product. Your Hub brings the signals together.</span></footer>
      </div>
    </div>
  );
}
