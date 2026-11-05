# Specialist task review — deployed with acceptance outstanding

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

## Observed deployment status, 5 November 2026

Application source c957a24020894f7160e0dd15853cf13c39d61c13 is deployed to Hub and Business Agent. The paired release journal records successful cutover, restored existing timers, retained rollback containers and unchanged protected services. The specialist review user timer is installed and active. Recovery ciphertext was independently restored on Acer in isolated PostgreSQL before cutover. These establish deployment and recovery evidence, not owner acceptance.

The actual deployed internal endpoint rejected unauthenticated calls with HTTP 401 and authenticated browser-origin calls with HTTP 403. Its first authorised read-only smoke request returned HTTP 503 after 93,477 ms. A subsequent source-level diagnostic also timed out. No task was accepted and no queue mutation was made by these probes. Earlier eight-role source/model checks passed, but do not establish deployed endpoint reliability under current host contention. The owner browser sign-in was interrupted; authenticated queue-to-draft-to-accept browser acceptance remains outstanding.

Current Sentinel monitor and NOC containers have no signing/alert/receiver configuration names or extra mounts. The staged Unix receiver package remains a prototype, not a production incident-delivery service. The wider workforce must remain labelled incomplete.

## Corrected deployed runtime acceptance

The agent-only follow-up application source 459c542fa37103fc8b97c3c26d6f67fc932e3602 is deployed. Specialist inference uses two threads and non-mapped model tensors. Agent prewarm and ordinary chat use the same configured context/thread/memory profile to avoid repeatedly reloading the shared local model. All twenty-one focused tests and the six agent-follow-up parity/security tests passed. GitHub run 42004026702 independently passed locked-dependency Hub/Agent type checks, Hub build, lifecycle/HTTP tests, role safety and synthetic browser acceptance. Local checkout-wide type checking was unavailable because its reused dependencies lacked the SDK packages; that local failure is not represented as a pass.

The actual deployed internal task-review endpoint subsequently returned HTTP 200, kind specialist-review-draft, model qwen2.5:3b, ownerAccepted false in 67,338 ms. This smoke request performed no queue mutation. A warmed source-level full review took 21.7 seconds. The slower deployed result shows that host load still affects latency; these are observed timings, not a service-level guarantee. The agent-only guarded cutover passed, retained its immediate rollback container, restored all four workforce timers and preserved unrelated services. Owner MFA queue-to-draft-to-accept acceptance and all previously listed broader workforce gaps remain outstanding.

## Specialist integration completion candidate

Owner reported completing queue → approve → receive draft → accept on 5 November 2026. This is owner-reported acceptance, separate from the earlier internal endpoint smoke. The next source change adds a shared, digest-pinned role/application manifest enforced both by Hub task validation and Agent review execution, scoped source reports for all eight protected roles, a private MFA-only integration report, and a Tools & reports panel. Hub member/session summary observations now retain timestamps and can appear as attributable owner-role facts. Sales/Finance/Support cannot gain unrelated app access by changing a task payload. Missing SLA, consent, currency, publication, security and launch evidence stays explicitly unknown.

Live baseline inspection on 5 November found fresh permitted aggregate sources for all eight roles, covering POS, FFPRO, Tiquet, Marketing, Academy, LaserTag, Website, Games and the local Hub summary where authorised. This does not establish detailed record access or external execution. Sentinel is deferred by the owner. The separate Evidence Gateway repository remains unavailable (GitHub 404); only its Phase-0 README was recovered. V79-MCP is a distinct repository and is not silently renamed or substituted.
