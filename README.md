# V79 Client Hub

The Hub is an invite-only multi-workspace operations portal for the V79 ecosystem. Production uses transactional PostgreSQL persistence, session-scoped organization boundaries, and explicit tenant mappings for POS, FFPRO, Tiquet and Marketing. Managed product launches use signed, single-use tickets and fail closed until the exact workspace mapping is active. Academy remains a separate learner service, while Vision79-only properties such as CombatZone, the Vision79 website and Gaming Studio J are not exposed to customer workspaces.

## Deploy on the shared reverse-proxy network

1. Back up the current `data/` directory and `.env`. Keep the `data/` directory across updates: it contains Hub records, the POS signing key and tenant identity.
2. Copy `.env.example` to `.env`. Set a unique `V79_HUB_ADMIN_PASSWORD` of at least 16 characters, `V79_HUB_ADMIN_EMAIL` to the owner's verified email, and the same 32+ character `V79_PLATFORM_SHARED_SECRET` as the POS container. Set three separate launch secrets matching FFPRO, Tiquet and Marketing. Do not use the old demo passwords. Set `APP_URL` to the public Hub HTTPS origin. If linking an existing POS tenant and owner, set `V79_POS_ORG_ID` and `V79_POS_OWNER_USER_ID` to their verified existing IDs **before first boot**; otherwise a new POS tenant will be created.
3. Ensure Docker network `proxy_network` exists. Run `docker compose --project-name v79-hub up -d --build` and route `hub.v79sl.com` in Nginx Proxy Manager to `v79-hub:3040` over that network. The Hub container exposes no host port.
4. On POS, use `JWT_ISSUER=https://hub.v79sl.com`, `HUB_INTERNAL_URL=http://v79-hub:3040`, `HUB_JWKS_URL=http://v79-hub:3040/.well-known/jwks.json`, `POS_PUBLIC_URL=https://pos.v79sl.com` and the matching service secret. Recreate POS after changing its environment.
5. Sign in at `https://hub.v79sl.com` with the configured admin **username** (default `admin`) and password. Launch FFPRO, Tiquet, Marketing or POS from their Hub card. Each product consumes the one-time ticket and establishes its own session. Direct visits to POS show the read-only demo until launched from Hub. Relaunch from Hub when its five-minute POS session expires.

The three existing product servers must each have `V79_HUB_INTERNAL_URL=http://v79-hub:3040` and the matching `V79_*_LAUNCH_SECRET`. An existing FFPRO or Tiquet account with the same email is deliberately **not** silently linked to Hub: back up the product database, verify ownership and use that product's documented `V79_ALLOW_EMAIL_ACCOUNT_LINK=1` for one reviewed launch, then switch it off again. The Hub supports an operator-controlled owner identity and invite-only customer workspaces. Workspace owners can invite scoped team members to POS, Tiquet and Marketing; FFPRO finance access remains owner-only. Open self-service signup and paid conversion remain disabled.

### Recover a failed administrator password

The password in `.env` only bootstraps a new admin record. Editing it later does not change the saved hash. Back up `/opt/v79/hub/data` and `.env`, set a new unique `V79_HUB_ADMIN_PASSWORD` in the server `.env`, then from `/opt/v79/hub` run:

```sh
docker compose --project-name v79-hub stop v79-hub
docker compose --project-name v79-hub run --rm --no-deps v79-hub node scripts/reset-admin-password.mjs
docker compose --project-name v79-hub up -d --no-build v79-hub
```

The command changes only the configured administrator's hash, makes a private backup beside `v79_store.json`, and the restart revokes previous in-memory sessions. Use the username from `V79_HUB_ADMIN_USERNAME`, not an email address, on the login screen. Do not paste the password into a shell command or chat.

Legacy demo passwords are disabled on startup and plaintext passwords in existing `data/v79_store.json` are converted to salted scrypt hashes. The configured admin password replaces the old seeded admin password. Other accounts with known demo passwords must be given new passwords by the administrator. Inspect existing Hub data before treating previously seeded inventory, transactions or integration metrics as real. Fresh production stores start without sample business records; existing records are preserved. Production reset is disabled.

## Development and verification

```sh
npm ci
npm run lint
npm run build
npm test
```

The active test suite covers private API access, role and organization boundaries, invite-only multi-business onboarding, password recovery, signed single-use launches, service contracts and Owner Assistant access. Older prototype tests for open signup and a removed SQLite owner recovery path are retained in `tests/legacy/` as historical specifications and are excluded from the active suite. Paid checkout remains disabled. Multi-business onboarding is invite-only and restricted to the V79 platform operator; managed product workspaces remain launch-disabled until their tenant mappings are activated. See `docs/multi-business-release-gates.md`.


## Account security and billing

Production Compose enables mandatory TOTP MFA for the V79 platform administrator with `V79_REQUIRE_ADMIN_MFA=1`. On the first administrator login after this release, V79 Hub shows an authenticator setup key and requires a valid six-digit code before creating the session. Existing administrator sessions are revoked when mandatory MFA is enabled but the owner has not enrolled yet. Customer users may enable optional MFA from **Security**.

Password reset links are one-time, expire after 30 minutes, revoke existing Hub sessions after use, and are sent only to the registered account email. Automatic delivery is enabled only when `RESEND_API_KEY` and an authorized `V79_HUB_EMAIL_FROM` are configured. The recovery/support address defaults to `vision79slu@gmail.com`; when transactional email is not configured, the login screen directs users there instead of exposing reset links.

**Plans & Billing** is informational in this release. It shows the current plan, enabled V79 modules, configured XCD monthly/annual pricing and renewal date. Self-service card payments and automatic subscription changes remain disabled; plan changes are handled by V79 Digital.
