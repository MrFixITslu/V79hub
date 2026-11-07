# V79 Skill Library management (7 November 2026)

## Current workflow and planned improvement
The Hub menu is **AI Workforce → Skill Library**; there is no separate Skills Manager page. Within the same page:
- **Your custom skills**: select a record and edit its Markdown; check, save a new immutable draft, then activate the exact version with fresh MFA. The editor uses the backend's 32,000-byte limit (not the stale 6 KB client cap).
- **Protected built-ins**: read-only, with versioned improvement drafts, never overwritten.
- **ZIP skill packages**: download a sealed copy, edit files offline (never run unreviewed scripts), upload a **new quarantined version**, review its SHA-256, approve with fresh MFA, then explicitly **Promote**. Promotion atomically migrates allowed scheduled assignments and archives the previous version. Until promotion, the original package remains active.
- **Archive / remove**: reversible removal from the active library, clearing assigned guidance and revoking approval. Restoring keeps packages quarantined and text skills paused; no automatic reactivation. Do not permanently delete sealed files or audit history while restore/forensics may be needed.

## Three alternatives considered
1. Mutable in-place ZIP editing: **rejected** because changing bytes silently invalidates digest-pinned approvals and may expose unreviewed scripts to scheduled agents.
2. Delete and reupload: **rejected as the default** because it destroys provenance and can interrupt scheduled guidance during review.
3. Immutable staged replacement plus reversible archive: **selected**. Preserves hashes, histories, permissions and continuity, with explicit promote/revoke after SHA review and MFA.

## REDTEAM / release gate
- Founder only; same-origin on all writes, fresh MFA for approval, archive, unarchive, promotion and role assignment; compare-and-swap revision checks.
- No ZIP extraction or script execution on Hub. Download is owner-only and rechecks archive SHA and `O_NOFOLLOW` file integrity. No changed ZIP runs under an existing approval.
- On stage, original scheduled assignments are unchanged. Promotion only after exact replacement digest approval, and transfers schedules atomically under policy limits. Stage failures, stale revisions and bad files fail closed.
- Archive stops future scheduled snapshots and newly loaded worker assignments; an already in-flight job may finish using a prior immutable snapshot.
- No direct permanent deletion is offered: maintain HMAC-sealed audit and recoverability.
- Browser checks of the authenticated live UI, MFA refresh flow, reduced-width layout and production persistence are still required before merge or deployment.

## Status
Implemented on an isolated feature branch. Unit and route tests pass; static build passes. **Not approved, merged, deployed or browser-verified.**
