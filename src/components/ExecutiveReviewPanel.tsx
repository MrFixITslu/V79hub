import { useEffect, useState } from "react";
import { BriefcaseBusiness, ClipboardList, RefreshCcw, ShieldCheck } from "lucide-react";

type ExecutiveRole = {
  id: "ceo" | "coo";
  name: string;
  accountability: string;
  mode: "read-only";
  approvalAuthority: "none";
};
type ExecutiveStructure = {
  mode: "read-only";
  actionsEnabled: false;
  roles: ExecutiveRole[];
};
type ExecutiveFinding = {
  id: string;
  system: string;
  severity: "attention" | "watch" | "information";
  title: string;
  metric: string;
  value: number;
  reportedAt: string;
  nextStep: string;
};
type ExecutiveHandoff = {
  mode: "read-only";
  state: "ceo-review-only";
  ownerApprovalGranted: false;
  executionEnabled: false;
  source: {
    collectedAt: string | null;
    coverage: string;
    status: string;
  };
  ceoReview: {
    priority: string;
    recommendation: string;
    requiresOwnerDecision: boolean;
  };
  cooReport: {
    findings: ExecutiveFinding[];
    unavailableSources: Array<{system: string; reason: string}>;
  };
};

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...init,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const label = response.status === 403
      ? "MFA-verified owner session required."
      : typeof body.error === "string" ? body.error : "Executive service unavailable.";
    throw new Error(label);
  }
  return body as T;
}

export function ExecutiveReviewPanel() {
  const [structure, setStructure] = useState<ExecutiveStructure | null>(null);
  const [handoff, setHandoff] = useState<ExecutiveHandoff | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    readJson<ExecutiveStructure>("/api/agent/executive-structure")
      .then(data => {
        if (!active) return;
        if (data.mode !== "read-only" || data.actionsEnabled !== false ||
            !Array.isArray(data.roles) || data.roles.length !== 2 ||
            !data.roles.every(role => role.mode === "read-only" && role.approvalAuthority === "none")) {
          throw new Error("Executive role configuration failed safety validation.");
        }
        setStructure(data);
      })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : "Unavailable"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const loadHandoff = async () => {
    if (!structure || refreshing) return;
    setRefreshing(true);
    setError("");
    try {
      const data = await readJson<ExecutiveHandoff>("/api/agent/executive-handoff", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: "{}",
      });
      if (data.mode !== "read-only" || data.state !== "ceo-review-only" ||
          data.executionEnabled !== false || data.ownerApprovalGranted !== false ||
          !Array.isArray(data.cooReport?.findings)) {
        throw new Error("Executive handoff failed safety validation.");
      }
      setHandoff(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Executive handoff unavailable");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <section aria-label="CEO and COO executive review" className="border-b border-slate-800 bg-slate-950 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <BriefcaseBusiness aria-hidden="true" className="mt-0.5 h-4 w-4 text-cyan-300" />
          <div>
            <h2 className="font-semibold text-slate-100 text-sm">Executive command review</h2>
            <p className="text-xs text-slate-400">COO gathers verified exceptions; CEO reviews priorities. You retain all decision authority.</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 text-xs text-emerald-300">
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Read-only · No autonomous actions
        </span>
      </div>

      {loading && <p className="mt-3 text-xs text-slate-400">Checking executive access...</p>}
      {structure && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            {structure.roles.map(role => (
              <div key={role.id} className="rounded-xl border border-slate-800 bg-slate-900 px-3 py-3">
                <div className="font-semibold text-xs text-cyan-200">{role.name}</div>
                <p className="mt-1 text-xs text-slate-300">{role.accountability}</p>
                <p className="mt-2 text-[11px] text-slate-500">Review only · Cannot authorize or execute</p>
              </div>
            ))}
          </div>
          <button type="button" onClick={loadHandoff} disabled={refreshing}
            className="mt-3 inline-flex items-center gap-2 rounded-lg border border-cyan-700 px-3 py-2 text-xs text-cyan-200 hover:bg-slate-900 disabled:opacity-50">
            <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
            {refreshing ? "Reading verified evidence..." : "Generate COO → CEO review"}
          </button>
        </>
      )}

      {error && <p role="alert" className="mt-3 text-xs text-amber-200">{error}</p>}

      {handoff && (
        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-xs text-slate-200">
          <div className="flex flex-wrap items-center gap-2 font-semibold text-cyan-200">
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
            COO evidence handoff → CEO
            <span className="font-normal text-slate-400">Priority: {handoff.ceoReview.priority}</span>
          </div>
          <p className="mt-2">{handoff.ceoReview.recommendation}</p>
          <p className="mt-1 text-slate-400">
            Coverage: {handoff.source.coverage} · Last collected: {handoff.source.collectedAt
              ? new Date(handoff.source.collectedAt).toLocaleString() : "Unavailable"}
          </p>
          {handoff.source.status !== "available" && (
            <p className="mt-2 text-amber-200">Some sources are missing or outdated. This is not an all-clear.</p>
          )}
          <div className="mt-3 space-y-2">
            {handoff.cooReport.findings.map(finding => (
              <div key={finding.id} className="rounded-lg border border-slate-700 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{finding.title}</span>
                  <span className={finding.severity === "attention" ? "text-amber-300" : "text-cyan-300"}>{finding.severity}</span>
                </div>
                <p className="mt-1 text-slate-400">
                  {finding.system} · {finding.metric}: {Number(finding.value).toLocaleString()}
                </p>
                <p className="mt-1">Review: {finding.nextStep}</p>
              </div>
            ))}
            {handoff.cooReport.findings.length === 0 && (
              <p className="text-slate-400">No currently verified exception meets the handoff rules. Missing sources may still exist.</p>
            )}
            {handoff.cooReport.unavailableSources.length > 0 && (
              <p className="text-amber-200">
                Missing/unverified: {handoff.cooReport.unavailableSources.map(item => `${item.system} (${item.reason})`).join(", ")}
              </p>
            )}
          </div>
          <p className="mt-3 text-[11px] text-slate-400">
            No records were modified, no approval was granted, and no message was sent by this review.
          </p>
        </div>
      )}
    </section>
  );
}
