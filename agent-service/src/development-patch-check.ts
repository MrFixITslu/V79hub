import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { lstatSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep } from "node:path";
import {
  generateDevelopmentReview,
  type DevelopmentDraft,
} from "./development-worker.js";
import { verifyPinnedDevelopmentSources } from "./development-source.js";

/**
 * G1.3: read-only Git patch applicability test, NEVER a patch executor.
 *
 * Caller must independently create a PRIVATE disposable checkout at an exact
 * pinned SHA. The model has no control over this directory and never obtains
 * shell, filesystem or GitHub write tools. This module only calls Git builtins
 * with fixed argument arrays, and `git apply --check` never applies a patch.
 */
export class DevelopmentPatchCheckError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DevelopmentPatchCheckError";
  }
}

function git(repo: string, args: readonly string[], input?: string) {
  try {
    return execFileSync("git", ["-C", repo, ...args], {
      input,
      encoding: "utf8",
      timeout: 5000,
      maxBuffer: 65536,
      stdio: ["pipe", "pipe", "ignore"],
      env: {
        ...process.env,
        GIT_CONFIG_NOSYSTEM: "1",
        GIT_CONFIG_GLOBAL: "/dev/null",
        GIT_CONFIG_SYSTEM: "/dev/null",
        GIT_CONFIG_COUNT: "0",
        GIT_OPTIONAL_LOCKS: "0",
        GIT_TERMINAL_PROMPT: "0",
      },
    });
  } catch {
    throw new DevelopmentPatchCheckError("Sandbox Git validation failed.");
  }
}

function requirePrivateDisposableCheckout(provided: string): string {
  if (typeof provided !== "string" || !provided.startsWith("/") ||
      provided.includes("\0")) {
    throw new DevelopmentPatchCheckError("Absolute disposable checkout required.");
  }
  const root = resolve(provided);
  const actual = realpathSync(root);
  const parent = realpathSync(tmpdir());
  if (root !== actual || !root.startsWith(parent + sep + "v79-dev-sandbox-") ||
      root.length <= parent.length + "/v79-dev-sandbox-".length) {
    throw new DevelopmentPatchCheckError("Checkout is not in an approved disposable sandbox.");
  }
  const st = lstatSync(root);
  if (!st.isDirectory() || st.isSymbolicLink() ||
      (st.mode & 0o077) !== 0 ||
      (typeof process.getuid === "function" && st.uid !== process.getuid())) {
    throw new DevelopmentPatchCheckError("Sandbox must be a private owner-controlled directory.");
  }
  const gitRoot = git(root, ["rev-parse", "--show-toplevel"]).trim();
  if (realpathSync(gitRoot) !== root) {
    throw new DevelopmentPatchCheckError("Nested checkout or unexpected Git root.");
  }
  if (git(root, ["status", "--porcelain", "--untracked-files=all"]).trim()) {
    throw new DevelopmentPatchCheckError("Sandbox source is not pristine.");
  }
  return root;
}

export type DryRunResult = Readonly<{
  version: "0.3";
  mode: "isolated-patch-check";
  status: "PATCH_APPLIES_UNVERIFIED";
  sourceCommit: string;
  taskId: string;
  localGitTreeVerified: true;
  githubOriginVerified: false;
  patchApplied: false;
  codeExecuted: false;
  testsExecuted: 0;
  productionWrites: 0;
  githubWrites: 0;
  files: readonly { path: string; patchSha256: string; applicable: true }[];
  ownerApprovalRequired: true;
}>;

/**
 * Caller supplies an AI-generated draft, exact work order and disposable
 * checkout path. Model content is validated by v0.1 and source identity by
 * v0.2 before git sees any patch. No model execution or network access.
 */
export async function dryRunDevelopmentProposal(
  workOrder: unknown,
  draft: unknown,
  disposableCheckout: string,
): Promise<DryRunResult> {
  const root = requirePrivateDisposableCheckout(disposableCheckout);
  const sources = verifyPinnedDevelopmentSources(workOrder, root);
  const review = await generateDevelopmentReview(workOrder, async () => draft);
  const approvedPaths = new Set(sources.files.map(file => file.path));
  const checked: Array<{path: string; patchSha256: string; applicable: true}> = [];
  for (const change of review.draft.changes) {
    if (!approvedPaths.has(change.path)) {
      throw new DevelopmentPatchCheckError("Patch targets a source that was not verified.");
    }
    if (Buffer.byteLength(change.unifiedDiff, "utf8") > 10000) {
      throw new DevelopmentPatchCheckError("Patch too large.");
    }
    // Fixed read-only command. No shell. No --unsafe-paths. No git apply
    // without --check. Rejects missing context and malformed hunks.
    git(root, ["apply", "--check", "-"], change.unifiedDiff + "\n");
    checked.push({
      path: change.path,
      patchSha256: createHash("sha256").update(change.unifiedDiff).digest("hex"),
      applicable: true,
    });
  }
  if (git(root, ["status", "--porcelain", "--untracked-files=all"]).trim()) {
    throw new DevelopmentPatchCheckError("Sandbox source changed unexpectedly.");
  }
  return {
    version: "0.3",
    mode: "isolated-patch-check",
    status: "PATCH_APPLIES_UNVERIFIED",
    sourceCommit: sources.baseCommit,
    taskId: sources.taskId,
    localGitTreeVerified: true,
    githubOriginVerified: false,
    patchApplied: false,
    codeExecuted: false,
    testsExecuted: 0,
    productionWrites: 0,
    githubWrites: 0,
    files: checked,
    ownerApprovalRequired: true,
  };
}
