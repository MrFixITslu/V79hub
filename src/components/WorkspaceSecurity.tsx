import { useEffect, useState } from "react";
import { Lock, KeyRound, ShieldCheck, Copy, CheckCircle2, AlertCircle, ArrowLeft } from "lucide-react";
import { ViewState } from "../types";

interface MfaStatus {
  enabled: boolean;
  mandatory: boolean;
  method: string | null;
}

export function WorkspaceSecurity({ onNavigate }: { onNavigate: (view: ViewState) => void }) {
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [challengeId, setChallengeId] = useState("");
  const [secret, setSecret] = useState("");
  const [provisioningUri, setProvisioningUri] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const load = async () => {
    try {
      const res = await fetch("/api/security/mfa/status", { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not load security settings.");
      setStatus(data);
    } catch (error) {
      setMessage({ type: "error", text: error instanceof Error ? error.message : "Could not load security settings." });
    }
  };

  useEffect(() => { void load(); }, []);

  const startSetup = async () => {
    setBusy(true); setMessage(null);
    try {
      const res = await fetch("/api/security/mfa/setup", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not start MFA setup.");
      setChallengeId(data.challengeId);
      setSecret(data.secret);
      setProvisioningUri(data.provisioningUri);
      setCode("");
    } catch (error) {
      setMessage({ type: "error", text: error instanceof Error ? error.message : "Could not start MFA setup." });
    } finally { setBusy(false); }
  };

  const confirmSetup = async () => {
    if (!challengeId || code.length !== 6) return;
    setBusy(true); setMessage(null);
    try {
      const res = await fetch("/api/security/mfa/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challengeId, code }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "The authentication code was not accepted.");
      setChallengeId(""); setSecret(""); setProvisioningUri(""); setCode("");
      setMessage({ type: "success", text: "Two-factor authentication is now enabled." });
      await load();
    } catch (error) {
      setMessage({ type: "error", text: error instanceof Error ? error.message : "The authentication code was not accepted." });
    } finally { setBusy(false); }
  };

  const disableMfa = async () => {
    if (!password || code.length !== 6) return;
    setBusy(true); setMessage(null);
    try {
      const res = await fetch("/api/security/mfa/disable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, code }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not disable MFA.");
      setPassword(""); setCode("");
      setMessage({ type: "success", text: "Two-factor authentication has been disabled." });
      await load();
    } catch (error) {
      setMessage({ type: "error", text: error instanceof Error ? error.message : "Could not disable MFA." });
    } finally { setBusy(false); }
  };

  const copySecret = async () => {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {}
  };

  return (
    <div className="min-h-full bg-[#07111f] text-slate-100">
      <div className="w-full max-w-6xl mx-auto px-4 sm:px-6 py-7 space-y-5">
        <button onClick={() => onNavigate("overview")} className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to dashboard
        </button>

        <section className="rounded-3xl border border-[#1a3854] bg-[#091728] p-6 sm:p-7">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] font-black text-[#65c9ff]">Account security</div>
              <h1 className="mt-1 text-2xl font-black text-white">Security & access</h1>
              <p className="mt-2 text-sm text-slate-400 max-w-2xl">Protect your Hub account and review how access to your business workspace is secured.</p>
            </div>
            <div className={"rounded-2xl border px-4 py-3 " + (status?.enabled ? "border-emerald-500/25 bg-emerald-500/10" : "border-amber-500/25 bg-amber-500/10")}>
              <div className={"text-[10px] uppercase font-black tracking-wider " + (status?.enabled ? "text-emerald-300" : "text-amber-300")}>
                Two-factor authentication
              </div>
              <div className="mt-1 text-sm font-bold text-white">{status?.enabled ? "Enabled" : "Not enabled"}</div>
              {status?.mandatory && <div className="mt-1 text-[10px] text-amber-200">Required for the V79 platform administrator</div>}
            </div>
          </div>
        </section>

        {message && (
          <div className={"rounded-xl border px-4 py-3 text-xs flex items-start gap-2 " + (message.type === "success" ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-200" : "border-rose-500/25 bg-rose-500/10 text-rose-200")}>
            {message.type === "success" ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            <span>{message.text}</span>
          </div>
        )}

        <div className="grid lg:grid-cols-[1.25fr_.75fr] gap-5">
          <section className="rounded-2xl border border-[#1a3854] bg-[#091728] p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl border border-[#1a3854] bg-[#06101d] flex items-center justify-center"><KeyRound className="w-5 h-5 text-[#65c9ff]" /></div>
              <div>
                <h2 className="font-bold text-white">Authenticator app</h2>
                <p className="mt-1 text-xs leading-5 text-slate-400">Use Google Authenticator, Microsoft Authenticator, 1Password, Authy or another TOTP-compatible authenticator.</p>
              </div>
            </div>

            {!status?.enabled && !challengeId && (
              <button onClick={startSetup} disabled={busy || !status}
                className="mt-5 inline-flex items-center justify-center rounded-xl bg-[#0A86FF] hover:bg-[#2a9cff] px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">
                Set up two-factor authentication
              </button>
            )}

            {!status?.enabled && challengeId && (
              <div className="mt-5 space-y-4">
                <div className="rounded-xl border border-[#1a3854] bg-[#06101d] p-4">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Setup key</div>
                  <div className="mt-2 flex items-center gap-2">
                    <code className="flex-1 break-all text-xs text-[#65c9ff]">{secret}</code>
                    <button onClick={copySecret} className="p-2 rounded-lg border border-[#1a3854] text-slate-400 hover:text-white">
                      {copied ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  {provisioningUri && <a href={provisioningUri} className="mt-3 inline-block text-xs font-semibold text-[#65c9ff] hover:text-white">Open in authenticator app</a>}
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-500">6-digit code</label>
                  <input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    inputMode="numeric" maxLength={6}
                    className="mt-1.5 w-full max-w-xs rounded-xl border border-[#1a3854] bg-[#06101d] px-4 py-3 text-center font-mono text-lg tracking-[0.3em] text-white outline-none focus:ring-2 focus:ring-[#0A86FF]"
                    placeholder="000000" />
                </div>
                <div className="flex gap-2">
                  <button onClick={confirmSetup} disabled={busy || code.length !== 6}
                    className="rounded-xl bg-[#0A86FF] hover:bg-[#2a9cff] px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">Verify & enable</button>
                  <button onClick={() => { setChallengeId(""); setSecret(""); setProvisioningUri(""); setCode(""); }}
                    className="rounded-xl border border-[#1a3854] px-4 py-2.5 text-xs font-semibold text-slate-300 hover:text-white">Cancel</button>
                </div>
              </div>
            )}

            {status?.enabled && (
              <div className="mt-5">
                {status.mandatory ? (
                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.07] p-4 text-xs leading-5 text-emerald-100">
                    MFA is mandatory for this platform administrator account and cannot be disabled from the Hub.
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">To disable MFA, confirm your current password and authenticator code.</p>
                    <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                      placeholder="Current password"
                      className="w-full max-w-md rounded-xl border border-[#1a3854] bg-[#06101d] px-4 py-3 text-sm text-white outline-none focus:ring-2 focus:ring-[#0A86FF]" />
                    <input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      inputMode="numeric" maxLength={6} placeholder="6-digit code"
                      className="w-full max-w-md rounded-xl border border-[#1a3854] bg-[#06101d] px-4 py-3 text-sm text-white outline-none focus:ring-2 focus:ring-[#0A86FF]" />
                    <button onClick={disableMfa} disabled={busy || !password || code.length !== 6}
                      className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-xs font-bold text-rose-200 hover:bg-rose-500/15 disabled:opacity-50">
                      Disable two-factor authentication
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>

          <div className="space-y-4">
            <div className="rounded-2xl border border-[#1a3854] bg-[#091728] p-5">
              <Lock className="w-5 h-5 text-[#65c9ff]" />
              <h2 className="mt-3 font-bold text-white">Secure Hub session</h2>
              <p className="mt-2 text-xs leading-5 text-slate-400">Hub uses an HttpOnly session cookie. Sign out when using shared devices and do not share your password.</p>
            </div>
            <div className="rounded-2xl border border-[#1a3854] bg-[#091728] p-5">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h2 className="mt-3 font-bold text-white">Workspace permissions</h2>
              <p className="mt-2 text-xs leading-5 text-slate-400">App access follows your workspace role and assigned V79 modules. Finance KPIs and full FFPRO access remain owner-restricted.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
