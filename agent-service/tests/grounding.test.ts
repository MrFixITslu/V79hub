import test from "node:test";
import assert from "node:assert/strict";
import { compactOwnerSnapshot, deterministicFactAnswer, formatPriorityBrief, isPriorityBriefRequest } from "../src/grounding.js";

test("compacts and deduplicates owner business snapshot", () => {
  const compact = compactOwnerSnapshot({
    generatedAt: "2026-09-29T20:00:00Z",
    hubAdmin: { users: 1, activeSessions: 1 },
    connections: { pos: { status: "online" } },
    business: { pos: { metrics: { sales30d: 4, revenue30d: 100, generatedAt: "x" } } },
    platform: { pos: { metrics: { sales30d: 4, activeTenants: 1, generatedAt: "y" } } },
  });
  assert.equal(compact.systems.pos.connection, "online");
  assert.deepEqual(compact.systems.pos.metrics, { sales30d: 4, revenue30d: 100 });
  assert.deepEqual(compact.systems.pos.platform, { activeTenants: 1 });
  assert.equal(compact.systems.ffpro.connection, "unknown");
});


test("priority signals put negative cashflow before generic inactivity", () => {
  const compact = compactOwnerSnapshot({
    business: {
      ffpro: { metrics: { currentMonthIncome: 1750, currentMonthExpenses: 5982.02, currentMonthNet: -4232.02 } },
      pos: { metrics: { sales30d: 0, revenue30d: 0, criticalReplenishmentItems: 0, delayedShipments: 0, unresolvedInventoryExceptions: 0 } },
      marketing: { metrics: { campaigns: 0, activeCampaigns: 0 } },
      lasertag: { metrics: { upcomingBookings: 0, upcomingPlayers: 0 } },
      academy: { metrics: { publishedCourses: 4, enrolledCourses: 1 } },
    },
  });

  const first = compact.prioritySignals[0];
  assert.ok(first);
  assert.equal(first.severity, "high");
  assert.equal(first.code, "finance_negative_month_net");
  assert.equal(first.values?.currentMonthNet, -4232.02);
  assert.ok(compact.prioritySignals.find(signal => signal.code === "pos_no_recent_sales"));
  assert.ok(compact.prioritySignals.find(signal => signal.code === "marketing_no_active_campaigns"));
});


test("priority briefing intent is narrow and explicit", () => {
  assert.equal(isPriorityBriefRequest("What needs my attention today?"), true);
  assert.equal(isPriorityBriefRequest("Give me my top priorities"), true);
  assert.equal(isPriorityBriefRequest("How is Gaming Studio J doing?"), false);
});

test("priority brief formatting preserves severity order", () => {
  const compact = compactOwnerSnapshot({
    business: {
      ffpro: { metrics: { currentMonthIncome: 1750, currentMonthExpenses: 5982.02, currentMonthNet: -4232.02 } },
      pos: { metrics: { sales30d: 0, revenue30d: 0 } },
      marketing: { metrics: { activeCampaigns: 0 } },
    },
  });
  const brief = formatPriorityBrief(compact.prioritySignals, 3);
  const lines = brief.split("\n");
  assert.match(lines[0] || "", /HIGH — Finance/);
  assert.match(lines[0] || "", /-4,232\.02/);
  assert.match(lines[1] || "", /POS: no sales/);
  assert.match(lines[2] || "", /Marketing: there are no active campaigns/);
});


test("finance facts are deterministic and do not invent period comparisons", () => {
  const compact = compactOwnerSnapshot({
    business: {
      ffpro: {
        metrics: {
          currentMonthIncome: 1750,
          currentMonthExpenses: 5982.02,
          yearToDateIncome: 11944,
          yearToDateExpenses: 7378.42,
        },
      },
    },
  });
  const answer = deterministicFactAnswer("Explain the current finance position in one sentence.", compact);
  assert.ok(answer);
  assert.equal(answer.domain, "finance");
  assert.match(answer.output, /current-month income 1,750/);
  assert.match(answer.output, /net -4,232\.02/);
  assert.match(answer.output, /year-to-date net 4,565\.58/);
  assert.doesNotMatch(answer.output, /previous month|last month|compared to/i);
});

test("sales and inventory facts stay grounded in POS metrics", () => {
  const compact = compactOwnerSnapshot({
    business: {
      pos: {
        metrics: {
          sales30d: 0,
          revenue30d: 0,
          openPurchaseOrders: 2,
          criticalReplenishmentItems: 1,
          delayedShipments: 0,
          unresolvedInventoryExceptions: 3,
        },
      },
    },
  });
  const answer = deterministicFactAnswer("How are POS sales and inventory?", compact);
  assert.ok(answer);
  assert.equal(answer.domain, "pos");
  assert.match(answer.output, /30-day sales 0/);
  assert.match(answer.output, /critical replenishment items 1/);
  assert.match(answer.output, /unresolved inventory exceptions 3/);
});

test("open-ended advice stays with the language model", () => {
  const compact = compactOwnerSnapshot({
    business: {
      ffpro: { metrics: { currentMonthIncome: 100, currentMonthExpenses: 200 } },
    },
  });
  assert.equal(deterministicFactAnswer("What should I do to improve cashflow?", compact), null);
});