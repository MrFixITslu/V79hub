/**
 * G1 supervised development-worker proposal contract.
 *
 * This worker never reads a repository, executes a patch, writes GitHub,
 * starts a process, or authorizes deployment. It produces unverified draft
 * diffs, constrained to an owner-supplied allowlist for later human review.
 */
export type DevelopmentWorkOrder = Readonly<{
  repository: "MrFixITslu/V79hub";
  baseCommit: string;
  taskId: string;
  objective: string;
  files: readonly Readonly<{ path: string; sourceBlob: string; excerpt: string }>[];
}>;

export type DevelopmentDraftChange = Readonly<{
  path: string;
  unifiedDiff: string;
  reason: string;
}>;

export type DevelopmentDraft = Readonly<{
  summary: string;
  changes: readonly DevelopmentDraftChange[];
  testIdeas: readonly string[];
  risks: readonly string[];
}>;

export type DevelopmentProposer = (order: DevelopmentWorkOrder) => Promise<unknown>;

export class InvalidDevelopmentOrder extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidDevelopmentOrder";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function safeText(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max &&
    !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value);
}
const SHA = /^[a-f0-9]{40}$/;
const TASK = /^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$/;

function allowedPath(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 180 || value.includes("\\") ||
      value.startsWith("/") || value.includes("..") ||
      value.includes("//") || /[\r\n\0]/.test(value)) return false;
  // This initial slice is intentionally Hub-agent-scoped. Sentinel's separate
  // source repository requires its own later allowlist and source audit.
  return value.startsWith("agent-service/src/") && value.endsWith(".ts") ||
    value.startsWith("agent-service/tests/") && value.endsWith(".test.ts");
}

export function validateDevelopmentWorkOrder(input: unknown): DevelopmentWorkOrder {
  if (!isRecord(input)) throw new InvalidDevelopmentOrder("Work order is required.");
  if (input.repository !== "MrFixITslu/V79hub") {
    throw new InvalidDevelopmentOrder("Only the inspected V79hub repository is in scope.");
  }
  if (typeof input.baseCommit !== "string" || !SHA.test(input.baseCommit)) {
    throw new InvalidDevelopmentOrder("A pinned 40-character base commit is required.");
  }
  if (typeof input.taskId !== "string" || !TASK.test(input.taskId)) {
    throw new InvalidDevelopmentOrder("Invalid task identifier.");
  }
  if (!safeText(input.objective, 1200)) {
    throw new InvalidDevelopmentOrder("Objective is missing or too long.");
  }
  if (!Array.isArray(input.files) || input.files.length < 1 || input.files.length > 3) {
    throw new InvalidDevelopmentOrder("One to three explicitly scoped source files are required.");
  }
  const files: Array<{path: string; sourceBlob: string; excerpt: string}> = [];
  for (const file of input.files) {
    if (!isRecord(file) || !allowedPath(file.path) ||
        typeof file.sourceBlob !== "string" || !SHA.test(file.sourceBlob) ||
        !safeText(file.excerpt, 3500)) {
      throw new InvalidDevelopmentOrder("Invalid source file, blob identity or excerpt.");
    }
    if (files.some(existing => existing.path === file.path)) {
      throw new InvalidDevelopmentOrder("Duplicate scoped source path.");
    }
    files.push({
      path: file.path,
      sourceBlob: file.sourceBlob,
      excerpt: file.excerpt,
    });
  }
  return {
    repository: "MrFixITslu/V79hub",
    baseCommit: input.baseCommit,
    taskId: input.taskId,
    objective: input.objective,
    files,
  };
}

function parseDraft(raw: unknown, allowed: readonly string[]): DevelopmentDraft {
  let value = raw;
  if (typeof value === "string") {
    if (value.length > 25000) throw new Error("Model response exceeded size limit.");
    try { value = JSON.parse(value); } catch { throw new Error("Model response was not valid JSON."); }
  }
  if (!isRecord(value) || !safeText(value.summary, 800) ||
      !Array.isArray(value.changes) || value.changes.length < 1 ||
      value.changes.length > allowed.length ||
      !Array.isArray(value.testIdeas) || value.testIdeas.length > 5 ||
      !Array.isArray(value.risks) || value.risks.length > 5) {
    throw new Error("Development proposal failed schema validation.");
  }
  const changes: DevelopmentDraftChange[] = [];
  for (const item of value.changes) {
    if (!isRecord(item) || typeof item.path !== "string" ||
        !allowed.includes(item.path) || changes.some(change => change.path === item.path) ||
        !safeText(item.reason, 600) || !safeText(item.unifiedDiff, 10000)) {
      throw new Error("Proposal changed an unapproved path or exceeded its bounds.");
    }
    const lines = item.unifiedDiff.split("\n");
    const header = ["--- a/" + item.path, "+++ b/" + item.path];
    if (lines[0] !== header[0] || lines[1] !== header[1] ||
        !lines.some(line => /^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@/.test(line)) ||
        lines.slice(2).some(line => /^(?:--- |\+\+\+ |diff --git |rename (?:from|to) |Binary files )/.test(line))) {
      throw new Error("Proposal did not contain a single-file unified diff.");
    }
    changes.push({ path: item.path, reason: item.reason, unifiedDiff: item.unifiedDiff });
  }
  const list = (input: unknown[], max: number) => {
    if (!input.every(item => safeText(item, max))) {
      throw new Error("Invalid test or risk description.");
    }
    return input as string[];
  };
  return {
    summary: value.summary,
    changes,
    testIdeas: list(value.testIdeas, 320),
    risks: list(value.risks, 320),
  };
}

export async function generateDevelopmentReview(
  input: unknown, proposer: DevelopmentProposer,
) {
  const order = validateDevelopmentWorkOrder(input);
  const raw = await proposer(order);
  const draft = parseDraft(raw, order.files.map(file => file.path));
  return {
    version: "0.1" as const,
    mode: "review-only" as const,
    status: "unverified-proposal" as const,
    taskId: order.taskId,
    repository: order.repository,
    sourceBase: order.baseCommit,
    scopedSources: order.files.map(file => ({ path: file.path, suppliedBlob: file.sourceBlob })),
    draft,
    sourceVerifiedAgainstGitHub: false as const,
    diffApplied: false as const,
    testsExecuted: 0 as const,
    gitWrites: 0 as const,
    productionWrites: 0 as const,
    ownerApprovalRequired: true as const,
    note: "Untrusted AI-generated draft. Compare against the exact source, run tests in an isolated checkout, and review before creating any PR.",
  };
}
