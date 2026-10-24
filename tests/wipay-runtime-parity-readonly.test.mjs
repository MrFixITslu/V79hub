import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { summarizeContainerInspection, inspectContainerReadOnly } from "../scripts/wipay-runtime-parity-readonly.mjs";

const secret = "HIGHLY_PRIVATE_MERCHANT_KEY_NEVER_OUTPUT_2026";
const db = "postgresql://real-user:REAL_PASSWORD@private-host/db";
function fixture() {
  return {
    Image: "sha256:" + "a".repeat(64),
    State: { Running: true, Health: { Status: "healthy" } },
    Config: {
      Labels: { "org.opencontainers.image.revision": "b".repeat(40),
        "arbitrary": secret },
      Env: [
        "V79_HUB_STORE_BACKEND=postgres", "DATABASE_URL=" + db,
        "WIPAY_API_KEY=" + secret,
        "WIPAY_PAYMENT_URL=https://merchant.invalid/secret=" + secret,
        "WIPAY_ENV=sandbox", "WIPAY_ENABLED=0",
        "V79_BILLING_STATE_SECRET=" + secret,
        "ACADEMY_TOKEN=" + secret,
        "WIPAY_RESPONSE_URL=https://example.invalid/callback?secret=" + secret,
      ],
    },
    Mounts: [{ Source: "/private/customer-records/" + secret, Destination: "/data" }],
  };
}
test("inspect parser never leaks env values, mount paths, labels or credentials", () => {
  const r = summarizeContainerInspection("v79-hub", fixture());
  const printed = JSON.stringify(r);
  assert.equal(r.state, "RUNNING");
  assert.equal(r.health, "healthy");
  assert.equal(r.observed.backend, "postgres");
  assert.equal(r.observed.wipay_environment, "sandbox");
  assert.equal(r.observed.wipay_enabled, false);
  assert.equal(r.observed.flags.WIPAY_API_KEY, true);
  assert.equal(r.mount_count, 1);
  assert.equal(r.provider_merchant_activation, "NOT_VERIFIED");
  for (const item of [secret, db, "REAL_PASSWORD", "/private/customer-records", "ACADEMY_TOKEN"]) {
    assert.equal(printed.includes(item), false, "Sensitive value/key leaked: " + item);
  }
});
test("invalid env flags fail closed and do not infer payment eligibility", () => {
  const d = fixture();
  d.Config.Env = ["V79_HUB_STORE_BACKEND=unknown", "WIPAY_ENV=xcd-prod", "WIPAY_ENABLED=yes"];
  d.Image = "not-an-immutable-image-id";
  d.Config.Labels["org.opencontainers.image.revision"] = "main";
  const v = summarizeContainerInspection("academy", d);
  assert.equal(v.observed.backend, "UNVERIFIED");
  assert.equal(v.observed.wipay_environment, "UNVERIFIED");
  assert.equal(v.observed.wipay_enabled, "UNVERIFIED");
  assert.equal(v.image_id, "UNVERIFIED");
  assert.equal(v.build_revision, "UNVERIFIED");
});
test("actual Docker command is read-only inspect with exact arguments", () => {
  const calls = [];
  const fake = (command, args, options) => {
    calls.push({ command, args, options });
    return JSON.stringify([fixture()]);
  };
  const v = inspectContainerReadOnly("v79-hub", fake);
  assert.equal(v.state, "RUNNING");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "docker");
  assert.deepEqual(calls[0].args, ["inspect", "--type", "container", "v79-hub"]);
  assert.equal(calls[0].options.stdio[2], "ignore");
});
test("untrusted flags, names, and malformed Docker output cannot launch commands or leak errors", () => {
  let called = false;
  assert.throws(() => inspectContainerReadOnly("hub; rm -rf /", () => { called = true; }), /Invalid container name/);
  assert.equal(called, false);
  assert.throws(() => inspectContainerReadOnly("--privileged", () => { called = true; }), /Invalid container name/);
  assert.equal(called, false);
  assert.throws(() => inspectContainerReadOnly("hub", () => { throw Error(secret); }), /Docker inspection unavailable/);
  assert.throws(() => inspectContainerReadOnly("hub", () => "not json"), /Invalid Docker inspection output/);
  assert.throws(() => inspectContainerReadOnly("hub", () => "[]"), /Unexpected Docker inspection record count/);
});
test("operator CLI source contains no container mutation or payment initiation", () => {
  const code = readFileSync(new URL("../scripts/wipay-runtime-parity-readonly.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(code, /runner\("docker",\s*\[(?:(?!"inspect")[\s\S])*\]/);
  assert.match(code, /runner\("docker", \["inspect", "--type", "container", name\]/);
  assert.match(code, /production_change: "NONE"/);
  assert.match(code, /wipay_live_activation_safe: false/);
  assert.match(code, /operator_go_live_authorization: false/);
});
test("CLI help prints usage without contacting a Docker daemon", () => {
  const output = execFileSync(process.execPath,
    ["scripts/wipay-runtime-parity-readonly.mjs", "--help"],
    { cwd: process.cwd(), encoding: "utf8", timeout: 5000 });
  assert.match(output, /Read-only usage/);
});
