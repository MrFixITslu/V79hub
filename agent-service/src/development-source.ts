import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import {
  validateDevelopmentWorkOrder,
  type DevelopmentWorkOrder,
} from "./development-worker.js";

/**
 * Verify a source work order against a separately supplied LOCAL Git object
 * database pinned at the requested HEAD. This does not authenticate the
 * remote origin, approve a patch, or grant execution authority.
 *
 * All git invocations use execFileSync argument arrays (never a shell);
 * the model cannot supply the checkout directory or arbitrary git arguments.
 */
export class DevelopmentSourceVerificationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DevelopmentSourceVerificationError";
  }
}

export type SourceVerification = Readonly<{
  taskId: string;
  baseCommit: string;
  repository: "MrFixITslu/V79hub";
  verifiedAgainstPinnedLocalGitTree: true;
  verifiedAgainstGitHubOrigin: false;
  checkoutModified: false;
  changesApplied: 0;
  commandsFromModelExecuted: 0;
  files: readonly Readonly<{
    path: string;
    commitTreeBlob: string;
    recomputedBlob: string;
    excerptFound: true;
    bytes: number;
  }>[];
}>;

function runGit(repo: string, args: string[], maxBuffer = 131072): Buffer {
  try {
    return execFileSync("git", ["-C", repo, ...args], {
      encoding: "buffer",
      timeout: 5000,
      maxBuffer,
      stdio: ["ignore", "pipe", "ignore"],
    });
  } catch {
    throw new DevelopmentSourceVerificationError("Pinned source Git read failed.");
  }
}

function gitBlob(bytes: Buffer): string {
  const header = Buffer.from(`blob ${bytes.length}\0`, "utf8");
  return createHash("sha1").update(header).update(bytes).digest("hex");
}

function sourceRecord(repo: string, order: DevelopmentWorkOrder, path: string, expectedSha: string, excerpt: string) {
  const tree = runGit(repo, ["ls-tree", "-z", order.baseCommit, "--", path], 2048);
  const pieces = tree.toString("utf8").split("\0").filter(Boolean);
  if (pieces.length !== 1) {
    throw new DevelopmentSourceVerificationError("Source path missing or ambiguous in pinned Git tree.");
  }
  const match = /^(100644|100755) blob ([a-f0-9]{40})\t(.+)$/.exec(pieces[0]);
  if (!match || match[3] !== path) {
    throw new DevelopmentSourceVerificationError("Unexpected Git object type, symlink or source path.");
  }
  const sha = match[2];
  if (sha !== expectedSha) {
    throw new DevelopmentSourceVerificationError("Supplied blob does not match pinned Git tree.");
  }
  const bytes = runGit(repo, ["cat-file", "blob", sha], 131072);
  if (bytes.length === 0 || bytes.length > 65536 || bytes.includes(0)) {
    throw new DevelopmentSourceVerificationError("Missing, oversized or binary source rejected.");
  }
  const recomputed = gitBlob(bytes);
  if (recomputed !== sha || !bytes.toString("utf8").includes(excerpt)) {
    throw new DevelopmentSourceVerificationError("Source content hash or excerpt mismatch.");
  }
  return {
    path,
    commitTreeBlob: sha,
    recomputedBlob: recomputed,
    excerptFound: true as const,
    bytes: bytes.length,
  };
}

/**
 * repoDirectory MUST be chosen by the privileged supervisor, not the model.
 * Only reads existing Git objects. No clone/fetch/checkout/apply/commit.
 */
export function verifyPinnedDevelopmentSources(
  input: unknown,
  repoDirectory: string,
): SourceVerification {
  const order = validateDevelopmentWorkOrder(input);
  if (typeof repoDirectory !== "string" || !repoDirectory.startsWith("/") ||
      repoDirectory.includes("\0")) {
    throw new DevelopmentSourceVerificationError("Supervisor must supply an absolute source checkout.");
  }
  const repo = resolve(repoDirectory);
  const head = runGit(repo, ["rev-parse", "--verify", "HEAD"]).toString("utf8").trim();
  if (head !== order.baseCommit) {
    throw new DevelopmentSourceVerificationError("Checkout HEAD differs from pinned base commit.");
  }
  const files = order.files.map(file =>
    sourceRecord(repo, order, file.path, file.sourceBlob, file.excerpt)
  );
  return {
    repository: order.repository,
    taskId: order.taskId,
    baseCommit: order.baseCommit,
    verifiedAgainstPinnedLocalGitTree: true,
    verifiedAgainstGitHubOrigin: false,
    checkoutModified: false,
    changesApplied: 0,
    commandsFromModelExecuted: 0,
    files,
  };
}
