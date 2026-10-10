import { accessDecision } from "./subscription-access.mjs";

export const TRIAL_REMINDER_OFFSETS = Object.freeze([
  {kind:"seven_days",beforeMs:7*86400000},
  {kind:"one_day",beforeMs:86400000},
  {kind:"expired",beforeMs:0},
]);
const MAX_RETRIES=4;

/** @param {any} store @param {{ownerOrganizationId?: string, now?: number}} [options] */
export function planTrialReminders(store, {ownerOrganizationId,now=Date.now()}={}) {
  const timestamp=new Date(now).getTime();
  if(!Number.isFinite(timestamp)||!ownerOrganizationId) throw new Error("Valid time and owner ID are required");
  const events=Array.isArray(store.trialReminderEvents)?store.trialReminderEvents:[];
  const reminders=[];
  for(const plan of store.organizationPlans||[]) {
    if(plan.organizationId===ownerOrganizationId||
       plan.accessPolicyType!=="trial" || plan.status!=="trial") continue;
    const start=Date.parse(plan.trialStartedAt||""),end=Date.parse(plan.trialEndsAt||"");
    if(!Number.isFinite(start)||!Number.isFinite(end)||end-start!==14*86400000||
       timestamp<start) continue;
    // After downtime, deliver the most urgent stage only, not stale notices.
    const due=TRIAL_REMINDER_OFFSETS.filter(s=>timestamp>=end-s.beforeMs).at(-1);
    if(!due)continue;
    if(due.kind==="expired" && accessDecision(plan,timestamp).allowed)continue;
    const organization=(store.organizations||[]).find(o=>o.id===plan.organizationId && o.status==="active");
    if(!organization)continue;
    const ownerMemberships=(store.memberships||[]).filter(m=>
      m.organizationId===plan.organizationId && m.role==="owner" && m.status==="active");
    if(ownerMemberships.length!==1)continue;
    const user=(store.users||[]).find(u=>u.id===ownerMemberships[0].userId);
    const email=String(user?.email||"").trim().toLowerCase();
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))continue;
    const key=[plan.organizationId,plan.trialStartedAt,due.kind].join(":");
    const previous=events.find(e=>e.key===key);
    if(previous?.status==="sent" || previous?.status==="sending")continue;
    if(previous && (
      Number(previous.attempts||0)>=MAX_RETRIES ||
      timestamp<Date.parse(previous.nextAttemptAt||"1970-01-01")
    ))continue;
    reminders.push({key,kind:due.kind,organizationId:plan.organizationId,
      trialEndsAt:plan.trialEndsAt,email,attempts:Number(previous?.attempts||0)});
  }
  return reminders;
}

export function claimTrialReminder(store,reminder,now=Date.now()) {
  const clone=structuredClone(store);
  const events=Array.isArray(clone.trialReminderEvents)?clone.trialReminderEvents:[];
  if(events.some(e=>e.key===reminder.key && ["sent","sending"].includes(e.status)))
    throw new Error("Duplicate notification claim refused");
  const entry={key:reminder.key,kind:reminder.kind,organizationId:reminder.organizationId,
    status:"sending",attempts:reminder.attempts+1,claimedAt:new Date(now).toISOString()};
  clone.trialReminderEvents=[...events.filter(e=>e.key!==reminder.key),entry];
  return clone;
}

export function completeTrialReminder(store,key,{success,now=Date.now()}) {
  const clone=structuredClone(store);
  const events=clone.trialReminderEvents||[];
  const index=events.findIndex(e=>e.key===key && e.status==="sending");
  if(index<0)throw new Error("Notification claim missing");
  const earlier=events[index];
  events[index]={...earlier,status:success?"sent":"failed",
    ...(success?{sentAt:new Date(now).toISOString()}:
      {nextAttemptAt:new Date(now+Math.min(3600000,60000*2**(earlier.attempts-1))).toISOString()})};
  return clone;
}
