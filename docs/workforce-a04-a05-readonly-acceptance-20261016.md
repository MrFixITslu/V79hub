# A04/A05 read-only owner acceptance — preparation, not live certification

**Source head:** `3adf8d7a590cfa5bda9ce631cae392cbdf54bb7c`  
**Time zone:** America/St_Lucia (UTC-04:00 all year)  
**Commercial scope:** Hub + Tiquet only, owner-MFA and existing G2 queue preserved.

## A04: unattended briefing acceptance

The host uses the **existing** owner-user systemd timers at 08:00 and 19:00 Saint Lucia local time. The Node scheduler in source is **not** a substitute: do not start duplicate scheduler instances. Python's state `recorded` is storage status; report evidence coverage separately distinguishes `available` and `incomplete`.

Next unverified morning: **2026-10-17 08:00 AST / 12:00 UTC**. Do not claim pass before that run. Read-only audit after 08:30 AST should inspect the morning unit and report inventory, using only safe status output:

```bash
python3 ~/.local/share/v79-workforce-operations/bin/v79_workforce_briefing.py status
systemctl --user list-timers --all --no-pager
journalctl --user -u 'v79-workforce-briefing@morning.service' --since '2026-10-17 07:30:00' --no-pager -l
```

**Do not paste email content, credentials, raw platform or customer payloads.** A reporting file is not trustworthy simply because it exists. Independently check exact owner/private mount, regular-file permissions, source timestamp, relevant run receipt and complete directory inventory. Verify **at least three successive local days** with morning and evening slots before considering sustained reliability, including future/missed-window, duplicate and stale denial tests. `auditBriefingReliability` in `workforce/quality/briefing-reliability.mjs` only emits a candidate for owner review; it does not grant GO or send emails. A missing signed/inventory verifier always prevents a healthy conclusion.

## A05: task follow-through acceptance

Use only the existing owner-MFA `/api/agent/work-actions` queue. Filter to `create_work_item` before passing to the draft read-only adapter. A trusted queue projection requires validation **outside the model** of the real Hub session, source ledger integrity, owner organization and exact action digest; a callback that always returns true is a test stub, **not** a production verifier.

Evidence ladder:

1. **Pending:** proposed draft; no approval or execution.
2. **Approved:** exact owner-MFA approval recorded; still not executed.
3. **Work item created:** fixed worker operation succeeded, signed queue result has a task ID + exact receipt digest. Engineering still unverified.
4. **Delivery verified:** independent owner acceptance bound to the same job, organization, task ID and digest, with pinned source commit and independent test provenance. Missing or unverifiable evidence remains `delivery_unverified`.
5. **Uncertain:** operator reconciliation required before retry; no assumption of either failure or success.

The `projectWorkItem` and `summarizeDeliveryBoard` functions in `workforce/quality/task-delivery-gates.mjs` are offline projections. They neither grant permissions nor write to task systems, and **are not yet installed in the Hub UI**. Do not substitute an LLM statement, a successful CI run, GitHub issue closure or a task-creation receipt for the founder's independently attested delivery decision.

## Source test and release gates

CI `39000783586` passed **44 tests** (22 previous + 11 A04 + 11 A05), including bogus owner scope, rejected/uncertain queue, forged owner acceptance, missing briefing inventory, forged reports, duplicates, stale and future slots. Source checks cannot certify a real host, actual model accuracy or a customer release.

Before any live integration: independently review the cumulative #156→#159 changes, map effective Hub UID/private report permissions and current signed ledger, test owner-MFA cross-tenant denials and read-only request boundaries, prove exact running mixed-image and pinned WiPay parity, preserve every ordered Compose input plus backup/rollback, and obtain a separate founder release decision.

**Explicitly out of scope:** changing the existing systemd timers, worker credentials, token mounts, agent/Hub/Tiquet containers, WiPay, customer invites, Sentinel collector coverage, phone/WhatsApp/email outbound actions, automatic deployments and autonomous privileged actions.
