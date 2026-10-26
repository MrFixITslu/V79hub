# Vision79 v3 — approved visuals, guarded release preparation

Owner decision: **approved**, 26 October 2026, in the active review conversation.
Approved visual source: `114841271d4f8b9c4b63df6aedfd55bde2e82f40`.

The approved source includes the Hub, Owner Assistant and Platform Admin candidate shown in the review package. No application code has changed since that approval. `vision79-v3-approved-source.json` freezes 133 runtime files, including the frontend, backend, dependencies and build configuration. The approval is for the reviewed visuals; production operation is still subject to the following technical gates.

## Source acceptance

The historical release checks have been reconciled with the explicitly approved v3 design. Four legacy UI blob pins now identify the approved App, Sidebar, AdminConsole and HubOverview. Four additional pins cover OwnerAssistant, OwnerToday, PlatformAdminOverview and workspace.css. Prior visual-v1 pins remain recorded in the test file. Existing server, Login, trusted-metrics and security markers are unchanged.

The visual structure checks now inspect the approved semantic classes and stylesheet. Signed launch, authorization filtering, real API data, missing-data behavior, focus styles, responsive rules and reduced-motion checks remain. A new whole-runtime check rejects drift from the exact reviewed source.

This is a new approved source contract. It does not authorize reuse of the previous deployment's image, manifest, runtime settings or rollback identity.

## Verification

Full Node source suite: 664 tests — 659 passed, zero failures, five skipped. The five skips still require their integration environment and are not counted as production acceptance. The inventory helper passes five synthetic safety tests. The read-only source preflight reports owner visual approval as APPROVED and release status HOLD; all 133 pinned runtime files match. Existing browser evidence remains applicable because application bytes have not changed.

## Read-only server preflight

`scripts/vision79-v3-live-inventory.py --self-test` exercises synthetic safety cases without accessing Docker.

On `v79sl`, `--run` uses only `docker inspect` and `systemctl is-active`. It reports current container/image IDs, health, a nonsecret configuration-shape fingerprint, mount destinations, network names, Compose-stack label fingerprint and workforce timer states. It never outputs environment values, command arguments, host mount sources, raw labels or health logs. It does not build, pull, stop, start, rename, remove or modify containers, volumes, services or timers.

The inventory is not a full runtime parity check or a sealed release plan. Private full configuration must still be compared by the guarded transaction before any switch. No recovery checkpoint or MFA/SSO acceptance is claimed by the inventory.

Direct server inspection is currently blocked because the remote-control service previously returned a monthly-usage-limit rejection and instructed the assistant not to retry. An operator must run the pinned read-only preflight from the Acer and return its sanitized output. The local work environment has no Docker or Podman, so no candidate container image is claimed built here.

## Release sequence

1. Collect and review the current server inventory. Preserve the observed Hub image as the prospective rollback identity; do not assume a historical image remains current.
2. Obtain the current private runtime/Compose contract and verify a fresh encrypted offhost recovery checkpoint against the observed image/data baseline.
3. Build an immutable Hub image from a clean, pinned Git checkout/archive. Do not build from a developer directory containing ignored review artifacts. Record resolved build-base digests and the resulting image ID.
4. Rehearse isolated boot, configuration parity and rollback. Preserve existing database and app images; no migrations belong in this UI release.
5. Complete genuine private-session MFA, session expiry/renewal and Hub-to-Tiquet SSO acceptance. The existing local synthetic tests are not production acceptance evidence.
6. Seal a guarded Hub-only cutover with the exact prior and candidate image/config identities, checkpoint and rollback command. Issue the exact deployment command only after all preceding gates pass.

Production status: **UNCHANGED / NOT DEPLOYED**. Release decision: **HOLD pending current server and recovery/runtime evidence**. Visual approval is complete and must not be requested again unless the visuals change.

## Rollback

No production rollback command is guessed from the earlier visual deployment. That script pins a different source, image, container identity and checkpoint. The final rollback command must come from the new sealed transaction and restore the newly observed prior image with its exact runtime configuration.

The approved application source is unchanged by this release-preparation commit; reverting this preparation would only remove its release records, test-pin reconciliation and read-only inventory helper.
