import test from "node:test";
import assert from "node:assert/strict";
import {
  EXECUTIVE_ROLES,
  SPECIALIST_EXECUTIVE_ASSIGNMENT,
  executiveForSpecialist,
  executiveWorkforceStructure,
} from "../src/executive-workforce.js";
import { WORKFORCE_SPECIALISTS, routeWorkforceRequest } from "../src/workforce.js";

test("exactly two accountable executive roles, both read-only with no approval authority", () => {
  const structure = executiveWorkforceStructure();
  assert.deepEqual(EXECUTIVE_ROLES.map(role => role.id), ["ceo", "coo"]);
  assert.equal(structure.roles.length, 2);
  assert.ok(structure.roles.every(role => role.mode === "read-only" && role.approvalAuthority === "none"));
  assert.equal(structure.roles.find(role => role.id === "ceo")?.reportsTo, "owner");
  assert.equal(structure.roles.find(role => role.id === "coo")?.reportsTo, "ceo");
  assert.equal(structure.approvalRoute, "coo-to-ceo-to-founder");
  assert.equal(structure.ownerApprovalRequiredForRestrictedActions, true);
});

test("every existing specialist has one accountable executive and remains read-only", () => {
  const structure = executiveWorkforceStructure();
  const ids = WORKFORCE_SPECIALISTS.map(specialist => specialist.id);
  assert.deepEqual(Object.keys(SPECIALIST_EXECUTIVE_ASSIGNMENT).sort(), [...ids].sort());
  assert.equal(structure.assignments.length, ids.length);
  assert.equal(structure.assignments.find(a => a.specialistId === "owner")?.executiveId, "ceo");
  assert.ok(structure.assignments.filter(a => a.specialistId !== "owner").every(a =>
    a.executiveId === "coo" && a.mode === "read-only"));
  assert.equal(executiveForSpecialist("finance").id, "coo");
  assert.throws(
    () => executiveForSpecialist("unrecognized" as never),
    /Unknown specialist/,
  );
});

test("no new write permissions, autonomy, market-scraping or Sentinel actions are advertised", () => {
  const structure = executiveWorkforceStructure();
  assert.equal(structure.mode, "read-only");
  assert.equal(structure.scope, "v79-digital-owner-only");
  assert.equal(structure.actionsEnabled, false);
  assert.equal(structure.applicationWriteAdaptersEnabled, false);
  assert.equal(structure.autonomousLearningPromotionEnabled, false);
  assert.equal(structure.specialistCapabilities.sentinel.integrationStatus, "unverified");
  assert.equal(structure.specialistCapabilities.sentinel.actionsEnabled, false);
  assert.equal(structure.specialistCapabilities.marketIntelligence.status, "planned");
  assert.equal(structure.specialistCapabilities.marketIntelligence.autonomousAgent, false);
  assert.equal(structure.specialistCapabilities.marketIntelligence.parentSpecialist, "growth");
});

test("legacy deterministic specialist routing remains unchanged by role metadata", () => {
  const cases = [
    ["Stock reorder and shipments", "operations", "coo"],
    ["POS is down", "technology", "coo"],
    ["FFPRO cashflow expenses", "finance", "coo"],
    ["Marketing leads", "growth", "coo"],
    ["Tiquet support tickets", "customer", "coo"],
    ["CombatZone bookings", "combatzone", "coo"],
    ["Overall company daily briefing", "owner", "ceo"],
  ] as const;
  for (const [question, specialistId, executiveId] of cases) {
    const routed = routeWorkforceRequest(question);
    assert.equal(routed.id, specialistId, question);
    assert.equal(executiveForSpecialist(routed.id).id, executiveId);
  }
});

test("returned structure data is a copy rather than writable shared governance state", () => {
  const a = executiveWorkforceStructure();
  a.roles[0]!.name = "Untrusted mutation";
  a.assignments[0]!.executiveId = "ceo";
  const b = executiveWorkforceStructure();
  assert.equal(b.roles[0]!.name, "V79 CEO");
  assert.equal(b.assignments[0]!.executiveId, "coo");
});
