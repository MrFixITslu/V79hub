import test from "node:test";
import assert from "node:assert/strict";
import {beginTrial} from "../server/subscription-access.mjs";
import {dispatchDueTrialReminders} from "../server/trial-reminder-dispatch.mjs";
const activated=Date.parse("2026-11-01T09:00:00Z");
const owner="vision79-internal";
function fixture() {
  return {
    organizations:[{id:"trial-customer",status:"active"}],
    organizationPlans:[{organizationId:"trial-customer",...beginTrial(activated)}],
    users:[{id:"customer-owner",email:"trial@example.test"}],
    memberships:[{organizationId:"trial-customer",userId:"customer-owner",role:"owner",status:"active"}],
    trialReminderEvents:[],
  };
}
test("claim-before-send sequence sends once and persists one event",async()=>{
  let state=fixture(),sends=0,saves=0;
  const options={
    ownerOrganizationId:owner, now:activated+7*86400000,
    getStore:()=>state,
    commit:async next=>{state=next;saves++;},
    send:async()=>{sends++;return true;},
  };
  assert.equal((await dispatchDueTrialReminders(options)).length,1);
  assert.equal(sends,1);assert.equal(saves,2);
  assert.equal(state.trialReminderEvents[0].status,"sent");
  assert.equal((await dispatchDueTrialReminders(options)).length,0);
  assert.equal(sends,1);
});
test("delivery errors are retryable with backoff, no instant retry storm",async()=>{
  let state=fixture(),sends=0;
  const options={ownerOrganizationId:owner,now:activated+7*86400000,
    getStore:()=>state,commit:async next=>{state=next;},
    send:async()=>{sends++;throw Error("offline");}};
  assert.equal((await dispatchDueTrialReminders(options))[0].success,false);
  assert.equal(state.trialReminderEvents[0].status,"failed");
  assert.equal((await dispatchDueTrialReminders(options)).length,0);
  assert.equal(sends,1);
  assert.equal((await dispatchDueTrialReminders({...options,now:options.now+60001})).length,1);
  assert.equal(sends,2);
});
test("an interrupted sending claim does not issue a second email",async()=>{
  let state=fixture();
  const options={ownerOrganizationId:owner,now:activated+7*86400000,
    getStore:()=>state,
    commit:async next=>{state=next;},
    send:async()=>true};
  await dispatchDueTrialReminders({
    ...options,
    commit:async next=>{state=next;throw Error("synthetic crash before send");}
  }).catch(e=>assert.match(e.message,/synthetic crash/));
  assert.equal(state.trialReminderEvents[0].status,"sending");
  assert.equal((await dispatchDueTrialReminders(options)).length,0);
});
