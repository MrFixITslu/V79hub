# G2 and Sentinel verification preflight

16 October 2026 evening Saint Lucia / 17 October UTC. Source inspection and local synthetic evidence only; runtime audit pending.

## G2 source results
13 focused tests passed for queue transitions, approval routes and release worker. Read-only live audit is in `scripts/workforce-g2-sentinel-audit.py`; it does not claim, approve, execute, pause or initialize the queue. The store read path performs a SELECT in PostgreSQL and does not run schema initialization. Existing envelopes are MAC-checked by the store reader; an absent record can return initial state and must not be falsely described as an authenticated persisted queue.

### Known release-worker blockers
- `validateReleaseManifest` permits at most five original Compose inputs. Current Hub has twelve ordered inputs after reporting and workboard activation. A Hub release manifest cannot pass this bound. Do not flatten or discard overlays just to fit it.
- Validation and target images require `org.opencontainers.image.revision` equal to the approved commit. Current Hub candidate was built atop a prior exact image and given a rehearsal label; its actual revision label needs runtime inspection. Image/source proof used during manual release is not interchangeable with worker manifest acceptance.
- Deployment/rollback allow only image changes. The earlier report/token mount/flag changes were owner-operated guarded releases, not automatically eligible G2 image-only jobs.
- Source presence or enabled queue flag does not prove a worker timer is installed. Live units/timers, queue state and token metadata must be checked independently. Do not invoke `runWorkerOnce` as a diagnostic: it executes approved work items and claims release jobs.

No queue payload, customer data, signing key or worker-token value is printed by the audit.

## Sentinel source reconciliation
Canonical PR #14 remains at `5baceb1aad29694b002b8c122cc98b8da4f085e4`. Both exact-head GitHub Actions runs (38200707860, 38200707857) succeeded. PR records still state GitGuardian check 114653264225 failed. The available combined-status query returned no statuses; that does not clear the separate check-run hold.

Evidence stack: #16 advisory gate -> #17 pinned Ed25519 evidence -> #18 durable replay checkpoint. Exact cumulative #18 head is `09e6496cadb222d6739f77cc798bebc556590f19`. All 26 advisory/signature/replay tests passed locally. These are disconnected evidence verifiers, not a deployed genuine HTTPS collector or alert system. Their result deliberately remains pending operator acceptance with executive trust/continuous monitoring/customer readiness false.

The canonical NOC `/readyz` explicitly reports collector simulated-only and integrations disabled. Existing real-Edge correlation code does not by itself establish a running collector, source-key custody, actual service measurements, alert delivery or Tiquet dispatch.

## Security-review limits
Issue #3 is open. Founder previously deferred independent review to customer pre-launch; implementation self-review is not independent sign-off. The documented internal exception is Acer-only and supervised, subject to exact operational approval and recovery. It does not silently authorize new server/customer monitoring, public ingress or live Sentinel-to-Tiquet dispatch.

Before genuine monitoring: privately resolve GitGuardian finding, reconcile exact source/runtime and recovery, define V79-owned HTTPS targets and vantage, provision collector keys locally, prove signed fresh measurements and durable replay, demonstrate synthetic fault/recovery alert delivery in isolation, then obtain acceptance for the specific internal monitoring scope. No probing, keys, monitoring schedule or public endpoint has been enabled by this preflight.
