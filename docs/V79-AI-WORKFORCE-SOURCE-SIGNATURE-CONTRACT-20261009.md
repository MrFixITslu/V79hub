# V79 AI Workforce — Original-source signed aggregate metric contract

**Phase 2C/Phase 3A pilot, 9 Oct 2026 · Two feature-flagged draft PRs; no production config or deployment.**

## Motivation and trust boundary
The deployed read-only agent obtains product summaries from authenticated Hub app integrations. A subsequent Hub proxy receipt proves that Hub observed matching evidence and investigation fields, **but not that the originating POS, FFPRO, Tiquet, or Marketing application cryptographically signed that data**. Do not label the current production summaries `source_signed`.

`server/source-metric-signature.mjs` provides the independent **Ed25519 verification primitive** and strict canonical JSON contract. The first **Hub GET-only verifier route** is now wired into feature branch code as `/api/agent/sources/tiquet/metrics`, gated on `V79_TIQUET_SIGNED_METRICS_ENABLED=1`, a trusted app-specific public key and completed founder MFA. Tiquet's source signer is separately implemented on [draft Tiquet PR #21](https://github.com/MrFixITslu/V79Tiquet/pull/21), behind its own default-OFF flag. **Neither flag is enabled nor any signing key configured in production.** The route returns independently verified aggregates to the owner only; it does **not** yet send these new metrics into the agent investigation planner or mark an existing Phase 3A proposal `source_signed`.

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

## Pilot implementation and remaining staged rollout (NOT enabled)
1. **Tiquet** (first test pilot): the app's [draft PR #21](https://github.com/MrFixITslu/V79Tiquet/pull/21) now implements a platform-HMAC-authenticated GET endpoint at `/api/platform/agent/signed-metrics/:organizationId/:requestId`. It obtains five tenant-scoped aggregate numeric metrics using read-only DB queries, signs a canonical envelope with a **new app-only Ed25519 key loaded from `/run/secrets/`**, and returns no account or customer records. Its feature flag is `V79_TIQUET_SIGNED_METRICS_ENABLED=0` by default. Hub's draft PR #103 uses its own `V79_TIQUET_SIGNED_METRICS_ENABLED=0` flag, a trusted **public key** supplied in `V79_TIQUET_SOURCE_ED25519_PUBLIC_KEY_B64`, and a fresh UUID in its HMAC-signed exact GET pathname. Hub rejects wrong tenant, wrong requestId, invalid signature, incomplete counters, expired timestamps, redirects, malformed JSON and oversized responses. Success returns only five safe metrics, observation timestamp and `provenance:"source_signed"` with `executionEnabled:false`. The signer and Hub reader are **feature-branch-only**, not deployed or enabled.
2. **POS**: counters for aggregate replenishment/delays, never supplier details, order creation or inventory changes.
3. **FFPRO**: only finance aggregates, no bank account identifiers or individual transactions.
4. **Marketing**: aggregate campaign/post/connectivity counters, no audience/contact lists or social tokens.

For each app: review existing read-only contracts and source timestamp semantics, implement a fixed-method endpoint with strict caller authentication, use a **new per-app key** and a Hub-supplied nonce, add synthetic tests in that app's own feature branch, review key custody/rotation and obtain a separate deployment approval. Only after a source genuinely emits signed envelopes may Hub's runtime verify the signature and mark them `source_signed`. Default is disabled/fail-closed. Unknown signatures or timestamp failure must appear as **unavailable**, never as zero.

## Evidence-to-approval integration gate (still OPEN)
The new owner-MFA GET diagnostic proves the signed source-read channel in **synthetic CI**; it is **not** yet a trusted input to the AI agent's findings or an eligible `source_signed` approval receipt. Before connecting it to the planner, use a structured source-verified finding adapter (not model-authored JSON) and bind proposal receipts to the specific verified source payload, tenant, nonce and freshness. Existing approval routes must continue enforcing MFA, allowlists, tenant, expiry, idempotency and audit. No write can occur merely because data is signed. The in-memory ten-minute Hub proxy receipts remain separate; multi-replica receipt storage and replay-safe source nonce caches require design review.

## Test evidence
`tests/source-metric-signature.test.mjs` and `tests/tiquet-signed-source-reader.test.mjs` use runtime-generated **synthetic** Ed25519 keys. They validate strict source/tenant/nonce freshness, complete metric schema, caller HMAC, no unsafe HTTP method, denial for unknown/forged/oversized payloads and default-off behavior. `tests/admin-mfa-flow.test.mjs` exercises the Hub MFA-protected route against a synthetic signed Tiquet fixture. Tiquet's corresponding `tests/sourceMetricSigner.test.js` and existing platform provisioning integration test live in draft PR #21. Synthetic tests **do not** establish source signing is running in production.

**No production config, secret, app repository, database, Docker workload, beta account or agent permission is changed by this contract.** PR #103 remains draft/unmerged. Completion requires app-specific source implementations and reviewed staging.
