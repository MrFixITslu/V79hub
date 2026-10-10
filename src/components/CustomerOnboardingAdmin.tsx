import { FormEvent, useCallback, useEffect, useState } from "react";
import { Clipboard, RefreshCw, Send, ShieldCheck, UserPlus, XCircle } from "lucide-react";

interface AssignableApp {
  id: string;
  name: string;
  shortName: string;
}

interface OwnerInvitation {
  id: string;
  organizationId: string;
  organizationName: string;
  organizationSlug: string;
  email: string;
  appIds: string[];
  status: "pending" | "accepted" | "revoked" | "expired";
  expiresAt: string;
  createdAt: string;
  acceptedAt?: string | null;
  revokedAt?: string | null;
  appMappings?: Array<{
    appId: string;
    status: "pending" | "active" | "disabled";
    externalTenantId?: string | null;
    externalOwnerId?: string | null;
    updatedAt: string;
  }>;
}

interface OnboardingData {
  invitations: OwnerInvitation[];
  assignableApps: AssignableApp[];
}

async function onboardingApi<T>(path = "", options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/admin/onboarding${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Onboarding request failed (${response.status})`);
  return data;
}

export function CustomerOnboardingAdmin() {
  const [data, setData] = useState<OnboardingData>({ invitations: [], assignableApps: [] });
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [expiresInHours, setExpiresInHours] = useState(72);
  const [appIds, setAppIds] = useState<string[]>([]);
  const [createdUrl, setCreatedUrl] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await onboardingApi<OnboardingData>("/invitations"));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load onboarding.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const createInvitation = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    setCreatedUrl("");
    try {
      const result = await onboardingApi<{ inviteUrl: string }>("/invitations", {
        method: "POST",
        body: JSON.stringify({ organizationName, email, expiresInHours, appIds }),
      });
      setCreatedUrl(result.inviteUrl);
      setMessage("Invitation created. Copy this link now; the token is not stored in readable form.");
      setOrganizationName("");
      setEmail("");
      setAppIds([]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create invitation.");
    } finally {
      setBusy(false);
    }
  };

  const revokeInvitation = async (invitation: OwnerInvitation) => {
    if (!window.confirm(`Revoke the unused invitation for ${invitation.organizationName}?`)) return;
    setBusy(true);
    setError("");
    try {
      await onboardingApi(`/invitations/${encodeURIComponent(invitation.id)}/revoke`, { method: "POST", body: "{}" });
      setMessage("Invitation revoked.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke invitation.");
    } finally {
      setBusy(false);
    }
  };

  const provisionPos = async (invitation: OwnerInvitation) => {
    if (!window.confirm(`Provision an isolated POS workspace for ${invitation.organizationName}?`)) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await onboardingApi(`/organizations/${encodeURIComponent(invitation.organizationId)}/apps/pos/provision`, {
        method: "POST",
        body: "{}",
      });
      setMessage(`POS workspace activated for ${invitation.organizationName}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "POS workspace could not be provisioned.");
    } finally {
      setBusy(false);
    }
  };

  const provisionFfpro = async (invitation: OwnerInvitation) => {
    if (!window.confirm(`Provision an isolated FFPRO finance workspace for ${invitation.organizationName}?`)) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await onboardingApi(`/organizations/${encodeURIComponent(invitation.organizationId)}/apps/ffpro/provision`, {
        method: "POST",
        body: "{}",
      });
      setMessage(`FFPRO workspace activated for ${invitation.organizationName}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "FFPRO workspace could not be provisioned.");
    } finally {
      setBusy(false);
    }
  };

  const provisionTiquet = async (invitation: OwnerInvitation) => {
    if (!window.confirm(`Provision an isolated Tiquet workspace for ${invitation.organizationName}?`)) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await onboardingApi(`/organizations/${encodeURIComponent(invitation.organizationId)}/apps/tiquet/provision`, {
        method: "POST",
        body: "{}",
      });
      setMessage(`Tiquet workspace activated for ${invitation.organizationName}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tiquet workspace could not be provisioned.");
    } finally {
      setBusy(false);
    }
  };

  const provisionMarketing = async (invitation: OwnerInvitation) => {
    if (!window.confirm(`Provision an isolated Marketing workspace for ${invitation.organizationName}?`)) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await onboardingApi(`/organizations/${encodeURIComponent(invitation.organizationId)}/apps/marketing/provision`, {
        method: "POST",
        body: "{}",
      });
      setMessage(`Marketing workspace activated for ${invitation.organizationName}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Marketing workspace could not be provisioned.");
    } finally {
      setBusy(false);
    }
  };

  const toggleApp = (appId: string) => {
    setAppIds(current => current.includes(appId) ? current.filter(id => id !== appId) : [...current, appId]);
  };

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(createdUrl);
      setMessage("Invitation link copied.");
    } catch {
      setError("Copy failed. Select the link and copy it manually.");
    }
  };

  const statusClass: Record<string, string> = {
    pending: "bg-amber-50 border-amber-200 text-amber-700",
    accepted: "bg-emerald-50 border-emerald-200 text-emerald-700",
    revoked: "bg-slate-100 border-slate-200 text-slate-600",
    expired: "bg-rose-50 border-rose-200 text-rose-700",
  };

  return (
    <div className="space-y-5">

      <section className="rounded-2xl border border-cyan-200 bg-cyan-50 p-5">
        <div className="flex gap-3">
          <ShieldCheck className="h-5 w-5 shrink-0 text-cyan-700" />
          <div>
            <h2 className="font-bold text-slate-900">Invite-only customer onboarding</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-600">
              Only V79 platform operators can create owner invitations. Send the generated link only to the approved email address.
              POS, FFPRO, Tiquet and Marketing stay in setup-pending mode until their product workspace mapping is activated.
            </p>
          </div>
        </div>
      </section>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}
      {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}

      <form onSubmit={createInvitation} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-5">
        <div className="flex items-center gap-2">
          <UserPlus className="h-5 w-5 text-cyan-700" />
          <div>
            <h3 className="font-bold text-slate-900">Create owner invitation</h3>
            <p className="text-xs text-slate-500">The invite token is shown once and stored only as a secure hash.</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <label className="block md:col-span-1">
            <span className="mb-1.5 block text-xs font-semibold text-slate-600">Business name</span>
            <input required value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} className="admin-input" placeholder="Example: Island Tech Ltd." />
          </label>
          <label className="block md:col-span-1">
            <span className="mb-1.5 block text-xs font-semibold text-slate-600">Owner email</span>
            <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="admin-input" placeholder="owner@example.com" />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-slate-600">Expires in hours</span>
            <input required type="number" min={1} max={168} value={expiresInHours} onChange={(e) => setExpiresInHours(Number(e.target.value))} className="admin-input" />
          </label>
        </div>

        <div>
          <div className="text-xs font-semibold text-slate-600">Apps this business can see in Hub</div>
          <p className="mb-3 mt-1 text-[11px] text-slate-400">Leave all unchecked for Hub-only access.</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.assignableApps.map(app => (
              <label key={app.id} className="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 text-xs hover:bg-slate-50">
                <input type="checkbox" checked={appIds.includes(app.id)} onChange={() => toggleApp(app.id)} />
                <span><strong>{app.shortName}</strong><span className="block text-[10px] text-slate-400">{app.name}</span></span>
              </label>
            ))}
          </div>
        </div>

        <button type="submit" disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-xs font-semibold text-white disabled:opacity-60">
          <Send className="h-4 w-4" /> {busy ? "Creating..." : "Create secure invitation"}
        </button>
      </form>

      {createdUrl && (
        <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="mb-2 text-xs font-bold uppercase tracking-wider text-emerald-700">Copy this invite now</div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input readOnly value={createdUrl} className="admin-input flex-1 font-mono text-[11px]" onFocus={(e) => e.currentTarget.select()} />
            <button onClick={() => void copyInvite()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-700 px-4 py-2.5 text-xs font-semibold text-white">
              <Clipboard className="h-4 w-4" /> Copy
            </button>
          </div>
          <p className="mt-2 text-[11px] text-emerald-800">Do not post this link publicly. Send it only to the approved owner email.</p>
        </section>
      )}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-200 p-4">
          <div>
            <h3 className="font-bold text-slate-900">Owner invitations</h3>
            <p className="mt-0.5 text-xs text-slate-500">{data.invitations.length} recorded invitation{data.invitations.length === 1 ? "" : "s"}</p>
          </div>
          <button onClick={() => void load()} disabled={loading} className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50" title="Refresh invitations">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        <div className="divide-y divide-slate-100">
          {data.invitations.map(invitation => (
            <div key={invitation.id} className="grid gap-3 p-4 lg:grid-cols-[1.2fr_1fr_1fr_auto] lg:items-center">
              <div>
                <div className="font-semibold text-sm text-slate-900">{invitation.organizationName}</div>
                <div className="mt-0.5 text-[11px] text-slate-400">{invitation.organizationSlug}</div>
              </div>
              <div className="text-xs text-slate-600">{invitation.email}</div>
              <div>
                <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${statusClass[invitation.status] || statusClass.revoked}`}>
                  {invitation.status}
                </span>
                <div className="mt-1 text-[10px] text-slate-400">Expires {new Date(invitation.expiresAt).toLocaleString()}</div>
              </div>
              <div className="flex justify-end gap-2">
                {invitation.status === "pending" && (
                  <button onClick={() => void revokeInvitation(invitation)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 px-3 py-2 text-[11px] font-semibold text-rose-700 hover:bg-rose-50">
                    <XCircle className="h-3.5 w-3.5" /> Revoke
                  </button>
                )}
                {invitation.status === "accepted" && invitation.appIds.includes("app-v79pos") && (
                  invitation.appMappings?.find(mapping => mapping.appId === "app-v79pos")?.status === "active"
                    ? <span className="inline-flex items-center rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-emerald-700">POS active</span>
                    : <button onClick={() => void provisionPos(invitation)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-purple-700 px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-50">
                        Provision POS
                      </button>
                )}
                {invitation.status === "accepted" && invitation.appIds.includes("app-ffpro") && (
                  invitation.appMappings?.find(mapping => mapping.appId === "app-ffpro")?.status === "active"
                    ? <span className="inline-flex items-center rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-emerald-700">FFPRO active</span>
                    : <button onClick={() => void provisionFfpro(invitation)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-teal-700 px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-50">
                        Provision FFPRO
                      </button>
                )}
                {invitation.status === "accepted" && invitation.appIds.includes("app-tiquet") && (
                  invitation.appMappings?.find(mapping => mapping.appId === "app-tiquet")?.status === "active"
                    ? <span className="inline-flex items-center rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-emerald-700">Tiquet active</span>
                    : <button onClick={() => void provisionTiquet(invitation)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-700 px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-50">
                        Provision Tiquet
                      </button>
                )}
                {invitation.status === "accepted" && invitation.appIds.includes("app-marketing") && (
                  invitation.appMappings?.find(mapping => mapping.appId === "app-marketing")?.status === "active"
                    ? <span className="inline-flex items-center rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-emerald-700">Marketing active</span>
                    : <button onClick={() => void provisionMarketing(invitation)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-700 px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-50">
                        Provision Marketing
                      </button>
                )}
              </div>
            </div>
          ))}
          {!loading && data.invitations.length === 0 && <div className="p-8 text-center text-sm text-slate-400">No customer invitations have been created.</div>}
        </div>
      </section>
    </div>
  );
}
