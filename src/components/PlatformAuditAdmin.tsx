import { useEffect, useMemo, useState } from "react";
import { Clock3, RefreshCw, Search, ShieldCheck, UserRound } from "lucide-react";

interface AuditEvent {
  id: string;
  type: string;
  createdAt: string;
  details: Record<string, unknown>;
  actor: { id: string; name: string; email: string } | null;
  organization: { id: string; name: string; slug: string } | null;
}

async function loadAudit(): Promise<AuditEvent[]> {
  const response = await fetch("/api/admin/audit?limit=300", { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Audit log could not be loaded.");
  return Array.isArray(payload.events) ? payload.events : [];
}

function eventLabel(type: string) {
  return type
    .replaceAll("_", " ")
    .replace(/w/g, value => value.toUpperCase());
}

function safeDetails(details: Record<string, unknown>) {
  const allowed = Object.entries(details || {})
    .filter(([key]) => !/token|secret|password|hash/i.test(key))
    .slice(0, 8);
  return allowed.map(([key, value]) => {
    const text = Array.isArray(value) ? value.join(", ") : typeof value === "object" && value !== null ? JSON.stringify(value) : String(value ?? "");
    return `${key.replaceAll("_", " ")}: ${text}`;
  });
}

export function PlatformAuditAdmin() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  const refresh = async () => {
    setBusy(true);
    setError("");
    try {
      setEvents(await loadAudit());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Audit log could not be loaded.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { void refresh(); }, []);

  const types = useMemo(() => [...new Set(events.map(event => event.type))].sort(), [events]);
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return events.filter(event => {
      const matchesType = !type || event.type === type;
      const matchesSearch = !term || [
        event.type,
        event.actor?.name,
        event.actor?.email,
        event.organization?.name,
        ...safeDetails(event.details),
      ].some(value => String(value || "").toLowerCase().includes(term));
      return matchesType && matchesSearch;
    });
  }, [events, search, type]);

  return (
    <div className="space-y-5">
      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</div>}

      <section className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-cyan-700" />
              <h2 className="font-bold text-slate-900">Audit & security activity</h2>
            </div>
            <p className="mt-1 text-xs text-slate-500">Owner invitations, provisioning, entitlement changes, customer suspension/reactivation, MFA and other Hub security events.</p>
          </div>
          <button onClick={() => void refresh()} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>

        <div className="p-4 border-b border-slate-200 grid md:grid-cols-[1fr_260px] gap-3">
          <label className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input value={search} onChange={e => setSearch(e.target.value)} className="admin-input pl-9" placeholder="Search actor, customer or event" />
          </label>
          <select value={type} onChange={e => setType(e.target.value)} className="admin-input">
            <option value="">All event types</option>
            {types.map(value => <option key={value} value={value}>{eventLabel(value)}</option>)}
          </select>
        </div>

        <div className="divide-y divide-slate-100">
          {filtered.map(event => {
            const details = safeDetails(event.details);
            return (
              <div key={event.id} className="p-4 grid lg:grid-cols-[190px_1fr_220px] gap-4">
                <div>
                  <div className="inline-flex items-center gap-1.5 text-[10px] font-bold text-slate-500">
                    <Clock3 className="w-3.5 h-3.5" />
                    {new Date(event.createdAt).toLocaleDateString()} {new Date(event.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                  <div className="mt-2 text-[10px] text-slate-400">{event.organization?.name || "Platform-wide"}</div>
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-900">{eventLabel(event.type)}</div>
                  {details.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {details.map(detail => <span key={detail} className="rounded-md bg-slate-50 border border-slate-100 px-2 py-1 text-[9px] text-slate-500">{detail}</span>)}
                    </div>
                  )}
                </div>
                <div className="flex items-start gap-2">
                  <UserRound className="w-4 h-4 text-slate-400 mt-0.5" />
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold text-slate-700 truncate">{event.actor?.name || "System / customer action"}</div>
                    <div className="text-[9px] text-slate-400 truncate">{event.actor?.email || "No platform actor"}</div>
                  </div>
                </div>
              </div>
            );
          })}
          {!busy && filtered.length === 0 && <div className="p-10 text-center text-sm text-slate-400">No audit events match these filters.</div>}
        </div>
      </section>
    </div>
  );
}
