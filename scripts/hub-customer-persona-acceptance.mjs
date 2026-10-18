/**
 * V79 customer-persona browser acceptance.
 * Strictly synthetic sessions, app entitlements and metrics. No real service calls.
 * UI checks do not substitute for backend session, tenant or SSO security acceptance.
 */
import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const origin = "http://127.0.0.1:4187";
const output = resolve("persona-artifacts");
await mkdir(output, { recursive: true });

const makeApp = (id, name, shortName, category, iconName, url, ready = true) => ({
  id, name, shortName, category, iconName, appUrl: url,
  status: "active", ssoSupported: true, launchReady: ready,
  tagline: "Synthetic app", description: "Synthetic entitlement and browser check only.",
  features: [], colorScheme: {
    primary: "from-blue-600 to-cyan-500", bgGradient: "",
    badgeBg: "", badgeText: "", border: "",
  },
});
const tiquet = makeApp("app-tiquet", "V79 Digital Tiquet", "Tiquet", "support", "Headphones", "https://tiquet.v79sl.com");
const finance = makeApp("app-ffpro", "FFPRO by V79", "FFPRO", "finance", "Wallet", "https://ffpro.v79sl.com");
const user = (id, role, organizationId, permissions, owned, apps) => ({
  id, username: id, fullName: role === "staff" ? "Synthetic Staff" : "Synthetic Owner",
  email: "not-real@example.invalid", role, platformOperator: false,
  ownerAgent: false, workspaceOwner: owned, permissions, appIds: apps.map(a => a.id),
});
const scenarios = [
  {
    id: "owner-a", org: "Synthetic Alpha Workspace",
    user: user("alpha-owner", "admin", "alpha", ["overview", "connections", "billing"], true, [tiquet, finance]),
    apps: [tiquet, finance],
    summary: { generatedAt: "2026-10-18T12:00:00Z", apps: {
      tiquet: { status: "ok", sourceReportedAt: "2026-10-18T11:50:00Z",
        metrics: { jobs: 10, clients: 3, jobsByStatus: { open: 2, resolved: 8 } } },
      ffpro: { status: "ok", sourceReportedAt: "2026-10-18T11:48:00Z",
        metrics: { currentMonthNet: 75, transactionCount: 3, currency: "XCD" } },
    }},
    visibleApps: 2, expectTiquetLink: true, expectFinance: true,
  },
  {
    id: "staff-a", org: "Synthetic Alpha Workspace",
    user: user("alpha-staff", "staff", "alpha", ["overview", "connections"], false, [tiquet]),
    apps: [{ ...tiquet, launchReady: false, accessMessage: "Access not yet provisioned" }],
    summary: { generatedAt: "2026-10-18T12:00:00Z", apps: {
      tiquet: { status: "restricted", metrics: {}, generatedAt: null },
      ffpro: { status: "restricted", metrics: {}, generatedAt: null },
    }},
    visibleApps: 1, expectTiquetLink: false, expectFinance: false,
  },
  {
    id: "owner-b-no-apps", org: "Synthetic Beta Workspace",
    user: user("beta-owner", "admin", "beta", ["overview", "connections"], true, []),
    apps: [],
    summary: { generatedAt: "2026-10-18T12:00:00Z", apps: {
      tiquet: { status: "not_enabled", metrics: {} },
      ffpro: { status: "not_enabled", metrics: {} },
    }},
    visibleApps: 0, expectTiquetLink: false, expectFinance: false,
  },
  {
    id: "staff-c-no-access", org: "Synthetic Beta Workspace",
    user: user("beta-staff", "staff", "beta", ["overview"], false, []),
    apps: [],
    summary: { generatedAt: "2026-10-18T12:00:00Z", apps: {
      tiquet: { status: "not_enabled", metrics: {} },
      ffpro: { status: "not_enabled", metrics: {} },
    }},
    visibleApps: 0, expectTiquetLink: false, expectFinance: false,
  },
  {
    id: "owner-a-empty-metrics", org: "Synthetic Alpha Workspace",
    user: user("alpha-owner", "admin", "alpha", ["overview", "connections"], true, [tiquet]),
    apps: [tiquet],
    summary: { generatedAt: "2026-10-18T12:00:00Z", apps: {
      tiquet: { status: "ok", metrics: {} },
    }},
    visibleApps: 1, expectTiquetLink: true, expectFinance: false,
  },
];
const report = { source: "synthetic-preview-only", results: [], errors: [], externalRequests: [] };
const browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
try {
  for (const scenario of scenarios) {
    for (const [width, height, device] of [[1440, 900, "desktop"], [390, 844, "mobile"]]) {
      const context = await browser.newContext({
        viewport: { width, height }, reducedMotion: "reduce", deviceScaleFactor: 1,
      });
      await context.addInitScript(() => {
        window.WebSocket = class SyntheticOfflineSocket {
          constructor() { this.readyState = 1; }
          close() {} send() {} addEventListener() {} removeEventListener() {}
        };
      });
      await context.route("**/*", route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) {
          report.externalRequests.push({ scenario: scenario.id, protocol: url.protocol });
          return route.abort("blockedbyclient");
        }
        return route.continue();
      });
      await context.route("**/api/**", route => {
        const path = new URL(route.request().url()).pathname;
        let response;
        if (path === "/api/auth/me")
          response = { user: scenario.user, organization: { name: scenario.org } };
        else if (path === "/api/ecosystem/apps") response = scenario.apps;
        else if (path === "/api/dashboard/summary") response = scenario.summary;
        else if (path === "/api/users") response = [];
        else return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "Not available in synthetic test" }) });
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
      });
      const page = await context.newPage();
      page.on("pageerror", e => report.errors.push({ scenario: scenario.id, type: e.name }));
      try {
        await page.goto(origin);
        await page.locator(".hub-dashboard").waitFor();
        await page.getByText("Application data availability", { exact: true }).waitFor();
        await page.waitForTimeout(300);
        assert.equal(await page.locator(".hub-product-card").count(), scenario.visibleApps,
          "Only synthetic assigned apps may render: " + scenario.id);
        assert.equal(await page.getByText("Platform Admin", { exact: true }).count(), 0,
          "Non-platform operators must not see Platform Admin");
        assert.equal(await page.getByText("Owner Assistant", { exact: true }).count(), 0,
          "Non-owner-agent accounts must not see Owner Assistant");
        const allLinks = await page.locator("a[href]").evaluateAll(els => els.map(el => el.getAttribute("href")));
        assert.ok(allLinks.every(href => !href || !href.includes("/api/apps/pos/launch")),
          "No unassigned POS launch links");
        assert.ok(allLinks.every(href => !href || !href.includes("/api/apps/marketing/launch")),
          "No unassigned marketing launch links");
        if (!scenario.expectFinance) {
          assert.equal(await page.locator(".hub-product-card").filter({ hasText: "FFPRO" }).count(), 0,
            "No finance app tile without entitlement");
        }
        const tiquetCard = page.locator(".hub-product-card").filter({ hasText: "V79 Digital Tiquet" });
        if (scenario.visibleApps && scenario.apps.some(a => a.id === "app-tiquet")) {
          assert.equal(await tiquetCard.count(), 1);
          const href = await tiquetCard.getAttribute("href");
          assert.equal(href, scenario.expectTiquetLink ? "/api/apps/tiquet/launch" : null,
            "Managed SSO or disabled launch; never direct service URL");
        }
        if (scenario.id === "owner-b-no-apps") {
          await page.getByText("No applications are enabled for this workspace.", { exact: true }).waitFor();
          await page.getByRole("heading", { name: "Your workspace is ready for apps" }).waitFor();
          assert.equal(await page.getByRole("button", { name: /View app access/ }).count(), 1,
            "Authorized customer receives a real permitted access-management action");
          assert.equal(await page.locator(".hub-kpi").count(), 0, "Empty tenant has no KPI cards");
          assert.ok(!(await page.locator(".hub-dashboard").innerText()).includes("All enabled app data summaries"),
            "Empty tenant is never shown as all green");
        }
        if (scenario.id === "staff-c-no-access") {
          await page.getByRole("heading", { name: "Your workspace is ready for apps" }).waitFor();
          await page.getByText("Ask your workspace administrator to assign an app to your account.").waitFor();
          assert.equal(await page.getByRole("button", { name: /View app access/ }).count(), 0,
            "Unprivileged staff cannot click access-management CTA");
          assert.equal(await page.getByRole("button", { name: "Manage apps" }).count(), 0,
            "Unprivileged staff cannot access hidden app settings");
        }
        if (scenario.id === "staff-a") {
          assert.ok((await page.locator(".hub-dashboard").innerText()).includes("Restricted"),
            "Unprivileged staff sees restricted state, not owner metrics");
          assert.equal(await page.getByText("75.00", { exact: false }).count(), 0);
        }
        if (scenario.id === "owner-a-empty-metrics") {
          const text = await page.locator(".hub-dashboard").innerText();
          assert.ok(text.includes("No metrics") && text.includes("No enabled application returned a usable data summary."),
            "Empty source returns neither fake zero nor positive data status");
        }
        if (scenario.id === "owner-a") {
          assert.match(await page.locator(".hub-dashboard").innerText(), /75[.,]00/,
            "Product-supplied XCD amount is displayed with its locale currency symbol");
          assert.equal(await tiquetCard.getAttribute("href"), "/api/apps/tiquet/launch");
        }
        await page.evaluate(() => {
          const badge = document.createElement("aside");
          badge.textContent = "SYNTHETIC PERSONA · NOT LIVE";
          badge.style.cssText = "position:fixed;bottom:16px;right:16px;z-index:99999;padding:8px 12px;border-radius:9px;background:#081422;color:white;font:700 11px sans-serif;";
          document.body.append(badge);
        });
        const file = scenario.id + "-" + device + ".png";
        await page.screenshot({ path: resolve(output, file), fullPage: true, animations: "disabled" });
        if (scenario.id === "owner-b-no-apps") {
          await page.getByRole("button", { name: /View app access/ }).click();
          await page.getByRole("heading", { name: "Ecosystem app launcher" }).waitFor();
        }
        report.results.push({ scenario: scenario.id, device, width, status: "PASS", file });
        console.log("PERSONA_PASS " + scenario.id + " " + device);
      } finally {
        await context.close();
      }
    }
  }
} finally {
  await browser.close();
}
await writeFile(resolve(output, "report.json"), JSON.stringify(report, null, 2));
console.log("PERSONA_SCREENSHOTS=" + report.results.length + " ERRORS=" + report.errors.length + " EXTERNAL=" + report.externalRequests.length);
if (report.errors.length || report.externalRequests.length) process.exitCode = 1;
