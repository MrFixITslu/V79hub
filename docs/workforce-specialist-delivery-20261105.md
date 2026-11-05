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

## Scoped evidence and model runtime
The internal agent review request includes the approved task's app. Only candidates from that app and the selected specialist's evidence scope are supplied as current facts; unavailable evidence stays unknown. The literal V79 brand is permitted in advice, while numeric claims and unsafe action/approval instructions remain rejected. Local structured output is followed by independent application validation; provider JSON-schema support is never treated as sufficient.

A dedicated `V79_SPECIALIST_REVIEW_MODEL` may select an installed local model. The response and saved result identify the actual model used. The proposed rollout uses the installed qwen2.5:3b model and a single loaded model to avoid observed cold-load memory contention. Review requests remain bounded; model failures leave tasks open and require a new owner-approved attempt.

## Paired release control
The guarded release tool pins the application source separately from release-tool documentation commits. It requires the fresh encrypted checkpoint SHA and an actual off-host PostgreSQL restore receipt. Stopped candidates must preserve the complete process configuration, mounts, host security, network membership, ports and restart policy, allowing only explicitly listed local-model/feature flags and source labels. Existing worker/report timers pause and drain before cutover, original containers remain available, and unrelated running container IDs/images must remain unchanged. Unit tests reject process, environment, MFA, capability, data-mount, port, network and source drift. No release is established by this runbook; use the actual deployment receipt and owner-MFA acceptance.
