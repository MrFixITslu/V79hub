import { useEffect, useState } from "react";
import { ClipboardList, RefreshCcw, ShieldCheck } from "lucide-react";

type CooTask = {
  lane: string; repo: string; number: number; kind: "pr" | "issue";
  label: string; nextStep: string; githubState:
    "OPEN_IN_GITHUB" | "NOT_LISTED_AS_OPEN" | "UNKNOWN_INCOMPLETE" | "UNKNOWN_SOURCE";
  url: string; updatedAt: string | null;
};
type CooReport = {
  mode: "read-only"; source: "github-issue-pr-register"; collectedAt: string;
  connection: "DISABLED" | "NOT_CONFIGURED" | "PARTIAL_OR_COMPLETE" | "UNAVAILABLE";
  lanes: string[]; repositories: Array<{repo: string; fetchState: string}>;
  tracked: CooTask[]; runtimeHealth: "UNKNOWN"; deployedRevision: "UNKNOWN";
  customerLaunchGo: "NOT_ESTABLISHED"; sentinelCoverage: "NOT_ESTABLISHED";
  approvalGranted: false; executionEnabled: false; caveat: string;
};

function validReport(value: unknown): value is CooReport {
  if (!value || typeof value !== "object") return false;
  const v = value as Partial<CooReport>;
  return v.mode === "read-only" && v.source === "github-issue-pr-register" &&
    v.runtimeHealth === "UNKNOWN" && v.deployedRevision === "UNKNOWN" &&
    v.customerLaunchGo === "NOT_ESTABLISHED" && v.sentinelCoverage === "NOT_ESTABLISHED" &&
    v.approvalGranted === false && v.executionEnabled === false &&
    Array.isArray(v.lanes) && Array.isArray(v.tracked) && Array.isArray(v.repositories) &&
    v.tracked.every(item =>
      typeof item.label === "string" && typeof item.nextStep === "string" &&
      typeof item.url === "string" && item.url.startsWith("https://github.com/MrFixITslu/") &&
      ["OPEN_IN_GITHUB", "NOT_LISTED_AS_OPEN", "UNKNOWN_INCOMPLETE", "UNKNOWN_SOURCE"].includes(item.githubState));
}

export type CooWorkItemDraft = { sourceId: string; system: string; summary: string; detail: string };

const issueSystem: Record<string, string> = {
  V79hub: "hub", V79Tiquet: "tiquet", "V79-Sentinel": "sentinel",
  V79Marketing: "marketing", V79acaedmy: "academy", V79POS: "pos",
};
export function OwnerCooWorkboardPanel({ onPrepareTask, embedded = false, active = true }: {
  onPrepareTask?: (draft: CooWorkItemDraft) => void;
  embedded?: boolean;
  active?: boolean;
} = {}) {
  const [open, setOpen] = useState(embedded);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<CooReport | null>(null);
  const [error, setError] = useState("");

  async function refresh() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/agent/coo-workboard", {
        credentials: "same-origin", cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(response.status === 403 ? "An MFA-verified founder session is required."
          : "COO workboard is unavailable.");
      }
      const data: unknown = await response.json();
      if (!validReport(data)) throw new Error("COO evidence failed read-only safety validation.");
      setReport(data);
    } catch (e) {
      setReport(null); // Never keep an apparently current last-success view after an error.
      setError(e instanceof Error ? e.message : "Unable to verify source data.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (embedded && active) void refresh();
  }, [embedded, active]);

  function toggle() {
    if (!open && !report && !busy) void refresh();
    setOpen(!open);
  }

  return (
    <section aria-label="COO GitHub delivery workboard" className="border-b border-slate-800 bg-slate-950 px-5 py-4 text-sm">
      {!embedded && <button type="button" aria-expanded={open} onClick={toggle}
        className="flex items-center gap-2 text-left font-semibold text-cyan-200 focus-visible:ring-2 focus-visible:ring-cyan-400">
        <ClipboardList className="w-4 h-4" aria-hidden="true" />
        COO workboard · P1/P2 engineering
      </button>}
      {open && <div className="mt-3 space-y-3">
        <p className="text-xs text-slate-400">
          Founder-only, read-only GitHub task register. Issue status is not app uptime, protection, security clearance, revenue or permission to deploy.
        </p>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <button type="button" disabled={busy} onClick={() => void refresh()}
            className="inline-flex items-center gap-2 rounded-lg border border-cyan-700 px-3 py-2 text-cyan-200 disabled:opacity-50">
            <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
            {busy ? "Checking GitHub..." : "Refresh read-only status"}
          </button>
          <span className="inline-flex items-center gap-1 text-emerald-300">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> No agent approvals or actions
          </span>
        </div>
        {error && <p role="alert" className="text-xs text-amber-200">{error}</p>}
        {report && <div className="space-y-3">
          <p className="text-xs text-slate-400">
            GitHub access: {report.connection.replaceAll("_", " ")} · Checked: {new Date(report.collectedAt).toLocaleString()}
          </p>
          <p className="text-xs text-amber-200">
            Production health: unknown · Sentinel verified protection: not established · Customer release: not established
          </p>
          {report.lanes.map(lane => <div key={lane} className="rounded-xl border border-slate-800 bg-slate-900 p-3">
            <h3 className="text-xs font-semibold text-cyan-200">{lane}</h3>
            <div className="mt-2 space-y-3">
              {report.tracked.filter(item => item.lane === lane).map(item => <div key={item.repo + item.number + item.kind}
                className="border-t border-slate-800 pt-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <a className="font-medium text-slate-100 underline underline-offset-2 hover:text-cyan-200"
                    href={item.url} target="_blank" rel="noopener noreferrer">{item.label}</a>
                  <span className={item.githubState === "OPEN_IN_GITHUB" ? "text-cyan-200 text-xs" : "text-amber-200 text-xs"}>
                    {item.githubState.replaceAll("_", " ")}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{item.repo} · Review: {item.nextStep}</p>
                {onPrepareTask && item.githubState === "OPEN_IN_GITHUB" && issueSystem[item.repo] && (
                  <button type="button" className="mt-2 rounded-md border border-slate-600 px-2 py-1 text-xs text-cyan-200"
                    onClick={() => onPrepareTask({
                      sourceId: item.repo + "#" + item.number,
                      system: issueSystem[item.repo],
                      summary: ("Review: " + item.label).slice(0,180),
                      detail: ("Inspect " + item.url + ". " + item.nextStep +
                        ". Record source evidence, test results and decisions needed. No production change or customer action is authorized.").slice(0,2000),
                    })}>
                    Prepare COO work item · approval required
                  </button>
                )}
              </div>)}
            </div>
          </div>)}
          {report.repositories.some(r => r.fetchState !== "COMPLETE") && <p className="text-xs text-amber-200">
            At least one repository is inaccessible or incompletely listed. Missing tasks must not be treated as closed.
          </p>}
          <p className="text-xs text-slate-400">No tasks, settings, customers, accounts or production services were modified by this read.</p>
        </div>}
      </div>}
    </section>
  );
}
