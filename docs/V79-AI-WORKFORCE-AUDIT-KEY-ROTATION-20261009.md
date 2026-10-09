# V79 AI Workforce — Approval audit key rotation and off-store anchoring

**9 October 2026 · NON-PRODUCTION DEVELOPMENT DESIGN · PR #103 · RELEASE HOLD**

The approval audit's HMAC-SHA256 chain validates the integrity of decision-only proposal metadata *within* Hub's database. Original event metadata and proposal snapshots live in the same mutable store. The HMAC key is supplied by `V79_AGENT_AUDIT_HMAC_KEY`, falling back to an existing stable Hub security/platform key for compatibility. **Changing that configured key without migrating and re-verifying all historic events would make the inbox fail closed**. The chain is not an immutable or externally anchored audit service.

## Implemented pure, non-executing migration primitive

`prepareAgentApprovalAuditKeyRotation({ events, proposals, oldKey, newKey })` in `server/agent-approval-audit-chain.mjs`:

1. Requires separate non-empty string keys with at least 32 characters. Rejects identical or missing keys.
2. **Before making a copy**, verifies the entire original HMAC chain **and** the chain's event-to-proposal snapshot linkage using the old key. Altered events, truncated decisions, missing proposals, changed revisions or execution state fail closed.
3. Creates a new **in-memory** event array preserving event ID, actor metadata, proposal ID, decision, revision and timestamp. It recalculates only `previousMac` and `mac` under the new key; never deletes or truncates the original event array.
4. Verifies the replacement HMAC chain with the new key and links it back to the *same* unchanged proposal snapshots.
5. Returns the replacement event array and small `previousCheckpoint` / `replacementCheckpoint` objects. It does **not** return either key, touch a file/database/network, change secrets, issue proposals or dispatch an action.

Negative tests check wrong old key, identical/weak new key, mismatched proposal status, edited event, deleted history, and source array integrity after successful or failed rotation. Empty history is supported, but both genesis checkpoints are identical and thus cannot prove the owner changed the key; an empty-history rotation needs an independently recorded key epoch.

## Required protected staging protocol — NOT EXECUTED

1. **Owner-controlled change window:** take a protected backup of the existing Hub state and its exact running revision, signing key identity and release image. Confirm the backup independently restores; do not publish it to a CI artifact or chat.
2. **Quiesce decision writes** on every instance before migration. If multiple Hub writers are active, reject/disable them; a per-process promise queue is **not** a distributed maintenance lock.
3. Export only the necessary proposal records and keyed decision events from a protected staging copy. Verify against the current key, including the event-to-proposal linkage. Record `previousCheckpoint` in an **independent write-once location** before making a replacement.
4. Generate an entirely new, distinct signing key using an approved secret manager. Never commit, print, email or expose it in logs. Use the **pure helper in a protected offline process**; verify the returned replacement with the newly configured key.
5. Record `replacementCheckpoint` independently with a key-epoch designation and operator-approved rotation record. Chain re-signing resets the signed head and **does not prove continuity without independent preservation of the old checkpoint and rotation record**.
6. In a separate approved deployment change, atomically replace only the dedicated `agentProposalAuditTrail` within an isolated revision-checked store transaction and switch `V79_AGENT_AUDIT_HMAC_KEY` as a coordinated cutover. A failed CAS, failed external anchor or mismatch must abort the migration; do not silently replace an existing history.
7. Restart cleanly in staging, verify MFA founder access, proposal list and decision-only operation, and check both post-migration linkage and external anchors. Simulate restart, stale replica and tampered metadata.
8. Roll back by restoring **both matching state and matching signing key** from the protected recovery set. Do not attempt to use an old key with newly re-signed events or vice versa.

**Absent today:** No runtime migration endpoint, secret manager, distributed writer quiescing control, atomic state/key transaction, off-store write-once retention, key epoch manifest or founder rollout approval. This deliberately leaves production unchanged. It is **not safe** to perform manual live rotation using only this helper.

## Evidence expiration: independently signed source previews

The separate source-signed Tiquet GET now carries `expiresAt` from the already verified signed envelope (no raw tenant/request ID or signature). Verification checks the clock again after the response arrives. The founder preview discards displayed figures at the signed expiry and explicitly asks for another read; a stale value must never remain labelled as currently verified. This does **not** feed the agent planner or upgrade `proxy_attested` approvals to independently source-signed evidence.

## Release blockers

- Independently retained and access-controlled audit checkpoint + documented key epochs.
- Full protected two-application Hub + Tiquet MFA and browser visual staging (existing full-joint launch was blocked; not executed).
- Credible outbound-write detection, durable source-side key escrow/rotation, and crash/restart verification.
- A final named SHA release candidate, successful exact-head CI, founder release approval, and no automatic merge/deploy before those gates.

**Safety:** No live secrets, customer records, production state, backup payloads, runtime write-enable switches, billing or messaging changes are made by this document or the pure helper.
