# V79 AI Workforce — Original-source signed aggregate metric contract

**Phase 2C/Phase 3A design pilot, 9 Oct 2026 · Inactive code and synthetic tests only.**

## Motivation and trust boundary
The deployed read-only agent obtains product summaries from authenticated Hub app integrations. A subsequent Hub proxy receipt proves that Hub observed matching evidence and investigation fields, **but not that the originating POS, FFPRO, Tiquet, or Marketing application cryptographically signed that data**. Do not label the current production summaries `source_signed`.

`server/source-metric-signature.mjs` provides an independent **Ed25519 verification primitive** and strict canonical JSON contract. It is NOT wired into any runtime handler, and no app signing key or public verification key has been configured. The contract is preparatory; it does not change the currently deployed beta's evidence state or authorise agent execution.

## Source-side envelope v1
The signing application constructs only this object, with exact property names and no extra customer fields:

```json
{
  "schema": "v79-source-metrics-v1",
  "source": "tiquet",
  "organizationId": "tenant-owner-opaque-id",
  "requestId": "01234567-89ab-4cde-8000-0123456789ab",
  "observedAt": "2026-10-09T12:00:00.000Z",
  "expiresAt": "2026-10-09T12:02:00.000Z",
  "metrics": [{ "key": "unreadNotifications", "value": 4 }]
}
```

**Illustrative synthetic data only.** The metrics array is bounded, allowlisted by app, consists of finite numbers within ±10¹², rejects duplicates and unknown keys, and is canonicalised in metric-key order. The signed bytes are UTF-8 of the canonical JSON returned by `canonicalSourceMetricPayload`.

- Each app signs the canonical bytes with its own protected **Ed25519 private key**. The signature is unpadded base64url (64 raw signature bytes).
- Hub validates using an **operator-configured per-app Ed25519 public key**, never one attached to the API response.
- Hub supplies the expected app, tenant and freshly minted `requestId` from server-side authenticated context. The signed response must match all three exactly. A different Hub request ID makes captured responses unusable for a new read.
- `observedAt` and `expiresAt` must be canonical UTC milliseconds. Observed source data older than five minutes, more than 30 seconds in the future, already expired or with a validity interval longer than two minutes is rejected.
- On verification success, return only the verified `system`, `observedAt`, numeric `metrics`, and `source_signed` provenance to the agent layer. Do not forward tenant IDs, request IDs, public/private keys or signatures to the model.
- A valid cryptographic signature attests that a holder of the configured source private key signed the **numeric envelope**. It does not independently prove the numeric facts are true, or protect against a compromised signer.

## Target rollout plan (NOT enabled)
1. **Tiquet** (first test pilot): define a read-only, immutable summary snapshot with counts and a signed envelope. Generate a new app-specific private key in a secure secret store, supply only its public key to Hub; do not reuse platform/API launch secrets. Exercise known missing/stale/forged/tenant-mismatch results.
2. **POS**: counters for aggregate replenishment/delays, never supplier details, order creation or inventory changes.
3. **FFPRO**: only finance aggregates, no bank account identifiers or individual transactions.
4. **Marketing**: aggregate campaign/post/connectivity counters, no audience/contact lists or social tokens.

For each app: review existing read-only contracts and source timestamp semantics, implement a fixed-method endpoint with strict caller authentication, use a **new per-app key** and a Hub-supplied nonce, add synthetic tests in that app's own feature branch, review key custody/rotation and obtain a separate deployment approval. Only after a source genuinely emits signed envelopes may Hub's runtime verify the signature and mark them `source_signed`. Default is disabled/fail-closed. Unknown signatures or timestamp failure must appear as **unavailable**, never as zero.

## Evidence-to-approval integration gate
Even after a source signature verifies, the approval route must re-check owner session MFA, proposal operation allowlist, tenant, expiration, idempotency and audit. No app writes may be caused by a signature verification or proposal approval in Phase 3A. The in-memory ten-minute Hub proxy receipts remain separate; multi-replica receipt storage and replay-safe source nonce caches require a full design review.

## Test evidence
`tests/source-metric-signature.test.mjs` uses runtime-generated **synthetic** Ed25519 keys; it rejects wrong source/tenant/request, forged or unrelated signatures, stale/future/expired metrics, RSA keys, unexpected fields, duplicate metrics, strings, NaN and contact data. These tests prove the isolated verifier implementation only; they do **not** prove any current V79 application signs this format.

**No production config, secret, app repository, database, Docker workload, beta account or agent permission is changed by this contract.** PR #103 remains draft/unmerged. Completion requires app-specific source implementations and reviewed staging.
