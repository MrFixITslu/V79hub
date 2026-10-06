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
    <div className="min-h-screen bg-[#06101d] flex items-center justify-center p-4 font-sans relative overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-15%] left-[-10%] w-[50%] h-[50%] bg-[#0A86FF]/15 rounded-full blur-[140px]" />
        <div className="absolute bottom-[-15%] right-[-10%] w-[50%] h-[50%] bg-violet-600/15 rounded-full blur-[140px]" />
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
        className="w-full max-w-md relative z-10">
        <div className="bg-[#091728]/95 backdrop-blur-xl border border-[#1a3854] rounded-3xl shadow-2xl overflow-hidden p-7 sm:p-8">
          <div className="text-center mb-7">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-tr from-[#0A86FF] to-violet-500 shadow-lg shadow-blue-500/20 mb-4 text-white">
              <ShieldCheck className="w-7 h-7" />
            </div>
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <span className="text-2xl font-black tracking-tight text-white">V79</span>
              <span className="ml-1 text-xs font-bold uppercase tracking-widest px-2 py-0.5 rounded bg-blue-500/15 text-[#65c9ff] border border-blue-500/25">HUB</span>
            </div>
            <p className="text-slate-500 text-xs">by V79 Digital · From Idea to Advantage.</p>
          </div>

          {mode === "login" && (
            <form onSubmit={handleLogin} className="space-y-5">
              <div>
                <h1 className="text-xl font-bold text-white">Sign in to V79 Hub</h1>
                <p className="mt-1 text-xs text-slate-500">Open your secure business workspace.</p>
              </div>
              {renderMessage()}
              <div>
                <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5 ml-1">Username or email</label>
                <div className="relative">
                  <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input type="text" required value={username}
                    onChange={e => { setUsername(e.target.value); setWorkspaces([]); setOrganizationId(""); }}
                    className="w-full bg-[#06101d] border border-[#1a3854] text-white pl-10 pr-4 py-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0A86FF] placeholder-slate-600"
                    placeholder="you@example.com" autoComplete="username" />
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1.5 ml-1">
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Password</label>
                  <button type="button" onClick={() => { clearMessages(); setRecoveryEmail(username.includes("@") ? username : ""); setMode("forgot"); }}
                    className="text-[11px] font-semibold text-[#65c9ff] hover:text-white">Forgot password?</button>
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
                className="w-full bg-gradient-to-r from-[#0A86FF] to-blue-600 hover:from-[#2a9cff] hover:to-blue-500 text-white font-semibold py-3.5 rounded-xl transition-all shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2 disabled:opacity-60 text-sm">
                {isLoading ? <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" /> :
                  <><ShieldCheck className="w-4 h-4" /><span>Sign in to V79 Hub</span></>}
              </button>
            </form>
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
  );
}
