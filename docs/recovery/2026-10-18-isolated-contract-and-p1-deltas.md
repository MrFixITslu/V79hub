# Academy contract and focused launch deltas

Status: draft runner integration candidate, NOT deployed, NO_GO.

Owner explicitly authorized narrow integration after reviewing the pure contract.
The standalone runner now includes a byte-compared copy of the pure contract.
Local contract/wiring tests pass; actual cached-image runtime remains pending.

The revised Academy startup and cleanup runner is source-only. The pure
`academy-isolation-contract.py` accepts supplied inspection dictionaries and
returns fixed codes. It has no process, Docker, filesystem, network or output
operations and authorizes no lifecycle actions. Its CI uses only synthetic data.

## Academy lifecycle contract

Three alternatives were reviewed: globally relaxing mounts (rejected), starting
before isolation checks (rejected), and state-specific declarations/realizations
(selected). CREATED may have no realized mounts only with exact bounded tmpfs
declarations. RUNNING requires exactly two writable realized tmpfs mounts. Docker CI proved
inspect.Mounts may remain empty after start: in that case, after all declaration
and security checks pass, the runner reads mountinfo and stat evidence inside the
exact probe and requires tmpfs type, size, rw/nosuid/nodev, uid/gid and mode.
An empty inspect field alone never establishes running mount acceptance. Root, extra
privileges, host namespaces, bind storage, published ports, resource-limit drift,
credentials, unknown environment keys and duplicate environment keys fail closed.
Image environment defaults require an independently reviewed pinned allowlist;
the container under test cannot supply its own allowlist. Image EXPOSE metadata
is not a published port and does not itself fail the contract.

Owner audit at 06:58 AST found zero Academy owner-labelled containers; no further
cleanup is needed. Core application health was reported, but full fingerprint
parity was not re-established by that listing. Do not infer startup acceptance
from absence or from synthetic contract tests.

Integration review: independently pinned image defaults must have exactly reviewed
Node20 base environment keys and public value formats, pinned command/entrypoint
and working directory. The explicit owner authorization follows the recorded
prior runner-edit hold; no main merge or production change is included.
Real Docker CI checks concrete inspection shapes before owner execution.
Command/entrypoint, working directory, disabled baked healthcheck and full pinned
Docker host defaults (including masked/read-only paths) require a separate exact
configuration comparison; command/entrypoint/workdir and disabled healthcheck
are now checked by the runner wrapper. Full protective masked/read-only path
comparison remains a separate review requirement; do not claim complete host
fingerprint acceptance from the pure predicate.
Then prove no previous probes remain, validate before start AND after start,
check actual HTTP health and unsigned admin 401, and always recheck protected
production identities/fingerprints/health even on failure. Runner wiring is implemented in the draft; exact cached-image Docker acceptance
has NOT been executed here.

## P1 source reconciliation

Reviewed Hub main df1046151a02dd27db746a2ec5b928f03dcb9b1d and Tiquet main
7da53ebb71530366168bd72a7efd52b57d34a23c. Hub155/156 remain draft/open but
their source heads are ancestors of main. Tiquet37/40 are merged;38/39 remain
ancestor stacks. Do not duplicate these implementations or infer installed
acceptance from Git ancestry. Preserve approved enterprise visual direction.

## Differential acceptance matrix

| Gate | Existing evidence to retain | Missing focused acceptance |
| --- | --- | --- |
| Tiquet logout | tokenRevocationIntegration.test.cjs: actual API/PG copied Cookie/Bearer denial, unrelated tenant valid | Current pinned image/restored synthetic schema, replay across processes and restart; active socket revoked |
| Hub logout | session-persistence.test.mjs: stored session deletion/cookie denial | Truthful per-app logout semantics; Hub session deletion is not global Tiquet logout |
| Staff socket | tiquetSocketAccess/StaffSocketParity helpers and heartbeat tests | Full handler on pinned image: A stops receiving after revoke/suspend, B unaffected; new revoked/expired handshake denied |
| Portal socket | real PG/WS helper tests in tiquetPortalSocketPostgresCI.test.cjs | Full handler with synthetic file/job/link, rotate/revoke while connected, old HTTP+socket denied, new link valid |
| Dependency stall | heartbeat guard and entitlement cache fail-closed source cases | Real disposable Hub/DB delay/outage, measure bounded close/no leaked post-revoke data |
| MFA | enrollment/challenge and owner authorization source tests | Consumed/expired challenge, historical session, MFA removal, wrong owner/tenant; explicitly define fresh-MFA age |
| Tenant API/files | Historical exact-image A/B clients; account-scoped source paths | Current-image cross-tenant GET/PATCH/DELETE, file/job download/delete, traversal; B records unchanged and A positive controls |
| Browser | Historical owner MFA/direct SSO happy path | Bounded synthetic expired/consumed/wrong-tenant ticket, back/refresh/cache after logout, role deep links and stale MFA |

The existing Hub paired test pins historical Tiquet
6f4d93c2f6ed2002eca6fb88bcba0e8bceacdd10. It proves cookie clearing, not
current copied-JWT revocation. Reuse cumulative Tiquet security tests rather than
adding redundant unit suites. A 15-second heartbeat is not a universal 15-second
revocation guarantee: entitlement cache and stalled-check bounds are 30 seconds
plus scheduling/query behavior. Measure each case separately. Current operator
authorization checks verified/enrolled MFA booleans; elapsed-age policy is not
established merely by text calling MFA fresh.

Fresh current offhost restore/rollback, provider inbox delivery, financial/legal
acceptance, actual Sentinel collector-to-alert evidence and owner release GO
remain open. No main merges, deployments, production account/data mutations,
provider sends, payments or DNS changes are included in this work.
