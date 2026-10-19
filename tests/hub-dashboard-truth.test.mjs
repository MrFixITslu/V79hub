import test from "node:test";
import assert from "node:assert/strict";
import { register } from "tsx/esm/api";
register();
const {
  numericMetric, countMetric, percentMetric, summaryCurrency, moneyMetric,
  openJobsMetric, hasUsableSummary, connectionCopy,
} = await import("../src/lib/dashboardTruth.ts");

test("valid zero is preserved, missing/invalid values never become zero", () => {
  for (const invalid of [undefined, null, "", " ", NaN, Infinity, "not-a-number", "0x10", false, {}, []]) {
    assert.equal(numericMetric(invalid), null);
    assert.equal(countMetric(invalid), "—");
  }
  assert.equal(numericMetric(0), 0);
  assert.equal(numericMetric("0"), 0);
  assert.equal(countMetric(0), "0");
  assert.equal(countMetric(12), "12");
  assert.equal(countMetric(-1), "—");
  assert.equal(countMetric(1.7), "—");
  assert.equal(percentMetric(0), "0%");
  assert.equal(percentMetric(null), "—");
  assert.equal(percentMetric(101), "—");
});

test("money requires a trustworthy product-provided currency, never assumes XCD", () => {
  assert.equal(summaryCurrency({}), null);
  assert.equal(summaryCurrency({ currency: "EC$" }), null);
  assert.equal(summaryCurrency({ currency: "usd" }), "USD");
  assert.equal(moneyMetric(0, {}), "—");
  assert.equal(moneyMetric(null, { currency: "XCD" }), "—");
  assert.match(moneyMetric(25, { currencyCode: "USD" }), /\$25\.00/);
  assert.match(moneyMetric(-8, { currency: "XCD" }), /8\.00/);
});

test("open-job totals distinguish absent, invalid, and actual zero statuses", () => {
  assert.equal(openJobsMetric(undefined), null);
  assert.equal(openJobsMetric({}), null);
  assert.equal(openJobsMetric({ active: undefined }), null);
  assert.equal(openJobsMetric({ open: 0, closed: 12 }), 0);
  assert.equal(openJobsMetric({ open: 4, in_progress: "2", resolved: 6 }), 6);
  assert.equal(openJobsMetric({ open: -1 }), null);
});

test("status ok without actual metrics is not a successful data summary", () => {
  assert.equal(hasUsableSummary({ status: "ok", metrics: {} }), false);
  assert.equal(hasUsableSummary({ status: "ok", metrics: { currency: "XCD" } }), false);
  assert.equal(hasUsableSummary({ status: "restricted", metrics: { sales: 99 } }), false);
  assert.equal(hasUsableSummary({ status: "ok", metrics: { sales: 0 } }), true);
  assert.equal(hasUsableSummary({ status: "ok", metrics: { jobsByStatus: { open: 0, closed: 1 } } }), true);
});

test("no-app, failed, and partial states cannot show an all-clear", () => {
  assert.match(connectionCopy(0, 0, true, false), /No applications/);
  assert.match(connectionCopy(1, 0, true, false), /No enabled application returned/);
  assert.match(connectionCopy(3, 2, true, false), /2 of 3/);
  assert.match(connectionCopy(3, 3, true, false), /not confirm service uptime/);
  assert.match(connectionCopy(3, 3, true, true), /unknown/);
  assert.match(connectionCopy(3, 0, false, false), /Checking/);
});

test("stale summary fetches cannot overwrite newer data, hidden tabs do not poll", async () => {
  const { readFileSync } = await import("node:fs");
  const dashboard = readFileSync(new URL("../src/components/HubOverview.tsx", import.meta.url), "utf8");
  assert.match(dashboard, /activeRequest\.current\?\.abort\(\)/);
  assert.match(dashboard, /controller\.signal\.aborted \|\| activeRequest\.current !== controller/);
  assert.match(dashboard, /visibilityState === "hidden"/);
  assert.match(dashboard, /visibilitychange/);
  assert.match(dashboard, /setDashboard\(null\)/);
  assert.match(dashboard, /Hub checked/);
  assert.match(dashboard, /Product source timestamp unavailable/);
});

test("approved light mode keeps readable dashboard and navy-sidebar text", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
  assert.match(css, /hub-theme-light \.hub-dashboard \.text-slate-100/);
  assert.match(css, /hub-theme-light \.hub-sidebar \.hub-nav-item/);
  assert.match(css, /hub-theme-light \.hub-dashboard \.text-emerald-300/);
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lightness = c => {
    const channels = rgb(c).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  const contrast = (a, b) => {
    const values = [lightness(a), lightness(b)].sort((x, y) => y - x);
    return (values[0] + 0.05) / (values[1] + 0.05);
  };
  assert.ok(contrast("#17324e", "#f8fafc") >= 4.5, "light dashboard title contrast");
  assert.ok(contrast("#cbd5e1", "#06101d") >= 4.5, "nav item contrast on navy");
});

// Only a source-contract test: full network/browser/auth acceptance is separate.
test("customer component still delegates launch and authentication to existing Hub code", async () => {
  const { readFileSync } = await import("node:fs");
  const dashboard = readFileSync(new URL("../src/components/HubOverview.tsx", import.meta.url), "utf8");
  assert.match(dashboard, /fetch\("\/api\/dashboard\/summary"/);
  assert.match(dashboard, /appLaunchUrl\(app, card\.fallback\)/);
  assert.doesNotMatch(dashboard, /EC\$|· XCD/);
});
