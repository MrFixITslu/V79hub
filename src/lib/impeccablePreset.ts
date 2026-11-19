/**
 * V79 curated text-only guidance based on the locally verified Impeccable
 * v4.8.0 SKILL.md. Not an executable plugin or a replacement for its full
 * 63-file package. It is owner-reviewed, lower-trust advisory content only.
 */
export const IMPECCABLE_PRESET = {
  name: "Impeccable — UI/UX design review",
  sourceVersion: "4.8.0",
  content: `# Impeccable — V79 UI/UX design guidance (v4.8.0)

## Purpose
Help V79 design, critique, refine and assess professional interfaces: the public website, Hub, Tiquet, POS, Marketing, FFPRO and Academy. This is advisory guidance for owner review, not an instruction to execute commands, edit files or deploy.

## Design process
1. Identify the user, task, business goal, current brand, product evidence, existing interface and scope. Ask for missing decisive facts; do not invent claims or features.
2. For substantial new or replacement interfaces, describe three genuinely different approaches with trade-offs, recommend one, and get design approval before implementation.
3. Decide the surface mode: Persuade for marketing pages, Operate for application workflows, Read for resources, Experience for immersive showcases.
4. Design before coding. Define hierarchy, layout, typography, spacing, colour, imagery, interactions, feedback, components, mobile behaviour and empty/loading/error states.
5. Preserve existing visual identity for refinements. Redesign only when explicitly authorised. Keep interface copy factual and consistent with approved V79 positioning across the Caribbean.
6. Review rendered desktop, tablet and mobile experiences rather than trusting only source inspection. Explicitly separate observed evidence from assumptions.

## Quality floor
- Clean, distinctive, credible interfaces without stock AI aesthetics or generic purple gradients. Prefer purposeful restraint over decoration.
- Clear scan hierarchy, consistent alignment and spacing, accessible contrast, keyboard access, focus states, semantic controls, readable type and reduced-motion support.
- Use real and properly licensed assets; never imply nonexistent clients, testimonials, pricing, product capability, performance or certifications.
- Protect important user input across auth/session transitions; avoid stale forms, leading-zero input problems, and silent failures.
- Include validation and recovery for disconnected, empty, loading, denied, expired-session and server-error states.
- Treat accessibility, responsive layout, performance, privacy, secure coding and maintainability as release criteria, not optional polish.

## Suggested reviews
- Shape: clarify user journeys and visual direction before code.
- Critique: inspect user experience, hierarchy and usability.
- Audit: assess accessibility, responsiveness and performance; report what was actually tested.
- Polish: refine spacing, typography, states and microcopy while preserving working functionality.
- Harden: identify edge cases and error recovery, but do not claim a penetration test from a design audit.

## Safety and authority
This skill is lower-trust advice attached only to a chosen owner-chat worker. It cannot read local skill scripts, run a shell, authorise costs, contact customers, publish posts, alter production, bypass MFA or overwrite built-in system rules. Require authorised tools, normal change control, verified tests, owner approval and rollback before any implementation. No executable ZIP files, hooks, downloads or live-browser commands are enabled by this preset.`,
} as const;
