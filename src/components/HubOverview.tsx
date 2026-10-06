import { useCallback, useEffect, useMemo, useState } from "react";
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

type ProductKey = "pos" | "ffpro" | "tiquet" | "marketing" | "academy";
type ProductStatus = "ok" | "needs_setup" | "unavailable" | "misconfigured" | "restricted" | "not_enabled" | "not_configured";

interface ProductSummary {
  status: ProductStatus;
  httpStatus?: number;
  metrics?: Record<string, any>;
  generatedAt?: string | null;
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

const money = new Intl.NumberFormat("en-LC", {
  style: "currency",
  currency: "XCD",
  maximumFractionDigits: 0,
});
const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const n = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);

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
      { label: "Jobs", value: whole.format(n(m.jobs)) },
      { label: "Clients", value: whole.format(n(m.clients)) },
      { label: "Team", value: whole.format(n(m.teamMembers)) },
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
      { label: "MTD net", value: money.format(n(m.currentMonthNet)) },
      { label: "Income", value: money.format(n(m.currentMonthIncome)) },
      { label: "Transactions", value: whole.format(n(m.transactionCount)) },
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
      { label: "Campaigns", value: whole.format(n(m.activeCampaigns)) },
      { label: "Customers", value: whole.format(n(m.customers)) },
      { label: "AI credits", value: whole.format(n(m.aiCreditsRemaining)) },
    ],
  },
  {
    key: "academy",
    id: "app-academy",
    shortName: "Academy",
    title: "V79 Digital Academy",
    category: "Learning and capability",
    fallback: "https://v79academy.v79sl.com/academy",
    icon: GraduationCap,
    iconClass: "text-[#52e6c2]",
    accent: "#10B981",
    accentSoft: "from-[#10B981]/24 to-[#10B981]/5",
    border: "hover:border-[#10B981]/65",
    description: "Learning progress, course access and certifications.",
    metrics: (m) => [
      { label: "Enrolled", value: whole.format(n(m.enrolledCourses)) },
      { label: "Progress", value: `${whole.format(n(m.overallProgressPercent))}%` },
      { label: "Certificates", value: whole.format(n(m.certificates)) },
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
      { label: "Sales", value: whole.format(n(m.sales)) },
      { label: "Products", value: whole.format(n(m.products)) },
      { label: "Open POs", value: whole.format(n(m.openPurchaseOrders)) },
    ],
  },
];

function statusMeta(summary?: ProductSummary) {
  if (!summary) return { label: "Loading", dot: "bg-slate-500", text: "text-slate-400", score: 35 };
  if (summary.status === "ok") return { label: "Operational", dot: "bg-emerald-400", text: "text-emerald-300", score: 100 };
  if (summary.status === "restricted") return { label: "Restricted", dot: "bg-slate-400", text: "text-slate-300", score: 55 };
  if (summary.status === "not_enabled" || summary.status === "not_configured") return { label: "Not enabled", dot: "bg-slate-600", text: "text-slate-500", score: 15 };
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

  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/dashboard/summary", { cache: "no-store" });
      if (!response.ok) throw new Error(`Dashboard request failed (${response.status})`);
      setDashboard(await response.json());
      setLoadError("");
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Dashboard unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
    const timer = window.setInterval(loadDashboard, 60000);
    return () => window.clearInterval(timer);
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
  const onlineCount = visibleAppCards.filter((card) => summaries?.[card.key]?.status === "ok").length;

  const openJobs = useMemo(() => {
    const byStatus =
      tiquet.jobsByStatus && typeof tiquet.jobsByStatus === "object" ? tiquet.jobsByStatus : {};
    return Object.entries(byStatus).reduce((sum, [status, count]) => {
      return /resolved|closed|complete/i.test(status) ? sum : sum + n(count);
    }, 0);
  }, [tiquet.jobsByStatus]);

  const actions = useMemo(() => {
    const result: Array<{ title: string; detail: string; key: ProductKey }> = [];
    if (summaries?.ffpro?.status === "ok" && n(ffpro.currentMonthNet) < 0) {
      result.push({
        title: "Monthly cash flow needs attention",
        detail: `Expenses exceed income by ${money.format(Math.abs(n(ffpro.currentMonthNet)))} this month.`,
        key: "ffpro",
      });
    }
    if (summaries?.tiquet?.status === "ok" && openJobs > 0) {
      result.push({
        title: `${whole.format(openJobs)} open service job${openJobs === 1 ? "" : "s"}`,
        detail: "Review ownership and service deadlines in V79 Digital Tiquet.",
        key: "tiquet",
      });
    }
    if (summaries?.marketing?.status === "ok" && n(marketing.activeCampaigns) === 0) {
      result.push({
        title: "No active marketing campaign",
        detail: "Marketing is connected, but there is no active campaign right now.",
        key: "marketing",
      });
    }
    if (
      summaries?.academy?.status === "ok" &&
      n(academy.enrolledCourses) > 0 &&
      n(academy.overallProgressPercent) < 100
    ) {
      result.push({
        title: "Training is in progress",
        detail: `Academy progress is ${whole.format(n(academy.overallProgressPercent))}% with ${whole.format(n(academy.certificates))} certificate(s).`,
        key: "academy",
      });
    }
    if (summaries?.pos?.status === "ok" && n(pos.openPurchaseOrders) > 0) {
      result.push({
        title: "Purchase orders require follow-up",
        detail: `${whole.format(n(pos.openPurchaseOrders))} POS purchase order(s) are still open.`,
        key: "pos",
      });
    }
    return result.slice(0, 5);
  }, [
    summaries,
    ffpro.currentMonthNet,
    openJobs,
    marketing.activeCampaigns,
    academy.enrolledCourses,
    academy.overallProgressPercent,
    academy.certificates,
    pos.openPurchaseOrders,
  ]);

  const firstName = (user.fullName || user.username || "there").trim().split(/\s+/)[0];
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  const metricCards = [
    {
      key: "pos",
      label: "POS sales",
      value: summaries?.pos?.status === "ok" ? whole.format(n(pos.sales)) : "-",
      detail: summaries?.pos?.status === "ok" ? `${whole.format(n(pos.products))} products tracked` : "Awaiting live feed",
      icon: CreditCard,
      color: "text-[#ff6b72]",
      glow: "from-[#EF4444]/20 to-transparent",
    },
    {
      key: "ffpro",
      label: "FFPRO cash flow",
      value: summaries?.ffpro?.status === "ok" ? money.format(n(ffpro.currentMonthNet)) : "-",
      detail: summaries?.ffpro?.status === "ok" ? `${whole.format(n(ffpro.transactionCount))} transactions` : "Awaiting live feed",
      icon: Wallet,
      color: "text-[#a78bfa]",
      glow: "from-[#8b5cf6]/22 to-transparent",
    },
    {
      key: "tiquet",
      label: "Tiquet open jobs",
      value: summaries?.tiquet?.status === "ok" ? whole.format(openJobs) : "-",
      detail: summaries?.tiquet?.status === "ok" ? `${whole.format(n(tiquet.clients))} clients` : "Awaiting live feed",
      icon: Headphones,
      color: "text-[#62c7ff]",
      glow: "from-[#0A86FF]/22 to-transparent",
    },
    {
      key: "marketing",
      label: "Marketing campaigns",
      value: summaries?.marketing?.status === "ok" ? whole.format(n(marketing.activeCampaigns)) : "-",
      detail: summaries?.marketing?.status === "ok" ? `${whole.format(n(marketing.customers))} customers` : "Awaiting live feed",
      icon: Megaphone,
      color: "text-[#ff9a3d]",
      glow: "from-[#FF7A00]/22 to-transparent",
    },
    {
      key: "academy",
      label: "Academy progress",
      value: summaries?.academy?.status === "ok" ? `${whole.format(n(academy.overallProgressPercent))}%` : "-",
      detail: summaries?.academy?.status === "ok" ? `${whole.format(n(academy.certificates))} certificates` : "Awaiting live feed",
      icon: GraduationCap,
      color: "text-[#52e6c2]",
      glow: "from-[#10B981]/22 to-transparent",
    },
  ] as const;
  const visibleMetricCards = metricCards.filter((metric) => visibleKeys.has(metric.key));

  return (
    <div className="min-h-full bg-[#07111f] text-slate-100 pb-24 lg:pb-10">
      <div className="mx-auto w-full max-w-[1540px] px-4 sm:px-5 xl:px-7 py-5 space-y-4">
        <section className="relative overflow-hidden rounded-[24px] border border-[#1a3854] bg-[#091728] shadow-[0_28px_80px_rgba(0,0,0,.26)]">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(10,134,255,.24),transparent_35%),radial-gradient(circle_at_95%_65%,rgba(255,122,0,.12),transparent_28%)]" />
          <div className="absolute inset-y-0 right-0 w-[58%] opacity-30 bg-[linear-gradient(120deg,transparent_5%,rgba(10,134,255,.16)_38%,rgba(255,122,0,.13)_70%,transparent_100%)]" />
          <div className="relative px-5 sm:px-7 py-6 flex flex-col xl:flex-row xl:items-center xl:justify-between gap-5">
            <div>
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-[#65c9ff]">
                <Sparkles className="w-3.5 h-3.5" />
                {organizationName}
              </div>
              <h1 className="mt-2 text-3xl sm:text-[38px] leading-tight font-black tracking-[-0.03em] text-white">
                {greeting}, <span className="text-[#55c7ff]">{firstName}</span>
              </h1>
              <p className="mt-2 text-sm text-slate-400 max-w-2xl">
                Your business pulse: performance, customer activity and the items that need your attention.
              </p>
            </div>
            <div className="flex items-center gap-3 xl:pl-8">
              <div className="rounded-2xl border border-[#21405d] bg-[#081422]/80 px-5 py-3 min-w-[135px]">
                <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 font-bold">Live feeds</div>
                <div className="mt-1 flex items-baseline gap-1.5">
                  <span className="text-2xl font-black text-white">{loading ? "..." : onlineCount}</span>
                  <span className="text-xs text-slate-500">of {visibleAppCards.length}</span>
                </div>
              </div>
              <div className="hidden sm:block h-12 w-px bg-gradient-to-b from-transparent via-[#36536d] to-transparent" />
              <div className="hidden sm:block">
                <div className="text-[9px] font-black uppercase tracking-[0.18em] text-[#ff9a3d]">From Idea</div>
                <div className="text-[9px] font-black uppercase tracking-[0.18em] text-[#ff9a3d]">to Advantage.</div>
              </div>
              <button
                onClick={() => void loadDashboard()}
                className="w-11 h-11 rounded-xl border border-[#21405d] bg-[#0b1a2c] hover:bg-[#10243b] flex items-center justify-center transition-colors"
                title="Refresh dashboard"
              >
                <RefreshCw className={`w-4 h-4 text-[#55c7ff] ${loading ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>
        </section>

        {loadError && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {loadError}
          </div>
        )}

        <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
          {visibleMetricCards.map((metric) => {
            const Icon = metric.icon;
            const summary = summaries?.[metric.key];
            const meta = statusMeta(summary);
            return (
              <div
                key={metric.key}
                className="group relative overflow-hidden rounded-2xl border border-[#1a3854] bg-[#0a1727] p-4 transition-transform duration-200 hover:-translate-y-0.5 hover:border-[#2b5275]"
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
                  <div className="mt-1 text-[24px] leading-none font-black tracking-tight text-white truncate">{metric.value}</div>
                  <div className="mt-2 text-[10px] text-slate-500 truncate">{metric.detail}</div>
                </div>
              </div>
            );
          })}
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-4">
          <div className="rounded-[22px] border border-[#1a3854] bg-[#091728] overflow-hidden">
            <div className="px-5 py-4 border-b border-[#18324b] flex items-center justify-between gap-4">
              <div>
                <div className="text-sm font-bold text-white">Your V79 apps</div>
                <div className="text-[10px] text-slate-500 mt-0.5">Availability of the modules enabled for this workspace</div>
              </div>
              <button
                onClick={() => onNavigate("connections")}
                className="text-[10px] font-bold text-[#55c7ff] hover:text-white transition-colors"
              >
                Manage apps
              </button>
            </div>
            <div className="p-5 grid grid-cols-1 md:grid-cols-5 gap-4 min-h-[220px] items-end">
              {visibleAppCards.map((card) => {
                const summary = summaries?.[card.key];
                const meta = statusMeta(summary);
                const Icon = card.icon;
                return (
                  <div key={card.key} className="flex md:flex-col items-center md:items-stretch gap-3">
                    <div className="flex md:block items-center gap-3 md:gap-0 flex-1">
                      <div className="md:mb-3 flex items-center justify-between gap-3">
                        <div className="w-9 h-9 rounded-xl border border-white/10 bg-[#07111f] flex items-center justify-center">
                          <Icon className={`w-4 h-4 ${card.iconClass}`} />
                        </div>
                        <span className="hidden md:inline text-[9px] text-slate-500">{meta.score}%</span>
                      </div>
                      <div className="md:hidden flex-1">
                        <div className="w-full h-2 rounded-full bg-[#07111f] border border-[#162d45] overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${meta.score}%`,
                              background: `linear-gradient(90deg, ${card.accent}88, ${card.accent})`,
                            }}
                          />
                        </div>
                      </div>
                      <div className="hidden md:flex h-[110px] items-end">
                        <div className="w-full h-full rounded-full bg-[#07111f] border border-[#162d45] overflow-hidden flex items-end">
                          <div
                            className="w-full rounded-full transition-all duration-500"
                            style={{
                              height: `${meta.score}%`,
                              background: `linear-gradient(180deg, ${card.accent}, ${card.accent}66)`,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                    <div className="w-[110px] md:w-auto">
                      <div className="text-[10px] font-bold text-slate-200 truncate">{card.shortName}</div>
                      <div className={`text-[9px] mt-0.5 ${meta.text} truncate`}>{meta.label}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-[22px] border border-[#1a3854] bg-[#091728] overflow-hidden">
            <div className="px-5 py-4 border-b border-[#18324b] flex items-center justify-between">
              <div>
                <div className="text-sm font-bold text-white">Needs your attention</div>
                <div className="text-[10px] text-slate-500 mt-0.5">Business signals worth reviewing next</div>
              </div>
              <Activity className="w-4 h-4 text-[#55c7ff]" />
            </div>
            <div className="p-4 space-y-2">
              {actions.length ? (
                actions.map((action) => {
                  const card = appCards.find((item) => item.key === action.key)!;
                  const app = appFor(card.id, card.shortName);
                  const launchUrl = appLaunchUrl(app, card.fallback);
                  const Icon = card.icon;
                  return (
                    <div key={action.title} className="rounded-xl border border-[#18324b] bg-[#07121f] p-3 flex items-start gap-3">
                      <div className="w-8 h-8 shrink-0 rounded-lg border border-white/10 flex items-center justify-center" style={{ backgroundColor: `${card.accent}18` }}>
                        <Icon className={`w-4 h-4 ${card.iconClass}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-bold text-slate-200">{action.title}</div>
                        <div className="text-[9px] text-slate-500 mt-1 leading-relaxed">{action.detail}</div>
                      </div>
                      {launchUrl && (
                        <a href={launchUrl} target="_blank" rel="noopener noreferrer" className="text-[#55c7ff] hover:text-white">
                          <ArrowUpRight className="w-4 h-4" />
                        </a>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.07] p-4 flex items-start gap-3">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5" />
                  <div>
                    <div className="text-[11px] font-bold text-emerald-200">No urgent signals</div>
                    <div className="text-[9px] text-slate-500 mt-1">Connected applications are not surfacing urgent actions right now.</div>
                  </div>
                </div>
              )}
              <div className="pt-2 text-[9px] text-slate-600">
                Last KPI refresh: {dashboard?.generatedAt ? new Date(dashboard.generatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "-"}
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[22px] border border-[#1a3854] bg-[#091728] overflow-hidden">
          <div className="px-5 py-4 border-b border-[#18324b] flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-bold text-white">App launcher</div>
              <div className="text-[10px] text-slate-500 mt-0.5">Your approved V79 Digital workspace applications</div>
            </div>
            <button onClick={() => onNavigate("connections")} className="text-[10px] font-bold text-[#55c7ff]">
              Open all apps
            </button>
          </div>
          <div className="p-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
            {appCards.map((card) => {
              const app = appFor(card.id, card.shortName);
              const summary = summaries?.[card.key];
              const meta = statusMeta(summary);
              const metrics = card.metrics(summary?.metrics || {});
              const launchUrl = appLaunchUrl(app, card.fallback);
              const Icon = card.icon;
              return (
                <a
                  key={card.key}
                  href={launchUrl || undefined}
                  target={launchUrl ? "_blank" : undefined}
                  rel={launchUrl ? "noopener noreferrer" : undefined}
                  aria-disabled={!launchUrl}
                  className={`group relative overflow-hidden min-h-[190px] rounded-2xl border border-[#1d3c58] bg-gradient-to-br ${card.accentSoft} p-4 no-underline text-inherit transition-all duration-200 hover:-translate-y-1 ${card.border} ${!launchUrl ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  <div className="absolute -right-8 -bottom-10 w-28 h-28 rounded-full blur-2xl opacity-25" style={{ backgroundColor: card.accent }} />
                  <div className="relative h-full flex flex-col">
                    <div className="flex items-start justify-between gap-3">
                      <div className="w-10 h-10 rounded-xl border border-white/10 bg-[#07111f]/85 flex items-center justify-center shadow-lg">
                        <Icon className={`w-5 h-5 ${card.iconClass}`} />
                      </div>
                      <span className={`text-[8px] font-bold uppercase tracking-[0.12em] ${meta.text}`}>{meta.label}</span>
                    </div>
                    <div className="mt-4">
                      <div className="text-[9px] uppercase tracking-[0.13em] text-slate-500 font-bold">{card.category}</div>
                      <div className="mt-1 text-[13px] font-black text-white leading-tight">{card.title}</div>
                      <div className="mt-2 text-[9px] leading-relaxed text-slate-500 line-clamp-2">{card.description}</div>
                    </div>
                    <div className="mt-auto pt-4 grid grid-cols-3 gap-1.5">
                      {metrics.map((metric) => (
                        <div key={metric.label} className="rounded-lg bg-black/15 border border-white/[0.06] px-2 py-1.5 min-w-0">
                          <div className="text-[7px] text-slate-600 truncate">{metric.label}</div>
                          <div className="text-[10px] font-bold text-slate-200 truncate">
                            {summary?.status === "ok" ? metric.value : "-"}
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center justify-between text-[9px]">
                      <span className="text-slate-600">{launchUrl ? "Ready" : app?.accessMessage || "Setup pending"}</span>
                      <span className="inline-flex items-center gap-1 font-bold" style={{ color: card.accent }}>
                        Open <ArrowUpRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                      </span>
                    </div>
                  </div>
                </a>
              );
            })}
          </div>
        </section>

        <section className="rounded-[22px] border border-[#1a3854] bg-[#091728] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#0A86FF]/12 border border-[#0A86FF]/25 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-[#55c7ff]" />
            </div>
            <div>
              <div className="text-[11px] font-bold text-white">System health</div>
              <div className="text-[9px] text-slate-500 mt-1">
                {onlineCount === 5 ? "All connected KPI feeds are operational." : `${onlineCount} of 5 KPI feeds are currently operational.`}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {appCards.map((card) => {
              const meta = statusMeta(summaries?.[card.key]);
              return (
                <div key={card.key} className="rounded-full border border-[#1d3c58] bg-[#07121f] px-2.5 py-1.5 flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                  <span className="text-[8px] font-bold text-slate-400">{card.shortName}</span>
                </div>
              );
            })}
          </div>
        </section>

        <footer className="px-1 pt-1 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[9px] text-slate-600">
          <span>V79 Digital - From Idea to Advantage.</span>
          <span>Private app data remains inside each product; the Hub displays aggregate operational signals.</span>
        </footer>
      </div>
    </div>
  );
}
