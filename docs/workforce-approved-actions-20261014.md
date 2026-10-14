# V79 workforce: owner-approved actions (G2)

Owner directive, 14 October 2026: enhance the existing CEO/COO team from
read-only to taking action with owner approval; test and deploy so workers can
continue building and managing Hub and apps. This authorizes implementation and
an internal deployment when the exact candidate and recovery checks pass.

## Delivered source and scope

The existing CEO/COO evidence, briefing and decision-only proposal ledger stay
compatible. G2 adds a separate execution queue under Owner Assistant → V79 team
→ Approved actions. Each immutable request specifies operation, app, summary,
payload and idempotency key. A fresh founder MFA session approves its SHA-256
digest and revision. Approval does not grant a role permission or unrestricted
future autonomy. The CEO and COO cannot approve actions.

Supported actions:

| Action | Actual effect after exact owner approval |
| --- | --- |
| `create_work_item` | Persist an engineering task, assigned to COO, in the separate signed ledger. An authenticated worker or the owner can execute it once. |
| `validate_release` | Run selected `npm run lint`, `test`, `build` scripts from an operator-prepared immutable validation image in network-none, non-root, read-only containers with no host mounts or secrets. |
| `deploy_release` | Recreate only the allowlisted application services with exact approved images. Requires successful validation for the same app, commit and manifest, plus current restore/rollback evidence. |
| `rollback_release` | Restore the exact original immutable images and original pinned Compose file list after an attempted deployment. Requires a separate owner approval. |

This is an execution foundation, not an autonomous coding implementation. A
developer/engineering worker still prepares code, tests and immutable images.
No generic shell, arbitrary command, repository-script execution on the host,
automatic payments, messages, customer deletion or unrestricted app-data
mutation is provided. Existing Marketing draft handoff remains separate. App
container names must be confirmed from inventory; registry entries are not
proof that every app is already connected or deployable.

## Authorization and failure behavior

- Owner identity uses the existing exact founder user, email, organization and
  active owner membership. Mutations require same-origin and MFA within five
  minutes. Re-login with MFA refreshes this window.
- Task/check approvals expire in 60 minutes; deploy/rollback in 15 minutes.
  Requests expire for review in 24 hours. Any payload change needs a new request.
- A separate `V79_WORKFORCE_TOKEN_FILE` credential authenticates the worker.
  The existing Business Agent token does not allow execution. Worker endpoints
  reject browser cookies and Origin headers; workers can propose but not approve.
- Pause prevents new claims, work-item execution and subsequent dispatch
  authorization checks. It cannot undo a command already accepted by Docker.
- Running jobs are never reclaimed on a timeout. A lost process, lost receipt
  or partial deployment needs runtime inspection and owner-approved recovery.
  No retry, rollback or success is inferred from a missing receipt.
- PostgreSQL uses a separate `workforce-actions-v1` store row and `FOR UPDATE`
  transaction. JSON mode uses an exclusive, non-expiring directory lock, atomic
  rename and fsync. A stale JSON lock requires operator reconciliation.
- A dedicated `V79_WORKFORCE_AUDIT_KEY` seals the entire persisted queue,
  payloads, approval identities, tasks, event history and receipts. This detects
  edits without the key, but does not provide independent immutable audit
  retention against an administrator who holds the key. Include this key and
  ledger in encrypted backup/restore and the separate key-custody process.
- The queue is bounded at 2,000 actions/tasks and 16,000 audit events; capacity
  fails closed. The UI shows the latest 200 jobs; historical evidence remains
  in the signed store.

## Worker placement and release manifests

Keep `scripts/workforce-release-worker.mjs` as an operator-managed program on
the deployment host. Do not mount the Docker socket, host credentials or worker
token into the Business Agent or an untrusted candidate test container. Invoke
the worker once per poll (for example an operator-installed systemd timer).
Only the operator-owned worker gets Docker privileges. No timer is installed by
the source change.

Worker environment (values stay outside GitHub/chat):

```
V79_WORKFORCE_HUB_URL=https://hub.v79sl.com
V79_WORKFORCE_TOKEN_FILE=<protected separate token file>
V79_WORKFORCE_MANIFEST_DIR=<protected reviewed manifests directory>
V79_WORKFORCE_RECEIPT_DIR=<protected receipt directory>
V79_WORKFORCE_SYSTEMS=hub,tiquet
```

The manifest filename is the SHA-256 of its exact JSON bytes plus `.json`.
Manifest/config/recovery files must be protected regular files, not symlinks or
group/world-writable files. The owner reviews the manifest before approving its
hash; the worker must not prepare and approve its own deployment scope.

Manifest fields: `version:1`, `system`, exact `commitSha`, `project`, immutable
`validationImage` (`sha256:…`), `validationScripts`, `services`, `compose`,
`releaseOverlay`, `backupReceipt`. Each `services` entry includes `container`,
`service`, `expectedImage`, `targetImage`, `rollbackImage` (equal to expected).
Each file reference includes absolute `path` and SHA-256 `sha256`.

The validation image and target application images must carry the exact
`org.opencontainers.image.revision` commit label. The validation image is
prepared with dependencies already present and supports tests without a network
or writable source tree. Build commands that need writable artifacts must use
an explicitly supported temporary path inside `/tmp`; the worker deliberately
does not relax its sandbox to make an incompatible project pass.

All original Compose files must already pin the baseline images by ID. Effective
configuration before/after must differ only in approved application image
fields. Environment, ports, volume mounts, commands, credentials, networks and
WiPay configuration cannot change through a release action. The original live
Compose labels must exactly match the manifest file list. This intentionally
refuses legacy/unpinned configs until a separately reviewed operator migration.

The recovery receipt is operator-reviewed, file-hash-bound evidence containing
`restoreVerified:true`, `rollbackVerified:true`, `capturedAt` within 24 hours and
`runtimeImages` matching each exact baseline application image. Merely setting
these fields is not verification: attach actual isolated restore and rollback
test evidence. Current G1.2 decryption results alone do not satisfy this gate.

The worker starts only approved application services with Compose `up --no-deps
--no-build --pull never --force-recreate --wait`; it does not replace database
services or synchronize source/config files. It verifies final exact image and
health status. A failure after recreation starts is reported `uncertain` and
needs inspection. Receipt files contain only bounded runtime results and their
hash is persisted; raw Docker stderr, test logs and resolved Compose secrets are
not uploaded to the Hub.

## Internal deployment sequence

1. Review this branch and run CI, the actual disposable Hub/Agent owner-MFA
   integration, action/worker tests and isolated PostgreSQL races.
2. Run `scripts/workforce-runtime-inventory.py` read-only on `v79sl`. Prepare a
   pinned-overlay-preserving upgrade from that current inventory; do not run the
   generic deployment script against a pinned WiPay runtime.
3. Back up current Hub/Agent configuration, source, exact rollback images, data
   and database, then prove isolated restore and exact rollback. Protect current
   WiPay overlay and existing users. Decryption-only evidence remains explicitly
   separate from restore/rollback proof.
4. Deploy the reviewed Hub source/images with the new G2 configuration using
   the controlled operator cutover. Add dedicated audit key and worker secret
   mount without exposing secret values. Start with
   `V79_WORKFORCE_ACTIONS_ENABLED=0`; verify owner-only queue and normal Hub/SSO.
5. Enable the exact reviewed G2 release for the internal owner workspace only.
   Supervise one task request: pending → exact approval → worker execution →
   persisted task. Verify replay denial, pause, rejection and MFA expiration.
6. Prepare one real, immutable, resource-bounded validation image and reviewed
   manifest; approve its check job. Only after actual checks succeed approve a
   deployment job for the same manifest, then verify app health/SSO and record
   receipts. Install the worker polling timer only after supervised acceptance.

Direct server execution is currently unavailable because Desktop Commander has
reached its monthly usage limit. No G2 live deployment or feature activation is
claimed by this source change. No commercial-launch claim is implied.
