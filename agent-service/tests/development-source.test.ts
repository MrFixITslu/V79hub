import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  DevelopmentSourceVerificationError,
  verifyPinnedDevelopmentSources,
} from "../src/development-source.js";

function git(repo: string, ...args: string[]) {
  return execFileSync("git", ["-C", repo, ...args], {
    encoding: "utf8", timeout: 5000, stdio: ["ignore", "pipe", "ignore"],
  }).trim();
}

function fixture() {
  const repo = mkdtempSync(join(tmpdir(), "v79-dev-git-proof-"));
  const path = "agent-service/tests/fixture.test.ts";
  mkdirSync(join(repo, "agent-service", "tests"), { recursive: true });
  writeFileSync(join(repo, path), 'test("fixture", () => 1);\n');
  git(repo, "init", "-q");
  git(repo, "add", path);
  git(repo, "-c", "user.email=synthetic@example.invalid",
    "-c", "user.name=V79 Synthetic QA", "commit", "-qm", "Synthetic fixture");
  const baseCommit = git(repo, "rev-parse", "HEAD");
  const sourceBlob = git(repo, "rev-parse", "HEAD:" + path);
  return {
    repo, path, sourceBlob, baseCommit,
    order: {
      repository: "MrFixITslu/V79hub",
      taskId: "G1-SRC-001",
      objective: "Draft an isolated test-only change.",
      baseCommit,
      files: [{
        path, sourceBlob,
        excerpt: 'test("fixture", () => 1);',
      }],
    },
  };
}

test("attest against pinned tree and recomputed Git blob without any mutation", t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const before = git(f.repo, "status", "--porcelain");
  const result = verifyPinnedDevelopmentSources(f.order, f.repo);
  assert.equal(result.verifiedAgainstPinnedLocalGitTree, true);
  assert.equal(result.verifiedAgainstGitHubOrigin, false);
  assert.equal(result.checkoutModified, false);
  assert.equal(result.commandsFromModelExecuted, 0);
  assert.equal(result.changesApplied, 0);
  assert.equal(result.files.length, 1);
  assert.equal(result.files[0].commitTreeBlob, f.sourceBlob);
  assert.equal(result.files[0].recomputedBlob, f.sourceBlob);
  assert.equal(git(f.repo, "status", "--porcelain"), before);
});

test("reject forged work-order blob against the tree", t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const attack = {
    ...f.order,
    files: [{ ...f.order.files[0], sourceBlob: "a".repeat(40) }],
  };
  assert.throws(
    () => verifyPinnedDevelopmentSources(attack, f.repo),
    DevelopmentSourceVerificationError,
  );
});

test("reject fabricated excerpt and missing path", t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const inventedExcerpt = {
    ...f.order, files: [{ ...f.order.files[0], excerpt: "injected unseen instruction" }],
  };
  assert.throws(() => verifyPinnedDevelopmentSources(inventedExcerpt, f.repo),
    DevelopmentSourceVerificationError);
  const unknownPath = {
    ...f.order,
    files: [{ ...f.order.files[0], path: "agent-service/tests/missing.test.ts" }],
  };
  assert.throws(() => verifyPinnedDevelopmentSources(unknownPath, f.repo),
    DevelopmentSourceVerificationError);
});

test("reject checkout HEAD that differs from the pinned work-order SHA", t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  const attack = { ...f.order, baseCommit: "b".repeat(40) };
  assert.throws(
    () => verifyPinnedDevelopmentSources(attack, f.repo),
    DevelopmentSourceVerificationError,
  );
});

test("reject model-supplied unsafe source paths before calling Git", t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  for (const path of ["/etc/passwd", "../../.env", ".github/workflows/deploy.yml"]) {
    assert.throws(() => verifyPinnedDevelopmentSources({
      ...f.order, files: [{ ...f.order.files[0], path }],
    }, f.repo));
  }
});

test("reject nonabsolute checkout directory and binary Git symlink", t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  assert.throws(() => verifyPinnedDevelopmentSources(f.order, "../other"),
    DevelopmentSourceVerificationError);
});

test("reject source size above 64 KiB rather than presenting it to a model", t => {
  const f = fixture();
  t.after(() => rmSync(f.repo, { recursive: true, force: true }));
  writeFileSync(join(f.repo, f.path), "x".repeat(65537));
  git(f.repo, "add", f.path);
  git(f.repo, "-c", "user.email=synthetic@example.invalid",
    "-c", "user.name=V79 Synthetic QA", "commit", "-qm", "Oversized fixture");
  const order = {
    ...f.order,
    baseCommit: git(f.repo, "rev-parse", "HEAD"),
    files: [{
      ...f.order.files[0],
      sourceBlob: git(f.repo, "rev-parse", "HEAD:" + f.path),
      excerpt: "x",
    }],
  };
  assert.throws(() => verifyPinnedDevelopmentSources(order, f.repo),
    DevelopmentSourceVerificationError);
});
