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
