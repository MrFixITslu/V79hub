import {
  planTrialReminders, claimTrialReminder, completeTrialReminder
} from "./trial-reminders.mjs";

// Inject the store and sender so retry/deduplication can be tested without
// running a server or sending real messages. The caller must own a single leader lock.
export async function dispatchDueTrialReminders({
  ownerOrganizationId,getStore,commit,send,now=Date.now()
}) {
  const due=planTrialReminders(getStore(),{ownerOrganizationId,now});
  const results=[];
  for(const reminder of due){
    if(!planTrialReminders(getStore(),{ownerOrganizationId,now})
      .some(x=>x.key===reminder.key))continue;
    await commit(claimTrialReminder(getStore(),reminder,now));
    let success=false;
    try{success=await send(reminder)===true;}catch{success=false;}
    await commit(completeTrialReminder(getStore(),reminder.key,{success,now}));
    results.push({key:reminder.key,success});
  }
  return results;
}
