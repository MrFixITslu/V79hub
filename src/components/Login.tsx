import { useEffect, useMemo, useState, FormEvent } from "react";
import {
  Lock, User as UserIcon, ShieldCheck, AlertCircle, Eye, EyeOff,
  Mail, KeyRound, ArrowLeft, Copy, CheckCircle2,
} from "lucide-react";
import { motion } from "motion/react";
import { User } from "../types";

interface LoginProps {
  onLoginSuccess: (user: User, token: string) => void;
}

interface WorkspaceOption {
  id: string;
  name: string;
  slug: string;
}

type LoginMode = "login" | "forgot" | "reset" | "mfa";

export function Login({ onLoginSuccess }: LoginProps) {
  const initialResetToken = useMemo(() => new URLSearchParams(window.location.search).get("reset") || "", []);
  const [mode, setMode] = useState<LoginMode>(initialResetToken ? "reset" : "login");
  const [resetToken] = useState(initialResetToken);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [workspaces, setWorkspaces] = useState<WorkspaceOption[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [recoveryEnabled, setRecoveryEnabled] = useState(false);
  const [supportEmail, setSupportEmail] = useState("vision79slu@gmail.com");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaSetupSecret, setMfaSetupSecret] = useState("");
  const [mfaProvisioningUri, setMfaProvisioningUri] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetch("/api/auth/recovery-status", { cache: "no-store" })
      .then(async response => response.ok ? response.json() : null)
      .then(data => {
        if (!data) return;
        setRecoveryEnabled(Boolean(data.emailRecoveryEnabled));
        if (data.supportEmail) setSupportEmail(data.supportEmail);
      })
      .catch(() => {});
  }, []);

  const clearMessages = () => {
    setError("");
    setNotice("");
  };

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setIsLoading(true);
    clearMessages();

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim(),
          password,
          ...(organizationId ? { organizationId } : {}),
        }),
      });
      const data = await res.json();

      if (res.status === 409 && Array.isArray(data.organizations)) {
        setWorkspaces(data.organizations);
        setOrganizationId("");
        setError("Choose the business workspace you want to open.");
        return;
      }

      if (res.status === 202 && data.mfaRequired) {
        setChallengeId(data.challengeId || "");
        setMfaSetupSecret(data.secret || "");
        setMfaProvisioningUri(data.provisioningUri || "");
        setMfaCode("");
        setMode("mfa");
        return;
      }

      if (!res.ok) throw new Error(data.error || "Authentication failed");
      onLoginSuccess(data.user, "cookie");
    } catch (err: any) {
      setError(err.message || "Failed to sign in. Please check your credentials.");
    } finally {
      setIsLoading(false);
    }
  };

  const completeMfa = async (e: FormEvent) => {
    e.preventDefault();
    if (!challengeId || !/^\d{6}$/.test(mfaCode.trim())) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setIsLoading(true);
    clearMessages();
    try {
      const res = await fetch("/api/auth/mfa/complete-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challengeId, code: mfaCode.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Authentication code was not accepted.");
      onLoginSuccess(data.user, "cookie");
    } catch (err: any) {
      setError(err.message || "Authentication code was not accepted.");
    } finally {
      setIsLoading(false);
    }
  };

  const requestReset = async (e: FormEvent) => {
    e.preventDefault();
    clearMessages();
    if (!recoveryEmail.trim()) return;
    if (!recoveryEnabled) {
      setNotice(`Automatic password reset email is not configured. Contact ${supportEmail} for account recovery.`);
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch("/api/auth/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: recoveryEmail.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Could not request password reset.");
      setNotice(data.message || "If that email is eligible for recovery, reset instructions will be sent.");
    } catch (err: any) {
      setError(err.message || "Could not request password reset.");
    } finally {
      setIsLoading(false);
    }
  };

  const completeReset = async (e: FormEvent) => {
    e.preventDefault();
    clearMessages();
    if (newPassword.length < 12) return setError("Use a password of at least 12 characters.");
    if (newPassword !== confirmPassword) return setError("The new passwords do not match.");
    setIsLoading(true);
    try {
      const res = await fetch("/api/auth/password-reset/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: resetToken, password: newPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Password reset failed.");
      const url = new URL(window.location.href);
      url.searchParams.delete("reset");
      window.history.replaceState({}, "", url.pathname + (url.search ? url.search : ""));
      setNewPassword("");
      setConfirmPassword("");
      setMode("login");
      setNotice("Password updated. Sign in with your new password.");
    } catch (err: any) {
      setError(err.message || "Password reset failed.");
    } finally {
      setIsLoading(false);
    }
  };

  const copySecret = async () => {
    if (!mfaSetupSecret) return;
    try {
      await navigator.clipboard.writeText(mfaSetupSecret);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {}
  };

  const renderMessage = () => (
    <>
      {error && (
        <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
          className="bg-rose-500/10 border border-rose-500/30 text-rose-200 px-4 py-3 rounded-xl text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
          <span>{error}</span>
        </motion.div>
      )}
      {notice && (
        <div className="bg-emerald-500/10 border border-emerald-500/25 text-emerald-200 px-4 py-3 rounded-xl text-xs flex items-start gap-2.5">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{notice}</span>
        </div>
      )}
    </>
  );

  return (
    <div className="hub-login hub-login-reference relative isolate min-h-[100svh] overflow-x-hidden bg-[#020813] font-sans text-white">
      <div className="hub-login-main relative mx-auto grid min-h-[100svh] w-full max-w-[1440px] grid-cols-1 items-center gap-8 px-5 py-8 lg:grid-cols-[minmax(0,1fr)_minmax(420px,560px)] lg:gap-10 lg:px-[52px] lg:py-10">
        <aside className="hub-login-story relative hidden min-w-0 self-stretch flex-col lg:flex" aria-label="About V79 Digital Hub">
          <div className="hub-login-network pointer-events-none" aria-hidden="true">
            <img src="/assets/v79-login-earth.svg" alt="" loading="eager" decoding="async" />
          </div>
          <div className="hub-login-brand relative z-10">
            <div className="text-[33px] font-black leading-none tracking-[-0.05em] text-white">V79 <span className="text-[#0A86FF]">Digital</span></div>
            <p className="mt-2 text-[14px] font-bold text-[#0A86FF]">From Idea to Advantage.</p>
          </div>
          <div className="hub-login-story-content relative z-10">
            <h2 className="hub-login-welcome font-black tracking-[-0.055em] text-[#f7f9ff]">
              Welcome to<br /><span className="text-[#0A86FF]">V79 Digital Hub</span>
            </h2>
            <p className="hub-login-pitch text-slate-400">
              Your command center for the V79 Digital ecosystem.<br />
              Access insights. Drive performance.<br />
              Build what’s next.
            </p>
            <div className="hub-login-highlights" aria-label="Platform benefits">
              <span>Enterprise-grade<br />security</span>
              <span>Your data.<br /><strong className="text-[#0A86FF]">Always protected.</strong></span>
              <span>Built for teams<br />across the Caribbean</span>
            </div>
          </div>
        </aside>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
          className="hub-login-card relative z-10 mx-auto w-full max-w-[560px]">
          <div className="hub-login-form rounded-[23px] border border-[#28527d] bg-[#071624]/95 px-6 py-8 shadow-[0_28px_80px_rgba(0,0,0,.48)] sm:px-9 sm:py-10 lg:px-10 lg:py-11">
            <div className="hub-login-mobile-brand mb-8 lg:hidden">
              <div className="text-3xl font-black tracking-tight">V79 <span className="text-[#0A86FF]">Digital</span></div>
              <div className="mt-1 text-sm font-bold text-[#0A86FF]">From Idea to Advantage.</div>
            </div>

          {mode === "login" && (
            <form onSubmit={handleLogin} className="hub-login-fields space-y-5">
              <div>
                <h1 className="text-[25px] font-bold tracking-tight text-white">Sign in to your account</h1>
                <p className="mt-2 text-[15px] text-slate-400">Secure access to your V79 Digital Hub</p>
              </div>
              {renderMessage()}
              <div>
                <label className="mb-2 block text-[14px] font-semibold text-slate-200">Email address or username</label>
                <div className="relative">
                  <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input type="text" required value={username}
                    onChange={e => { setUsername(e.target.value); setWorkspaces([]); setOrganizationId(""); }}
                    className="w-full bg-[#06101d] border border-[#1a3854] text-white pl-10 pr-4 py-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0A86FF] placeholder-slate-600"
                    placeholder="you@company.com" autoComplete="username" aria-label="Email address or username" />
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1.5 ml-1">
                  <label className="block text-[14px] font-semibold text-slate-200">Password</label>
                  <button type="button" onClick={() => { clearMessages(); setRecoveryEmail(username.includes("@") ? username : ""); setMode("forgot"); }}
                    className="text-[12px] font-semibold text-[#65c9ff] hover:text-white">Forgot password?</button>
                </div>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input type={showPassword ? "text" : "password"} required value={password}
                    onChange={e => { setPassword(e.target.value); setWorkspaces([]); setOrganizationId(""); }}
                    className="w-full bg-[#06101d] border border-[#1a3854] text-white pl-10 pr-11 py-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0A86FF]"
                    placeholder="••••••••••••" autoComplete="current-password" />
                  <button type="button" onClick={() => setShowPassword(v => !v)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-200 p-1" aria-label="Toggle password visibility">
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {workspaces.length > 0 && (
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5 ml-1">Business workspace</label>
                  <select required value={organizationId} onChange={e => { setOrganizationId(e.target.value); setError(""); }}
                    className="w-full bg-[#06101d] border border-[#1a3854] text-white px-3.5 py-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0A86FF]">
                    <option value="">Choose a workspace</option>
                    {workspaces.map(workspace => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
                  </select>
                </div>
              )}

              <button type="submit" disabled={isLoading}
                className="hub-login-submit flex w-full items-center justify-center gap-2 rounded-lg bg-[#0A86FF] py-4 text-[16px] font-semibold text-white shadow-[0_10px_25px_rgba(0,113,255,.24)] transition-colors hover:bg-[#167cff] disabled:opacity-60">
                {isLoading ? <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" /> :
                  <>Sign in</>}
              </button>
            </form>
          )}

          {mode === "login" && (
            <>
              <div className="hub-login-divider" aria-label="Other sign-in methods">
                <span>or</span>
              </div>
              <button type="button" disabled aria-disabled="true" title="Google sign-in is not yet configured"
                className="hub-login-google flex w-full items-center justify-center gap-3 rounded-lg border border-[#46607c] bg-[#34445b] px-4 py-3.5 text-sm font-semibold text-slate-200 disabled:cursor-not-allowed">
                <span aria-hidden="true" className="hub-login-google-icon">G</span>
                <span>Continue with Google</span>
                <span className="sr-only">Not yet available</span>
              </button>
              <p className="mt-2 text-center text-[11px] text-slate-400">Google sign-in is not yet available.</p>
              <div className="hub-login-security mt-10 flex items-start gap-3 text-[13px] leading-5 text-slate-400">
                <Lock className="mt-0.5 h-5 w-5 shrink-0 text-[#0A86FF]" aria-hidden="true" />
                <p>Secure encryption. Multi-factor authentication.<br />We never share your information.</p>
              </div>
            </>
          )}

          {mode === "forgot" && (
            <form onSubmit={requestReset} className="space-y-5">
              <button type="button" onClick={() => { clearMessages(); setMode("login"); }} className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white">
                <ArrowLeft className="w-3.5 h-3.5" /> Back to sign in
              </button>
              <div>
                <h1 className="text-xl font-bold text-white">Reset your password</h1>
                <p className="mt-1 text-xs leading-5 text-slate-500">Enter the email registered to your Hub account.</p>
              </div>
              {renderMessage()}
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input type="email" required value={recoveryEmail} onChange={e => setRecoveryEmail(e.target.value)}
                  className="w-full bg-[#06101d] border border-[#1a3854] text-white pl-10 pr-4 py-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0A86FF]"
                  placeholder="you@example.com" />
              </div>
              <button type="submit" disabled={isLoading}
                className="w-full bg-[#0A86FF] hover:bg-[#2a9cff] text-white font-semibold py-3.5 rounded-xl text-sm disabled:opacity-60">
                {recoveryEnabled ? "Send reset instructions" : "Get recovery help"}
              </button>
              <p className="text-[11px] text-slate-600 text-center">Recovery support: {supportEmail}</p>
            </form>
          )}

          {mode === "reset" && (
            <form onSubmit={completeReset} className="space-y-5">
              <div>
                <h1 className="text-xl font-bold text-white">Choose a new password</h1>
                <p className="mt-1 text-xs text-slate-500">Use at least 12 characters and avoid passwords you use elsewhere.</p>
              </div>
              {renderMessage()}
              <input type="password" required value={newPassword} onChange={e => setNewPassword(e.target.value)}
                className="w-full bg-[#06101d] border border-[#1a3854] text-white px-4 py-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0A86FF]"
                placeholder="New password" autoComplete="new-password" />
              <input type="password" required value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                className="w-full bg-[#06101d] border border-[#1a3854] text-white px-4 py-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0A86FF]"
                placeholder="Confirm new password" autoComplete="new-password" />
              <button type="submit" disabled={isLoading}
                className="w-full bg-[#0A86FF] hover:bg-[#2a9cff] text-white font-semibold py-3.5 rounded-xl text-sm disabled:opacity-60">
                Update password
              </button>
            </form>
          )}

          {mode === "mfa" && (
            <form onSubmit={completeMfa} className="space-y-5">
              <div>
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-3">
                  <KeyRound className="w-5 h-5 text-emerald-400" />
                </div>
                <h1 className="text-xl font-bold text-white">{mfaSetupSecret ? "Secure your Hub account" : "Two-factor authentication"}</h1>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  {mfaSetupSecret
                    ? "Add V79 Hub to an authenticator app, then enter the 6-digit code to finish signing in."
                    : "Enter the current 6-digit code from your authenticator app."}
                </p>
              </div>
              {renderMessage()}
              {mfaSetupSecret && (
                <div className="space-y-3">
                  <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3.5 py-3 text-[11px] leading-5 text-amber-100">
                    Use only the setup key shown on this screen. If you previously added V79 Hub and received an invalid-code error, remove the older V79 Hub entry from your authenticator before adding this key.
                  </div>
                  <div className="rounded-2xl border border-[#1a3854] bg-[#06101d] p-4 space-y-3">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Authenticator setup key</div>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 break-all text-xs text-[#65c9ff]">{mfaSetupSecret}</code>
                    <button type="button" onClick={copySecret} className="p-2 rounded-lg border border-[#1a3854] text-slate-400 hover:text-white">
                      {copied ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  {mfaProvisioningUri && (
                    <a href={mfaProvisioningUri} className="inline-flex text-xs font-semibold text-[#65c9ff] hover:text-white">
                      Open in authenticator app
                    </a>
                  )}
                  </div>
                </div>
              )}
              <input inputMode="numeric" pattern="[0-9]*" maxLength={6} required value={mfaCode}
                onChange={e => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                className="w-full bg-[#06101d] border border-[#1a3854] text-white px-4 py-3 rounded-xl text-center text-xl tracking-[0.35em] font-mono focus:outline-none focus:ring-2 focus:ring-[#0A86FF]"
                placeholder="000000" autoComplete="one-time-code" />
              <button type="submit" disabled={isLoading || mfaCode.length !== 6}
                className="w-full bg-[#0A86FF] hover:bg-[#2a9cff] text-white font-semibold py-3.5 rounded-xl text-sm disabled:opacity-50">
                Verify and continue
              </button>
            </form>
          )}
        </div>
        </motion.div>
      </div>
    </div>
  );
}
