import test from "node:test";
import assert from "node:assert/strict";
import { createSupervisedQa, cleanupSupervisedQa } from "../src/lib/sentinel-qa-client.mjs";

const org = { id: "cc576f94-4d8b-439d-9a9e-6fb22bd9b164", name: "Sentinel-QA-cc576f94-4d8b-439d-9a9e-6fb22bd9b164" };
const baseline = { userCount: 2, organizationCount: 2 };
const createdStatus = {
  organizations: [{ ...org, eligible: true, memberCount: 3 }],
  userCount: 5, organizationCount: 3, syntheticUserCount: 3, syntheticMembershipCount: 3,
};
const preview = { state: "eligible-hub-only", organizationId: org.id, organizationName: org.name,
  memberCount: 3, previewHash: "a".repeat(64), externalTenants: 0, billingReferences: 0 };
const removed = { success: true, organizationId: org.id, syntheticUsersDeleted: 3, auditId: "audit-fixture" };
const cleanedStatus = { organizations: [], syntheticUserCount: 0, syntheticMembershipCount: 0,
  latestCleanup: { auditId: removed.auditId, organizationId: org.id, syntheticUsersDeleted: 3 } };
function transport(responses) {
  const calls = [];
  return { calls, request: async (path, body) => {
    calls.push({ path, body });
    const response = responses[calls.length - 1];
    if (response instanceof Error) throw response;
    return structuredClone(response);
  } };
}

test("supervised browser creation exposes only reconciled status, never generated credentials", async () => {
  const input = structuredClone(baseline);
  const response = { organization: org, testAccounts: [{ oneTimePassword: "synthetic-only-do-not-return" }] };
  const h = transport([response, createdStatus]);
  assert.deepEqual(await createSupervisedQa(h.request, input), createdStatus);
  assert.deepEqual(input, baseline);
  assert.deepEqual(h.calls.map(c => c.path), ["organizations", "status"]);
  assert.deepEqual(h.calls[0].body, { confirm: "CREATE ISOLATED SENTINEL QA" });
  assert(!JSON.stringify(createdStatus).includes(response.testAccounts[0].oneTimePassword));
});

test("browser never retries a creation with an uncertain transport outcome", async () => {
  for (const responses of [[new Error("Connection lost")], [{ organization: org }, new Error("Status lost")]]) {
    const h = transport(responses);
    await assert.rejects(createSupervisedQa(h.request, baseline));
    assert.equal(h.calls.filter(c => c.body).length, 1);
  }
});

test("browser refuses success when creation cannot be reconciled to the exact manifest", async () => {
  for (const patch of [
    { organizations: [] }, { organizations: [{ ...org, id: "another", eligible: true, memberCount: 3 }] },
    { syntheticUserCount: 2 }, { syntheticMembershipCount: 2 }, { userCount: 4 },
    { organizationCount: 2 }, { organizations: [{ ...org, eligible: false, memberCount: 3 }] },
  ]) {
    const h = transport([{ organization: org }, { ...createdStatus, ...patch }]);
    await assert.rejects(createSupervisedQa(h.request, baseline), /operator review/);
    assert.equal(h.calls.filter(c => c.body).length, 1);
  }
});

test("browser refuses deletion before a matching eligible preview and exact phrase", async () => {
  for (const [p, phrase] of [
    [preview, "DELETE existing customer"], [{ ...preview, state: "blocked" }, "DELETE " + org.name],
    [{ ...preview, externalTenants: 1 }, "DELETE " + org.name],
    [{ ...preview, billingReferences: 1 }, "DELETE " + org.name],
  ]) {
    const h = transport([]);
    await assert.rejects(cleanupSupervisedQa(h.request, p, phrase), /eligible preview/);
    assert.equal(h.calls.length, 0);
  }
});

test("browser verifies exact cleanup receipt and absence without changing the selected manifest", async () => {
  const p = structuredClone(preview);
  const h = transport([removed, cleanedStatus]);
  assert.deepEqual(await cleanupSupervisedQa(h.request, p, "DELETE " + org.name), cleanedStatus);
  assert.deepEqual(p, preview);
  assert.equal(h.calls[0].path, "organizations/" + org.id + "/cleanup");
  assert.deepEqual(h.calls[0].body, { confirmName: "DELETE " + org.name, previewHash: preview.previewHash });
  assert.equal(h.calls[1].path, "status");
});

test("browser refuses cleanup success on orphan resources or a mismatched retained audit", async () => {
  const cases = [
    { organizations: [org] }, { syntheticUserCount: 1 }, { syntheticMembershipCount: 1 },
    { latestCleanup: null },
    { latestCleanup: { ...cleanedStatus.latestCleanup, organizationId: "existing-customer" } },
    { latestCleanup: { ...cleanedStatus.latestCleanup, auditId: "unrelated-audit" } },
    { latestCleanup: { ...cleanedStatus.latestCleanup, syntheticUsersDeleted: 2 } },
  ];
  for (const patch of cases) {
    const h = transport([removed, { ...cleanedStatus, ...patch }]);
    await assert.rejects(cleanupSupervisedQa(h.request, preview, "DELETE " + org.name), /operator review/);
    assert.equal(h.calls.filter(c => c.body).length, 1);
  }
});

test("browser never repeats a cleanup after transport loss or uncertain post-deletion verification", async () => {
  for (const responses of [[new Error("Deletion response lost")], [removed, new Error("Status lost")]]) {
    const h = transport(responses);
    await assert.rejects(cleanupSupervisedQa(h.request, preview, "DELETE " + org.name));
    assert.equal(h.calls.filter(c => c.body).length, 1);
  }
});
