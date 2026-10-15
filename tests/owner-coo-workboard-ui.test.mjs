import test from "node:test";
import assert from "node:assert/strict";
import { register } from "tsx/esm/api";
import { Window } from "happy-dom";
import React, { act } from "react";
register();

const browser = new Window({
  url: "https://hub.synthetic.test",
  settings: { disableCSSFileLoading: true, disableJavaScriptFileLoading: true },
});
for (const key of ["document", "HTMLElement", "Event", "MouseEvent", "DOMException"])
  globalThis[key] = browser[key];
globalThis.window = browser;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { createRoot } = await import("react-dom/client");
const { OwnerCooWorkboardPanel } = await import("../src/components/OwnerCooWorkboardPanel.tsx");

const safe = {
  mode: "read-only", source: "github-issue-pr-register",
  collectedAt: "2026-10-15T20:00:00Z", connection: "PARTIAL_OR_COMPLETE",
  lanes: ["Hub + Tiquet", "Sentinel protection"], repositories: [
    { repo: "V79hub", fetchState: "COMPLETE" },
    { repo: "V79-Sentinel", fetchState: "UNAVAILABLE" },
  ],
  tracked: [
    { lane: "Hub + Tiquet", repo: "V79hub", number: 152, kind: "issue",
      label: "COO delivery board", nextStep: "Review evidence only",
      githubState: "OPEN_IN_GITHUB",
      url: "https://github.com/MrFixITslu/V79hub/issues/152", updatedAt: "2026-10-15T20:00:00Z" },
    { lane: "Sentinel protection", repo: "V79-Sentinel", number: 15, kind: "issue",
      label: "Sentinel actual monitoring", nextStep: "No live claims",
      githubState: "UNKNOWN_SOURCE",
      url: "https://github.com/MrFixITslu/V79-Sentinel/issues/15", updatedAt: null },
  ],
  runtimeHealth: "UNKNOWN", deployedRevision: "UNKNOWN",
  customerLaunchGo: "NOT_ESTABLISHED", sentinelCoverage: "NOT_ESTABLISHED",
  approvalGranted: false, executionEnabled: false,
  caveat: "GitHub is not uptime or security evidence",
};

async function fixture(t, next) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, opts });
    if (typeof next === "function") return await next(calls.length);
    return { ok: true, json: async () => structuredClone(next) };
  };
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(OwnerCooWorkboardPanel)));
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete globalThis.fetch;
  });
  const click = async text => {
    const b = [...container.querySelectorAll("button")].find(x => x.textContent.includes(text));
    assert.ok(b, "Missing button: " + text);
    await act(async () => b.click());
  };
  return { container, calls, click };
}

test("collapsed panel performs no network request; opening requires only same-origin GET", async t => {
  const h = await fixture(t, safe);
  assert.equal(h.calls.length, 0);
  await h.click("COO workboard");
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].url, "/api/agent/coo-workboard");
  assert.equal(h.calls[0].opts.credentials, "same-origin");
  assert.equal(h.calls[0].opts.cache, "no-store");
  assert.equal(h.calls[0].opts.method, undefined);
  assert.match(h.container.textContent, /Production health: unknown/);
  assert.match(h.container.textContent, /Sentinel verified protection: not established/);
  assert.match(h.container.textContent, /inaccessible or incompletely listed/);
  const links = [...h.container.querySelectorAll("a")];
  assert.equal(links.length, 2);
  assert.equal(links[0].getAttribute("href"), "https://github.com/MrFixITslu/V79hub/issues/152");
  assert.equal(links[0].getAttribute("rel"), "noopener noreferrer");
  assert.ok(h.container.querySelector('button[aria-expanded="true"]'));
  assert.equal(h.container.querySelectorAll("form").length, 0);
});

test("MFA denial shows access requirement, never task data or mutation UI", async t => {
  const h = await fixture(t, async () => ({
    ok: false, status: 403, json: async () => ({ error: "Synthetic" }),
  }));
  await h.click("COO workboard");
  assert.match(h.container.textContent, /MFA-verified founder session is required/);
  assert.doesNotMatch(h.container.textContent, /COO delivery board/);
  assert.equal(h.container.querySelectorAll("a").length, 0);
});

test("unexpected escalation of AI execution permission fails closed", async t => {
  const h = await fixture(t, { ...safe, executionEnabled: true });
  await h.click("COO workboard");
  assert.match(h.container.textContent, /failed read-only safety validation/);
  assert.doesNotMatch(h.container.textContent, /COO delivery board/);
});

test("a failed refresh clears earlier successful evidence instead of presenting stale success", async t => {
  const h = await fixture(t, async count => count === 1
    ? { ok: true, json: async () => structuredClone(safe) }
    : { ok: false, status: 503, json: async () => ({ error: "Unavailable" }) });
  await h.click("COO workboard");
  assert.match(h.container.textContent, /COO delivery board/);
  await h.click("Refresh read-only status");
  assert.match(h.container.textContent, /COO workboard is unavailable/);
  assert.doesNotMatch(h.container.textContent, /COO delivery board/);
  assert.equal(h.calls.length, 2);
});

test("unknown private Sentinel status is never shown as operationally healthy", async t => {
  const h = await fixture(t, safe);
  await h.click("COO workboard");
  assert.match(h.container.textContent, /UNKNOWN SOURCE/);
  assert.doesNotMatch(h.container.textContent, /7\/7 UP/);
  assert.doesNotMatch(h.container.textContent, /Sentinel verified protection: established/);
});
