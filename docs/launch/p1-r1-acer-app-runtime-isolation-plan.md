# R1 — Acer isolated Hub/Tiquet app recovery plan (source-only)

**Recorded:** 2026-10-17. **State:** DESIGN/PREFLIGHT ONLY — no app boot or rollback accepted. This plan is not authorization to merge, deploy or enable external beta.

## Verified on Acer against the original 14 encrypted streams

- Original ciphertext SHA256, complete GPG decryption and archive structure: **14/14 PASS**.
- Five original Docker29 OCI index-image pins cryptographically resolve to five distinct image configurations, and the five exact cached Podman config-image IDs: **5/5 PASS**. There is no need to rebuild or recapture images, re-tag, change manifest, or re-import.
- Saved Hub PG17 dump restored and checked in disconnected temporary database: **PASS, 1 user table**. Saved Tiquet PG16 dump restored: **PASS, 25 user tables**. Both disposable DB containers verified removed.
- Real owner run of blob-verified app-archive inventory at commit `787e61782435d998e53293204345e2e50b04893f`: **10/10 TAR streams passed** (6 Hub mounts, 2 Tiquet mounts, 2 config TARs). All zero special, unsafe or out-of-prefix members; no symlinks/hardlinks in these source archives. Original report explicitly states `R1_APP_MOUNT_RESTORE=NOT_PERFORMED` and `R1_APPLICATION_BOOT=NOT_PERFORMED`.
- Four of the Hub mounts are credential-file mounts. The *source ciphertext may contain original live tokens*. Do **not** replay those or original `.env` content into the rehearsal.

## Required boundaries for NEXT execution (not performed yet)

1. Acer laptop **only**, non-root, rootless local Podman `--remote=false`; original original ciphertext/manifest read-only and source Git commit + blob hashes pinned. Refuse `CONTAINER_HOST` or `DOCKER_HOST`, SSH to `v79sl`, image pulls, auto-update and production network/provider calls.
2. Verify disposable **network-none** four-image runtime design and that pods can share *only local loopback*, with **no host port publishing** and no external routes. Existing production Compose requires `proxy_network` and externally reachable hostnames; do not reuse it, or blindly paste the saved `.env`.
3. Restore only **Hub /app/data, Tiquet /app/data and /app/uploads** into a separate, capacity-bounded, access-restricted **ephemeral storage** (explicitly verified tmpfs/no persistence), with safe tar path enforcement, no link/device members, size/count quotas and mandatory secure cleanup. Never extract app secrets or archived `.env` into runtime. Source tar inspection alone does not prove files can be restored.
4. Use saved verified Hub PG17 and Tiquet PG16 images with **separate SQL identities/ports**; both PostgreSQL images default to TCP 5432, so in a shared loopback pod, assign one a different loopback port (e.g. 5433) and reflect it in Tiquet `DB_PORT`. Preserve recovered business records only inside disconnected ephemeral storage.
5. Start original Hub and Tiquet images with **synthetic session, provider, gateway and shared-platform keys**; explicitly disable WiPay, email dispatch, webhooks, other Hub connected-app calls, remote AI and unattended background actions. Keep admin MFA enforcement enabled and Tiquet legacy auth disabled. Do not claim old live MFA/session crypto works with synthetic keys. Startup may reject recovered encrypted data; record this as a gate, not reason to copy original live secrets.
6. Test GET Hub `/api/health` on loopback 3040 and Tiquet `/health` on loopback 3050, PostgreSQL `SELECT 1` against **each distinct restored DB**, source/capture image identity, and anonymous/unauthorized denial. Do not infer positive owner MFA/Hub→Tiquet SSO or tenant isolation from health alone.
7. Separately design a **synthetic owner identity** and cross-app signed-request flow to test positive SSO and negative replay/tenant behavior without original customer accounts or keys. Explicitly document what is and is not verified.
8. For rollback, must **boot the original saved prior Hub OCI-index image** in this same disconnected environment against appropriate scoped/immutable synthetic data. Merely importing the rollback image is not rollback acceptance. No historical Tiquet rollback image was captured, so do not advertise Tiquet application version rollback.
9. End with **verified teardown** of all pod containers and plaintext ephemeral workspaces. Fail CLOSED on cleanup failure or unexpected network mounts/ports. Retain only aggregated nonsecret evidence; never log credentials, restored account records, raw `docker inspect`, full config JSON, image tags or file contents.

## Safe acceptance sequence

A. Network-none Podman capability + four-image boot contract **without recovered data**.
B. Original recovered Hub+Tiquet *data mounts* restored in an isolated ephemeral file tree and re-verified.
C. Four exact saved runtime images with two recovered databases + application files: boot, bounded health and anonymous denial.
D. Synthetic credentials and tenant SSO negative/positive acceptance, isolated rollback boot, verified teardown.
E. Independent security signoff, owner beta release decision and external provider sandbox separate from any recovery rehearsal.

**Release gate:** NO-GO until C/D/E are accepted. Previous passes do **not** justify calling the whole app restored, production recovery complete or beta ready. No merge/deploy by this runbook.
