import test from "node:test";
import assert from "node:assert/strict";
import { createMarketingRenameHandler } from "../server/marketing-rename-endpoint.mjs";

const pathname = "/api/platform/organization/rename";

function validBody() {
  return {
    organizationId: "org-a",
    hubOwnerUserId: "owner-a",
    marketingBusinessId: "business-a",
    marketingUserId: "marketing-owner-a",
    expectedName: "Old Name",
    name: "New Name",
    eventId: "rename-001",
    occurredAt: "2026-11-13T16:00:00.000Z",
  };
}

async function request({
  body = validBody(),
  serviceId = "v79-marketing",
  signature = "valid",
  secret = "local-test-secret",
  timestamp = "timestamp-1",
  rename = async () => ({
    applied: true, duplicate: false, revision: 2,
  }),
} = {}) {
  const rawBody = JSON.stringify(body);
  const calls = [];
  const headers = {
    "x-v79-service-id": serviceId,
    "x-v79-signature": signature,
    "x-v79-timestamp": timestamp,
  };

  const req = {
    body,
    rawBody: Buffer.from(rawBody),
    get: name => headers[name.toLowerCase()] || "",
  };
  const res = {
    code: 200,
    payload: null,
    headers: {},
    setHeader(name, value) { this.headers[name] = value; },
    status(code) { this.code = code; return this; },
    json(value) { this.payload = value; return this; },
  };

  const handler = createMarketingRenameHandler({
    secret: () => secret,
    verify: args =>
      args.method === "POST" &&
      args.pathname === pathname &&
      args.body === rawBody &&
      args.timestamp === timestamp &&
      args.signature === "valid" &&
      args.secret === "local-test-secret",
    rename: async input => {
      calls.push(input);
      return rename(input);
    },
  });

  await handler(req, res);
  return { res, calls };
}

test("valid signed request queues independent deliveries", async () => {
  const { res, calls } = await request();
  assert.equal(res.code, 202);
  assert.equal(res.payload.accepted, true);
  assert.equal(res.payload.deliveryConfirmed, false);
  assert.deepEqual(res.payload.destinations, ["tiquet", "pos"]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].auditEvent.type, "organization.name.changed");
  assert.equal(calls[0].auditEvent.actorUserId, "owner-a");
  assert.equal(calls[0].marketingAuthorization.marketingBusinessId, "business-a");
});

test("retries retain stable audit identity and payload", async () => {
  const a = await request();
  const b = await request({
    timestamp: "timestamp-2",
    rename: async () => ({
      applied: false, duplicate: true, revision: 2,
    }),
  });
  assert.deepEqual(a.calls[0], b.calls[0]);
  assert.equal(b.res.code, 200);
  assert.equal(b.res.payload.duplicate, true);
});

for (const [description, options] of [
  ["incorrect service", { serviceId: "v79-pos" }],
  ["invalid signature", { signature: "invalid" }],
  ["missing secret", { secret: "" }],
]) {
  test(`rejects ${description} before persistence`, async () => {
    const { res, calls } = await request(options);
    assert.equal(res.code, 401);
    assert.equal(calls.length, 0);
  });
}

for (const [description, change] of [
  ["empty event ID", b => { b.eventId = ""; }],
  ["invalid name", b => { b.name = " Invalid"; }],
  ["unchanged name", b => { b.name = b.expectedName; }],
  ["invalid event date", b => { b.occurredAt = "not-a-date"; }],
  ["missing tenant", b => { b.marketingBusinessId = ""; }],
]) {
  test(`rejects ${description} before persistence`, async () => {
    const body = validBody();
    change(body);
    const { res, calls } = await request({ body });
    assert.equal(res.code, 400);
    assert.equal(calls.length, 0);
  });
}

test("rejects revoked owner and stale-name conflicts", async () => {
  for (const [code, expectedStatus] of [
    ["denied", 403],
    ["conflict", 409],
  ]) {
    const { res } = await request({
      rename: async () => {
        const error = new Error("Denied");
        error.name = "MarketingRenameAccessError";
        error.code = code;
        throw error;
      },
    });
    assert.equal(res.code, expectedStatus);
    assert.equal(res.payload.accepted, undefined);
  }
});

test("rejects conflicting duplicate event IDs", async () => {
  const { res } = await request({
    rename: async () => {
      throw new Error("Organisation rename event ID was reused with different data.");
    },
  });
  assert.equal(res.code, 409);
});
