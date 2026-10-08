import test from "node:test";
import assert from "node:assert/strict";
import {beginTrial} from "../server/subscription-access.mjs";
import {planTrialReminders,claimTrialReminder,completeTrialReminder} from "../server/trial-reminders.mjs";
const start=Date.parse("2026-11-01T09:00:00Z");
const owner="v79-owner", org="customer-one";
function fixture(){
  return {
    organizations:[{id:owner,status:"active"},{id:org,status:"active"}],
    users:[{id:"u-customer",email:"customer@example.test"}],
    memberships:[{organizationId:org,userId:"u-customer",role:"owner",status:"active"}],
    organizationPlans:[{organizationId:org,...beginTrial(start)},{organizationId:owner,...beginTrial(start)}],
    trialReminderEvents:[],
  };
}
function at(days){return start+days*86400000;}
test("seven-day, one-day and expiry reminders are computed from actual activation",()=>{
  const state=fixture();
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(0)}).length,0);
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(7)})[0].kind,"seven_days");
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(13)})[0].kind,"one_day");
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(14)})[0].kind,"expired");
});
test("durable sent event prevents duplicate email and does not affect another stage",()=>{
  const state=fixture(), item=planTrialReminders(state,{ownerOrganizationId:owner,now:at(7)})[0];
  const claimed=claimTrialReminder(state,item,at(7));
  assert.equal(planTrialReminders(claimed,{ownerOrganizationId:owner,now:at(7)}).length,0);
  const complete=completeTrialReminder(claimed,item.key,{success:true,now:at(7)});
  assert.equal(planTrialReminders(complete,{ownerOrganizationId:owner,now:at(7)}).length,0);
  assert.equal(planTrialReminders(complete,{ownerOrganizationId:owner,now:at(13)})[0].kind,"one_day");
  assert.equal((state.trialReminderEvents||[]).length,0);
});
test("down time never blasts all old reminders, only most relevant",()=>{
  assert.equal(planTrialReminders(fixture(),{ownerOrganizationId:owner,now:at(20)})[0].kind,"expired");
});
test("invalid or revoked owner identity, stopped plan, and invalid trial never notify",()=>{
  const state=fixture();
  state.organizationPlans[0].status="cancelled";
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(8)}).length,0);
  state.organizationPlans[0].status="trial";
  state.memberships[0].status="revoked";
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(8)}).length,0);
  state.memberships[0].status="active";
  state.organizationPlans[0].trialEndsAt="not-date";
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(8)}).length,0);
});
test("failed sends retry with bounded delay and finite attempt count",()=>{
  let state=fixture();
  const item=planTrialReminders(state,{ownerOrganizationId:owner,now:at(7)})[0];
  for(let i=0;i<4;i++){
    const next=planTrialReminders(state,{ownerOrganizationId:owner,now:at(7)+i*7200000})[0];
    assert.ok(next);
    state=completeTrialReminder(claimTrialReminder(state,next,at(7)+i*7200000),next.key,
      {success:false,now:at(7)+i*7200000});
  }
  assert.equal(planTrialReminders(state,{ownerOrganizationId:owner,now:at(8)}).length,0);
});
