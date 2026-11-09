# V79 Skill Manager — development candidate, 1 November 2026

## Purpose and decision
Compared: (1) editing source files directly (not accessible), (2) per-worker uploads (drift and repeated approvals), (3) Hub-managed versioned custom instruction registry (chosen).
This implementation extends **Hub → Owner Assistant → Skill Library** without replacing the pinned built-in CEO, COO or six specialist instructions. Custom skills affect advisory **local Ollama chat only**, not scheduled COO/CEO briefings, G2 task execution, Marketing customer Studio, or other worker processes. Do not advertise general worker execution coverage.

## Implemented
- Founder-only CRUD-style workflow: save a draft, validate its format, select workers, activate with fresh MFA, pause and restore a historical version as a new draft.
- Markdown or text import, or paste. No arbitrary ZIP extraction, JavaScript, shell plugins, dependencies, hook scripts or executable content.
- HMAC-sealed registry stored in the existing persistent Hub DATA_DIR as workforce-skill-registry.json, separate from the Hub customer store. Atomic fsync/rename, exclusive lock and compare-and-swap revision; fail closed on tampering, stale writes, simultaneous writers or an abandoned lock. The registry key must be backed up alongside the file.
- At most 100 skills, 30 immutable versions per skill, 6000 UTF-8 bytes per skill, two active custom skills per worker and eight fixed workers.
- All owner/API mutation requests enforce existing authenticated session and same-origin; activation and pause additionally demand a challenge-verified session whose MFA timestamp is at most five minutes old.
- Hub reads validated assignments; only its authenticated internal chat proxy attaches them to the agent request. The agent validates worker names, exact fields, content SHA-256, lengths and version and applies only the selected local role's content as lower-trust advisory guidance. Existing pinned skill, system rules, API permissions and approval paths remain unchanged.
- Audit events contain metadata, actor and action, not raw instructions or credentials. Do not paste secrets into skills.
- Front-end does **not** call automatic code execution or claim static validation is a penetration test.

## Owner-only advisory mode

- When a selected local Ollama chat role has an approved and assigned custom skill, open-ended planning requests can produce **model-authored draft review suggestions** even when no live business metrics are available. This is not automatic task execution.
- Current business measurements remain separately rendered from allowlisted, fresh, source-verified evidence. No model-generated figures are accepted as verified business facts.
- The agent requests structured JSON; only bounded review-step and question fields are rendered. Unknown output fields are ignored, while claims of approval, execution authority, authentication bypass, credential transfer and unverified numeric measurements fail closed.
- If the model is unavailable or its output is rejected, the user receives a read-only fallback with no suggestion that the skill was applied. Deterministic direct factual and priority-brief answers retain their original evidence path.
- An accepted advisory draft is explicitly labelled as **for owner review only**, with an on-screen notice that no action occurred. Semantic model errors remain possible; the bounded output filter is an extra safeguard, not a certification of correctness.

## Built-in Skill Library inspection and improvement review

- The eight **protected original** skills (CEO, COO, Finance, Strategy, Marketing, Customer Service, Technical & Security, Sales) are now viewable by the authenticated owner. The Hub reads exact `workforce/skills/<role>/SKILL.md` content from a fixed known path and checks its pinned Git-blob hash; it fails closed if any original is modified unexpectedly.
- Read-only built-in catalog: `GET /api/agent/skills/builtins`. A specific protected original: `GET /api/agent/skills/builtins/:role`. Neither endpoint accepts a mutation. Both use existing owner-only access controls; ordinary users cannot list or read the protected source.
- **Improve this skill** creates a role-specific editable add-on draft (not an overwrite). The draft incorporates suggestions to check current product state and evidence, rather than trusting older Hub/Tiquet-only P1/P2 assumptions. Original source bytes and protected system instructions never change.
- The editor explicitly distinguishes the **active assigned version** from the newest draft; a read-only selector previews any historical version before restoration or activation. Suggestions remain inactive until reviewed, saved, revalidated, assigned and activated with fresh owner MFA.
- New UI and API tests verify all eight roles, source pin parity with the independent agent, anonymous API denial, desktop/mobile built-in previews and the existing custom skill activation flow.
- Scope limit: this updates **owner chat advisory skills only**. Scheduled CEO/COO jobs and customer-facing marketing skills are separate processes and are **not updated** by these add-on drafts.

## Config / release gating
Both Hub and agent images need the paired candidate; shipping only Hub will cause agent request errors when skills are supplied.
The flag is disabled by default:
- Hub: V79_WORKFORCE_SKILL_MANAGER_ENABLED=0 (turn on only after paired acceptance).
- Hub: V79_WORKFORCE_SKILL_REGISTRY_KEY=<new random independent 32+ byte secret>.
- Hub DATA_DIR must be durable and backed up, including the new registry and its key; do not place sensitive key inside source control.
- Agent uses its existing independent V79_AGENT_API_TOKEN; no new browser credential. Model provider must be local Ollama for active skills.

Source tests are not actual local-model evaluation. Before a guarded production rollout, independently verify: pinned existing role bytes/sha, all new focused tests and both type checks/build, isolated restored registry plus key, real localhost Ollama advisory output, fresh-MFA activation/denial, separate skill/worker isolation, negative prompt-injection samples, cross-origin session denial, desktop/mobile UI, exact paired image/rollback profiles, and founder acceptance. Keep Marketing PR #34 / Hub PR #220 intact and do not merge/deploy until approved.

## Known scope limits / follow-up
- ZIP bundles, AI-authored skill drafts, upload antivirus/malware scanning, semantic adversarial model evaluation, sharing skills across customer businesses, tenant skill editors and scheduled worker-skill injection are **not** enabled by this feature. They need separate design/permissions and negative tests.
- A rule-based text scanner only issues warnings for common patterns and cannot guarantee safe model outputs. A reviewed skill is still untrusted from the perspective of system permissions.
- An unclean shutdown leaving a .lock directory needs owner investigation; do not bypass it by disabling integrity checks. A second Hub replica must not write to the same file without an appropriate distributed locking/storage migration.
- Existing scheduled agents are separate products; a specialist's chat guidance must not be misrepresented as an installed scheduling skill.
- A history cap keeps the most recent 1000 metadata audit events. Requirements for long-term compliance should use an independently preserved audit sink.


## 3 November 2026 — live Skill Manager / Impeccable integration
- The existing owner-only Skill Library is live on Hub and paired with its current Business Agent. The sealed persistent registry passed a live HMAC integrity read; the app remains healthy.
- Hub has been updated to include an owner-selectable **Impeccable v4.8.0 UI/UX advisory template**. This loads an editable text draft in the Skill Library, with the Technical & Security chat worker selected as an initial suggestion. Saving creates a new version; review/validation and fresh MFA are still required before activation.
- The original 63-file Impeccable skill is installed at `/home/firelion/.agents/skills/impeccable/` for future coding-agent workflows, but its executable helpers, downloads and hooks are **not** used by the owner-chat Skill Manager.
- A repository `AGENTS.md` routes approved UI development work to the full installed skill's guidance on the server. That guidance file alone does not grant code execution or deploy capabilities to a worker.
- The Hub-only guarded cutover retained the old Hub container for rollback, preserved all seven mounts and existing environment/network/health settings, and verified six protected peer services.
- The candidate image was built from an explicitly filtered context and passed 11 focused isolated image tests, including role/permission boundaries, stale MFA, cross-origin and preset safety tests. The production public endpoint and unauthenticated skill APIs passed smoke checks.
- Scope remains **text-only skills for selected founder owner-chat workers**. No executable ZIP import, automatic publication, scheduled COO/CEO skill injection, customer Marketing Studio inheritance, or unrestricted development execution is implied.
- Activation of the new preset requires a fresh owner MFA challenge through the existing UI; the release itself never bypasses that approval.
