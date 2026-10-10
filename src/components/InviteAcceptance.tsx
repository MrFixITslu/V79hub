import { FormEvent, useEffect, useState } from "react";
import { AlertCircle, Building2, Eye, EyeOff, Lock, Mail, ShieldCheck } from "lucide-react";
import { User } from "../types";

interface InviteAcceptanceProps {
  token: string;
  onAccepted: (user: User) => void;
  onCancel: () => void;
}

interface InviteDetails {
  organizationName: string;
  organizationSlug: string;
  email: string;
  expiresAt: string;
  appIds: string[];
}

export function InviteAcceptance({ token, onAccepted, onCancel }: InviteAcceptanceProps) {
  const [invite, setInvite] = useState<InviteDetails | null>(null);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const response = await fetch("/api/onboarding/invitation", { cache: "no-store", headers: { "x-v79-invite-token": token } });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "This invitation is unavailable.");
        if (active) setInvite(data);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "This invitation is unavailable.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [token]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!invite || busy) return;
    if (password !== confirmPassword) return setError("The passwords do not match.");
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/onboarding/invitation/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-v79-invite-token": token },
        body: JSON.stringify({ fullName, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "The invitation could not be accepted.");
      onAccepted(data.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The invitation could not be accepted.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-3xl border border-slate-800 bg-slate-900/95 p-8 text-white shadow-2xl">
        <div className="text-center mb-7">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500">
            <ShieldCheck className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-black">Join V79 Hub</h1>
          <p className="mt-2 text-sm text-slate-400">Secure invite-only customer onboarding</p>
        </div>

        {loading ? (
          <div className="py-10 text-center text-sm text-slate-400">Checking invitation...</div>
        ) : !invite ? (
          <div className="space-y-5">
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
              <div className="flex gap-2"><AlertCircle className="h-5 w-5 shrink-0" /><span>{error || "This invitation is unavailable."}</span></div>
            </div>
            <button onClick={onCancel} className="w-full rounded-xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-200 hover:bg-slate-800">
              Return to sign in
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-5">
            <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4 space-y-3">
              <div className="flex items-center gap-3"><Building2 className="h-5 w-5 text-cyan-400" /><div><div className="text-xs text-slate-400">Business</div><div className="font-semibold">{invite.organizationName}</div></div></div>
              <div className="flex items-center gap-3"><Mail className="h-5 w-5 text-cyan-400" /><div><div className="text-xs text-slate-400">Invited email</div><div className="font-semibold">{invite.email}</div></div></div>
              <div className="text-xs text-slate-500">Expires {new Date(invite.expiresAt).toLocaleString()} · {invite.appIds.length} app entitlement{invite.appIds.length === 1 ? "" : "s"}</div>
            </div>

            {error && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">{error}</div>}

            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-400">Your name</span>
              <input
                required
                maxLength={120}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                className="w-full rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-400">Password</span>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  required
                  minLength={12}
                  maxLength={1024}
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full rounded-xl border border-slate-800 bg-slate-950/70 py-3 pl-10 pr-11 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400" aria-label="Toggle password visibility">
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-400">Confirm password</span>
              <input
                required
                minLength={12}
                maxLength={1024}
                type={showPassword ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                className="w-full rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </label>

            <p className="text-[11px] leading-relaxed text-slate-500">
              If this email already has a V79 Hub account, use that account's existing password. The invite will add this business as another workspace.
            </p>

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 py-3.5 text-sm font-semibold shadow-lg shadow-indigo-600/20 disabled:opacity-60"
            >
              {busy ? "Creating secure workspace..." : "Accept invitation & open Hub"}
            </button>
            <button type="button" onClick={onCancel} className="w-full text-xs font-medium text-slate-400 hover:text-slate-200">
              Cancel and return to sign in
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
