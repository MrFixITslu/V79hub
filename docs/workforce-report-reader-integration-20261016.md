# Workforce report reader integration

Source candidate only; not mounted in server.ts, not deployed, no new scheduler.

## Selected design and red-team
Retain verified host systemd 08:00/19:00 Saint Lucia briefings. Replacing them or also starting the Node scheduler risks duplicate reports. Add a disabled-by-default owner-MFA GET reader instead. It rejects mutations before reading, uses no-store, preserves unavailable/stale states and suppresses internal errors. No action queue or execution API is invoked.

`createOwnerBriefingReader` requires the existing authoritative owner-MFA context function, a separate opt-in access flag, and a validated status reader. It must never receive raw JSON read directly from disk. The Node briefing store schema is not established as compatible with the installed Python runner.

## Exact owner evidence, 16 October
Host runner recorded the evening slot at 23:00 UTC with AVAILABLE coverage and five reported findings. Next morning timer is 17 October 12:00 UTC. This proves report generation, not email delivery, specialist completeness, or AI execution.
Hub image: sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06
Agent image: sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f
Tiquet image: sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42
All reported healthy. Nine ordered Hub Compose inputs must be preserved.

## Remaining integration requirements
Inspect the installed Python report schema and private filesystem ownership without disclosing secrets. Implement and test a read-only adapter into validated report DTOs; do not start the Node scheduler. Plan a narrow read-only mount or atomic sanitized export without exposing the runner's credentials. Mount the owner reader only after resolving the recorded server.ts integration hold. Add the Hub history panel and authenticated staged acceptance tests. Preserve the exact nine-file Compose baseline, immutable images and tested rollback. No live release is claimed by these unit tests.
