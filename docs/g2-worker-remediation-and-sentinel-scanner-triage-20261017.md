# G2 remediation and Sentinel scanner triage

Owner instruction 16 October 2026: proceed until deployed, find gaps and fix them. This record distinguishes implemented source from operator-executed deployment.

## G2 source correction
Release-manifest Compose input bound raised from 5 to 16, enough for the verified current 12-file Hub stack. Ordered paths, exact hashes, duplicate rejection, image-only diffs and owner approval checks remain. Added a 12-layer acceptance and oversized/duplicate rejection regression. 14 focused queue/route/release tests passed locally. This Node worker source correction is staged, not falsely attributed to the current Hub image.

New separate Python task worker calls only the fixed HTTPS `execute-work-item` endpoint with an empty body and the existing separate worker credential. It cannot approve, queue arbitrary payloads, claim releases, access Docker, deploy or roll back. The Hub server still selects only exact owner-approved, unexpired create_work_item jobs and enforces pause and replay protections. HTTP redirects, oversized/malformed responses and unexpected operations reject. An unknown POST/receipt outcome writes a latch and all subsequent timer invocations stop without retry until operator reconciliation. Six local tests passed, including latch/no-retry behavior.

Operator installer is checksum-pinned, requires the verified live Hub image/health, private worker token, persistent user scheduling and no approved/running queue jobs before a first idle poll. It installs a 60-second user timer and leaves Hub/Agent/Tiquet containers unchanged. Timer activation and actual approved task creation remain unverified until owner executes the installer and performs a separately MFA-approved work-item check. Creating a COO task is not autonomous engineering implementation.

## Sentinel GitGuardian finding now retrieved
GitHub check-runs API exposed exact finding metadata without retrieving the detected value:
- Check 114653264225; incident 38116562; Generic Password.
- File deploy/docker/smoke-private-pilot.py, commit 6c84d54f985136c62e2df5b23fa955c7d20aff19, linked around line 39.
- Canonical PR #14 remains 5baceb1aad29694b002b8c122cc98b8da4f085e4.

AST review of the historical and current files shows the credential variable is read using PASSWORD.read_text().strip() from a protected password file. The nearby branch checks file mode and errors if it is not private. No hardcoded credential assignment was found at that location. This supports a **probable scanner false positive**, not a claim that GitGuardian has accepted a disposition. No password value was printed, no scanner was disabled, no exclusion added, no history rewritten, and no scan failure was relabelled as success.

The external GitGuardian incident still needs formal false-positive disposition or further finding evidence. The independent customer pre-launch review also remains open. This must not be concealed by source CI success or the already healthy private server stage.

## Remaining rollout work
Run task-worker installer and inspect first idle result/timer, then exercise one owner-approved harmless work item. Prepare a correctly revision-labelled candidate/validation image with readable non-root source and temporary writable build outputs before release-worker deployment. Reconcile and back up every active Sentinel collector worktree and server image; preserve current Acer observations. Review the scanner disposition, implement authenticated bounded genuine server observations with stale/fault/recovery semantics, test alerts without customer dispatch, then deploy the specific reviewed internal candidate with rollback. No new monitoring was enabled by these source changes.
