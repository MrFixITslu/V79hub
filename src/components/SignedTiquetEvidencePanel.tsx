import { useState } from "react";
import { ShieldCheck, RefreshCw, AlertCircle } from "lucide-react";

type SignedMetric = { key: string; value: number };
type SignedTiquetSnapshot = {
  status: "available"; source: "tiquet"; provenance: "source_signed";
  observedAt: string; metrics: SignedMetric[]; executionEnabled: false;
};

const metricLabels: Record<string, string> = Object.freeze({
  clients: "Clients",
  jobs: "Jobs",
  teamMembers: "Team members",
  unreadNotifications: "Unread notifications",
  jobValueTotal: "Total job value",
});
const allowedKeys = Object.keys(metricLabels);

function validSnapshot(value: unknown): value is SignedTiquetSnapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const data = value as Record<string, unknown>;
  if (data.status !== "available" || data.source !== "tiquet" ||
      data.provenance !== "source_signed" || data.executionEnabled !== false ||
      typeof data.observedAt !== "string" || !Number.isFinite(Date.parse(data.observedAt)) ||
      !Array.isArray(data.metrics) || data.metrics.length !== allowedKeys.length) return false;
  const names = new Set<string>();
  for (const item of data.metrics as unknown[]) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const metric = item as Record<string, unknown>;
    if (typeof metric.key !== "string" || !Object.hasOwn(metricLabels, metric.key) ||
        names.has(metric.key) || typeof metric.value !== "number" ||
        !Number.isFinite(metric.value)) return false;
    names.add(metric.key);
  }
  return names.size === allowedKeys.length;
}

/**
 * The source check is an explicit, read-only owner action. Neither the
 * current agent investigation nor any proposal is relabelled source_signed.
 * The only trust decision lives on Hub's server-side Ed25519 verifier.
 */
export function SignedTiquetEvidencePanel() {
  const [snapshot, setSnapshot] = useState<SignedTiquetSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const verify = async () => {
    if (busy) return;
    setBusy(true);
    setSnapshot(null);
    setStatus("");
    try {
      const response = await fetch("/api/agent/sources/tiquet/metrics", {
        method: "GET", credentials: "same-origin", cache: "no-store",
      });
      if (!response.ok) {
        setStatus(response.status === 403
          ? "A founder session with completed MFA is required."
          : "Source-signed evidence is not enabled or the source is unavailable. Unknown is not zero.");
        return;
      }
      const payload: unknown = await response.json();
      if (!validSnapshot(payload)) {
        setStatus("The verified source did not return the expected safe metric set.");
        return;
      }
      setSnapshot(payload);
    } catch {
      setStatus("Tiquet source verification could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Tiquet original-source verification" className="border-b border-slate-800 bg-slate-900/70 px-5 py-3 text-sm">
      <div className="flex flex-wrap justify-between items-center gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-slate-100">
            <ShieldCheck className="w-4 h-4 text-cyan-300" />
            Tiquet source integrity
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Independent signature check · Five aggregate counters only · No actions
          </p>
        </div>
        <button
          type="button"
          onClick={verify}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-700 px-3 py-2 text-xs font-medium text-cyan-200 disabled:opacity-40"
        >
          <RefreshCw className={`w-4 h-4 ${busy ? "animate-spin" : ""}`} />
          {busy ? "Checking source..." : "Verify Tiquet data"}
        </button>
      </div>
      {status && (
        <p role="status" className="mt-3 flex gap-2 items-center text-xs text-amber-200">
          <AlertCircle className="h-4 w-4 shrink-0" /> {status}
        </p>
      )}
      {snapshot && (
        <div className="mt-3 space-y-2" role="status">
          <p className="text-xs text-emerald-300 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            Source signature verified · Observed {new Date(snapshot.observedAt).toLocaleString()}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {snapshot.metrics.map(metric => (
              <div key={metric.key} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2">
                <p className="text-xs text-slate-400">{metricLabels[metric.key]}</p>
                <p className="text-base font-semibold text-slate-100 tabular-nums">
                  {metric.value.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400">
            Verified figures are read-only. Existing AI findings and approval proposals are
            not automatically upgraded to source-signed evidence. Execution stays disabled.
          </p>
        </div>
      )}
    </section>
  );
}
