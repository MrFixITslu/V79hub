import test from "node:test";
import assert from "node:assert/strict";
import {
  createOrganizationNameDeliveryWorker,
  ORGANIZATION_NAME_SYNC_PATH,
} from "../server/organization-name-delivery.mjs";
import { verifyPlatformRequest } from "../server/platform-contract.mjs";

const secret = "test-secret-123456789012345678901234567890";

function setup(fetchImpl, configured = true) {
  const jobs = {
    tiquet: {
      id: "job-t",
      eventId: "event-1",
      organizationId: "org-a",
      destination: "tiquet",
      name: "New Name",
      nameRevision: 5,
      attempts: 1,
      leaseToken: "lease-t",
    },
    pos: {
      id: "job-p",
      eventId: "event-1",
      organizationId: "org-a",
      destination: "pos",
      name: "New Name",
      nameRevision: 5,
      attempts: 1,
      leaseToken: "lease-p",
    },
  };

  const delivered = [];
  const failed = [];
  const claimed = [];

  const repository = {
    async claimOrganizationNameDelivery(destination) {
      claimed.push(destination);
      return jobs[destination];
    },
    async markOrganizationNameDelivered(value) {
      delivered.push(value);
    },
    async markOrganizationNameFailed(value) {
      failed.push(value);
      return "pending";
    },
  };

  const endpoints = configured ? {
    tiquet: { baseUrl: "http://tiquet.test/", secret },
    pos: { baseUrl: "http://pos.test/", secret },
  } : {};

  const worker = createOrganizationNameDeliveryWorker({
    repository,
    endpoints,
    fetchImpl,
  });

  return { worker, delivered, failed, claimed };
}

function acknowledgement(body) {
  return new Response(JSON.stringify({
    accepted: true,
    ...JSON.parse(body),
  }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

test("worker signs requests and accepts exact acknowledgements", async () => {
  const x = setup(async (url, options) => {
    assert.equal(
      new URL(url).pathname,
      ORGANIZATION_NAME_SYNC_PATH,
    );
    assert.equal(options.redirect, "error");

    assert.equal(verifyPlatformRequest({
      method: options.method,
      pathname: new URL(url).pathname,
      timestamp: options.headers["x-v79-timestamp"],
      signature: options.headers["x-v79-signature"],
      body: options.body,
      secret,
    }), true);

    return acknowledgement(options.body);
  });

  const result = await x.worker.deliverOnce("pos");
  assert.equal(result.status, "delivered");
  assert.equal(x.delivered.length, 1);
  assert.equal(x.failed.length, 0);
});

test("incorrect acknowledgement never marks delivery complete", async () => {
  const x = setup(async (_, options) => {
    const body = JSON.parse(options.body);
    return new Response(JSON.stringify({
      accepted: true,
      ...body,
      nameRevision: body.nameRevision - 1,
    }), { status: 200 });
  });

  const result = await x.worker.deliverOnce("pos");
  assert.equal(result.status, "pending");
  assert.equal(x.delivered.length, 0);
  assert.equal(x.failed.length, 1);
});

test("Tiquet failure does not block POS", async () => {
  const x = setup(async (url, options) => {
    if (url.includes("tiquet.test")) {
      throw new Error("Tiquet offline");
    }
    return acknowledgement(options.body);
  });

  const results = await x.worker.runOnce();
  assert.equal(results.tiquet.status, "pending");
  assert.equal(results.pos.status, "delivered");
  assert.equal(x.delivered.length, 1);
  assert.equal(x.failed.length, 1);
});

test("missing configuration prevents any database claim", async () => {
  const x = setup(async () => {
    throw new Error("Must not send");
  }, false);

  const results = await x.worker.runOnce();
  assert.equal(results.tiquet.status, "worker_error");
  assert.equal(results.pos.status, "worker_error");
  assert.equal(x.claimed.length, 0);
});

test("lost acknowledgement lease cannot report success", async () => {
  const x = setup(
    async (_, options) => acknowledgement(options.body),
  );

  x.worker; // The repository is intentionally exercised through its lease API.
  const repository = {
    async claimOrganizationNameDelivery() {
      return {
        id: "job-p",
        eventId: "event-1",
        organizationId: "org-a",
        destination: "pos",
        name: "New Name",
        nameRevision: 5,
        attempts: 1,
        leaseToken: "expired",
      };
    },
    async markOrganizationNameDelivered() {
      throw new Error("Outbox lease lost");
    },
    async markOrganizationNameFailed() {
      throw new Error("Should not mark failed after acknowledgement");
    },
  };

  const worker = createOrganizationNameDeliveryWorker({
    repository,
    endpoints: {
      pos: { baseUrl: "http://pos.test/", secret },
    },
    fetchImpl: async (_, options) => acknowledgement(options.body),
  });

  await assert.rejects(
    worker.deliverOnce("pos"),
    /lease lost/,
  );
});
