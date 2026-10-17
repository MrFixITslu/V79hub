# V79 workforce read-only reporting: isolated first deployment

**Date:** 2026-10-16 · **Owner scope:** V79 Digital founder · **Status:** Owner-run deployment package prepared; no live execution yet.

## Reconciled live baseline
Founder read-only fingerprint confirmed Hub running the G3 tracked source (Hub image `sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06`), Agent G3 shared source (`sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f`), and Tiquet (`sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42`). All HEALTHY, prior source audit was READ_ONLY. Hub admin MFA ON, G2 owner-approved actions ON, Marketing production ON, COO workboard missing, executive model OFF, automatic briefings OFF. Ollama READY, 4190 MiB memory and 226.2 GiB root disk free. Do not confuse HTTP 401 anonymous denial with route existence.

## Selected path / REDTEAM
- Reject broad activation of absent code or wholesale merge of #155/#151/#154: risks recently restored MFA, current Hub WiPay/price runtime and Tiquet SSO.
- Reject new separate privileged autonomous AI: duplicates G2 approvals, increases attack and memory burden.
- **Chosen:** install separate owner-private read-only evidence runner, using Hub's already configured token and internal Agent handoff. No Hub/Agent/Tiquet recreations, credentials exported, database mutations, payments, external customer actions or worker approvals.

## Generated operator artifact, pending founder execution
`V79_AI_Workforce_Ops_Deploy_v1_20261016.zip`, SHA256 `d3b9becead274ddb69c8b862a2ae39d3967da8791732bccb0bd18bbe083594ee`.
- `install_v79_workforce_ops_from_acer.sh`, SHA256 `12cb495c9d64c3a37afded760f8f888db83bcb79d40575ff52dad5bedcf00e93`
- `v79_workforce_briefing.py`, SHA256 `437e590660f3836b1b45f583ba421368b3abd655a999be72de21a46947f465d4`
- `test_workforce_briefing.py`, SHA256 `fe628a6bb1fcfe43f0780265207757696ce8fb8e5c96b7c702840b9062bfd742`

Local checks completed: archive byte-for-byte readback, Python compile, Bash -n, systemd calendar validation (12UTC = 08 AST; 23UTC = 19 AST), and six local tests (owner report sanitization, stale data rejection, injection rejection, action claims rejection, private persistence and idempotency). No integration run on live.

Installer checks exact current Hub/Agent/Tiquet image IDs and health before any copy. Copies Python script to protected owner home, runs a **read-only agent probe** before enabling two user-systemd timers. If persistent user systemd is absent or lingering disabled, prints UNAVAILABLE/UNVERIFIED rather than claiming scheduled. Reports store only allowlisted metric/system/severity/numeric values, mode 0600, no customer text/secrets/OTP. Does not change any running Docker services or enable autonomous release worker.

## Full-workforce release remains outstanding
This is the first **reporting component**, not the full connected AI workforce. Need to reconcile native COO GitHub workboard #155 into current exact G3 build, integrate scheduled report visibility, verify independent specialized skills and execution queue, ensure effective current runtime/WiPay/price preservation, stage immutable image + rollback and deploy with owner acceptance. New draft #156 currently only contains independent library and isolated CI; Hub auth-adjacent integration edit was blocked by a safety check and was not forced. Sentinel remains deferred until full owner workforce acceptance.

Founder should run checksum-verified operator ZIP from Acer and return only nonsecret status flags. Next task is to finalize isolated Hub UI integration and release gates without bypassing safety controls.