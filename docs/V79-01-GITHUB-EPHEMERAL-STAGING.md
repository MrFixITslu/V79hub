# V79-01 — Disposable GitHub Actions five-application staging

**Release status:** This is a **non-production** PR-only test workflow. The V79-01 application changes stay in draft PRs and no trial activation or database migration is approved by this workflow.

## How it works

1. GitHub-hosted `ubuntu-24.04` runners separately build the five known development commits of Hub, POS, FFPRO, Tiquet and Marketing. All five GitHub repositories are publicly readable. Each runner uploads a short-lived image archive to the workflow, without publishing to GHCR or touching `main`.
2. A separate GitHub runner downloads those archives, creates random credentials valid only for its disposable lifecycle, pulls PostgreSQL and Redis images, and starts a Docker Compose `internal: true` network with no published host ports.
3. The network includes four independent PostgreSQL instances (Hub, POS, FFPRO, Tiquet), Redis and a separate SQLite-backed Marketing service. It writes a synthetic-only Hub state to its own PostgreSQL. It never copies production database backups, app data, SSH keys, social credentials or payment secrets.
4. All five app images boot with entitlement revalidation enabled. A networked smoke test checks real HTTP health and Hub's signed entitlement endpoint: an active synthetic trial allows an authorised mapped owner; a cancelled tenant, cross-tenant identity and invalid HMAC signature are denied. It tests synthetic customer Hub login and tenant-bound session.
5. The runner always tears down services and **deletes temporary Docker volumes**. Short-lived image artifacts expire after one day. No public endpoint remains available after the job.

## Trigger and current limits

- Triggered by a same-repository PR to `main` when this workflow or its dedicated staging files change. A future manual dispatch from default branch would require this workflow to be merged first and does not operate as an approved production release.
- The Hub image in the matrix follows the PR HEAD. The four other images use the exact approved development commit SHAs recorded in this workflow; update them deliberately when their drafts change.
- This runs only on GitHub-hosted runners. No Tailscale, production secrets, SSH, `environment: production`, GitHub package publishing, email/WhatsApp sending or live banking processing is used.
- Five real application processes and isolated databases do **not** fully replace a user-operated end-to-end staging environment. External integrations, OAuth/SSO redirects to production domains, invitation email receipt, social publishing and real payment settlement are deliberately out of scope. Some product-specific provisioning and rollback flows still need independent tests.
- Do not enable the customer 14-day trial or merge/deploy until the founder explicitly approves release after reviewing remaining gates.

## Review command

Open the V79hub draft PR, then GitHub **Checks** > **V79-01 Disposable Five-App Staging**. A successful **Five real containers and synthetic-tenant contract** job proves the runner exercised the intended integrated paths. Any failed build/service step must be fixed before release.
