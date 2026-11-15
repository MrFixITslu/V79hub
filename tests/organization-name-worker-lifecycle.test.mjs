import assert from "node:assert/strict";
import { test } from "node:test";
import { createOrganizationNameDeliveryLifecycle } from "../server/organization-name-worker-lifecycle.mjs";

const config = {
  V79_ORG_NAME_DELIVERY_ENABLED: "1",
  V79_ORG_NAME_TIQ_URL: "http://tiquet.internal:3050/",
  V79_ORG_NAME_POS_URL: "http://pos.internal:8080/",
  V79_ORG_NAME_TIQ_SECRET: "t".repeat(32),
  V79_ORG_NAME_POS_SECRET: "p".repeat(32),
};
const persistence = { mode: "postgres", deliveryRepository: { claimOrganizationNameDelivery() {} } };
function fixture(options = {}) {
  const state = { calls: 0, clears: 0, events: [], workerArgs: null, callback: null };
  const worker = options.worker || { runOnce: async () => {
    state.calls++;
    return { tiquet: {status: "idle"}, pos: {status: "idle"} };
  }};
  const lifecycle = createOrganizationNameDeliveryLifecycle({
    persistence, env: config,
    createWorker(args) { state.workerArgs=args; return worker; },
    schedule(cb, ms) { state.events.push(ms); state.callback=cb; return {unref() {}}; },
    unschedule() { state.clears++; },
    logger: {warn() {},error() {}},
    ...options.extra,
  });
  return {state,lifecycle};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test("disabled by default: no repository or destination calls", async () => {
  let calls=0;
  const x=createOrganizationNameDeliveryLifecycle({
    persistence:{mode:"json"},env:{},createWorker() {calls++; throw Error("not allowed");}
  });
  x.start(); assert.equal(x.enabled,false);
  assert.deepEqual(await x.poll(),{status:"disabled"}); assert.equal(calls,0);
});

test("fail closed when enabled without PostgreSQL repository", () => {
  assert.throws(() => createOrganizationNameDeliveryLifecycle({env:config,persistence:{mode:"json"}}),/PostgreSQL/);
});

test("rejects missing secrets, untrusted URL syntax and invalid opt-in", () => {
  for(const env of [
    {...config,V79_ORG_NAME_TIQ_SECRET:"short"},
    {...config,V79_ORG_NAME_POS_URL:"http://user:pass@host/"},
    {...config,V79_ORG_NAME_POS_URL:"http://host/other"},
    {...config,V79_ORG_NAME_POS_URL:"file:///etc/passwd"},
    {...config,V79_ORG_NAME_DELIVERY_ENABLED:"true"},
  ]) assert.throws(() => createOrganizationNameDeliveryLifecycle({env,persistence}));
});

test("starts only once, polls immediately and schedules periodic retry", async () => {
  const {state,lifecycle}=fixture();
  lifecycle.start(); lifecycle.start(); await settle();
  assert.equal(state.calls,1); assert.deepEqual(state.events,[30000]);
  assert.equal(state.workerArgs.repository,persistence.deliveryRepository);
  assert.equal(state.workerArgs.endpoints.tiquet.baseUrl,config.V79_ORG_NAME_TIQ_URL);
  state.callback(); await settle(); assert.equal(state.calls,2);
  lifecycle.stop(); lifecycle.stop(); assert.equal(state.clears,1);
  assert.deepEqual(await lifecycle.poll(),{status:"stopped"});
});

test("overlapping polls do not claim an outbox row twice", async () => {
  let release;
  let count=0;
  const deferred=new Promise(resolve=> {release=resolve;});
  const {lifecycle}=fixture({worker:{async runOnce() { count++; await deferred; return {tiquet:{status:"idle"},pos:{status:"idle"}}; }}});
  lifecycle.start();
  assert.deepEqual(await lifecycle.poll(),{status:"busy"});
  assert.equal(count,1);
  release(); await settle();
  await lifecycle.poll(); assert.equal(count,2);
  lifecycle.stop();
});

test("worker errors do not crash the process or stop retries", async () => {
  let count=0; const {lifecycle}=fixture({worker:{async runOnce() {count++;throw Error("network down");}}});
  lifecycle.start(); await settle();
  assert.deepEqual(await lifecycle.poll(),{status:"worker_error"});
  assert.equal(count,2); lifecycle.stop();
});

test("rejects invalid polling intervals before scheduling", () => {
  assert.throws(() => createOrganizationNameDeliveryLifecycle({
    env:config,persistence,intervalMs:1000,
  }), /polling interval/);
});
