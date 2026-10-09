import test from "node:test";
import assert from "node:assert/strict";
import { buildEvidenceLedger } from "../src/evidence.js";
import { getWorkforceSpecialist } from "../src/workforce.js";
import { buildInvestigationBrief } from "../src/investigations.js";

const stamp = "2026-10-09T03:00:00.000Z";
const now = Date.parse(stamp);
const raw = () => ({
  generatedAt: stamp,
  owner: { email: "vision79slu@gmail.com", organizationId: "owner-test" },
  business: {
    pos: { status: "ok", sourceReportedAt: stamp, metrics: {
      criticalReplenishmentItems: 4, delayedShipments: 2, unresolvedInventoryExceptions: 3,
      openPurchaseOrders: 5, sales30d: 0, products: 12, revenue30d: 0,
      supplierEmail: "private@example.invalid", customerId: "personal",
    }},
    ffpro: { status: "ok", sourceReportedAt: stamp, metrics: {
      currentMonthNet: -120, currentMonthExpenses: 370, currentMonthIncome: 250,
      bankAccount: "private-bank-data",
    }},
    marketing: { status: "ok", sourceReportedAt: stamp, metrics: {
      campaigns: 3, activeCampaigns: 0, scheduledPosts: 2,
      connectedSocialAccounts: 0, customers: 6, customerEmail: "secret",
    }},
    tiquet: { status: "ok", sourceReportedAt: stamp, metrics: {
      jobs: 8, unreadNotifications: 3, clients: 5, clientName: "secret",
    }},
    website: { status: "unavailable", sourceReportedAt: null, metrics: { followUpsDue: 9999 } },
    lasertag: { status: "not_configured", metrics: { upcomingBookings: 111 } },
  },
  connections: {
    pos: { status: "online" }, ffpro: { status: "online" },
    tiquet: { status: "online" }, marketing: { status: "online" },
    website: { status: "unavailable" }, lasertag: { status: "unavailable" },
  },
  platform: {
    pos: { status: "ok", metrics: { delayedShipments: 4000, inventorySecret: "secret" } },
  },
});

function make(id: "owner" | "finance" | "operations" | "growth" | "customer" | "combatzone" | "technology",
  snapshot: ReturnType<typeof raw> = raw()) {
  return buildInvestigationBrief(buildEvidenceLedger(snapshot, getWorkforceSpecialist(id), now));
}

test("Operations provides traceable read-only POS findings and scoped systems", () => {
  const report = make("operations");
  const titles = report.findings.map(f=>f.title);
  for(const title of ["Inventory replenishment needs review","Delayed shipments need investigation",
    "Open inventory exceptions","Purchase orders remain open","No completed sales recorded in the last 30 days",
    "Unread support notifications","Tiquet jobs recorded"]) assert.ok(titles.includes(title), title);
  assert.equal(report.dataStatus, "available");
  assert.ok(report.findings.every(f => f.evidence.source === "signed_product_summary"));
  assert.ok(report.findings.every(f => f.evidence.reportedAt === stamp));
  assert.ok(report.findings.every(f => ["pos","tiquet"].includes(f.system)));
  assert.equal(report.mode, "read-only");
  assert.ok(!JSON.stringify(report).includes("private@example.invalid"));
});

test("Finance recommendations cite only FFPRO and POS; admin-wide counts never trigger findings", () => {
  const report = make("finance");
  assert.ok(report.findings.some(f => f.id === "ffpro:currentMonthNet" && f.evidence.value === -120));
  assert.ok(report.findings.every(f=>["pos","ffpro"].includes(f.system)));
  assert.equal(report.findings.find(f=>f.id==="pos:delayedShipments")?.evidence.value,2);
  assert.ok(report.findings.every(f=>f.evidence.value !== 4000));
});

test("Growth stays within Marketing/Website and reports unavailability rather than ungrounded lead claims", () => {
  const report = make("growth");
  assert.deepEqual(report.missing, [{ system:"website", reason:"unavailable" }]);
  assert.equal(report.dataStatus, "partial");
  assert.ok(report.findings.every(f => f.system === "marketing"));
  assert.ok(report.findings.some(f => f.id === "marketing:activeCampaigns" && f.evidence.value === 0));
  assert.ok(!JSON.stringify(report).includes("9999"));
});

test("Customer Care is Tiquet-scoped, does not invent ticket details or send notifications", () => {
  const report = make("customer");
  assert.ok(report.findings.some(f=>f.id==="tiquet:unreadNotifications"));
  assert.ok(!JSON.stringify(report).includes("clientName"));
  assert.ok(!JSON.stringify(report).includes("private@example.invalid"));
  assert.ok(report.findings.every(f=>f.evidence.metric !== "clients"));
});

test("Stale, unavailable and unknown summaries never generate findings", () => {
  const data=raw();
  data.business.pos.sourceReportedAt="2026-10-08T12:00:00Z";
  data.business.tiquet.status="unavailable";
  const report=make("operations",data);
  assert.deepEqual(report.findings, []);
  assert.deepEqual(report.missing, [
    { system:"pos", reason:"stale" },{ system:"tiquet", reason:"unavailable" },
  ]);
  assert.equal(report.dataStatus,"unavailable");
});

test("Zero with a known recent reading is distinct from missing zero", () => {
  const data=raw();
  data.business.marketing.metrics.activeCampaigns=0;
  assert.ok(make("growth",data).findings.some(f=>f.id==="marketing:activeCampaigns"));
  delete (data.business.marketing.metrics as Record<string,unknown>).activeCampaigns;
  assert.ok(!make("growth",data).findings.some(f=>f.id==="marketing:activeCampaigns"));
});

test("CombatZone source offline produces unavailable brief, not fictional bookings", () => {
  const report=make("combatzone");
  assert.equal(report.dataStatus,"unavailable");
  assert.deepEqual(report.findings,[]);
  assert.deepEqual(report.missing,[{ system:"lasertag", reason:"unavailable" }]);
});

test("Recommendations are bounded, fixed advisory strings, no tool execution or model commands", () => {
 const report=make("owner");
 assert.ok(report.findings.length <=20);
 assert.ok(report.findings.every(f=>!/(https?:|curl |ssh |\bexecute\b|\brefund\b|\bdelete\b)/i.test(f.nextStep)));
 assert.ok(report.findings.every(f=>/^[a-z]+:[A-Za-z0-9]+$/.test(f.id)));
});
