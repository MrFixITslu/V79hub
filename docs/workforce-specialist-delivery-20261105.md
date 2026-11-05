# Specialist task delivery candidate

Existing G2 task creation leaves an open COO task. This candidate adds a separate exact owner-approved specialist advisory review, one-at-a-time local model execution, a durable result, and fresh-MFA acceptance of that advisory result as the linked task deliverable. It does not implement engineering changes, independently attest security, deploy software, send messages or execute uploaded packages.

## Three approaches and red team
Rebuilding loses working services; deploying all drafts mixes unrelated changes. Selected: a bounded extension on the exact running Skill Package branch. Task creation, model draft and accepted delivery stay separate. Approvals bind task content hash, selected role and protected skill pin. Custom advisory skills are not silently included. No automatically accepted results, automatic replay or timeout-based claim stealing. Failed/interrupted reviews leave tasks open. Owner can reconcile an interrupted advisory review after the bounded model timeout, then propose a new attempt with new approval.

## Runtime
Default off: `V79_WORKFORCE_SPECIALIST_REVIEWS_ENABLED=1` is necessary in the Hub. Paired updated Hub and Business Agent required. No database migration or dependency changes. Host oneshot/timer templates are in scripts/v79-specialist-review.{service,timer}; they invoke the worker inside the Hub and reuse existing protected credentials without exposing them to systemd arguments. One result per invocation; new model work defers during high host I/O pressure. Existing G2 creation timer and morning/evening report collectors are unchanged.

Hub -> Owner Assistant -> Tasks & approvals -> Task delivery -> select specialist -> Queue specialist review -> Approve exact action with fresh MFA -> scheduled worker saves draft -> owner reads result -> Accept advisory review as task deliverable with fresh MFA. Existing tasks are not automatically converted or accepted.

## Validation and release
Focused lifecycle, HTTP, role-model contract, existing approval regressions and Hub type/build checks performed locally. Nondeploying CI adds independent full type checks and synthetic desktop/tablet/mobile interactions and screenshots. Synthetic responses are not evidence of actual model quality. Real local-model acceptance, current encrypted off-host recovery, guarded paired image replacement and owner-MFA browser acceptance remain release gates. No production change is established by this document.

## Workforce completion remains broader
This review workflow alone does not close Sentinel signed incident-to-owner delivery, the Evidence Gateway, all product-specific specialist capabilities, actual engineering delivery, scheduled briefing notification delivery, or full recovery acceptance. These must be tracked separately and must not be labelled complete because this candidate passes.
