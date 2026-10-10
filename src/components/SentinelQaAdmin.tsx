import { useEffect, useState } from "react";
import { RefreshCw, ShieldCheck } from "lucide-react";
import { createSupervisedQa, cleanupSupervisedQa } from "../lib/sentinel-qa-client.mjs";

type QaOrganization = { id: string; name: string; eligible: boolean; memberCount?: number; reason?: string };
type QaStatus = {
  createEnabled: boolean; cleanupEnabled: boolean; maintenanceReady: boolean;
  organizations: QaOrganization[]; userCount: number; organizationCount: number;
  syntheticUserCount: number; syntheticMembershipCount: number;
  latestCleanup: { auditId: string; organizationId: string; syntheticUsersDeleted: number; createdAt: string } | null;
};
type CleanupPreview = {
  state: string; organizationId: string; organizationName: string; memberCount: number;
  previewHash: string; externalTenants: number; billingReferences: number;
};

async function qaRequest<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  const response = await fetch("/api/admin/sentinel-qa/" + path, {
    method: body ? "POST" : "GET", credentials: "same-origin", cache: "no-store",
    ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Sentinel request failed. Refresh status before retrying.");
  return payload as T;
}

export function SentinelQaAdmin() {
  const [status, setStatus] = useState<QaStatus | null>(null);
  const [preview, setPreview] = useState<CleanupPreview | null>(null);
  const [createPhrase, setCreatePhrase] = useState("");
  const [deletePhrase, setDeletePhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uncertain, setUncertain] = useState(false);

  const refresh = async () => {
    setBusy(true); setError(""); setPreview(null); setDeletePhrase("");
    try { setStatus(await qaRequest<QaStatus>("status")); setUncertain(false); }
    catch (e) { setStatus(null); setError(e instanceof Error ? e.message : "Status unavailable."); }
    finally { setBusy(false); }
  };
  useEffect(() => { void refresh(); }, []);

  const create = async () => {
    if (busy || uncertain || !status?.createEnabled || !status.cleanupEnabled || !status.maintenanceReady ||
        status.organizations.length || status.syntheticUserCount || createPhrase !== "CREATE ISOLATED SENTINEL QA") return;
    setBusy(true); setError(""); setNotice(""); setPreview(null); setDeletePhrase("");
    try {
      // Credentials returned by the existing API are discarded here. Never place
      // passwords in React state, rendered markup, storage, logs or downloads.
      const current = await createSupervisedQa(qaRequest, status) as QaStatus;
      setCreatePhrase(""); setStatus(current);
      setNotice("Created one temporary Hub organization with three synthetic identities. Preview its cleanup next.");
    } catch (e) {
      setUncertain(true);
      setError((e instanceof Error ? e.message : "Creation response unavailable.") + " Refresh status to reconcile the outcome before another mutation.");
    } finally { setBusy(false); }
  };

  const loadPreview = async (organization: QaOrganization) => {
    if (busy || !status?.cleanupEnabled || !organization.eligible) return;
    setBusy(true); setError(""); setPreview(null); setDeletePhrase(""); setNotice("");
    try {
      const result = await qaRequest<CleanupPreview>("organizations/" + encodeURIComponent(organization.id) + "/cleanup-preview");
      if (result.state !== "eligible-hub-only" || result.organizationId !== organization.id ||
          result.organizationName !== organization.name || result.externalTenants !== 0 || result.billingReferences !== 0) {
        throw new Error("Cleanup preview did not match the exact temporary organization.");
      }
      setPreview(result);
    } catch (e) { setError(e instanceof Error ? e.message : "Cleanup preview unavailable."); }
    finally { setBusy(false); }
  };

  const cleanup = async () => {
    if (busy || uncertain || !preview || !status?.cleanupEnabled || !status.maintenanceReady ||
        deletePhrase !== "DELETE " + preview.organizationName) return;
    const target = preview;
    setBusy(true); setError(""); setNotice("");
    try {
      const current = await cleanupSupervisedQa(qaRequest, target, deletePhrase) as QaStatus;
      setPreview(null); setDeletePhrase(""); setStatus(current);
      setNotice("Cleanup verified: the temporary organization, " + target.memberCount + " identities and their memberships are absent. The deletion audit was retained.");
    } catch (e) {
      setUncertain(true); setPreview(null); setDeletePhrase("");
      setError((e instanceof Error ? e.message : "Cleanup response unavailable.") + " Refresh status to reconcile; do not create replacement resources.");
    } finally { setBusy(false); }
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4" aria-label="Sentinel supervised testing">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-bold text-slate-900 flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-cyan-700" />Sentinel supervised testing</h2>
          <p className="text-sm text-slate-500 mt-1">Create one temporary Hub workspace, review its exact cleanup, then verify removal.</p>
        </div>
        <button disabled={busy} onClick={() => void refresh()} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm disabled:opacity-50">
          <RefreshCw className={busy ? "w-4 h-4 animate-spin" : "w-4 h-4"} />Refresh test status
        </button>
      </div>
      {error && <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      {notice && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
      {status && <>
        <div className="flex flex-wrap gap-3 text-sm text-slate-700">
          <span>Creation: {status.createEnabled ? "Enabled" : "Disabled"}</span>
          <span>Cleanup: {status.cleanupEnabled ? "Enabled" : "Disabled"}</span>
          <span>Maintenance: {status.maintenanceReady ? "Ready" : "Blocked"}</span>
          <span>Test organizations: {status.organizations.length}</span>
          <span>Synthetic users: {status.syntheticUserCount}</span>
          <span>Synthetic memberships: {status.syntheticMembershipCount}</span>
        </div>
        {(!status.createEnabled || !status.cleanupEnabled || !status.maintenanceReady) &&
          <p className="text-sm text-amber-800">Live mutations require the reviewed maintenance configuration and a quiet Hub. These controls cannot change release flags or pause workers.</p>}
        <div className="flex flex-col sm:flex-row gap-3">
          <label className="flex-1 text-sm text-slate-700">Creation confirmation
            <input className="admin-input mt-1" value={createPhrase} disabled={busy} onChange={e => setCreatePhrase(e.target.value)} placeholder="CREATE ISOLATED SENTINEL QA" autoComplete="off" />
          </label>
          <button onClick={() => void create()} disabled={busy || uncertain || !status.createEnabled || !status.cleanupEnabled || !status.maintenanceReady || status.organizations.length > 0 || status.syntheticUserCount > 0 || createPhrase !== "CREATE ISOLATED SENTINEL QA"}
            className="self-end rounded-lg bg-slate-950 text-white px-4 py-2 text-sm disabled:opacity-40">Create temporary test organization</button>
        </div>
        {status.organizations.map(o => <div key={o.id} className="rounded-xl border border-slate-200 p-4 space-y-2">
          <p className="font-semibold text-sm break-all text-slate-900">{o.name}</p>
          <p className="text-sm text-slate-600">{o.eligible ? "Trusted test manifest: " + o.memberCount + " synthetic identities." : o.reason}</p>
          <button onClick={() => void loadPreview(o)} disabled={busy || uncertain || !status.cleanupEnabled || !o.eligible} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40">Preview exact cleanup</button>
        </div>)}
        {preview && <div className="rounded-xl border border-rose-200 p-4 space-y-3">
          <h3 className="font-semibold text-slate-900">Exact temporary resource cleanup</h3>
          <p className="text-sm break-all text-slate-700">{preview.organizationName}</p>
          <p className="text-sm text-slate-600">{preview.memberCount} synthetic identities · {preview.externalTenants} external tenants · {preview.billingReferences} billing references</p>
          <label className="block text-sm text-slate-700">Deletion confirmation
            <input className="admin-input mt-1" value={deletePhrase} disabled={busy} onChange={e => setDeletePhrase(e.target.value)} placeholder={"DELETE " + preview.organizationName} autoComplete="off" />
          </label>
          <button onClick={() => void cleanup()} disabled={busy || uncertain || !status.cleanupEnabled || !status.maintenanceReady || deletePhrase !== "DELETE " + preview.organizationName}
            className="rounded-lg bg-rose-700 px-4 py-2 text-sm text-white disabled:opacity-40">Delete exact temporary resources</button>
        </div>}
        {status.latestCleanup && <p className="text-sm break-all text-slate-500">Latest retained cleanup audit: {status.latestCleanup.auditId} · {status.latestCleanup.syntheticUsersDeleted} synthetic identities removed.</p>}
      </>}
    </section>
  );
}
