# Customer guided support — development record

Status: implemented and tested on the development branch. No merge, deployment, production access or configuration changes authorised for this iteration.

## Decision and scope

Customer Help becomes a guided support experience while preserving ordinary answers and topic browsing. Compared fixed issue scripts (narrow coverage), deterministic walkthroughs of reviewed articles (chosen: complete coverage without model dependency), and AI-written diagnostic trees (unnecessary inference and ungrounded instructions). Interface alternatives: a separate wizard hides the conversation; a floating drawer is cramped; an inline guide preserves the existing readable Help page (chosen).

Product/UX/engineering/security/QA perspectives are handled sequentially by the implementing agent. No independent reviewer is claimed. Existing V79 styling, spacing, theme and navigation remain authoritative. Additional Impeccable guidance was unavailable in this environment.

## Design and API contract

- Manual-backed answers offer an opt-in walkthrough: prerequisite, one instruction at a time, result check, then customer-reported solved/blocked outcomes. Back/retry/restart preserve source context. No automatic task execution.
- Common access, publishing and import problems ask one focused clarification question with reviewed article choices. Other unsupported operations retain the honest fallback.
- Optional screen context is a customer-selected reviewed article ID, never an arbitrary URL, screenshot, customer record or automatic screen capture. Explicit new app/task wins over prior context.
- Extend the existing authenticated, same-origin, no-store, rate-limited chat endpoint with strict `context: {articleId}` and `guide` objects. Guide actions are recomputed from the current article/version, not supplied instruction text. There is no server conversation state or new database.
- A support summary is an editable in-memory draft. Displayed steps are distinguished from completed steps. Transcript inclusion is opt-in; the customer reviews/copies before using the existing support contact or Tiquet instructions. No ticket/email submission or transcript logging.
- Session expiry, pending cancellation, errors, guide version changes, keyboard use and small screens must have clear states. New conversation and app changes clear the draft and contextual state.

## Red team

Risks: invented troubleshooting, stale manuals, context misleading retrieval, forged guide state, accidental repetition of payment/refund steps, private transcript sharing, implicit authority and cross-customer state. Controls: only reviewed wording; strict IDs/version/actions/index; explicit result confirmation; blocked state never retries an operation; no screenshot/record reading; source-preserving navigation; opt-in editable hand-off; obvious credential redaction plus a review warning; page-memory state only; unchanged active-session/membership and origin enforcement. Links point to Hub views or the existing support contact, and never grant app permissions.

## Acceptance / completion criteria

1. All 49 topics can be walked through with exact reviewed text and source references; prerequisite and result checks are not skipped by Next.
2. Ambiguous problems ask a useful question; unsupported actions remain unsupported; new tasks do not inherit unrelated instructions.
3. Wrong IDs, owner content, extra keys, invalid steps/actions and stale versions cannot produce invented instructions, tool calls or private access.
4. Support preparation performs no external write, excludes transcripts by default and clearly labels customer-reported outcomes.
5. Affected service/router/UI/full-Hub tests, TypeScript and build pass. Desktop/tablet/mobile/dark/keyboard and failure paths are inspected in an isolated synthetic Hub.
6. Tested source and evidence are committed to a separate development branch and draft PR. Nothing is deployed.

## Explicit limits

No live status integration, new language model connection, persistent preferences, analytics storage, automatic ticket creation, screenshots or media guides are included. These need separate verified sources or integration contracts. Existing customer-manual review/version controls remain in effect.


## Review and verification — 6 November 2026

| Requirement | Observed evidence |
|---|---|
| Reviewed instruction coverage | All 49 articles traverse prerequisite, each exact source step, final result check, customer-reported resolution and restart. |
| Guided state / privacy / resilience | Invalid state/identity fields, owner IDs, injection, cross-app context, unsupported operations, stale versions (including removed old steps), denied origins, rate/concurrency budgets, expiry and retry checked. No model request is made by guide navigation. |
| Consolidated automated checks | 64 focused service, guide, HTTP router, React DOM and full-Hub tests passed. Final affected UI regressions passed again after the visual/layout and screen-selection fixes. Previously passed unrelated suites were not repeated. |
| Real synthetic Hub | Separate customer/viewer identities can use guides without app entitlements. Revoked/suspended/anonymous sessions remain denied; owner endpoints remain forbidden. No production data or credentials used. |
| Browser | Desktop at 1363px; same-origin viewport frames at 320, 390, 768 and 1024px; no horizontal overflow at these inspected widths. Mobile guided steps and long routes, 768px dark theme and 1024px keyboard focus checked. These are viewport frames, not physical-device tests. |
| Support summary | In-browser expected/actual editing and copy confirmation verified. Preview removes a labelled synthetic password, excludes the transcript by default and labels displayed steps separately from completion. No ticket/email is sent. |
| Build | TypeScript check and Vite build pass. Existing large-bundle advisory remains; final main client asset is about 785 kB uncompressed / 210 kB gzip. No new dependency or migration. |
| Visual corrections | Removed related-topic chips during guides; scroll the current guide into view; hide repeated summary prose; use a full-width support draft; preserve matching screen selection when the app is inferred. |

Evidence screenshots are in `docs/review/guided-support/`. The dark-theme screenshot shows the ordinary article view preceding its guide; the final desktop screenshot shows the active guided step and retained screen selection. Browser-extension metadata errors were observed from `chrome-extension://...`; no application error was identified in the bounded final console sample. This is a sequential self-review, not an independent security assessment, screen-reader audit or field-performance measurement.

Source baseline: local tree `113cdbad8520b98e7a5a2e14d5de3f9b029a9eaf` exactly matches draft PR #227 head `6ffd8545c1203481f7dd8ec15f8a506fb36aaf9b`. This iteration targets that branch to keep its incremental diff focused. A future release must reconcile against the then-current production source and rerun applicable release checks. No deployment script, merge, image build or production change was run.
