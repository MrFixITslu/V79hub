# Sales review: isolated scheduled-guidance slot

## Options considered
1. Reassign Sales & Outreach to Marketing Review — rejected: its two slots are full, and sales communications need distinct approval/accountability.
2. Put the Sales ZIP into COO Daily — rejected: mixes commercial and operating instructions and weakens auditability.
3. Add Sales Review as an explicit fifth allowed ZIP guidance profile — selected. Keep the existing Sales custom text worker role separate.

## /REDTEAM before implementation
- Capability inflation: Sales Review does not schedule a new agent. No runner is authorised or wired by this UI.
- Communication risk: ZIP advice cannot send messages, change CRM contacts, make commercial offers, spend money or bypass consent/approval. The existing MFA requirement still gates package approval and configuration.
- Over-assignment: still a maximum of two approved packages per job, independently enforced server-side.
- Untrusted ZIP: digest-pinned archive only, no extraction/execution in Hub; worker token remains required to read scheduled guidance.
- Data and revision safety: existing schedules are unchanged by software deployment; owner must explicitly approve any new assignment.
- Regression/rollback: copy only the two matched files into a candidate built from the exact running image; preserve last image and the package registry.

## Scope
- Backend expands the fixed allowlist only to include sales-review in package scheduling and token-protected snapshots.
- Frontend exposes one Sales review (approved guidance only) option, with an explicit reminder that an actual scheduled task does not yet exist.
- Existing HMAC, CAS revisions, owner-only configuration, fresh MFA, integrity and two-slot limit are unchanged.
- No Sales skill ZIP has been uploaded as of the last read-only registry inventory. The existing Sales — My improvements text skill is an inactive draft; owner must validate and activate it separately using Hub's MFA flow.

## Release verification
- Seven focused tests PASS, covering Sales Review scheduling, max-two limit, unchanged CEO/COO/Technology/Marketing snapshots, fresh owner MFA, same-origin protection, trusted worker token and read-only guidance.
- TypeScript noEmit PASS; production Vite build PASS.
- Current live JavaScript, CSS and index baseline reproduced byte-for-byte from isolated source before applying the Sales UI change.
- Synthetic owner desktop and mobile browser tests PASS, including Sales Review checkbox interaction, visible warning about absent runner and zero client JavaScript errors.
- Guarded production release and authenticated owner acceptance to be recorded separately.
