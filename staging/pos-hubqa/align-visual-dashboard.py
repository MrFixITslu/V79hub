#!/usr/bin/env python3
"""Guarded visual-only Hub overview + sidebar overlay on private POS staging.

Read-only preflight is default. --apply operates ONLY on isolated staging Hub
and reuses the exact reviewed MFA, POS, rollback, and frontend build guards.
Never replaces App.tsx, Login.tsx, routes, backend, admin, billing or keys.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

HELPER_PATH = Path(__file__).with_name("align-dashboard-ui.py")
spec = importlib.util.spec_from_file_location("v79_stage_guards", HELPER_PATH)
assert spec and spec.loader
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)

VISUAL_IMAGE = "v79hub:pos-hubqa-dashboard-visual-20261109-r1"
VISUAL_PIN = guards.ROOT / "approved-dashboard-visual.json"
SOURCE_SHA = {
    "src/components/HubOverview.tsx":
        "b00c05056dd7a8dfcfb6055425644d26ac6880472b714b17461995b16a381096",
    "src/components/Sidebar.tsx":
        "c690df486b7f43d606ce50486bb94e077eccd33a8ed090e1009920537de5cce0",
}
DIRECT_IMPORTS = {
    "src/components/HubOverview.tsx":
        {"src/types", "src/lib/appLaunch", "src/lib/dashboardTruth"},
    "src/components/Sidebar.tsx":
        {"src/types"},
}
REQUIRED_APP_PROPS = {
    "HubOverview": {
        "ecosystemApps": "ecosystemApps",
        "onNavigate": "setCurrentView",
        "user": "user",
        "organizationName": "organizationName",
    },
    "Sidebar": {
        "currentView": "currentView",
        "onViewChange": "setCurrentView",
        "onLogout": "handleLogout",
        "user": "user",
        "organizationName": "organizationName",
    },
}
# Only the already-established navigation views (not newly introduced screens).
REQUIRED_STAGE_VIEWS = (
    "overview", "connections", "team", "security", "billing",
    "admin", "assistant",
)
PROTECTED_SOURCES = (
    "src/App.tsx",
    "src/components/Login.tsx",
    "src/index.css",
    "src/types.ts",
    "src/lib/appLaunch.ts",
    "src/lib/dashboardTruth.ts",
    "src/components/AdminConsole.tsx",
    "src/components/OwnerAssistant.tsx",
    "src/components/WorkforceActionPanel.tsx",
)

def require(ok, why):
    guards.ensure(ok, why)

def extract_bytes(container, filename, directory):
    out = directory / (container[:12].replace("/", "_") + "__" +
                       filename.replace("/", "_"))
    require(guards.extract(container, filename, out),
            "Expected private/candidate frontend file absent: " + filename)
    data = out.read_bytes()
    require(len(data) <= 1_000_000,
            "Frontend source exceeded 1MB: " + filename)
    return data

def check_app_contract(src):
    text = src.decode("utf-8")
    for component, props in REQUIRED_APP_PROPS.items():
        m = re.search(r"<" + re.escape(component) + r"\b([\s\S]{0,1500}?)/>", text)
        require(m is not None, "Staging App lost " + component + " render contract")
        jsx = m.group(1)
        for name, var in props.items():
            require(re.search(r"\b" + name + r"\s*=\s*\{\s*" +
                              var + r"\s*\}", jsx) is not None,
                    "Staging App prop drift: " + component + "." + name)
    for view in REQUIRED_STAGE_VIEWS:
        require(re.search(r'currentView\s*===\s*["\']' + view + r'["\']', text)
                is not None,
                "Staging App does not render required navigation: " + view)
    require('"/api/auth/me"' in text and
            "/api/auth/logout" in text,
            "Stage App cookie-session or logout contract changed")

def scan(stage, live, scratch):
    """Explicitly limited two-file import graph; no broad source grafting."""
    candidate_id = guards.inspect(guards.CANDIDATE, "image")["Id"]
    source_pin = json.loads((guards.ROOT / "approved-login-overlay.json").read_text())
    require(source_pin.get("source_image_id") == candidate_id,
            "Connected Login candidate image identity changed")
    cid = guards.candidate_container()
    hashes = {}
    protected = {}
    try:
        stage_app = extract_bytes(guards.STAGE_NAME, "src/App.tsx", scratch)
        check_app_contract(stage_app)
        for filename in PROTECTED_SOURCES:
            protected[filename] = guards.digest(
                extract_bytes(guards.STAGE_NAME, filename, scratch))
        for filename, sha in SOURCE_SHA.items():
            new = extract_bytes(cid, filename, scratch)
            old = extract_bytes(guards.STAGE_NAME, filename, scratch)
            live_data = extract_bytes(guards.LIVE_NAME, filename, scratch)
            require(guards.digest(new) == sha,
                    "Approved visual source fingerprint changed: " + filename)
            require(new == live_data and new != old,
                    "Visual candidate differs from live or already matches stage: " +
                    filename)
            refs = guards.relative_imports(filename, new.decode("utf-8"))
            reviewed = DIRECT_IMPORTS[filename]
            if refs != reviewed:
                # Diagnostic only: show exact import paths, never source or secrets.
                # The approved import allowlist remains unchanged and fails shut.
                for ref in sorted(refs - reviewed):
                    print("UNREVIEWED_VISUAL_IMPORT=" + filename + " -> " + ref,
                          flush=True)
                for ref in sorted(reviewed - refs):
                    print("MISSING_APPROVED_VISUAL_IMPORT=" + filename + " -> " +
                          ref, flush=True)
            require(refs == reviewed,
                    "Visual component new relative imports not reviewed: " + filename)
            for ref in sorted(refs):
                possibilities = guards.dependency_paths(ref)
                found = False
                for dep in possibilities:
                    tmp = scratch / ("source__" + dep.replace("/", "_"))
                    if guards.extract(cid, dep, tmp):
                        found = True
                        candidate_dep = tmp.read_bytes()
                        stage_dep = extract_bytes(guards.STAGE_NAME, dep, scratch)
                        require(candidate_dep == stage_dep,
                                "Visual dependency mismatch: " + dep)
                        break
                require(found, "Visual source import absent: " + ref)
            target = scratch / filename
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            target.write_bytes(new)
            hashes[filename] = sha
            print("APPROVED_VISUAL_COMPONENT=" + filename + " SHA256=" + sha)
        # Current CSS was previously approved for the Version 3 Connected
        # Workspace design; don't replace it or the login page.
        require(protected["src/index.css"] ==
                "ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c",
                "Approved login stylesheet fingerprint drift")
        # Auth/login and component imports are all known to match the current
        # stage, not assumed merely because the component prop names match.
        print("STAGE_APP_AUTH_NAVIGATION_PROPS=PASS")
        print("DIRECT_VISUAL_IMPORT_PARITY=PASS")
        print("STAGE_LOGIN_CSS_AND_ADMIN_SOURCES_FINGERPRINTED=PASS")
        return hashes, protected
    finally:
        guards.run("docker", "rm", cid, check=False)

def verify_protected_sources(stage, protected):
    current = guards.inspect(guards.STAGE_NAME)
    for filename, expected in protected.items():
        actual = guards.run("docker", "exec", guards.STAGE_NAME,
                            "sha256sum", "/app/" + filename).stdout.split()[0]
        require(actual == expected,
                "A protected frontend source changed during visual-only overlay: " +
                filename)
    require(current["Config"]["Image"] == VISUAL_IMAGE,
            "Private stage image tag unexpectedly changed")
    print("APP_LOGIN_ADMIN_ROUTING_AND_WORKFORCE_SOURCES_UNCHANGED=PASS")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Build and recreate only PRIVATE staging Hub, with rollback")
    args = parser.parse_args()
    # Changing only the named image/tag/components lets us reuse the original
    # hardened stage topology, immutable prior image, MFA, isolated POS, and
    # checkpoint/rollback implementation without re-implementing those guards.
    guards.AFTER = VISUAL_IMAGE
    guards.PIN = VISUAL_PIN
    guards.COMPONENTS = tuple(SOURCE_SHA)
    stage, live, stage_pos, live_pos, compose, previous = guards.check_preflight()
    require(not (guards.ROOT / "approved-dashboard-alignment.json").exists(),
            "An independent 3-component dashboard overlay already exists")
    print("PRIVATE_VISUAL_STAGE_PREFLIGHT=PASS")

    with tempfile.TemporaryDirectory(
        prefix="v79-visual-dashboard-", dir=guards.ROOT
    ) as scratch_dir:
        scratch = Path(scratch_dir)
        hashes, protected = scan(stage, live, scratch)
        if not args.apply:
            print("PRIVATE_VISUAL_DASHBOARD_DRY_RUN=PASS")
            print("NO_STAGING_OR_PRODUCTION_DEPLOYMENT=PASS")
            return
        image_id = guards.build(scratch) # Offline build, only 2 source files.
        checkpoint = guards.checkpoint(compose)
        print("PRIVATE_VISUAL_DASHBOARD_CHECKPOINT=" + str(checkpoint))
        updated_compose = compose.replace(
            "    image: " + guards.BEFORE + "\n",
            "    image: " + VISUAL_IMAGE + "\n", 1
        )
        guards.save_compose(updated_compose)
        try:
            guards.run("docker", "compose", "--env-file", ".env",
                       "-f", "compose.yml", "config", "--quiet", cwd=guards.ROOT)
            guards.restart()
            guards.verify_after(stage, live, stage_pos, live_pos, image_id, hashes)
            verify_protected_sources(stage, protected)
        except Exception:
            print("STAGING_VISUAL_DASHBOARD_ROLLBACK_ATTEMPT", flush=True)
            guards.save_compose(compose)
            try:
                guards.restart()
                print("PREVIOUS_MFA_POS_STAGE_RESTORED=PASS", flush=True)
            except Exception as exc:
                print("STAGING_VISUAL_DASHBOARD_ROLLBACK_FAILED=" + str(exc),
                      flush=True)
            print("VISUAL_DASHBOARD_CHECKPOINT_RETAINED=" + str(checkpoint),
                  flush=True)
            raise

        record = {
            "dashboard_image": VISUAL_IMAGE,
            "image_id": image_id,
            "base_stage_image": guards.BEFORE,
            "base_stage_image_id": stage["Image"],
            "dashboard_source_image": guards.CANDIDATE,
            "dashboard_source_image_id":
                guards.inspect(guards.CANDIDATE, "image")["Id"],
            "changed_files_sha256": hashes,
            "protected_file_sha256": protected,
            "checkpoint": str(checkpoint),
            "applied_utc": datetime.now(timezone.utc).isoformat(),
        }
        fd = os.open(VISUAL_PIN, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")
        print("PRIVATE_STAGING_VISUAL_DASHBOARD=PASS")
        print("DASHBOARD_BROWSER_REVIEW_AND_MFA_POS_SSO=NOT_YET_VERIFIED")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, UnicodeError, ValueError, KeyError,
            subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
