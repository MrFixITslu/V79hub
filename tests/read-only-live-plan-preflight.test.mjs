import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const source = readFileSync(new URL("../scripts/read-only-live-cutover-preflight.mjs", import.meta.url), "utf8");
const embedded = source.match(/const inspect=String\.raw`([\s\S]*?)`;/)?.[1];
assert.ok(embedded?.includes('import { Client } from "pg";'), "real read-only SQL client must remain present");

function baselinePlans() {
  return [
    { organizationId: "org-internal", status: "active", accessPolicyType: "internal" },
    { organizationId: "org-customer", status: "trial", accessPolicyType: "trial",
      trialStartedAt: "2026-10-09T10:00:00.000Z", trialEndsAt: "2026-10-23T10:00:00.000Z" },
  ];
}

function check(plans) {
  const store = {
    users: [{ id: "user-founder", username: "admin@example.test" }, { id: "user-customer", username: "customer@example.test" }],
    organizations: [{ id: "org-internal", status: "active" }, { id: "org-customer", status: "active" }],
    memberships: [
      { userId: "user-founder", organizationId: "org-internal", role: "owner", status: "active" },
      { userId: "user-customer", organizationId: "org-customer", role: "owner", status: "active" },
    ],
    appEntitlements: ["app-tiquet", "app-pos", "app-marketing", "app-ffpro", "app-academy"].map(appId =>
      ({ organizationId: "org-customer", appId, enabled: true })),
    organizationPlans: plans,
    trialReminderEvents: [],
  };
  const fakeClient = [
    "const MOCK_STORE = " + JSON.stringify(store) + ";",
    'class Client { async connect() {} async end() {} async query(sql) {',
    'if (String(sql).includes("SELECT")) return { rowCount: 1, rows: [{ state: MOCK_STORE, revision: 3 }] };',
    'return { rows: [] }; } }',
  ].join("\n");
  const input = embedded.replace('import { Client } from "pg";', fakeClient);
  const result = spawnSync(process.execPath, ["--input-type=module", "-"], {
    input, encoding: "utf8", timeout: 3500,
    env: { ...process.env, DATABASE_URL: "postgres://mock.invalid/never-connected",
      V79_HUB_ADMIN_EMAIL: "admin@example.test" },
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("read-only preflight accepts approved current trial without altering any plan", () => {
  const o = check(baselinePlans());
  assert.equal(o.planCount, 2);
  assert.equal(o.ownerPlanPolicyValid, true);
  assert.equal(o.customerTrialPolicyValid, true);
  assert.equal(o.cutoverBaselineReady, true);
});

test("preflight refuses stale no-plan state", () => {
  assert.equal(check([]).cutoverBaselineReady, false);
});

test("preflight refuses forged paid access without a verified billing trail", () => {
  const plans = baselinePlans();
  plans[1] = { organizationId: "org-customer", status: "active", accessPolicyType: "paid" };
  assert.equal(check(plans).cutoverBaselineReady, false);
});

test("preflight refuses an invalid trial duration", () => {
  const plans = baselinePlans();
  plans[1].trialEndsAt = "2026-10-22T10:00:00.000Z";
  assert.equal(check(plans).customerTrialPolicyValid, false);
});

test("preflight refuses cross-organization plan references", () => {
  const plans = baselinePlans();
  plans[1].organizationId = "unrelated-org";
  assert.equal(check(plans).cutoverBaselineReady, false);
});

test("preflight refuses duplicate owner plans", () => {
  const plans = baselinePlans();
  plans.push({ ...plans[0] });
  assert.equal(check(plans).cutoverBaselineReady, false);
});
