# V79 Studio / Hub paired release – guarded go/no-go

**Status: NO-GO for production enablement.** This is an owner-facing release contract, not an approval to deploy.

## 1. What is actually verified

- Hub draft PR #220, Marketing draft PR #34. Both must remain pinned to their **exact Git SHAs** when release evidence is collected; never pair a newly edited head with an older green result.
- Hub has isolated signed-read, fresh-MFA owner/manager approval, one-time nonce, live creator and approver entitlement checks, and SHA-256-reviewed media. Marketing's exact creative package is immutable and separate from the publisher.
- Isolated browser: Marketing Studio creative draft → actual PNG/JPEG + locally composed MP4 → immutable owner review → zero publication. Hub's approval page was captured at desktop/mobile widths with publishing locked.
- Publisher: single atomic delivery claim, original creator account fingerprint, exact signed approval, no provider dispatch if business/user/credential/skill/asset changes, ambiguous dispatch means UNKNOWN with **no blind retry**.
- Additional requirements: Marketing manager must not approve own campaign; solo business owner may approve only with fresh Hub MFA. Facebook requires a recorded `pages_manage_posts` scope, this Facebook-login Instagram route requires `instagram_content_publish`. These *recorded* grants are NOT proof that Meta accepts the token now.
- Media: Instagram feed requires an inspected JPEG with valid aspect ratio. Facebook can use JPEG/PNG. Local MP4 preview and export do not imply generative AI video or authorise Reels/YouTube publishing.
- Preserve historical accepted Hub production source fingerprints; candidate changes are separately pinned. Do **not** change production acceptance hashes to make a test pass.

## 2. Flags and secrets — OFF until approved

Marketing:
- `V79_STUDIO_PUBLISH_ENABLED=0` until separate live-provider release approval
- `V79_ENTITLEMENT_RECHECK_ENABLED=1` only after independently validating signed Hub entitlement
- `V79_MARKETING_STUDIO_REVIEW_KEY` – stable 32+ character dedicated HMAC secret, kept in the protected secret store
- `V79_STUDIO_HUB_SHARED_SECRET` – stable dedicated 32+ character HMAC secret, **same value on Hub and Marketing**, different from all other keys
- `APP_URL=https://marketing.v79sl.com/` canonical HTTPS media origin
- `V79_PERSONAL_IMAGE_GENERATION_ENABLED=0`, `V79_MEDIA_CLOUD_SPEND_POLICY_ENABLED=0` until a separate approved dollar-cap policy exists

Hub:
- `V79_STUDIO_READ_ENABLED=0` initially; a separately approved *read-only* preview can use `1`
- `V79_STUDIO_PUBLISH_ENABLED=0` until owner approves social dispatch
- `V79_STUDIO_HUB_SHARED_SECRET` matches Marketing but must never be logged, pasted into chat, committed or printed

If either service cannot establish strong key provenance/rotatable recovery, **do not enable**. Creative review must never be interpreted as publication approval.

## 3. Required checks before staging or promotion

1. Owner confirms the *exact paired Git commit SHAs*, all affected PR checks, one real desktop/mobile Hub screenshot, and no unexplained CI failures. Previously passing tests need not be re-run unless their corresponding code or runtime assumption changed.
2. Read-only host/container inventory from the authoritative Dell. Capture current image digests, healthy states, volumes, service/DB identity, disk headroom, TLS routes and proxy state. Do not print container env values.
3. Off-host encrypted backups: Hub and Marketing databases, SQLite WAL-aware/online backup, media, Docker volumes, container configuration and **recoverable signing/encryption keys**. Reject prior files marked `INCOMPLETE_DO_NOT_RESTORE`.
4. Restore to an **isolated, non-production** host/container with **network egress disabled** and publishing flags OFF; verify DB integrity, owner/tenant isolation, review HMACs, private asset bytes, approval queue and login. Store receipt/manifest and rollback instructions.
5. Verify an owner-created *original personal* Facebook Page or Instagram professional account, exact page ID, OAuth ownership, actual granted publish scopes, provider business/app access status, account expiration, and whether Meta App Review/Advanced Access is required. Never use a shared team token or assume a stored scope string proves current permission.
6. Test signed public media URL availability without exposing creator tokens. Check MIME, TLS, SHA-256, range/caching behaviour and provider fetch window. Do not enable paid cloud inference.
7. Request **separate, explicit** owner consent for a single exact pilot (channel, creator, destination account, full caption, media digest and proposed time). Do not silently publish to a public Facebook Page as a connectivity test.
8. Execute at most one owner-approved pilot under observed supervision, check provider receipt against the destination, record entitlement/key state, and confirm UNKNOWN cases require manual reconciliation. Do not retry when the response may have been lost.
9. Set a bounded read-only smoke/health monitor. Rehearse reversal to exact pre-promotion Hub/Marketing images without rolling back database migrations unless separately verified safe.
10. Only after all checks, present an explicit **GO / NO-GO** with change record and owner approval. Merge/deploy is a separate action.

## 4. Non-mutating Dell inventory example

Run **manually on the Dell** in an authorised shell only. This is deliberately read-only:

```bash
(
  set -euo pipefail
  test "$(hostname)" = "v79sl"
  date -u '+UTC=%Y-%m-%dT%H:%M:%SZ'
  for name in v79-hub v79marketing-app; do
    sudo docker inspect --format \
      'CONTAINER={{.Name}} IMAGE={{.Image}} HEALTH={{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}} RESTART={{.HostConfig.RestartPolicy.Name}}' "$name"
  done
  sudo docker system df
  printf '%s\n' 'PRODUCTION_CHANGES=NONE' 'SECRET_VALUES_PRINTED=NONE'
)
```

This **does not** confirm backup, rollback or account readiness. Those require independent evidence.

## 5. Rollback and non-reversible outcomes

- Keep the old image digests and migration/volume state documented before any cutover. Rollback must not delete the new private media or invalidate existing customer data; prefer forward-compatible additive migrations.
- No external social post can be undone merely by rolling back a container. An UNKNOWN delivery stays on hold until the provider account has been checked and an authorised reviewer records the outcome.
- If preflight, creator entitlement, personal OAuth, public media fetch, signed approval, or off-host restore fails: **NO-GO**, keep both publishing flags OFF, no automatic retry, no source-code deployment.

## 6. Evidence currently missing

- Live Dell read-only inventory and off-host recovery test (the remote control connection currently has exhausted tool quota).
- Live Meta account identity, actual granted permissions and App Review eligibility.
- An explicitly authorised, controlled real provider pilot and receipt reconciliation.
- Owner's final paired-release approval.

A green synthetic browser test or a successful Docker build is **not** equivalent to these missing checks.
