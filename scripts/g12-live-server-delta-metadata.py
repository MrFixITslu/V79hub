#!/usr/bin/env python3
"""Read-only source-delta metadata for the WiPay-pinned live Hub.

Runs on the authorized Acer against an exact audited GitHub commit.
Reads running /app/server.ts over SSH into memory; no server writes.
Prints only hashes, changed line ranges, and fixed CATEGORY LABELS.
It deliberately NEVER prints live source, code excerpts, HTTP response bodies,
credentials, environment values, or an assertion that deployment is safe.
"""
from __future__ import annotations
import collections
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

SOURCE_COMMIT = "7bbea7b597910e52d27d8fece6b9089a01fcec86"
EXPECTED_LIVE_BASELINE_BLOB = "b69c46637970bd7dc95f3cf45f8a29fee5a10e3a"
EXPECTED_PREVIOUS_LIVE_BLOB = "349c54621b8bb4d3abe54bf50ffade9db768f4e9"
MAX_BYTES = 2 * 1024 * 1024
MAX_HUNKS_DISPLAYED = 80
CATEGORIES = (
    ("wipay", re.compile(r"wipay", re.I)),
    ("billing", re.compile(r"billing|invoice|receipt|subscription|entitlement", re.I)),
    ("sentinel", re.compile(r"sentinel|noc|capture", re.I)),
    ("agent", re.compile(r"agent|executive|handoff", re.I)),
    ("authentication", re.compile(r"authentication|login|session|mfa|token", re.I)),
    ("onboarding", re.compile(r"invitation|invite|registration|onboarding|organization", re.I)),
    ("other", re.compile(r".", re.S)),
)
ROUTE_RE = re.compile(r"""app\.(?:get|post|put|patch|delete|use)\(\s*['"](/[^'"]+)['"]""")

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def checked_run(args, *, timeout=35, cwd=None) -> bytes:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       cwd=cwd, timeout=timeout, check=False)
    if p.returncode != 0:
        raise RuntimeError("Verified read-only subprocess unavailable or returned nonzero")
    if len(p.stdout) > MAX_BYTES:
        raise RuntimeError("STOP: source exceeds size bound")
    return p.stdout

def categories(data: str) -> list[str]:
    return [label for label, matcher in CATEGORIES[:-1] if matcher.search(data)] or ["other"]

def route_family(path: str) -> str:
    if "wipay" in path.lower():
        return "wipay"
    if path.startswith("/api/agent/") or path.startswith("/internal/agent/"):
        return "agent"
    if path.startswith("/api/billing/"):
        return "billing"
    if path.startswith("/api/"):
        return "other_api"
    return "other"

def safe_report(expected: bytes, live: bytes) -> dict:
    main = expected.decode("utf-8", errors="replace").splitlines()
    running = live.decode("utf-8", errors="replace").splitlines()
    matcher = difflib.SequenceMatcher(a=main, b=running, autojunk=True)
    hunks = []
    counts = collections.Counter()
    for tag, ref_a, ref_b, runtime_a, runtime_b in matcher.get_opcodes():
        if tag == "equal":
            continue
        text = "\n".join(main[ref_a:ref_b] + running[runtime_a:runtime_b])
        category = categories(text)
        for name in category:
            counts[name] += 1
        if len(hunks) < MAX_HUNKS_DISPLAYED:
            hunks.append({
                "kind": tag,
                "github_lines": [ref_a + 1, ref_b],
                "live_lines": [runtime_a + 1, runtime_b],
                "categories": category,
            })

    def routes(lines):
        return collections.Counter(route_family(m.group(1)) for m in
            ROUTE_RE.finditer("\n".join(lines)))
    expected_routes = routes(main)
    live_routes = routes(running)
    families = sorted(set(expected_routes) | set(live_routes))
    return {
        "purpose": "Live WiPay-pinned Hub source comparison — READ ONLY",
        "source_commit": SOURCE_COMMIT,
        "expected_repo_server_blob": EXPECTED_LIVE_BASELINE_BLOB,
        "repository_verified": git_blob(expected) == EXPECTED_LIVE_BASELINE_BLOB,
        "live_server_blob": git_blob(live),
        "live_matches_previous_audit": git_blob(live) == EXPECTED_PREVIOUS_LIVE_BLOB,
        "live_matches_repository": expected == live,
        "github_line_count": len(main),
        "live_line_count": len(running),
        "changed_block_count": sum(counts.values()) if False else len([op for op in matcher.get_opcodes() if op[0] != "equal"]),
        "changed_blocks_by_category": dict(sorted(counts.items())),
        "changed_hunks_shown": hunks,
        "changed_hunks_truncated": len(hunks) >= MAX_HUNKS_DISPLAYED,
        "registered_route_families": {
            family: {"github": expected_routes[family], "live": live_routes[family]}
            for family in families
        },
        "source_code_printed": False,
        "production_modified": False,
        "release_authorized": False,
    }

def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        baseline = b'app.get("/api/billing/wipay/return", cb);\nconst ok = 1;\n'
        runtime = b'app.get("/api/billing/wipay/return", cb);\nconst ok = 2;\n'
        result = safe_report(baseline, runtime)
        assert result["changed_block_count"] == 1
        assert result["changed_hunks_shown"][0]["categories"] == ["other"]
        assert result["source_code_printed"] is False
        print("READ_ONLY_DELTA_SELF_TEST_PASS")
        return 0
    if sys.argv[1:]:
        raise RuntimeError("No arguments allowed; run from pinned checkout")

    repo = Path(__file__).resolve().parent.parent
    revision = checked_run(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip()
    if revision != SOURCE_COMMIT:
        raise RuntimeError("STOP: checkout does not match pinned audited commit")
    expected = checked_run(["git", "show", f"{SOURCE_COMMIT}:server.ts"], cwd=repo)
    if git_blob(expected) != EXPECTED_LIVE_BASELINE_BLOB:
        raise RuntimeError("STOP: GitHub baseline code differs from expected blob")
    live = checked_run([
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10", "firelion@v79sl",
        "docker", "exec", "v79-hub", "cat", "/app/server.ts"
    ], timeout=35)
    result = safe_report(expected, live)
    print(json.dumps(result, sort_keys=True, indent=2))
    if not result["live_matches_previous_audit"]:
        print("STOP: running source has changed since last inventory", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("STOP: source comparison could not be verified: " +
              type(error).__name__, file=sys.stderr)
        sys.exit(2)
