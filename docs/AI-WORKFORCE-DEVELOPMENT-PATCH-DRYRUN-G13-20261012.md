# AI Workforce G1.3 — disposable local patch dry-run

Status: **draft source only**, stacked on Development Worker draft PRs #134 and #135. No automatic CI writeback, no production merge/deploy.

## Purpose

Validate that a model-proposed **single-file diff would apply** to the matching source without applying that diff or executing the generated code.

### Required prior gates

1. Founder-supervised runner obtains an isolated, private disposable Git checkout. Its absolute path is NOT supplied by model content.
2. Work order specifies an immutable full-length Git commit and 1–3 allowlisted `agent-service` source or test files.
3. G1.2 validator confirms the requested paths, blob SHA identifiers, excerpts, and output boundaries.
4. G1.2 source proof checks the work-order blob identifiers against Git object contents and pinned HEAD.

### New dry-run checks

- Checkout must be a genuine, private, owner-controlled `/tmp/v79-dev-sandbox-*` directory (platform temporary root), owned by the executing user with mode `0700`.
- Reject symlinks to the checkout, nested Git roots, dirty tracked files, and untracked files.
- Validate every diff against the approved file list with the v0.1 validator. No renames, additional files, binary patches, or model-supplied Git commands.
- Run **only** `git apply --check -` via an argument array and supplied standard input. This checks patch applicability but does **not** apply the patch or execute code.
- Reread `git status` to detect any unexpected modification. Return a SHA-256 fingerprint of each accepted patch without echoing the diff or source.
- Explicitly report `patchApplied=false`, `codeExecuted=false`, `testsExecuted=0`, `githubWrites=0`, `productionWrites=0`, `githubOriginVerified=false`.

A successful result means **only** `PATCH_APPLIES_UNVERIFIED`. It does NOT mean semantic correctness, source origin authentication, release security, test pass, protected app parity, Docker compatibility, or production permission.

### Isolated CI fixtures

Synthetic disposable Git repositories check: valid patch applies without changing a byte; mismatched context fails; dirty checkout refuses; production directory refused; unpinned source refused; multi-file injected diff refused; forged tree blob refused.

### Later gates

- Authenticated trusted-source acquisition (GitHub owner/repository identity and exact immutable SHA, no arbitrary network or model-supplied URLs).
- Model-safe patch format and path validation tightened by red-team tests; isolated preview build/test runner with restricted resources and no secrets or Docker socket.
- Reviewer-approved draft pull requests through a narrow GitHub service identity, branch protection and required test checks.
- CEO/COO backlog prioritization and audit; founder approval of deployments and high-risk actions.

Keep Hub, Tiquet, WiPay, Sentinel, and existing customers/data unchanged. External participants still require completed privacy/auth and critical-security gates before any invitations.
