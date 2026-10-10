import { useEffect, useMemo, useState } from "react";
import { CreditCard, CheckCircle2, ArrowLeft, Mail, PackageCheck, CalendarDays, WalletCards, Loader2, ShieldCheck, FlaskConical } from "lucide-react";
import { ViewState } from "../types";

interface PaymentProviderSummary {
  provider: "wipay";
  enabled: boolean;
  ready: boolean;
  environment: "sandbox" | "live";
  countryCode: string;
  currency: string;
  feeStructure: string;
  endpointConfigured: boolean;
  accountConfigured: boolean;
  sandboxDocumentationDefaults: boolean;
  problems: string[];
}

interface BillingSummary {
  organization: string;
  planName: string;
  status: string;
  accessStatus: string;
  trialStartedAt: string | null;
  trialEndsAt: string | null;
  paidThroughAt: string | null;
  billingCycle: "monthly" | "annual" | "custom";
  enabledApps: Array<{ id: string; name: string }>;
  pricing: { currency: string; monthly: number | null; annual: number | null; custom?: number | null };
  renewalDate: string | null;
  billingManagedBy: string;
  supportEmail: string;
  selfServicePaymentsEnabled: boolean;
  sandboxTestPaymentsEnabled?: boolean;
  manualPaymentAvailable?: boolean;
  paymentProvider?: PaymentProviderSummary;
}

interface CheckoutResponse {
  order: { id: string; description: string; amount: number; currency: string; status: string };
  checkout: {
    provider: "wipay";
    environment: "sandbox" | "live";
    action: string;
    method: "POST";
    fields: Record<string, string>;
  };
}

const money = (value: number | null, currency: string) =>
  value === null ? "By agreement" : new Intl.NumberFormat("en-LC", { style: "currency", currency }).format(value);

function submitHostedCheckout(checkout: CheckoutResponse["checkout"]) {
  const action = new URL(checkout.action);
  if (action.protocol !== "https:") throw new Error("The payment provider URL is not secure.");

  const form = document.createElement("form");
  form.method = "POST";
  form.action = action.toString();
  form.style.display = "none";

  for (const [name, value] of Object.entries(checkout.fields)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  }

  document.body.appendChild(form);
  form.submit();
}

export function WorkspaceBilling({ onNavigate }: { onNavigate: (view: ViewState) => void }) {
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [error, setError] = useState("");
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [manualBusy, setManualBusy] = useState(false);
  const [manualMessage, setManualMessage] = useState("");
  const [manualError, setManualError] = useState("");
  const [checkoutError, setCheckoutError] = useState("");

  const paymentResult = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("payment");
    if (!status) return null;
    return {
      status,
      reason: params.get("payment_reason") || "",
      orderId: params.get("order") || "",
    };
  }, []);

  useEffect(() => {
    fetch("/api/billing/summary", { cache: "no-store" })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Could not load plan details.");
        setSummary(data);
      })
      .catch(err => setError(err instanceof Error ? err.message : "Could not load plan details."));
  }, []);

  async function startCheckout() {
    setCheckoutBusy(true);
    setCheckoutError("");
    try {
      const endpoint = provider?.environment === "sandbox" ? "/api/billing/sandbox-test" : "/api/billing/checkout";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const data = await res.json() as CheckoutResponse & { error?: string };
      if (!res.ok) throw new Error(data.error || "Could not start WiPay checkout.");
      submitHostedCheckout(data.checkout);
    } catch (err) {
      setCheckoutError(err instanceof Error ? err.message : "Could not start WiPay checkout.");
      setCheckoutBusy(false);
    }
  }

  async function requestManualInvoice() {
    setManualBusy(true);
    setManualError("");
    try {
      const response = await fetch("/api/billing/manual/request", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not request invoice.");
      setManualMessage(`Manual invoice ${data.order.id} requested for EC$ ${Number(data.order.amount).toFixed(2)}. Contact V79 Digital for verified bank instructions. Paid access begins only after funds are independently confirmed.`);
    } catch (err) {
      setManualError(err instanceof Error ? err.message : "Could not request invoice.");
    } finally {
      setManualBusy(false);
    }
  }
  const provider = summary?.paymentProvider;
  const isSandbox = provider?.environment === "sandbox";

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
              <p className="mt-2 text-sm text-slate-400 max-w-2xl">See the plan, V79 modules and payment status for this business workspace.</p>
            </div>
            {summary && (
              <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 min-w-[180px]">
                <div className="text-[10px] uppercase tracking-wider font-black text-emerald-300">Plan status</div>
                <div className="mt-1 flex items-center gap-2 text-sm font-bold text-white">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" /> {summary.status.charAt(0).toUpperCase() + summary.status.slice(1)}
                </div>
              </div>
            )}
          </div>
        </section>

        {paymentResult?.status === "success" && (
          <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-100">
            <strong>Payment verified.</strong> Your V79 billing record has been updated{paymentResult.orderId ? ` for order ${paymentResult.orderId}` : ""}.
          </div>
        )}
        {paymentResult && paymentResult.status !== "success" && (
          <div className="rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-xs text-rose-100">
            <strong>Payment was not applied.</strong> No access was granted from this return. {paymentResult.reason ? `Reference: ${paymentResult.reason}.` : "Please try again or contact V79 Digital."}
          </div>
        )}
        {error && <div className="rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-xs text-rose-200">{error}</div>}

        {summary && (
          <>
            <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
              <InfoCard icon={WalletCards} label="Current plan" value={summary.planName} detail={summary.organization} />
              <InfoCard icon={CreditCard} label="Monthly price" value={money(summary.pricing.monthly, summary.pricing.currency)} detail="V79 plan price" />
              <InfoCard icon={CreditCard} label="Annual price" value={money(summary.pricing.annual, summary.pricing.currency)} detail="V79 plan price" />
              <InfoCard icon={CalendarDays} label={summary.status === "trial" ? "Trial expires" : "Renewal"} value={summary.status === "trial" ? (summary.trialEndsAt ? new Date(summary.trialEndsAt).toLocaleString() : "Not configured") : (summary.renewalDate ? new Date(summary.renewalDate + "T00:00:00").toLocaleDateString() : "Managed by V79")} detail={summary.status === "trial" ? (summary.accessStatus === "trial_expired" ? "Trial ended — paid app access restricted" : "14-day V79 pilot trial") : "Updated only after verified payment"} />
            </div>

            <section className="grid lg:grid-cols-[1fr_380px] gap-5">
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
                {(summary.selfServicePaymentsEnabled || summary.sandboxTestPaymentsEnabled) ? (
                  <>
                    <div className="flex items-center justify-between gap-3">
                      {isSandbox ? <FlaskConical className="w-5 h-5 text-amber-300" /> : <ShieldCheck className="w-5 h-5 text-emerald-300" />}
                      <span className={`rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${isSandbox ? "border-amber-500/30 bg-amber-500/10 text-amber-200" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"}`}>
                        WiPay {isSandbox ? "sandbox" : "live"}
                      </span>
                    </div>
                    <h2 className="mt-3 font-bold text-white">{isSandbox ? "Test payment flow" : "Renew with WiPay"}</h2>
                    <p className="mt-2 text-xs leading-5 text-slate-400">
                      {isSandbox
                        ? `Sandbox checkout is enabled for integration testing only. This uses a fixed 10.00 ${provider?.currency || "test"} test charge and never changes plan access, course access or Tiquet revenue.`
                        : "You will be sent to WiPay's hosted checkout. V79 activates the renewal only after the server verifies the returned transaction."}
                    </p>
                    {checkoutError && <div className="mt-3 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">{checkoutError}</div>}
                    <button
                      onClick={startCheckout}
                      disabled={checkoutBusy}
                      className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-xl bg-[#0A86FF] hover:bg-[#2a9cff] disabled:opacity-60 px-4 py-2.5 text-xs font-bold text-white"
                    >
                      {checkoutBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
                      {isSandbox ? "Open WiPay test checkout" : "Pay securely with WiPay"}
                    </button>
                    <div className="mt-3 text-[10px] leading-4 text-slate-600">Card details are entered on WiPay's hosted payment page, not stored by V79 Hub.</div>
                  </>
                ) : (
                  <>
                    <Mail className="w-5 h-5 text-[#65c9ff]" />
                    <h2 className="mt-3 font-bold text-white">Billing setup</h2>
                    <p className="mt-2 text-xs leading-5 text-slate-400">
                      Self-service payment is currently disabled. Plan changes and billing questions are handled by V79 Digital while the payment provider setup is completed.
                    </p>
                    <a href={"mailto:" + summary.supportEmail + "?subject=V79%20Hub%20Plan%20Change"}
                      className="mt-5 inline-flex items-center justify-center rounded-xl bg-[#0A86FF] hover:bg-[#2a9cff] px-4 py-2.5 text-xs font-bold text-white no-underline">
                      Contact V79 Digital
                    </a>
                    <div className="mt-3 text-[10px] text-slate-600">{summary.supportEmail}</div>
                  </>
                )}
              </div>
            </section>

            {summary.manualPaymentAvailable && (
              <section className="rounded-xl border border-[#1a3854] bg-[#091728] px-5 py-4 space-y-3">
                <h2 className="text-sm font-bold text-white">Pay by verified bank transfer</h2>
                <p className="text-xs text-slate-400">Request an invoice with your plan amount and reference. Obtain official payment instructions directly from V79 Digital. Uploading a receipt or claiming a transfer does not activate a subscription.</p>
                {manualError && <p role="alert" className="text-xs text-rose-300">{manualError}</p>}
                {manualMessage && <p role="status" className="text-xs text-emerald-200">{manualMessage}</p>}
                <button disabled={manualBusy} type="button" onClick={() => void requestManualInvoice()}
                  className="rounded-lg border border-sky-500 px-4 py-2 text-xs font-bold text-sky-200 disabled:opacity-50">
                  {manualBusy ? "Requesting…" : "Request bank-transfer invoice"}
                </button>
                <a href={`mailto:${summary.supportEmail}?subject=V79%20Manual%20Payment%20Invoice`} className="ml-3 text-xs text-sky-300 underline">Contact V79 Digital</a>
              </section>
            )}
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.07] px-4 py-3 text-xs leading-5 text-amber-100">
              V79 Hub remains the source of truth for plans, billing orders and app entitlements. Neither a WiPay browser redirect nor a customer's bank-transfer claim activates access. Only verified payment records can extend a paid plan.
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
