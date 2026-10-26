import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const overview = readFileSync("src/components/HubOverview.tsx", "utf8");
const sidebar = readFileSync("src/components/Sidebar.tsx", "utf8");
const css = readFileSync("src/index.css", "utf8");

test("visual release is clearly versioned and places signed app launch first", () => {
  for (const token of [
    "vision79-release-v1", "vision79-command-hero", "Vision79 / Business workspace",
    "Your business, one command centre.", "vision79-focus-panel",
    "Your workspace apps", "vision79-app-section", "vision79-metric-card",
    "Explore my apps", "visibleAppCards.map", "availableSummaryCount",
  ]) assert.ok(overview.includes(token), "missing visibly reviewed UI contract: " + token);
  assert.ok(overview.indexOf("Your workspace apps") < overview.indexOf("Performance overview"));
  assert.match(overview, /appLaunchUrl\(app, card\.fallback\)/);
  assert.match(overview, /onClick=\{\(\) => onNavigate\("connections"\)\}/);
  assert.match(overview, /\{attentionLabel\}/);
  assert.match(overview, /\{organizationName\}/);
});

test("no simulated health, revenue, uptime or customer content replaces the product API", () => {
  assert.match(overview, /fetch\("\/api\/dashboard\/summary", \{ cache: "no-store", signal: controller\.signal \}\)/);
  assert.match(overview, /setDashboard\(null\)/);
  assert.match(overview, /hasUsableSummary/);
  assert.match(overview, /statusMeta\(summary/);
  assert.match(overview, /aria-disabled=\{!launchUrl\}/);
  assert.match(overview, /rel=\{launchUrl \? "noopener noreferrer" : undefined\}/);
  assert.doesNotMatch(overview, /Math\.random\(|mockKpi|fakeRevenue|99999/);
});

test("Vision79 identity is shown in the existing permission-aware sidebar", () => {
  assert.match(sidebar, /vision79-sidebar hub-sidebar/);
  assert.match(sidebar, />Vision<span className="text-\[#55c7ff\]">79<\/span>/);
  assert.match(sidebar, /primary\.filter\(\(item\) => item\.visible\)/);
  assert.match(sidebar, /onClick=\{onLogout\}/);
  assert.match(sidebar, /can\("connections"\)/);
});

test("visual CSS is scoped and accessible on desktop and mobile", () => {
  assert.match(css, /Vision79 command-centre visual release v1/);
  for (const cls of [
    ".vision79-release-v1 .vision79-command-hero",
    ".vision79-release-v1 .vision79-app-section",
    ".vision79-release-v1 .vision79-product-card",
    ".vision79-release-v1 .vision79-focus-panel",
    ".vision79-sidebar .hub-nav-item",
  ]) assert.ok(css.includes(cls));
  assert.match(css, /prefers-reduced-motion:reduce/);
  assert.match(css, /max-width:640px/);
  assert.match(overview, /focus-visible:outline/);
});
