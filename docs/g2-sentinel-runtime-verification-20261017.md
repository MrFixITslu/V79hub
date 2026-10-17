# G2 and existing Sentinel runtime verification

Owner terminal evidence, 16 October 2026 21:06–21:09 Saint Lucia / 17 October UTC. Read-only audits; no claims, approvals, queue execution, timer changes or new monitoring probes.

## G2
Hub `sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698` healthy. G2 actions flag on, audit key configured, worker token metadata private/valid. Store-reader status succeeded, queue unpaused, status counts succeeded=1, COO tasks=1, audit events=3, expired approved jobs=0. Read success authenticates any existing envelope; it does not imply an absent store was initialized.

Worker/queue/route SHA256 values matched reviewed local sources exactly:
- worker: 2915c4c11c01065dbaed9cd184f3942dfd3a4d20b1ebe33dea32b05bba12f03c
- queue: 2a4f68b9e6bd1a3e994f5ade321a7505946ba497ca3432a0b9d8e2ca80397e09
- routes: dc4cf57dcae8121495be5acd3dc1168bcc7c4ce366debc049d750e614584196e

No G2 worker timer appeared in the audited user/system systemd scopes or user crontabs on either host. The server has only morning/evening briefing timers among matching timers. Root crontabs, arbitrary process schedulers or unrelated unit names were not comprehensively inspected. Do not claim that no possible scheduler exists.

**Release-worker readiness BLOCKED:** current Hub has 12 Compose inputs while source manifest maximum is 5. Image revision label is inherited `045d68a61257c758f2f6ca229d050e4e7a7df618`, not application source `5c13dc9612752f896ef5cb2e8c1da63c0cfd8e04`. The correct manual source/image recovery evidence does not satisfy the worker's exact-label contract. No worker was installed or run during this verification. An observed completed queue job is not proof of scheduled worker execution.

## Acer monitoring observed
NOC unit runs from `/home/firelion/V79-Sentinel/g221-mobilefix-isolated-review` at e544c8db2b1fda73a4078ece988fc70d4b37ceca. Existing signed Dell collector, network collection, public app/readiness and mock-incident timers are active with last successful exit status. Different timers use separate staging worktrees; do not assume a single deployed code revision covers all of them.

Acer SQLite read-only aggregates: sentinel_real_measurements=2868, sentinel_real_checks=1; newest stored record age 3 seconds. Most recent Dell claim signature verified directly against the locally configured public key; its SHA256 matched the local pinned fingerprint and claimed policy identifiers/target matched configuration. Signed observation age 3 seconds, TCP check to the fixed Dell endpoint 192.168.100.163:443, reported open. Private signing key was never read by this audit. Signed incident table had no open/resolved rows at observation time.

These are 2868 historical observations of one check, not 2868 devices. Local signature/key consistency does not establish independent source attestation, effective source-code parity for every timer, TLS certificate validity, successful HTTPS response, uptime/SLA or alert delivery. No forced failure/recovery experiment was performed.

Private existing evidence files were recently modified: network observation about 2 seconds, public/readiness/mock snapshots about 382 seconds, certificate-health snapshot about 8990 seconds. Timestamp/file existence alone does not validate every report's scope, classification or service health. The audit did not initiate those checks; already-installed timers generated them.

## Server Sentinel stage
Three containers healthy:
- ingress sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752, UID 101
- monitor sha256:eb55dddd3af182213382bce20147ad09b00f1ba6fef1ccfc478357498cf8edda, UID 10001
- NOC sha256:f9cef385aadd96229bea161473f627b006505216b1025692adfa6c5e832e5464, UID 10001

No host networking or Docker socket mount observed. Only NOC published port 8080 to host 127.0.0.1:14078; other two had no host port bindings. This does not prove that no reverse proxy or separate path exists outside the inspected container metadata.

NOC readiness explicitly collector=simulated-only and integrations=disabled. Healthy process checks must not be presented as genuine server monitoring or as proof Acer signed observations are ingested by the server stage. No evidence of live Sentinel-to-Hub/COO or supervised Tiquet alert dispatch was established.

## Security disposition
Engineering verification is partial and bounded; independent review issue #3 remains open as customer pre-launch condition. Canonical PR #14 records GitGuardian failure 114653264225; successful Actions and unsigned/empty combined-status outputs do not resolve it. Need private scanner finding type/file and owner-authorized remediation/false-positive disposition, without exposing the value.

Next: privately triage scanner finding, reconcile source/units for current Acer collectors and server stage, validate existing application-readiness evidence, design isolated fault/recovery and alert-delivery acceptance. Genuine server monitoring/integration remains incomplete. Preserve all current collectors/accounts; no unattended G2 deployment worker or new probes activated by this report.
