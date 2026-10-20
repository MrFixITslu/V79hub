# Owner Google authorization — supervised pilot

Status: source implemented, not deployed or authorized. Use a dedicated Desktop app OAuth client, PKCE S256, state validation and a loopback callback. Do not use deprecated copy/paste authorization codes or a service account for personal Gmail.

## Owner setup required
1. Open https://console.cloud.google.com/ and select/create a project for this private workforce.
2. Enable **Gmail API** and **Google Calendar API** in that project.
3. Configure **Google Auth Platform** branding and audience. For the initial pilot, External/Testing with vision79slu@gmail.com as a test user is appropriate. Do not claim unattended long-term reliability from this: Google's Testing-mode external refresh tokens for these scopes expire after seven days.
4. Create a dedicated OAuth client with application type **Desktop app**, named `V79 Workforce Owner`. Download its JSON and rename it `v79-workforce-client.json`. A Web application client will be rejected by the helper.
5. Keep the JSON private; do not upload it to chat, GitHub, a shared drive or an AI prompt.

Requested permissions are Gmail read and compose, Calendar read and owner-event write. Gmail compose also allows sending at Google's permission layer. The trusted Hub adapter exposes draft creation only; the separate model service gets no OAuth credential mount or token endpoint.

## Transfer from Acer to v79sl
Run on Acer after downloading the client:

```bash
chmod 600 "$HOME/Downloads/v79-workforce-client.json"
ssh firelion@192.168.100.163 'umask 077; mkdir -p /home/firelion/.config/v79-workforce/google; chmod 700 /home/firelion/.config/v79-workforce/google'
scp "$HOME/Downloads/v79-workforce-client.json" firelion@192.168.100.163:/home/firelion/.config/v79-workforce/google/client.json
```

Check source SHA and helper hash against the reviewed branch before execution. The authorizer uses only Python standard-library modules and does not install dependencies or change Hub.

## Browser callback from Acer
Open a new SSH session from Acer:

```bash
ssh -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 firelion@192.168.100.163
```

Within that server session, run the checksum-verified `workforce-google-authorize.py` file:

```bash
python3 -B workforce-google-authorize.py --client /home/firelion/.config/v79-workforce/google/client.json
```

The helper binds only server loopback, prints a Google consent URL, and waits up to ten minutes. Open that URL in your Acer browser, select vision79slu@gmail.com and review the exact permissions. The callback returns through SSH. The helper verifies both Gmail profile and primary-calendar owner before saving a refresh token. It prints status and the credential path, never token values.

The output defaults to `/home/firelion/.config/v79-workforce/google/credentials.json` (directory 700, file 600). It refuses symlinks, exposed input files, wrong accounts, missing scopes/offline grants and overwriting existing credentials. A failed identity check does not save a token; revoke an unwanted grant from Google account settings if necessary.

No Gmail draft, email, event or workforce job is created by consent. No service is enabled by the helper. Consent approval is the owner's action in Google's browser.

## Integration after consent
The candidate Hub now contains owner-MFA Google status/inbox/thread/agenda routes and a manual run-once route backed by the same G2 ledger. Owner Assistant → More tools includes email/calendar review and proposal forms. Tasks & approvals shows the exact email body, recipient, time and attendee notification effects. Partial or HTML-only threads cannot be queued through that panel.

Activation requires an isolated rehearsal and exact live image/config reconciliation first. Candidate settings: `V79_GOOGLE_WORKFORCE_ENABLED=1`, `V79_GOOGLE_CREDENTIAL_FILE=/run/secrets/v79-google-credentials.json`, and a read-only credential mount **only in Hub**. Do not add it to v79-business-agent. Ensure mounted file UID matches the Hub process and its private mode survives the mount; do not relax file permissions to fix an identity mismatch. Preserve all current ordered Compose files, images, settings and schedules until that guarded cutover is prepared.

No unattended Google worker/poller or AI draft generator is enabled by this source. The initial UI supports manual text preparation and owner-approved execution. Automatic drafts, bounded V79 business-email classification, source-message deduplication, follow-up reminders and whole-workforce model/live acceptance remain outstanding.

## Latest host evidence (owner-provided)
19 October: v79sl reports Hub image `sha256:18ccee0838ecce6a29d34ddd45b4ab6363aa33a45193366c873d6e3f47dca2a8` and Agent image `sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f`, both running/healthy. Workboard, actions and reports flags are 1. Agent has no matching Google/workforce env keys. This does not prove no token files exist elsewhere.

Timers show the last morning trigger at 19 October 12:00:17 UTC (08:00:17 AST) and last evening trigger at 18 October 23:00:17 UTC (19:00:17 AST), plus the G2 approved-task worker timer. Timer entries establish triggers, not successful report generation, correct evidence or notification delivery. Existing reporting acceptance remains open.

References: https://developers.google.com/identity/protocols/oauth2/native-app ; https://developers.google.com/identity/protocols/oauth2/ ; https://developers.google.com/workspace/calendar/api/auth .

