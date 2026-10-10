# Sentinel reconciliation with intentional runtime baseline — 2026-10-10 UTC

This document supersedes the release baseline and operational identities in the
earlier Sentinel receipts. Those receipts remain historical evidence for 05942fa.
The user confirmed that the observed live Hub replacement was intentional.

## Integrated baseline

- Intentional source baseline: fab2f1a08f459a389f938d66bd9156e33671bf4e,
  from /home/firelion/v79hub-main-clean-20261009 on v79sl.
- Sentinel predecessor: 05942fa8d911f807ced90c3485e938e349c364e1,
  continued from staging 6f21a8d.
- New isolated Acer checkout: /home/firelion/V79-Sentinel/hub-runtime-integration.
- Branch: feat/sentinel-runtime-fab2f1a-20261009.
- Newer agent approval ledger, keyed audit chain, supervised Marketing/Tiquet
  and Ollama prewarm work remain intact. No dependency or schema migration.
- The merge excludes five obsolete Stage3A files absent from the intentional
  baseline and unmodified by Sentinel. Sentinel adds only its reviewed changes.

A read-only inventory compared 220 tracked baseline files with /opt/v79/hub.
There were no missing tracked files or unknown code files. Exactly four deployed
operational files differ from the source baseline and must remain preserved:
agent-service/src/index.ts, agent-service/src/model-runtime.ts,
docker-compose.yml, scripts/deploy-server.sh.

Do not copy the whole candidate source tree over /opt/v79/hub or replace the agent.
Build a pinned Hub-only image from the immutable candidate and validate overrides
against the actual live Compose configuration. Keep DB and agent running.
The old 05942fa image and rollback overrides are historical and must not be applied.

## New-base integration coverage

Full-Hub tests now seed one unrelated, nonempty agent proposal and a valid keyed
audit chain using the actual current modules. They verify MFA-protected operator
inbox/checkpoint access and reject synthetic accounts. Exact proposal, audit
chain and checkpoint equality survive Sentinel creation, deletion and restart.

Both a proposal organization reference and an audit actor reference to Sentinel
block preview and deletion, preserving the contaminated durable snapshot exactly.
Actual PostgreSQL row-lock contention confirms all three current agent POST paths
return 423 before side effects, while the read-only checkpoint remains available.

Existing full-Hub auth/MFA, replay denial, exact deletion, synthetic session
revocation, unrelated account/session preservation and disconnected upstream
provisioning tests remain in both JSON and disposable PostgreSQL 17.11 runs.
All credentials and records are generated; no live customer data enters fixtures.

## Operational status

Implementation verification does not authorize cutover while operational gates
fail. Live reminders remain enabled with leader=1. Genuine operator MFA remains
mandatory; no bypass, password reset or enrollment replacement is permitted.
Both live Sentinel flags remain disabled. No live account mutation, external
provisioning, live flag change, restart or deployment was performed by this work.

The current observed runtime image is
sha256:13d8f9d87640fa3ade87ab73a514e099a91554887d8a6b4aa3f41ce29ed7705d,
started 2026-10-10T00:21:36.345449835Z.
Its server.ts SHA256 matches fab2f1a:
60773b8b1ddfbadf782aa3e1ce9013016e067140afdaa14d90e8fea68caf6586.
Recheck identity/configuration drift before any maintenance. Preserve all
operational overrides, secrets, mounts, latest database state and sessions.
Never restore an older database automatically over new activity.

## Verification results

- Complete integrated suite: 254 passed, zero failures or skips; 90.55 seconds.
- Actual full Hub auth/MFA/lifecycle passed on generated JSON and PostgreSQL
  17.11 fixtures, including nonempty proposal/HMAC preservation.
- Independent-process agent approval PostgreSQL CAS races passed against a
  separately initialized loopback-only CI database, never the live Hub database.
- TypeScript lint, production build and whitespace checks passed. Existing
  bundle-size advisory remains.
- Suite log: /tmp/v79-sentinel-rebaseline-final-20261010.log.
- Lint/build logs: /tmp/v79-sentinel-rebaseline-lint-20261010.log and
  /tmp/v79-sentinel-rebaseline-build-20261010.log.
- Disposable fixture processes/directories were removed; temporary unpacked
  PostgreSQL runtime removed after the final suite.
- Independent working-tree review: 50 Sentinel/agent pure and HTTP tests passed
  with zero skips/failures; new-base fixture extensions reviewed without findings.
  Immutable commit sign-off and image validation are recorded separately.
