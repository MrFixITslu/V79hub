import { planTrialReminders, claimTrialReminder, completeTrialReminder } from "./trial-reminders.mjs";

/**
 * Transactional PostgreSQL trial reminder worker.
 *
 * Claim-before-send ensures another Hub worker cannot send the same reminder.
 * State is read from the authoritative DB and only trialReminderEvents are
 * changed in the transaction. A crashed sender intentionally leaves a
 * "sending" claim requiring operator review; it never automatically resends.
 *
 * This is for the existing single nominated leader, with DB row-lock safety.
 * Real email dispatch only occurs when explicitly enabled by the owner.
 */
/**
 * @param {{
 *   persistence?: any,
 *   ownerOrganizationId?: string,
 *   send?: (reminder: any) => Promise<boolean>,
 *   now?: number,
 * }} [args]
 */
export async function dispatchTransactionalTrialReminders({
  persistence,
  ownerOrganizationId,
  send,
  now = Date.now(),
} = {}) {
  if (persistence?.mode !== "postgres" ||
      typeof persistence.refresh !== "function" ||
      typeof persistence.transact !== "function") {
    throw new Error("PostgreSQL transactional reminder persistence is required.");
  }
  if (typeof send !== "function") throw new Error("Reminder delivery callback is required.");
  const initial = await persistence.refresh();
  const candidates = planTrialReminders(initial, { ownerOrganizationId, now });
  const results = [];

  for (const reminder of candidates) {
    const claimed = await persistence.transact(state => {
      const current = planTrialReminders(state, { ownerOrganizationId, now })
        .find(item => item.key === reminder.key);
      if (!current) return { claimed: false, key: reminder.key };
      const next = claimTrialReminder(state, current, now);
      state.trialReminderEvents = next.trialReminderEvents;
      return { claimed: true, reminder: current };
    }, { skipWriteWhen: decision => !decision.claimed });

    // Concurrent workers skip a claim already made by another leader. No
    // email is attempted until PostgreSQL has durably committed the claim.
    if (!claimed.result.claimed) continue;
    let success = false;
    try { success = (await send(claimed.result.reminder)) === true; }
    catch { success = false; }

    // On an interrupted completion, the persisted "sending" claim remains.
    // Retrying would risk duplicate customer mail, so review manually.
    await persistence.transact(state => {
      const next = completeTrialReminder(state, reminder.key, { success, now });
      state.trialReminderEvents = next.trialReminderEvents;
      return { completed: true, key: reminder.key };
    });
    results.push({ key: reminder.key, success });
  }
  return results;
}
