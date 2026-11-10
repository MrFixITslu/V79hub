#!/usr/bin/env python3
"""Read-only audit of the extra workspace CSS imported by the approved dashboard.

Never starts containers, builds images, changes stage files, prints CSS contents,
or mutates production. Uses the exact existing staging and source-image guards.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile

HELPER = Path(__file__).with_name("align-dashboard-ui.py")
spec = importlib.util.spec_from_file_location("v79_stage_css_guard", HELPER)
assert spec and spec.loader
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)

SOURCE = "src/components/HubOverview.tsx"
CSS = "src/workspace.css"
KNOWN_SHA = "b00c05056dd7a8dfcfb6055425644d26ac6880472b714b17461995b16a381096"
EXPECTED_IMPORTS = {
    "src/types", "src/lib/appLaunch", "src/lib/dashboardTruth", CSS
}


def require(ok, reason):
    guards.ensure(ok, "Workspace CSS audit: " + reason)


def optional_copy(container, name, scratch):
    target = scratch / (container[:12].replace("/", "_") + "__" +
                        name.replace("/", "_"))
    if not guards.extract(container, name, target):
        return None
    data = target.read_bytes()
    require(0 < len(data) <= 1_000_000, name + " size invalid")
    return data


def main():
    guards.check_preflight()
    source_pin = json.loads(
        (guards.ROOT / "approved-login-overlay.json").read_text())
    candidate_image = guards.inspect(guards.CANDIDATE, "image")
    require(source_pin.get("source_image_id") == candidate_image["Id"],
            "candidate source image identity changed")
    print("WORKSPACE_CSS_STAGE_SAFETY=PASS")

    cid = guards.candidate_container()
    try:
        with tempfile.TemporaryDirectory(
            prefix="v79-workspace-css-audit-", dir=guards.ROOT
        ) as location:
            scratch = Path(location)
            candidate_overview = optional_copy(cid, SOURCE, scratch)
            live_overview = optional_copy(guards.LIVE_NAME, SOURCE, scratch)
            require(candidate_overview is not None and
                    candidate_overview == live_overview and
                    hashlib.sha256(candidate_overview).hexdigest() == KNOWN_SHA,
                    "overview is not exact approved candidate and live source")
            imports = guards.relative_imports(
                SOURCE, candidate_overview.decode("utf-8"))
            for extra in sorted(imports - EXPECTED_IMPORTS):
                print("UNREVIEWED_OVERVIEW_IMPORT=" + extra)
            for missing in sorted(EXPECTED_IMPORTS - imports):
                print("MISSING_EXPECTED_OVERVIEW_IMPORT=" + missing)
            require(imports == EXPECTED_IMPORTS,
                    "overview imports differ from four reviewed imports")
            print("OVERVIEW_CSS_IMPORT_CONFIRMED=PASS")

            candidate_css = optional_copy(cid, CSS, scratch)
            live_css = optional_copy(guards.LIVE_NAME, CSS, scratch)
            stage_css = optional_copy(guards.STAGE_NAME, CSS, scratch)
            require(candidate_css is not None and live_css is not None,
                    "workspace stylesheet missing from candidate or live")
            print("WORKSPACE_CSS_CANDIDATE_SHA256=" +
                  hashlib.sha256(candidate_css).hexdigest())
            print("WORKSPACE_CSS_LIVE_SHA256=" +
                  hashlib.sha256(live_css).hexdigest())
            print("WORKSPACE_CSS_BYTES=" + str(len(candidate_css)))
            print("WORKSPACE_CSS_STAGE=" +
                  ("ABSENT" if stage_css is None else
                   ("IDENTICAL" if stage_css == candidate_css else "DIFFERENT")))
            require(candidate_css == live_css,
                    "candidate workspace stylesheet differs from live")
            css = candidate_css.decode("utf-8")
            import_count = len(re.findall(r"@import\b", css, re.I))
            url_count = len(re.findall(r"url\s*\(", css, re.I))
            external_count = len(re.findall(
                r"url\s*\(\s*['\"]?\s*(?:https?:)?//", css, re.I))
            print("WORKSPACE_CSS_AT_IMPORT_COUNT=" + str(import_count))
            print("WORKSPACE_CSS_URL_REFERENCE_COUNT=" + str(url_count))
            print("WORKSPACE_CSS_EXTERNAL_URL_COUNT=" + str(external_count))
            print("WORKSPACE_CSS_MATCHES_RUNNING_LIVE=PASS")
            print("WORKSPACE_CSS_AUDIT_READ_ONLY=PASS")
            print("STAGING_BUILD_AND_DEPLOYMENT=NOT_ATTEMPTED")
    finally:
        guards.run("docker", "rm", cid, check=False)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, UnicodeError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
