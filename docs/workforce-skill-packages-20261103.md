# V79 Skill Package Manager — guarded v1 (3 November 2026)

## What is implemented
The existing Hub owner-only Skill Library now accepts **skill-only ZIP packages** alongside its legacy text-only custom skills. A ZIP must contain exactly one `SKILL.md` (up to 64 KB). If that file exceeds the agent's 6 KB context ceiling, include a separate `ADVISORY.md` of 1–6000 UTF-8 bytes. Only the advisory text can be sent to scheduled agents.

ZIP import is inert: it performs bounded inspection in a Python subprocess, rejects unsafe paths, symlinks, encrypted members, duplicate names, nested archives and native binaries, and stores the original ZIP as an immutable, SHA-256-addressed quarantine file. The package index has an HMAC envelope with an independently named domain separator. Import never evaluates archive files.

Hub → Owner Assistant → Skill Library → ZIP skill packages:
1. Upload a **skill-only** ZIP of at most 1.35 MB compressed; at most 120 entries / 4 MB expanded.
2. Inspect filename, SHA-256, file count, entrypoints and advisory scope.
3. Approve the exact ZIP digest with a **fresh founder MFA challenge**. Only this changes status from quarantined to approved. Uploaded code still does not execute.
4. Optionally assign built-in hook policies and scheduled advisory jobs with fresh MFA.
5. Revoke approval using fresh MFA to revoke execution eligibility and immediately clear hooks and scheduled bindings.

Package metadata and archive bytes are in the existing persistent Hub data bind at `/app/data/workforce-skill-packages/`; backup and restore the archive files **and** sealed `packages.json` together with the existing registry secret. Restoring only the JSON without the ZIP files deliberately fails closed. There is no database migration, and existing custom skill records and protected built-ins are unmodified.

## Executable scripts — host isolation and manual invocation
The host-side `scripts/v79-skill-package-sandbox.py` requires the exact approved package ID, exact approved digest and a manifest-indexed script path. It re-reads the sealed Hub index, copies and rehashes the archive, revalidates every path and content hash and runs the selected entrypoint in a separate Docker container with:
- network disconnected, read-only root and ZIP extraction mounted read-only;
- unprivileged numeric user 65534, all Linux capabilities dropped, no-new-privileges;
- default seccomp/AppArmor, 24 process limit, 0.5 CPU, 128 MB memory limit, tiny private tmpfs;
- 20-second wall-time limit and bounded stdout/stderr;
- no Hub data volume, token, session, customer data, host project directories or Docker socket.

The runner uses a pinned, already installed image digest; it never pulls an image or passes user-provided shell commands through the host shell. No public API may request execution. The owner must deliberately invoke the command on an authorised host. The container is still **not a formal sandbox security certification**, and kernel/container runtime vulnerabilities remain a risk.

Example (replace only with the exact package values shown in Hub):
```sh
python3 scripts/v79-skill-package-sandbox.py --package pkg-... \
  --approve-sha256 <64-lowercase-hex-digest> --entrypoint scripts/check.py
```

## Automatic design hooks
Impeccable's native detector hook is installed **per development workspace** in the local repos. Its configuration is under `.impeccable/config.json`; provider integration manifests include `.codex/hooks.json`. These hooks analyse supported future UI edits in supported coding-agent environments. They do not auto-deploy, publish or execute an uploaded ZIP's scripts. Each repo uses a symlink to the previously verified Impeccable v4.8.0 skill at `/home/firelion/.agents/skills/impeccable`.

The package hook policy `package-integrity` is enforced by the package store's digest checks whenever the archive is accessed. The `ui-static-review` policy is advisory metadata; the actual per-edit hook is the separately configured Impeccable native detector on the development host.

## Scheduled-agent integration
An authenticated internal endpoint, `GET /internal/workforce/skill-guidance/:job`, uses the preexisting G2 workforce token, rejects browser Origin/Cookie requests and returns only approved, pinned advisory text for an allowlisted job. Script contents and ZIP files are never returned. Jobs are `ceo-daily`, `coo-daily`, `technology-review` and `marketing-review`; maximum two approved packages per job.

The optional post-briefing companion `scripts/v79-scheduled-skill-review.py` can run after the existing morning/evening evidence collectors. It fetches scoped approved text through the internal route and asks the existing local Ollama read-only Owner Assistant for an owner-review-only checklist. A bounded sidecar record is written, **separate from signed business evidence**; model text is never called verified fact. No scripts, hooks, emails, payment actions or G2 jobs are executed by scheduled guidance. If no approved assignment exists, it records `no-approved-assignments` without calling the model. Any failure must not interrupt the existing verified briefing.

The customer's ChatGPT-hosted automations are a separate scheduling system and are not silently modified by this server integration.

## Release safety and acceptance
- Host and image tests: ZIP traversal/bomb/link/digest rejection, immutable quarantine, stale revision, MFA, same-origin, internal bearer-token denial, revocation, scheduled allowlist, built-in skill pins, original text-only skill manager.
- Run built frontend static checks and strict type check in the image.
- Guarded Hub-only image cutover with old image retained, original environment, volumes/networks, service health and API denial checks.
- Do **not** change the independent Business Agent image, G2 permissions, existing canonical evidence collectors or customer services.
- Packages become active **only** after an actual founder MFA approval. Do not spoof or bypass the session to mark an executable archive approved.
- Roll back only the Hub container if candidate health or auth checks fail; never delete signed registries or the previous image until a separate restore exercise.
