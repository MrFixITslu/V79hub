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
    <div className="vision79-release-v1 min-h-full bg-[#07111f] text-slate-100 pb-24 lg:pb-10">
      <div className="vision79-dashboard hub-dashboard mx-auto w-full max-w-[1540px] px-4 sm:px-5 xl:px-7 py-6 space-y-5">
        <section className="vision79-command-hero hub-hero relative isolate overflow-hidden rounded-[30px] border border-[#1a3854]">
          <div aria-hidden="true" className="vision79-hero-glow pointer-events-none absolute inset-0" />
          <div className="relative z-10 grid gap-7 p-6 sm:p-9 lg:p-10 xl:grid-cols-[minmax(0,1.4fr)_minmax(290px,0.6fr)] xl:items-center">
            <div>
              <div className="vision79-identity inline-flex items-center gap-3">
                <span className="vision79-mark inline-flex h-11 w-11 items-center justify-center rounded-2xl font-black tracking-tight text-white">V79</span>
                <span className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-[#82d8ff]">Vision79 / Business workspace</span>
              </div>
              <p className="mt-8 text-[11px] font-bold uppercase tracking-[0.27em] text-[#8ab9e4]">From Idea to Advantage.</p>
              <h1 className="vision79-main-greeting mt-3 max-w-[780px] text-[clamp(2.4rem,5vw,4.6rem)] leading-[1.08] font-black tracking-[-0.055em] text-white">
                {greeting}{user.fullName ? `, ${user.fullName.trim().split(/\s+/)[0]}` : ""}
              </h1>
              <p className="mt-5 text-base sm:text-lg leading-relaxed font-medium text-[#d2e5f6]">Your business, one command centre.</p>
              <p className="mt-2 max-w-[590px] text-sm leading-relaxed text-[#9ab5ce]">Open your connected tools, review verified activity and stay focused on what matters.</p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <button type="button" onClick={() => onNavigate("connections")} className="vision79-primary-action inline-flex min-h-12 items-center gap-2 rounded-2xl px-5 py-3 text-sm font-bold text-[#071b31] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-300">
                  Explore my apps <ArrowUpRight className="h-4 w-4" />
                </button>
                <span className="rounded-full border border-white/15 bg-white/[0.06] px-3.5 py-2 text-[11px] font-semibold text-[#bdcee2]">{organizationName}</span>
              </div>
            </div>
            <aside className="vision79-focus-panel rounded-[25px] border border-white/15 bg-[#091d35]/85 p-5 sm:p-6" aria-label="Workspace activity summary">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[10px] font-black uppercase tracking-[0.24em] text-[#9dc6ea]">Today's focus</span>
                <Activity className="h-5 w-5 text-[#72d9ff]" aria-hidden="true" />
              </div>
              <div className="mt-7 text-[26px] leading-snug font-extrabold tracking-tight text-white">{attentionLabel}</div>
              <p className="mt-3 text-xs leading-relaxed text-[#a6bfd7]">Based on available connected app data. Missing reports never count as all-clear.</p>
              <div className="mt-7 flex items-center justify-between gap-3 border-t border-white/10 pt-4">
                <div>
                  <div className="text-[10px] uppercase tracking-widest font-bold text-[#799dbe]">Latest Hub check</div>
                  <div className="mt-1 text-sm font-bold text-white">{lastUpdated}</div>
                </div>
                <button type="button" onClick={() => void loadDashboard()} aria-label="Refresh dashboard" title="Refresh dashboard" className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-[#55c7ff]/35 bg-[#55c7ff]/10 text-[#82d8ff] transition-colors hover:bg-[#55c7ff]/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-300">
                  <RefreshCw className={`h-5 w-5 ${loading ? "animate-spin" : ""}`} />
                </button>
              </div>
            </aside>
          </div>
        </section>

        {loadError && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {loadError}
          </div>
        )}

        <section className="vision79-app-section rounded-[22px] border border-[#1a3854] bg-[#091728] overflow-hidden">
          <div className="px-5 py-4 border-b border-[#18324b] flex items-center justify-between gap-4">
            <div>
              <div className="text-base font-bold text-white">Your workspace apps</div>
              <div className="text-[10px] text-slate-500 mt-0.5">Your tools in one place. Only applications enabled for this workspace are shown.</div>
            </div>
            <button onClick={() => onNavigate("connections")} className="text-[10px] font-bold text-[#55c7ff] hover:text-white">
              Manage apps
            </button>
          </div>
          <div className="p-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
            {visibleAppCards.map((card) => {
              const app = appFor(card.id, card.shortName);
              const summary = summaries?.[card.key];
              const meta = statusMeta(summary);
              const metrics = card.metrics(summary?.metrics || {}).slice(0, 2);
              const launchUrl = appLaunchUrl(app, card.fallback);
              const Icon = card.icon;
              return (
                <a
                  key={card.key}
                  href={launchUrl || undefined}
                  target={launchUrl ? "_blank" : undefined}
                  rel={launchUrl ? "noopener noreferrer" : undefined}
                  aria-disabled={!launchUrl}
                  className={`vision79-product-card hub-product-card group relative overflow-hidden min-h-[206px] rounded-2xl border border-[#1d3c58] bg-gradient-to-br ${card.accentSoft} p-4 no-underline text-inherit transition-all duration-200 hover:-translate-y-1 ${card.border} ${!launchUrl ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  <div className="absolute -right-8 -bottom-10 w-28 h-28 rounded-full blur-2xl opacity-25" style={{ backgroundColor: card.accent }} />
                  <div className="relative h-full flex flex-col">
                    <div className="flex items-start justify-between gap-3">
                      <div className="w-10 h-10 rounded-xl border border-white/10 bg-[#07111f]/85 flex items-center justify-center shadow-lg">
                        <Icon className={`w-5 h-5 ${card.iconClass}`} />
                      </div>
                      <span className={`inline-flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] ${meta.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} /> {meta.label}
                      </span>
                    </div>
                    <div className="mt-3">
                      <div className="text-[13px] font-black text-white leading-tight">{card.title}</div>
                      <div className="mt-1 text-[10px] font-medium text-slate-300">{card.category}</div>
                       <p className="mt-2 text-[11px] leading-relaxed text-slate-400 line-clamp-2">{card.description}</p>
                    </div>
                    <div className="mt-3 flex gap-4">
                      {metrics.map((metric) => (
                        <div key={metric.label} className="min-w-0">
                          <div className="text-[7px] uppercase tracking-wide text-slate-600">{metric.label}</div>
                          <div className="mt-0.5 text-[10px] font-bold text-slate-200 truncate">
                            {summary?.status === "ok" ? metric.value : "-"}
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 text-[9px] text-slate-500 truncate" title={summary?.sourceReportedAt || "Source timestamp unavailable"}>
                      {summary?.sourceReportedAt && Number.isFinite(Date.parse(summary.sourceReportedAt))
                        ? `Product reported ${new Date(summary.sourceReportedAt).toLocaleDateString()}`
                        : "Product source timestamp unavailable"}
                    </div>
                    <div className="mt-auto pt-3 flex items-center justify-between">
                      <span className="text-[9px] text-slate-600">{launchUrl ? "Ready to open" : app?.accessMessage || "Setup pending"}</span>
                      <span className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-black/10 px-2.5 py-1.5 text-[9px] font-bold" style={{ color: card.accent }}>
                        Open <ArrowUpRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                      </span>
                    </div>
                  </div>
                </a>
              );
            })}
          </div>
        </section>

        <section className="vision79-performance">
          <div className="mb-2 px-1">
            <div className="text-base font-bold text-white">Performance overview</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Live metrics from connected products, with source-specific reporting periods.</div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            {visibleMetricCards.map((metric) => {
              const Icon = metric.icon;
              const summary = summaries?.[metric.key];
              const meta = statusMeta(summary);
              return (
                <div
                  key={metric.key}
                  className="vision79-metric-card hub-kpi group relative overflow-hidden rounded-[20px] border border-[#1a3854] bg-[#0a1727] p-5 transition-transform duration-200 hover:-translate-y-0.5 hover:border-[#2b5275]"
                >
                  <div className={`absolute inset-0 bg-gradient-to-br ${metric.glow} opacity-90 pointer-events-none`} />
                  <div className="relative">
                    <div className="flex items-start justify-between gap-3">
                      <div className="w-10 h-10 rounded-xl bg-[#07111f]/75 border border-white/10 flex items-center justify-center">
                        <Icon className={`w-5 h-5 ${metric.color}`} />
                      </div>
                      <span className={`inline-flex items-center gap-1.5 text-[9px] font-semibold ${meta.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                        {meta.label}
                      </span>
                    </div>
                    <div className="mt-4 text-[10px] uppercase tracking-[0.13em] text-slate-500 font-bold">{metric.label}</div>
                    <div className="mt-2 text-[30px] leading-none font-black tracking-tight text-white truncate" title={metric.value}>{metric.value}</div>
                    <div className="mt-3 text-[11px] leading-relaxed text-slate-400">{metric.detail}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="rounded-[22px] border border-[#1a3854] bg-[#091728] overflow-hidden">
          <div className="px-5 py-4 border-b border-[#18324b] flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-bold text-white">Needs your attention</div>
              <div className="text-[10px] text-slate-500 mt-0.5">The most useful next actions across your business apps</div>
            </div>
            <Activity className="w-4 h-4 text-[#55c7ff]" />
          </div>
          <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
            {actions.length ? (
              actions.map((action) => {
                const card = appCards.find((item) => item.key === action.key)!;
                const app = appFor(card.id, card.shortName);
                const launchUrl = appLaunchUrl(app, card.fallback);
                const Icon = card.icon;
                const actionText =
                  action.key === "ffpro" ? "Review cash flow" :
                  action.key === "tiquet" ? "Review open jobs" :
                  action.key === "marketing" ? "Open marketing" :
                  "Review in app";
                return (
                  <div key={action.title} className="rounded-2xl border border-[#18324b] bg-[#07121f] p-4 flex items-start gap-3">
                    <div className="w-9 h-9 shrink-0 rounded-xl border border-white/10 flex items-center justify-center" style={{ backgroundColor: `${card.accent}18` }}>
                      <Icon className={`w-4 h-4 ${card.iconClass}`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-bold text-slate-100">{action.title}</div>
                      <div className="text-[10px] text-slate-500 mt-1 leading-relaxed">{action.detail}</div>
                      {launchUrl && (
                        <a href={launchUrl} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-[10px] font-bold text-[#55c7ff] hover:text-white no-underline">
                          {actionText} <ArrowUpRight className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>
                );
              })
            ) : (
              <div className={`lg:col-span-2 rounded-2xl border p-4 flex items-start gap-3 ${!dashboard || loadError || availableSummaryCount === 0 ? "border-slate-500/20 bg-slate-500/[0.07]" : "border-emerald-500/20 bg-emerald-500/[0.07]"}`} role="status">
                {!dashboard || loadError || availableSummaryCount === 0 ? <Activity className="w-4 h-4 text-slate-400 mt-0.5" /> : <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5" />}
                <div>
                  <div className={`text-xs font-bold ${!dashboard || loadError || availableSummaryCount === 0 ? "text-slate-200" : "text-emerald-200"}`}>{!dashboard || loadError || availableSummaryCount === 0 ? "No verified action insights available" : "No action alerts reported by available sources"}</div>
                  <div className="text-[10px] text-slate-500 mt-1">Only connected apps with available data contribute alerts. Check your apps for complete activity.</div>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="rounded-[22px] border border-[#1a3854] bg-[#091728] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#0A86FF]/12 border border-[#0A86FF]/25 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-[#55c7ff]" />
            </div>
            <div>
              <div className="text-[11px] font-bold text-white">Application data availability</div>
              <div className="text-[9px] text-slate-500 mt-1">
                {connectionCopy(visibleAppCards.length, availableSummaryCount, Boolean(dashboard), Boolean(loadError))}
              </div>
            </div>
          </div>
          {user.platformOperator && (
            <div className="flex flex-wrap gap-2">
              {visibleAppCards.map((card) => {
                const meta = statusMeta(summaries?.[card.key]);
                return (
                  <div key={card.key} className="rounded-full border border-[#1d3c58] bg-[#07121f] px-2.5 py-1.5 flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                    <span className="text-[8px] font-bold text-slate-400">{card.shortName}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <footer className="px-1 pt-1 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[9px] text-slate-600">
          <span>V79 Digital - From Idea to Advantage.</span>
          <span>Private app data remains inside each product; the Hub displays aggregate operational signals.</span>
        </footer>
      </div>
    </div>
  );
}
