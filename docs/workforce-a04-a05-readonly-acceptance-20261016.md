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
3. **Work item created:** the authentic G2 ledger shows the approved job as `succeeded`, with `job.result = {taskId, at}`, **and** an independently authenticated matching `state.tasks[]` row (same job, task ID, organization, app, COO assignee and creation timestamp). G2 does **not** generate `receiptSha256` for `create_work_item`. Engineering remains unverified.
4. **Delivery verified:** independent owner acceptance bound to the same job, organization, task ID and digest, with pinned source commit and independent test provenance. Missing or unverifiable evidence remains `delivery_unverified`.
5. **Uncertain:** operator reconciliation required before retry; no assumption of either failure or success.

The `projectWorkItem` and `summarizeDeliveryBoard` functions in `workforce/quality/task-delivery-gates.mjs` are offline projections. They neither grant permissions nor write to task systems, and **are not yet installed in the Hub UI**. Do not substitute an LLM statement, a successful CI run, GitHub issue closure or a task-creation receipt for the founder's independently attested delivery decision.

## Source test and release gates

CI `39000783586` passed **44 tests** (22 previous + 11 A04 + 11 A05), including bogus owner scope, rejected/uncertain queue, forged owner acceptance, missing briefing inventory, forged reports, duplicates, stale and future slots. Source checks cannot certify a real host, actual model accuracy or a customer release.

Before any live integration: independently review the cumulative #156→#159 changes, map effective Hub UID/private report permissions and current signed ledger, test owner-MFA cross-tenant denials and read-only request boundaries, prove exact running mixed-image and pinned WiPay parity, preserve every ordered Compose input plus backup/rollback, and obtain a separate founder release decision.

**Explicitly out of scope:** changing the existing systemd timers, worker credentials, token mounts, agent/Hub/Tiquet containers, WiPay, customer invites, Sentinel collector coverage, phone/WhatsApp/email outbound actions, automatic deployments and autonomous privileged actions.

## Live G2 data-shape reconciliation — 17 October 2026

**Confirmed from actual Hub source**: `server/workforce-actions.mjs` writes `job.result = { taskId, at }` for successful `create_work_item`, and separately appends `state.tasks[]` with `{id,jobId,organizationId,system,title,detail,status:'open',assignedTo:'coo',createdAt}`. The previous offline A05 gate erroneously required `job.result.receiptSha256` (a field used for release receipts), which could never pass a real created task. PR #159 fixes the mismatch, requires trusted queue **and** task-row verifiers, and adds a regression that calls the real `proposeWork`, `decideWork` and `createApprovedWorkItem` functions on synthetic data without network access. Latest source CI: [#39001286288](https://github.com/MrFixITslu/V79hub/actions/runs/39001286288), **53/53 tests PASS**. This does not install the adapter into Hub or independently accept live worker behavior. Owner receipt acceptance remains separate from task creation.


## One-pass operator evidence (no secrets; 17 October 2026)

The morning slot of **17 October 2026 08:00 AST** is now due, but its actual host result has **not** been observed through this ChatGPT session. The remote-terminal connector is usage-limited, not evidence that the timer failed. Run the following **read-only** command locally on \`v79sl\` and share only its terminal output. It does not call any live application API, dump tokens, write files, or change a timer:

\`\`\`bash
(
  set -u
  echo '=== HOST_AND_TIME ==='
  hostname
  date -Is

  echo '=== ALLOWLISTED_REPORT_STATUS ==='
  REPORTER="$HOME/.local/share/v79-workforce-operations/bin/v79_workforce_briefing.py"
  if test -f "$REPORTER"; then
    python3 -B "$REPORTER" status |
      grep -E '^(WORKFORCE_BRIEFINGS_COUNT=|REPORT=|WORKFORCE_STATUS=)' || true
  else
    echo 'REPORTER=UNAVAILABLE'
  fi

  echo '=== SCHEDULED_TIMERS ==='
  systemctl --user list-timers --all --no-pager |
    grep -E 'v79-workforce|v79-g2-approved-task' || true

  echo '=== G2_TASK_WORKER_STATE ==='
  for unit in v79-g2-approved-task-worker.timer v79-g2-approved-task-worker.service; do
    printf 'UNIT=%s\n' "$unit"
    systemctl --user show "$unit" \
      -p LoadState -p ActiveState -p Result -p ExecMainStatus \
      --no-pager 2>/dev/null || echo 'UNIT_UNAVAILABLE'
  done

  echo '=== G2_UNCERTAINTY_LATCH ==='
  if test -e "$HOME/.local/share/v79-approved-task-worker/uncertain.json"; then
    echo 'TASK_WORKER_UNCERTAIN=YES_RECONCILE_NO_RETRY'
  else
    echo 'TASK_WORKER_UNCERTAIN=NOT_OBSERVED'
  fi
)
\`\`\`

This is a **triage snapshot, not final acceptance**: a timer being active does not prove successful execution, status \`AVAILABLE\` alone does not prove complete authentic app evidence, and absence of an uncertainty latch does not demonstrate approval/denial/audit pass. After reading results, use independent source-timestamp, G2 ledger, task-row, and supervisor MFA verification before any owner GO.
