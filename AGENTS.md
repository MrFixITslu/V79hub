# V79 UI/UX development standards

## When to use Impeccable
For any frontend design, redesign, layout, interaction, UX copy, accessibility, responsive, animation or visual-polish task, consult the installed Impeccable v4.8.0 source at:
`/home/firelion/.agents/skills/impeccable/SKILL.md`
Read the relevant reference playbook for the task. For backend-only work, do not force the design skill into the workflow. If the skill is unavailable, state that and use the project’s existing design guidance; do not claim it was loaded.

The Impeccable package is an external tool. Do not enable its hooks, remote browser, automatic binary downloads or any executable helper without verifying the required code and permitted environment. Reading guidance does not grant execution privileges.

## V79 product standards
- Design first. For a new or substantially redesigned surface, present three genuinely distinct design directions and their trade-offs before implementation. Keep existing identity for refinements.
- Treat public marketing pages as Persuade, operational dashboards and application forms as Operate, learning or documentation as Read.
- Keep the existing V79 branding, current approved product positioning, clean Apple-like typographic discipline and Caribbean-wide audience. Avoid generic AI-looking purple gradients.
- Use real product features, data, screenshots and rights-cleared assets. No fabricated customers, testimonials, certifications or claims.
- Plan desktop, tablet and phone layouts; spacing, hierarchy, navigation, focus, keyboard access, colour contrast, reduced motion, empty/loading/error/session-expiry states and data persistence.
- Verify rendered UI and user journeys at the actual breakpoints; review accessibility and performance; distinguish a design audit from a penetration test.
- Do not change other product features, payment state, authorisation, MFA, tenancy, secrets or deployment without the usual approved workflow.
- Prefer focused tests and evidence-based checks. Avoid rerunning previously passed tests unless code or inputs have changed. Keep a tested rollback path for production changes.

## Skill Manager boundary
Hub -> Owner Assistant -> Skill Library provides founder-approved, text-only advisory add-ons for selected owner-chat workers. It is not a coding agent, an executable skill runner, or a means of bypassing owner approval. The V79 Impeccable UI/UX preset is deliberately a curated advisory subset of the installed full skill.
