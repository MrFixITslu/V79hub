import test from "node:test";
import assert from "node:assert/strict";
import {
  generateDevelopmentReview,
  InvalidDevelopmentOrder,
  validateDevelopmentWorkOrder,
} from "../src/development-worker.js";

const base = {
  repository: "MrFixITslu/V79hub",
  baseCommit: "75291868e9392d82fdb31cfbc59ffb80b7d41d86",
  taskId: "G1-DEV-001",
  objective: "Add an isolated test for a bounded API response.",
  files: [{
    path: "agent-service/tests/sample.test.ts",
    sourceBlob: "1234567890abcdef1234567890abcdef12345678",
    excerpt: 'test("example", () => assert.equal(1, 1));',
  }],
};

const valid = {
  summary: "Proposed a test-only change; verify it in a separate checkout.",
  changes: [{
    path: "agent-service/tests/sample.test.ts",
    reason: "Add a negative case.",
    unifiedDiff: [
      "--- a/agent-service/tests/sample.test.ts",
      "+++ b/agent-service/tests/sample.test.ts",
      "@@ -1 +1,2 @@",
      " test(\"example\", () => assert.equal(1, 1));",
      "+test(\"negative\", () => assert.equal(2, 2));",
    ].join("\n"),
  }],
  testIdeas: ["Run targeted Node test in an isolated checkout."],
  risks: ["The supplied excerpt is not a verified full source file."],
};

test("bounded review contract returns unverified draft with zero side effects", async () => {
  const result = await generateDevelopmentReview(base, async () => valid);
  assert.equal(result.mode, "review-only");
  assert.equal(result.ownerApprovalRequired, true);
  assert.equal(result.diffApplied, false);
  assert.equal(result.sourceVerifiedAgainstGitHub, false);
  assert.equal(result.gitWrites, 0);
  assert.equal(result.productionWrites, 0);
  assert.equal(result.testsExecuted, 0);
  assert.equal(result.draft.changes.length, 1);
});

test("invalid repo, unpinned source, traversal, duplicates and unsupported paths fail closed", () => {
  const overrides: unknown[] = [
    { ...base, repository: "someone/other" },
    { ...base, baseCommit: "main" },
    { ...base, files: [{ ...base.files[0], path: "../.env" }] },
    { ...base, files: [{ ...base.files[0], path: "agent-service/src/.env" }] },
    { ...base, files: [{ ...base.files[0], path: ".github/workflows/deploy.yml" }] },
    { ...base, files: [base.files[0], base.files[0]] },
    { ...base, files: [{ ...base.files[0], sourceBlob: "bad" }] },
    { ...base, files: [{ ...base.files[0], excerpt: "x".repeat(3501) }] },
    { ...base, files: [] },
    { ...base, files: [base.files[0], base.files[0], base.files[0], base.files[0]] },
  ];
  for (const example of overrides) {
    assert.throws(() => validateDevelopmentWorkOrder(example), InvalidDevelopmentOrder);
  }
});

test("AI cannot move a proposal outside the exact requested source path", async () => {
  const attack = {
    ...valid,
    changes: [{ ...valid.changes[0], path: "agent-service/src/index.ts" }],
  };
  await assert.rejects(
    generateDevelopmentReview(base, async () => attack),
    /unapproved path/,
  );
});

test("forged diff header and multi-file diff are rejected", async () => {
  const changes = [
    valid.changes[0].unifiedDiff.replace(
      "+++ b/agent-service/tests/sample.test.ts",
      "+++ b/server.ts",
    ),
    valid.changes[0].unifiedDiff + "\n--- a/server.ts\n+++ b/server.ts",
  ];
  for (const diff of changes) {
    await assert.rejects(
      generateDevelopmentReview(base, async () => ({
        ...valid, changes: [{ ...valid.changes[0], unifiedDiff: diff }],
      })),
      /single-file unified diff/,
    );
  }
});

test("invalid JSON, duplicate change, excessive output and missing test schema fail closed", async () => {
  const invalid: unknown[] = [
    "not json",
    { ...valid, changes: [valid.changes[0], valid.changes[0]] },
    { ...valid, changes: [{ ...valid.changes[0], unifiedDiff: "x".repeat(10001) }] },
    { ...valid, testIdeas: ["x".repeat(321)] },
    { ...valid, risks: "not an array" },
  ];
  for (const response of invalid) {
    await assert.rejects(generateDevelopmentReview(base, async () => response));
  }
});

test("proposer never receives an unvalidated work order", async () => {
  let called = false;
  await assert.rejects(generateDevelopmentReview(
    { ...base, taskId: ".." }, async () => { called = true; return valid; },
  ), InvalidDevelopmentOrder);
  assert.equal(called, false);
});
