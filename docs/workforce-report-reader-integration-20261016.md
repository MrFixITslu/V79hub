# Workforce report reader integration

Integrated source candidate; disabled by default, not deployed, no new scheduler.

## Selected design and red-team
Retain verified host systemd 08:00/19:00 Saint Lucia briefings. Replacing them or also starting the Node scheduler risks duplicate reports. Add a disabled-by-default owner-MFA GET reader instead. It rejects mutations before reading, uses no-store, preserves unavailable/stale states and suppresses internal errors. No action queue or execution API is invoked.

`createOwnerBriefingReader` requires the existing authoritative owner-MFA context function, a separate opt-in access flag, and a validated status reader. It must never receive raw JSON read directly from disk. The Node briefing store schema is not established as compatible with the installed Python runner.

## Exact owner evidence, 16 October
Host runner recorded the evening slot at 23:00 UTC with AVAILABLE coverage and five reported findings. Next morning timer is 17 October 12:00 UTC. This proves report generation, not email delivery, specialist completeness, or AI execution.
Hub image: sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06
Agent image: sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f
Tiquet image: sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42
All reported healthy. Nine ordered Hub Compose inputs must be preserved.

## Implemented candidate integration
The actual Python state `recorded` is mapped explicitly using separate evidence coverage. Owner ran the pinned adapter on private copies of two real reports: report_available, count 2; eight reader tests passed on Acer.

Hub mounts `/api/agent/workforce-briefings` using the existing `ownerApprovalContext`. The opt-in flag `V79_WORKFORCE_REPORTS_ENABLED` must equal `1`. All mutation methods are rejected. The only filesystem source is `/run/v79-workforce-reports`; no user-supplied paths, browser context, agent credentials or scheduler are accepted. Owner Assistant includes the request-loaded history panel. This source change does not grant production release clearance or claim independent security assessment.

`deploy/workforce-reports.overlay.example.yml` requires an explicit immutable candidate image and existing host report path, defaults access off, mounts only reports read-only and refuses to create a missing host directory. It must be appended to all existing ordered Compose inputs, never replace them. Do not mount the entire operations folder: it includes scripts and may contain credentials.

Validation: 30 focused tests including private-file HTTP acceptance, denied anonymous/disabled/mutation requests, UI error clearing, real-format read-only mapping; TypeScript lint and production build passed locally. Browser DOM tests use synthetic identities and do not establish live owner-MFA acceptance.

## Remaining release requirements
Verify live report timestamps/permissions and image/source parity against the candidate base. Confirm effective UID can read the narrow mount without broadening file permissions. Build immutable candidate image and rehearse on isolated synthetic data, including the real Hub owner-MFA session guard. Preserve exact nine-file Compose configuration, encrypted recovery and original immutable rollback. Obtain authenticated desktop/mobile acceptance. No production replacement, worker activation or token provisioning has occurred.
