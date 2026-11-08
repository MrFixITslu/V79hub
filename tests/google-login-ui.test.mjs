import test from "node:test";
import assert from "node:assert/strict";
import { register } from "tsx/esm/api";
import { Window } from "happy-dom";
import React, { act } from "react";
register();
const browser = new Window({ url: "https://hub.synthetic.test/login" });
for (const key of ["document", "HTMLElement", "Event", "MouseEvent", "DOMException"]) globalThis[key] = browser[key];
globalThis.window = browser;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import("react-dom/client");
const { GoogleSignIn } = await import("../src/components/GoogleSignIn.tsx");

async function mount(t, props, respond) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    const result = respond(url, options, calls);
    return { ok: result.ok !== false, status: result.status || 200, json: async () => result.body };
  };
  await act(async () => { root.render(React.createElement(GoogleSignIn, props)); });
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete globalThis.fetch;
    delete window.google;
  });
  return { container, calls };
}

test("Google option is not shown when the Hub backend has disabled the provider", async t => {
  const h = await mount(t, { organizationId: "", onCredential: async () => {} },
    url => {
      assert.equal(url, "/api/auth/google/config");
      return { body: { enabled: false, clientId: null } };
    });
  assert.equal(h.container.textContent.trim(), "");
  assert.equal(h.calls.length, 1, "No Google nonce or SDK request when disabled");
});

test("Google identity is bound to a fresh single-use server nonce and existing Hub workspace", async t => {
  let options, renderCount = 0, nonces = 0;
  window.google = { accounts: { id: {
    initialize(opts) { options = opts; },
    renderButton(element) { renderCount++; element.textContent = "Google verified sign-in"; },
  } } };
  const sent = [];
  const h = await mount(t, {
    organizationId: "tenant-approved",
    onCredential: async (...args) => { sent.push(args); },
  }, (url, request) => {
    if (url === "/api/auth/google/config") return { body: { enabled: true, clientId: "synthetic-client.apps.googleusercontent.com" } };
    if (url === "/api/auth/google/challenge") {
      assert.equal(request.method, "POST");
      assert.equal(request.credentials, "same-origin");
      nonces++;
      return { body: { nonce: "synthetic_nonce_" + String(nonces).padStart(20, "0") } };
    }
    throw Error("Unexpected endpoint: " + url);
  });
  assert.equal(renderCount, 1);
  assert.equal(options.auto_select, false);
  assert.equal(options.client_id, "synthetic-client.apps.googleusercontent.com");
  assert.equal(options.nonce, "synthetic_nonce_00000000000000000001");
  assert.match(h.container.textContent, /Google verified sign-in/);
  await act(async () => { await options.callback({ credential: "synthetic.untrusted.jwt" }); });
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
  assert.deepEqual(sent, [["synthetic.untrusted.jwt", "synthetic_nonce_00000000000000000001", "tenant-approved"]]);
  assert.equal(nonces, 2, "Every subsequent attempt must fetch a new nonce");
  assert.equal(renderCount, 2);
  assert.equal(options.nonce, "synthetic_nonce_00000000000000000002");
  assert.doesNotMatch(h.container.textContent, /synthetic\.untrusted\.jwt/);
  assert.ok(h.calls.every(c => c.url === "/api/auth/google/config" || c.url === "/api/auth/google/challenge"));
});

test("Google callback cannot issue concurrent credential submissions", async t => {
  let options;
  let finish;
  window.google = { accounts: { id: {
    initialize(opts) { options = opts; },
    renderButton(element) { element.textContent = "Continue with Google"; },
  } } };
  const seen = [];
  await mount(t, {
    organizationId: "",
    onCredential: async credential => {
      seen.push(credential);
      await new Promise(resolve => { finish = resolve; });
    },
  }, url => url.endsWith("/config")
    ? { body: { enabled: true, clientId: "synthetic-client" } }
    : { body: { nonce: "synthetic_nonce_00000000000000000001" } });
  await act(async () => {
    const first = options.callback({ credential: "first" });
    const second = options.callback({ credential: "second" });
    assert.deepEqual(seen, ["first"]);
    finish();
    await Promise.all([first, second]);
  });
});
