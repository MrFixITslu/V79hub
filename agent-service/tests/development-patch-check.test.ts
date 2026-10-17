import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  DevelopmentPatchCheckError,
  dryRunDevelopmentProposal,
} from "../src/development-patch-check.js";

function git(root: string, ...args: string[]) {
  return execFileSync("git", ["-C", root, ...args], {
    encoding: "utf8",
    timeout: 5000,
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
}
function fixture() {
  const repo = mkdtempSync(join(tmpdir(), "v79-dev-sandbox-"));
  const path = "agent-service/tests/dryrun.test.ts";
  const source = 'test("baseline", () => 1);\n';
  mkdirSync(join(repo, "agent-service", "tests"), { recursive: true });
  writeFileSync(join(repo, path), source);
  git(repo, "init", "-q");
  git(repo, "add", path);
  git(repo, "-c", "user.email=synthetic@example.invalid",
    "-c", "user.name=Synthetic CI", "commit", "-qm", "synthetic baseline");
  const sourceBlob = git(repo, "rev-parse", "HEAD:" + path);
  const order = {
    repository: "MrFixITslu/V79hub",
    baseCommit: git(repo, "rev-parse", "HEAD"),
    taskId: "G1-DRY-001",
    objective: "Draft a single test-only patch.",
    files: [{ path, sourceBlob, excerpt: source.trim() }],
  };
  const proposal = {
    summary: "Test-only draft for independent review.",
    changes: [{
      path,
      reason: "Add a second synthetic test.",
      unifiedDiff: [
        "--- a/" + path,
        "+++ b/" + path,
        "@@ -1 +1,2 @@",
        " test(\"baseline\", () => 1);",
        "+test(\"second\", () => 2);",
      ].join("\n"),
    }],
    testIdeas: ["Run node:test after separate authorized patch application."],
    risks: ["Diff applies but tests have not been executed."],
  };
  return { repo, path, source, order, proposal };
}

test("valid patch dry-run checks applicability and leaves checkout byte-for-byte unchanged", async t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const before = readFileSync(join(f.repo, f.path), "utf8");
  const result = await dryRunDevelopmentProposal(f.order, f.proposal, f.repo);
  assert.equal(result.status, "PATCH_APPLIES_UNVERIFIED");
  assert.equal(result.localGitTreeVerified, true);
  assert.equal(result.githubOriginVerified, false);
  assert.equal(result.patchApplied, false);
  assert.equal(result.codeExecuted, false);
  assert.equal(result.testsExecuted, 0);
  assert.equal(result.githubWrites, 0);
  assert.equal(result.productionWrites, 0);
  assert.equal(result.files.length, 1);
  assert.equal(result.files[0].applicable, true);
  assert.equal(readFileSync(join(f.repo, f.path), "utf8"), before);
  assert.equal(git(f.repo, "status", "--porcelain"), "");
});

test("incorrect hunk content fails read-only git apply check", async t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const proposal = {
    ...f.proposal,
    changes: [{
      ...f.proposal.changes[0],
      unifiedDiff: f.proposal.changes[0].unifiedDiff.replace(
        ' test("baseline", () => 1);',
        ' test("not-in-the-tree", () => 123);',
      ),
    }],
  };
  await assert.rejects(
    dryRunDevelopmentProposal(f.order, proposal, f.repo),
    DevelopmentPatchCheckError,
  );
  assert.equal(git(f.repo, "status", "--porcelain"), "");
});

test("refuse checkout with unsaved edits or untracked files", async t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  writeFileSync(join(f.repo, "unexpected.txt"), "unreviewed content");
  await assert.rejects(
    dryRunDevelopmentProposal(f.order, f.proposal, f.repo),
    DevelopmentPatchCheckError,
  );
});

test("refuse checkout outside private disposable namespace or an unpinned SHA", async t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  for (const location of [".", "/opt/v79/hub", "/tmp", "../whatever"]) {
    await assert.rejects(
      dryRunDevelopmentProposal(f.order, f.proposal, location),
      DevelopmentPatchCheckError,
    );
  }
  await assert.rejects(
    dryRunDevelopmentProposal({ ...f.order, baseCommit: "0".repeat(40) }, f.proposal, f.repo),
  );
});

test("model cannot add a second unapproved file in a diff", async t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const proposal = {
    ...f.proposal,
    changes: [{
      ...f.proposal.changes[0],
      unifiedDiff: f.proposal.changes[0].unifiedDiff +
        "\n--- a/server.ts\n+++ b/server.ts\n@@ -1 +1 @@\n-a\n+b",
    }],
  };
  await assert.rejects(dryRunDevelopmentProposal(f.order, proposal, f.repo));
  assert.equal(git(f.repo, "status", "--porcelain"), "");
});

test("forged file blob cannot be validated by a patch that happens to apply", async t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const order = {
    ...f.order,
    files: [{ ...f.order.files[0], sourceBlob: "a".repeat(40) }],
  };
  await assert.rejects(dryRunDevelopmentProposal(order, f.proposal, f.repo));
  assert.equal(git(f.repo, "status", "--porcelain"), "");
});
