# AI Workforce Development Worker v0.2 — pinned Git source proof

**Status:** draft, isolated unit-test component only. No process is scheduled or deployed.

## Trust boundary

The existing v0.1 developer can produce review-only model-proposed diffs for exact allowlisted files, but its `sourceBlob` value is **caller supplied**. v0.2 adds a deterministic verifier that must operate on an independently acquired local Git clone pinned to a specified commit.

- The supervisor, never the model, supplies the absolute checkout path.
- `git rev-parse --verify HEAD` must exactly match the 40-character work-order base commit.
- Every requested path must be allowed by the v0.1 development-work-order validator.
- `git ls-tree -z SHA -- path` must yield one ordinary file (not a symlink).
- The Git tree blob SHA must equal the work-order expected blob SHA.
- `git cat-file blob SHA` retrieves bytes from the object database, not from the mutable working directory.
- The verifier recomputes Git's SHA-1 blob identity, enforces a 64-KiB maximum and requires the provided excerpt inside the verified bytes.
- It never clones, fetches, checks out, edits, applies a patch, runs tests or creates a PR. It never displays repository secrets or raw file contents.
- All Git calls use `execFileSync` argument arrays with fixed command names, timeouts and buffer limits, not `sh -c`.

**Truth limitation:** This proves consistency with a *local* pinned Git tree only. A maliciously prepared repository could still contain an attacker-controlled commit and origin. The result explicitly returns `verifiedAgainstGitHubOrigin=false`. A later dedicated worker must establish a trusted GitHub owner/repository identity and fetch a reviewed exact commit, with a restrictive checkout boundary. This verifier does not yet promote draft output to an applied patch or verified test result.

## Testing

`cd agent-service && npm ci && npm run lint && npm test`

New disposable local Git fixtures test positive source proofs and rejection for:
- forged Git blob IDs;
- fabricated excerpts;
- missing or out-of-scope paths;
- HEAD mismatch;
- oversized source;
- nonabsolute repository directory;
- no checkout modification.

## Progression

v0.3 should add a separate *disposable-worktree-only* patch-dry-run runner: independently authenticate source, validate complete diff parser and file list, use a sandbox with no network/secrets, and run build/test with strict CPU, memory and wall-time caps. Only after review should a tightly scoped GitHub app publish **draft** PRs. Human owner approval remains required for release. Do not give the model direct shell, production Docker socket or payment keys.

The existing V79 Hub/Tiquet customer release and independent Sentinel security gate remain separate.
