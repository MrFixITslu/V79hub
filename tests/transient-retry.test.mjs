import test from "node:test";
import assert from "node:assert/strict";
import { retryTransient } from "../server/transient-retry.mjs";

test("retryTransient returns the first successful result", async () => {
  let calls = 0;
  const result = await retryTransient(async () => {
    calls += 1;
    return "ok";
  }, { attempts: 2, delayMs: 0 });

  assert.equal(result, "ok");
  assert.equal(calls, 1);
});

test("retryTransient retries one transient exception", async () => {
  let calls = 0;
  const result = await retryTransient(async () => {
    calls += 1;
    if (calls === 1) throw new Error("temporary");
    return "recovered";
  }, { attempts: 2, delayMs: 0 });

  assert.equal(result, "recovered");
  assert.equal(calls, 2);
});

test("retryTransient rethrows after the final attempt", async () => {
  let calls = 0;
  await assert.rejects(
    retryTransient(async () => {
      calls += 1;
      throw new Error("still down");
    }, { attempts: 2, delayMs: 0 }),
    /still down/,
  );
  assert.equal(calls, 2);
});