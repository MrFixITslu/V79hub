#!/usr/bin/env python3
"""Owner-only, read-only V79 GitHub delivery overview.

This tool never writes GitHub data, invokes shell commands, or checks live services.
It deliberately marks runtime health, deployed source, and customer readiness UNKNOWN.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import urllib.error
import urllib.request

OWNER = "MrFixITslu"
REPOSITORIES = (
    "V79hub", "V79Tiquet", "V79-Sentinel", "V79Marketing",
    "V79acaedmy", "V79POS",
)
# A small owner-approved register, not an AI-generated assessment of readiness.
# Each tuple: lane, repo, issue/PR number, type, short internal label, next review.
TRACKED = (
    ("P1 Hub + Tiquet", "V79hub", 113, "issue", "Commercial launch board", "Maintain release gates"),
    ("P1 Hub + Tiquet", "V79Tiquet", 35, "issue", "Session revocation risk", "Independent security review"),
    ("P1 Hub + Tiquet", "V79Tiquet", 37, "pr", "Session security candidate", "Review draft exact head"),
    ("P1 AI workforce", "V79hub", 152, "issue", "CEO/COO coordination", "Track validated work and decisions"),
    ("P1 AI workforce", "V79hub", 138, "issue", "Founder-only agent pilot", "Confirm installed runtime"),
    ("P1 AI workforce", "V79hub", 145, "pr", "Owner-approved work queue", "Preserve approval boundary"),
    ("P1 AI workforce", "V79hub", 146, "pr", "Marketing approvals/tracking", "Check real provider receipt"),
    ("P1 Sentinel", "V79-Sentinel", 15, "issue", "Owned-service protection", "Validate actual collector evidence"),
    ("P1 Sentinel", "V79-Sentinel", 14, "pr", "Isolated NOC packaging", "Resolve scanner hold privately"),
    ("P1 Sentinel", "V79hub", 124, "issue", "Signed COO evidence gate", "Do not trust simulated telemetry"),
    ("P2 isolated apps", "V79acaedmy", 25, "issue", "Academy publishing", "Reproduce in isolated tests"),
    ("P2 isolated apps", "V79POS", 12, "issue", "Hub-to-POS SSO", "Validate direct/dashboard paths"),
    ("P2 isolated apps", "V79Marketing", 28, "pr", "Publication tracking", "Confirm true provider receipt"),
)
LANES = ("P1 Hub + Tiquet", "P1 AI workforce", "P1 Sentinel", "P2 isolated apps")
API = "https://api.github.com"
MAX_PAGES = 3
MAX_RESPONSE_BYTES = 5_000_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not redirect a bearer token to an untrusted host.


def _github_page(repo: str, page: int, token: str | None) -> list[dict]:
    """Strict fixed-host GET; no URL, pathname, or method from API payloads."""
    assert repo in REPOSITORIES
    assert 1 <= page <= MAX_PAGES
    request = urllib.request.Request(
        f"{API}/repos/{OWNER}/{repo}/issues?state=open&per_page=100&page={page}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "v79-owner-readonly-workboard/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="GET",
    )
    # Ignore machine-configured HTTP proxies, which must not receive our token.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=8) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("UNEXPECTED_RESPONSE")
    return data


def collect_one(repo: str, token: str | None, fetch_page=_github_page) -> dict:
    """Fail closed on errors or incomplete/ambiguous GitHub pages."""
    items = {}
    try:
        complete = False
        for page in range(1, MAX_PAGES + 1):
            batch = fetch_page(repo, page, token)
            if not isinstance(batch, list) or len(batch) > 100:
                raise ValueError("INVALID_PAGE")
            for obj in batch:
                if not isinstance(obj, dict):
                    raise ValueError("INVALID_ITEM")
                number = obj.get("number")
                if type(number) is not int or number <= 0:
                    raise ValueError("INVALID_NUMBER")
                if number in items:
                    raise ValueError("DUPLICATE_NUMBER")
                kind = "pr" if "pull_request" in obj else "issue"
                items[number] = {
                    "kind": kind,
                    "updated_at": obj.get("updated_at") if isinstance(obj.get("updated_at"), str) else None,
                }
            if len(batch) < 100:
                complete = True
                break
        return {"state": "COMPLETE" if complete else "INCOMPLETE", "items": items}
    except urllib.error.HTTPError as exc:
        reason = "ACCESS_DENIED_OR_RATE_LIMIT" if exc.code in (401, 403, 404, 429) else "API_ERROR"
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        reason = "UNAVAILABLE_OR_INVALID"
    return {"state": "UNAVAILABLE", "reason": reason, "items": {}}


def build_report(sources: dict[str, dict], collected_at: str) -> dict:
    results = []
    for lane, repo, number, kind, label, action in TRACKED:
        src = sources.get(repo, {"state": "UNAVAILABLE", "items": {}})
        known = src.get("items", {}).get(number)
        state = src.get("state")
        if state == "UNAVAILABLE" or state is None:
            status = "UNKNOWN_SOURCE"
        elif known and known.get("kind") == kind:
            status = "OPEN_IN_GITHUB"
        elif state == "INCOMPLETE":
            status = "UNKNOWN_INCOMPLETE"
        else:
            # Not listed among open issues does NOT prove fixed/merged/closed.
            status = "NOT_LISTED_AS_OPEN"
        results.append({
            "lane": lane, "repo": repo, "number": number, "kind": kind,
            "label": label, "review": action, "github_state": status,
            "updated_at": known.get("updated_at") if known and status == "OPEN_IN_GITHUB" else None,
            "url": f"https://github.com/{OWNER}/{repo}/{'pull' if kind == 'pr' else 'issues'}/{number}",
        })
    return {
        "version": 1,
        "collected_at": collected_at,
        "evidence_source": "GitHub open issues/PRs read-only (not installed application state)",
        "runtime_health": "UNKNOWN",
        "deployed_revision": "UNKNOWN",
        "customer_security_go": "UNKNOWN_REQUIRES_INDEPENDENT_EVIDENCE",
        "agent_autonomy": "NOT_AUTHORIZED_BY_THIS_TOOL",
        "repositories": [
            {"repo": repo,
             "fetch_state": sources.get(repo, {}).get("state", "UNAVAILABLE"),
             "error_class": sources.get(repo, {}).get("reason")}
            for repo in REPOSITORIES
        ],
        "tracked": results,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# V79 Digital — COO owner-only workboard",
        f"GitHub evidence collected: {report['collected_at']}",
        "**This is a code/issue tracker, NOT live service monitoring or deployment approval.**",
        "Installed app health, active runtime source, and external-customer readiness: **UNKNOWN**.",
    ]
    for lane in LANES:
        lines.extend(["", f"## {lane}"])
        for item in report["tracked"]:
            if item["lane"] != lane:
                continue
            status = item["github_state"].replace("_", " ")
            lines.append(f"- **{item['label']}** — {status} — {item['review']} ({item['url']})")
    missing = [x["repo"] for x in report["repositories"] if x["fetch_state"] != "COMPLETE"]
    if missing:
        lines.append("\n**Incomplete/unavailable GitHub sources:** " + ", ".join(missing) + ". Do not infer closure.")
    lines.append("\n**Founder sign-off required:** production deployment, payments, real invitations, security exceptions and agent permissions.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only, fail-closed founder COO GitHub workboard")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda repo: collect_one(repo, token), REPOSITORIES))
    report = build_report(dict(zip(REPOSITORIES, results)), now)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    # Partial/unavailable sources are reflected in report; refuse a false success exit.
    return 0 if all(x["state"] == "COMPLETE" for x in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
