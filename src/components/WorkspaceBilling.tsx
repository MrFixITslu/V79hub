import { useEffect, useState } from "react";
import { CreditCard, CheckCircle2, ArrowLeft, Mail, PackageCheck, CalendarDays, WalletCards } from "lucide-react";
import { ViewState } from "../types";

interface BillingSummary {
  organization: string;
  planName: string;
  status: string;
  enabledApps: Array<{ id: string; name: string }>;
  pricing: { currency: string; monthly: number | null; annual: number | null };
  renewalDate: string | null;
  billingManagedBy: string;
  supportEmail: string;
  selfServicePaymentsEnabled: boolean;
}

const money = (value: number | null, currency: string) =>
  value === null ? "By agreement" : new Intl.NumberFormat("en-LC", { style: "currency", currency }).format(value);

export function WorkspaceBilling({ onNavigate }: { onNavigate: (view: ViewState) => void }) {
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/billing/summary", { cache: "no-store" })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Could not load plan details.");
        setSummary(data);
      })
      .catch(err => setError(err instanceof Error ? err.message : "Could not load plan details."));
  }, []);

  return (
    <div className="min-h-full bg-[#07111f] text-slate-100">
      <div className="w-full max-w-6xl mx-auto px-4 sm:px-6 py-7 space-y-5">
        <button onClick={() => onNavigate("overview")} className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to dashboard
        </button>

        <section className="rounded-3xl border border-[#1a3854] bg-[#091728] p-6 sm:p-7">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] font-black text-[#65c9ff]">Workspace plan</div>
              <h1 className="mt-1 text-2xl font-black text-white">Plans & billing</h1>
              <p className="mt-2 text-sm text-slate-400 max-w-2xl">See the plan and V79 modules enabled for this business workspace. Plan changes are managed with V79 Digital.</p>
            </div>
            {summary && (
              <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 min-w-[180px]">
                <div className="text-[10px] uppercase tracking-wider font-black text-emerald-300">Plan status</div>
                <div className="mt-1 flex items-center gap-2 text-sm font-bold text-white"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Active</div>
              </div>
            )}
          </div>
        </section>

        {error && <div className="rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-xs text-rose-200">{error}</div>}

        {summary && (
          <>
            <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
              <InfoCard icon={WalletCards} label="Current plan" value={summary.planName} detail={summary.organization} />
              <InfoCard icon={CreditCard} label="Monthly price" value={money(summary.pricing.monthly, summary.pricing.currency)} detail="XCD pricing when configured" />
              <InfoCard icon={CreditCard} label="Annual price" value={money(summary.pricing.annual, summary.pricing.currency)} detail="XCD pricing when configured" />
              <InfoCard icon={CalendarDays} label="Renewal" value={summary.renewalDate ? new Date(summary.renewalDate + "T00:00:00").toLocaleDateString() : "Managed by V79"} detail="Confirmed in your service agreement" />
            </div>

            <section className="grid lg:grid-cols-[1fr_360px] gap-5">
              <div className="rounded-2xl border border-[#1a3854] bg-[#091728] p-5 sm:p-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl border border-[#1a3854] bg-[#06101d] flex items-center justify-center"><PackageCheck className="w-5 h-5 text-[#65c9ff]" /></div>
                  <div>
                    <h2 className="font-bold text-white">Enabled V79 apps</h2>
                    <p className="text-xs text-slate-500 mt-1">Modules included in this workspace entitlement.</p>
                  </div>
                </div>
                <div className="mt-5 grid sm:grid-cols-2 gap-3">
                  {summary.enabledApps.length > 0 ? summary.enabledApps.map(app => (
                    <div key={app.id} className="rounded-xl border border-[#1a3854] bg-[#06101d] px-4 py-3 flex items-center gap-2.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span className="text-xs font-semibold text-slate-200">{app.name}</span>
                    </div>
                  )) : (
                    <div className="text-xs text-slate-500">No business modules are currently enabled.</div>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-[#1a3854] bg-[#091728] p-5 sm:p-6">
                <Mail className="w-5 h-5 text-[#65c9ff]" />
                <h2 className="mt-3 font-bold text-white">Change your plan</h2>
                <p className="mt-2 text-xs leading-5 text-slate-400">
                  Self-service payments are not enabled yet. Upgrades, downgrades, app changes and billing questions are handled by V79 Digital so your workspace is provisioned correctly.
                </p>
                <a href={"mailto:" + summary.supportEmail + "?subject=V79%20Hub%20Plan%20Change"}
                  className="mt-5 inline-flex items-center justify-center rounded-xl bg-[#0A86FF] hover:bg-[#2a9cff] px-4 py-2.5 text-xs font-bold text-white no-underline">
                  Contact V79 Digital
                </a>
                <div className="mt-3 text-[10px] text-slate-600">{summary.supportEmail}</div>
              </div>
            </section>

            <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.07] px-4 py-3 text-xs leading-5 text-amber-100">
              The Hub shows your current plan and app entitlement. It does not currently process card payments or automatically change subscriptions. Any amount or renewal date shown here should match your V79 Digital agreement.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function InfoCard({ icon: Icon, label, value, detail }: { icon: typeof CreditCard; label: string; value: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-[#1a3854] bg-[#091728] p-5">
      <div className="w-9 h-9 rounded-xl border border-[#1a3854] bg-[#06101d] flex items-center justify-center"><Icon className="w-4 h-4 text-[#65c9ff]" /></div>
      <div className="mt-4 text-[10px] uppercase tracking-wider font-bold text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-black text-white">{value}</div>
      <div className="mt-1 text-[10px] text-slate-600">{detail}</div>
    </div>
  );
}
