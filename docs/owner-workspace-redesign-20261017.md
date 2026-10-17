# Owner workspace redesign

The former Owner Assistant stacked seven panels above the conversation. Tasks, planning approvals and evidence were difficult to find; a successful create_work_item receipt looked like completed engineering work, and old approval expiries remained visible after success.

The workspace now has Agents, Tasks & approvals, Delivery board, Briefings and More tools navigation. Agent prompts are editable starting points for the existing assistant route, not claims of newly independent agents. Chat requests and confirmed GitHub workboard items can prefill a task; no mutation occurs until the owner explicitly queues it. The task form stays open in the task view, drafts survive navigation, release operations are under Advanced, and the queue has approval/active/history filters and title/app search. Exact approval confirmations and existing server MFA/revision/digest checks remain.

While the task view is active and the page is visible, read-only status refresh runs every 15 seconds. Leaving the view stops polling. No poll queues, approves or executes anything. A failed read clears private queue data and disables mutation controls; older successful responses cannot restore it. Lost proposal responses reuse the same idempotency key when explicitly retried with identical content. Task text whitespace is normalized to the server's one-line plain-text contract before saving; approval always reviews the saved exact scope.

Succeeded task creation is labelled Work item created, with explicit separation from completing the underlying assignment. Expiry warnings apply to awaiting execution rather than old successful jobs. Uncertain results require operator reconciliation. Worker health is not inferred from approval or queue access; manual execution is secondary and clearly identified.

## Verification

25 focused UI, workboard, briefing-history, queue and HTTP authorization tests passed; TypeScript check and production Vite build passed. Three rollout guard tests cover allowed image-only changes and rejection of environment, mount, network, other-service and runtime configuration drift. A local Chromium download was unavailable, so rendered desktop/mobile browser acceptance remains outstanding; DOM workflow tests are not a visual inspection.

## UI-only rollout

scripts/workforce-owner-workspace-update.py pins UI source b1c2a24e903509d4037d0166bc31813fcf25e228 and builds from the exact currently accepted Hub image 4a9f5868...cec1698 without network access during build. It copies only the three UI components and the new DOM test, preserving the existing backend and dependency tree. Provenance labels explicitly identify a mixed UI overlay, not an entire repository revision suitable for an automatic release manifest.

The operator verifies the 12 current ordered Compose inputs, current image/health, declared environment/process/ports/mounts, candidate configuration image-only diff and exact rollback configuration. It runs isolated UI/approval tests before replacing Hub. The supervised task timer is briefly stopped and its service allowed to finish before restart to prevent an in-flight task POST being interrupted. It resumes only after a healthy update or verified rollback and no uncertainty latch. Agent/Tiquet identities and health are rechecked. Reports, workboard flags, credentials and mounts are preserved.

Execution requires the owner to run the checksum-pinned script on v79sl. Source publication and local checks do not establish deployment. After a successful update, refresh Owner Assistant and check the five navigation items, task prefill/review, and phone layout. The scheduled-worker acceptance test and Sentinel monitoring/security work remain separate outstanding checks.
