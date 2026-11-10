#!/usr/bin/env python3
"""Align only the private staging Hub dashboard frontend with approved production UI.

Read-only by default. Source = the independently owner-compared 9 Nov Connected
Login candidate, cross-checked byte-for-byte against the running production
Hub's three dashboard files. Never replaces backend, stage credentials, POS or DB.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = Path("/home/firelion/v79-hub-pos-hubqa-20261109")
STAGE_NAME = "v79-hub-pos-hubqa"
LIVE_NAME = "v79-hub"
POS_NAME = "v79-pos-hubqa-api"
LIVE_POS_NAME = "v79-pos"
STAGE_NET = "v79pos-hubqa-20261109_stage_internal"
BEFORE = "v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1"
CANDIDATE = "localhost/v79-hub-login-connected:20261109-r1"
AFTER = "v79hub:pos-hubqa-dashboard-aligned-20261109-r1"
PIN = ROOT / "approved-dashboard-alignment.json"
PREVIOUS_PIN = ROOT / "approved-login-assets-perms.json"
COMPONENTS = (
    "src/App.tsx",
    "src/components/HubOverview.tsx",
    "src/components/Sidebar.tsx",
)
COMPANIONS = (
    "src/components/Login.tsx",
    "src/index.css",
    "src/components/AppSwitcher.tsx",
    "src/components/WorkspaceConnections.tsx",
    "src/lib/dashboardTruth.ts",
    "index.html",
)
IMPORT_PATTERN = re.compile(
    r"""(?:from\s*|import\s*[\(\s]*)['"](\.[^'"]+)['"]"""
)
IGNORE_EXT = (".ts", ".tsx", ".js", ".jsx", ".css", ".json", ".svg", ".html")
PNG = bytes.fromhex("89504e470d0a1a0a")
PRODUCTS = ("academy", "ffpro", "marketing", "pos", "tiquet")

def ensure(condition, why):
    if not condition:
        raise RuntimeError("STAGING_DASHBOARD_ALIGNMENT_BLOCKED: " + why)

def run(*cmd, cwd=None, check=True):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=cwd, check=check)

def inspect(name, kind="container"):
    return json.loads(run("docker", kind, "inspect", name).stdout)[0]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def env_map(container):
    """Keep exact values, tolerate name syntax Docker accepts and harmless repeats.

    Linux container environment keys are not restricted to Python identifiers.
    Comparing values by key avoids false differences caused by ordering. Never
    expose values, and reject repeated keys if their values disagree.
    """
    data = {}
    for entry in container["Config"].get("Env") or []:
        ensure(isinstance(entry, str) and "=" in entry,
               "Malformed Docker environment entry (contents suppressed)")
        key, value = entry.split("=", 1)
        ensure(bool(key) and "\x00" not in key and "\x00" not in value,
               "Invalid Docker environment entry (contents suppressed)")
        if key in data:
            ensure(data[key] == value,
                   "Conflicting repeated Docker environment key (values suppressed)")
        else:
            data[key] = value
    return data

def ip_of(container):
    net = container["NetworkSettings"]["Networks"]
    ensure(set(net) == {STAGE_NET}, "Stage container attached to an unexpected network")
    value = net[STAGE_NET]["IPAddress"]
    ensure(ipaddress.ip_address(value).is_private, "Stage IP is not private")
    return value

def port_check(container):
    ports = container["HostConfig"].get("PortBindings") or {}
    ensure(set(ports) == {"3040/tcp"} and ports["3040/tcp"] ==
           [{"HostIp": "127.0.0.1", "HostPort": "18082"}],
           "Stage Hub published a non-loopback or extra port")

def get(url, maxbytes=256):
    try:
        with urllib.request.urlopen(url, timeout=9) as response:
            return (response.status, response.headers.get("Content-Type", ""),
                    response.read(maxbytes))
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read(maxbytes)

def check_preflight():
    ensure(os.geteuid() != 0, "Run as stage owner, not root")
    ensure(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.resolve() == ROOT,
           "Staging directory unexpected")
    ensure(not PIN.exists() and not PIN.is_symlink(),
           "Stage dashboard already promoted; do not reapply")
    data = ROOT / "data"
    ensure(data.is_dir() and not data.is_symlink() and
           data.stat().st_uid == os.getuid() and
           stat.S_IMODE(data.stat().st_mode) == 0o700 and
           not any(p.is_symlink() for p in data.rglob("*")),
           "Private stage store owner/permissions changed")
    for file in (ROOT / ".env", ROOT / "compose.yml", PREVIOUS_PIN):
        ensure(file.is_file() and not file.is_symlink() and
               stat.S_IMODE(file.stat().st_mode) == 0o600,
               "Stage config or previous immutable image pin unsafe")
    previous = json.loads(PREVIOUS_PIN.read_text())
    source_pin = ROOT / "approved-login-overlay.json"
    ensure(source_pin.is_file() and not source_pin.is_symlink() and
           stat.S_IMODE(source_pin.stat().st_mode) == 0o600,
           "Previously approved exact Connected Login source pin unavailable")
    original_source = json.loads(source_pin.read_text())
    ensure(original_source.get("source_image") == CANDIDATE and
           original_source.get("source_image_id") ==
           inspect(CANDIDATE, "image")["Id"],
           "Candidate image differs from approved 9 Nov login source ID")
    ensure(previous.get("image") == BEFORE and
           previous.get("approved_css_sha256") ==
           "ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c" and
           previous.get("approved_login_sha256") ==
           "cb250f00742c5bc3f40f119cbc51f626a1fb94f542f254e27b0d3c6884b4c49b",
           "Previous stage image pin or login/CSS fingerprint unexpected")
    before = inspect(STAGE_NAME)
    live = inspect(LIVE_NAME)
    stage_pos = inspect(POS_NAME)
    live_pos = inspect(LIVE_POS_NAME)
    db = inspect("v79-pos-hubqa-db")
    for name, obj in [
        ("Stage Hub", before), ("Live Hub", live),
        ("Stage POS", stage_pos), ("Live POS", live_pos), ("Stage DB", db)
    ]:
        ensure(obj["State"].get("Health", {}).get("Status") == "healthy",
               name + " is not healthy")
    ensure(before["Config"]["Image"] == BEFORE and
           before["Image"] == previous.get("image_id") and
           before["Image"] == inspect(BEFORE, "image")["Id"],
           "Running Hub stage is not the exact previously approved image")
    ensure(set(stage_pos["NetworkSettings"]["Networks"]) == {STAGE_NET} and
           set(db["NetworkSettings"]["Networks"]) == {STAGE_NET} and
           inspect(STAGE_NET, "network")["Internal"] is True,
           "Stage POS/DB or network isolation changed")
    port_check(before)
    stage_env = env_map(before)
    ensure(before["Config"]["User"] == "1000:1000" and
           stage_env.get("V79_REQUIRE_ADMIN_MFA") == "1" and
           stage_env.get("V79_HUB_STORE_BACKEND") == "json" and
           stage_env.get("NODE_ENV") == "development" and
           stage_env.get("POS_BASE_URL") == "http://v79-pos-hubqa-api:8080" and
           stage_env.get("POS_PUBLIC_URL") == "http://127.0.0.1:18081" and
           stage_env.get("APP_URL") == "http://127.0.0.1:18082" and
           stage_env.get("RESEND_API_KEY", "") == "" and
           stage_env.get("WIPAY_ENABLED") == "0" and
           stage_env.get("V79_WORKFORCE_ACTIONS_ENABLED") == "0",
           "Staging MFA, store, signed POS or disabled integration flags changed")
    live_env = env_map(live)
    ensure(stage_env.get("V79_PLATFORM_SHARED_SECRET") and
           stage_env.get("V79_PLATFORM_SHARED_SECRET") !=
           live_env.get("V79_PLATFORM_SHARED_SECRET") and
           stage_env.get("V79_PLATFORM_SHARED_SECRET") !=
           stage_env.get("V79_HUB_SECURITY_KEY") and
           stage_env.get("V79_POS_PLATFORM_SHARED_SECRET") ==
           stage_env.get("V79_PLATFORM_SHARED_SECRET"),
           "Stage secrets appear shared with live or MFA encryption")
    compose = (ROOT / "compose.yml").read_text()
    old_line = "    image: " + BEFORE + "\n"
    ensure(compose.count(old_line) == 1 and
           "container_name: v79-hub-pos-hubqa" in compose and
           'V79_REQUIRE_ADMIN_MFA: "1"' in compose and
           "127.0.0.1:18082:3040" in compose and
           'RESEND_API_KEY: ""' in compose and
           'WIPAY_ENABLED: "0"' in compose,
           "Staging Compose expected image/auth safeguards changed")
    ensure(run("docker", "image", "inspect", AFTER, check=False).returncode != 0,
           "Output tag exists: refuse to overwrite an existing image")
    stage_url = "http://" + ip_of(before) + ":3040"
    ensure(get(stage_url + "/api/health")[0] == 200,
           "Stage Hub health endpoint failed")
    pos_url = "http://" + ip_of(stage_pos) + ":8080"
    ensure(get(pos_url + "/ready")[0] == 200 and
           get(pos_url + "/v1/me")[0] == 401,
           "Stage POS health or anonymous-denial changed")
    return before, live, stage_pos, live_pos, compose, previous

def extract(container, path, out):
    result = run("docker", "cp", container + ":/app/" + path,
                 str(out), check=False)
    return result.returncode == 0 and out.is_file() and not out.is_symlink()

def candidate_container():
    cid = run("docker", "create", "--network", "none", "--entrypoint",
              "sh", CANDIDATE, "-c", ":").stdout.strip()
    ensure(re.fullmatch(r"[0-9a-f]{64}", cid) is not None,
           "Could not create a read-only candidate inspector")
    return cid

def relative_imports(name, contents, outside_src=None):
    """Resolve imports without trusting path traversal outside /app/src.

    Discovery may continue after a suspicious path so all non-source imports
    can be reported at once. Promotion remains blocked for any such import.
    If no collector is passed, preserve fail-closed behaviour for callers.
    """
    parent = PurePosixPath(name).parent
    results = set()
    for ref in IMPORT_PATTERN.findall(contents):
        parts = []
        escaped = False
        for piece in (parent / ref).parts:
            if piece == "..":
                if not parts:
                    escaped = True
                    break
                parts.pop()
            elif piece not in (".", ""):
                parts.append(piece)
        path = "/".join(parts)
        if escaped or not path.startswith("src/"):
            if outside_src is None:
                ensure(False, "Frontend import outside src: " + name +
                       " -> " + ref)
            else:
                outside_src.add((name, ref))
            continue
        results.add(path)
    return results

def dependency_paths(name):
    """Use explicit HTML/TS/JS/CSS filenames as-is, never append a second suffix."""
    if name.endswith(IGNORE_EXT):
        return (name,)
    return tuple(name + ext for ext in IGNORE_EXT) + (
        name + "/index.ts", name + "/index.tsx"
    )


def verify_candidate_dependency_parity(scratch):
    """Block if the proposed 3-component overlay imports other mismatched TS/JS.

    Traverse all relative local imports of proposed components recursively.
    Files already in current stage must equal the approved candidate. Source
    candidate's three changed components are the ONLY allowed differences.
    """
    cid = candidate_container()
    compared = set()
    compared_files = set()
    candidate_bytes = {}
    mismatches = {}
    missing_stage = {}
    missing_candidate = set()
    outside_src = set()
    imported = set(COMPONENTS) | set(COMPANIONS)
    try:
        while imported:
            name = sorted(imported)[0]
            imported.remove(name)
            if name in compared:
                continue
            compared.add(name)
            ensure(len(compared) < 400, "Unexpectedly large frontend dependency graph (limit 399)")
            paths = dependency_paths(name)
            contents = None
            actual = None
            for p in paths:
                tmp = scratch / "compare" / p.replace("/", "__")
                tmp.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if extract(cid, p, tmp):
                    contents = tmp.read_bytes()
                    actual = p
                    break
            if actual is None:
                missing_candidate.add(name)
                continue
            ensure(contents is not None and len(contents) <= 1_000_000,
                   "Candidate frontend file too large: " + actual)
            # Relative imports may mention both a stem and explicit extension.
            # Count each resolved file exactly once and keep checking the graph.
            if actual in compared_files:
                continue
            compared_files.add(actual)
            candidate_bytes[actual] = contents
            stage_copy = scratch / "stage" / actual.replace("/", "__")
            stage_copy.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if extract(STAGE_NAME, actual, stage_copy):
                ensure(stage_copy.stat().st_size <= 1_000_000,
                       "Staging frontend dependency too large: " + actual)
                stage_content = stage_copy.read_bytes()
                if actual in COMPONENTS:
                    ensure(contents != stage_content,
                           "Dashboard component unexpectedly already matches: " + actual)
                elif contents != stage_content:
                    mismatches[actual] = (digest(stage_content), digest(contents))
            else:
                missing_stage[actual] = digest(contents)
            if actual in COMPONENTS:
                # Never silently introduce one of the 3 target components.
                ensure(actual not in missing_stage,
                       "Target dashboard component missing from stage: " + actual)
                live_copy = scratch / "live" / actual.replace("/", "__")
                live_copy.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                ensure(extract(LIVE_NAME, actual, live_copy) and
                       live_copy.read_bytes() == contents,
                       "Latest dashboard source does not match running live frontend: " + actual)
                print("APPROVED_LIVE_DASHBOARD_COMPONENT=" + actual +
                      " SHA256=" + digest(contents))
            if actual.endswith((".ts", ".tsx", ".js", ".jsx")):
                imported |= relative_imports(actual, contents.decode("utf-8"),
                                             outside_src)
        print("DASHBOARD_DEPENDENCIES_SCANNED=" + str(len(compared_files)))
        print("MISSING_STAGE_FRONTEND_DEPENDENCIES=" + str(len(missing_stage)))
        for name, candidate_sha in sorted(missing_stage.items()):
            print("MISSING_STAGE_FRONTEND_DEPENDENCY=" + name +
                  " CANDIDATE_SHA256=" + candidate_sha)
        print("MISSING_CANDIDATE_FRONTEND_DEPENDENCIES=" + str(len(missing_candidate)))
        for name in sorted(missing_candidate):
            print("MISSING_CANDIDATE_FRONTEND_DEPENDENCY=" + name)
        print("NON_DASHBOARD_DEPENDENCY_DIFFERENCES=" + str(len(mismatches)))
        for path, (stage_sha, candidate_sha) in sorted(mismatches.items()):
            print("DIFFERING_NON_DASHBOARD_DEPENDENCY=" + path +
                  " STAGE_SHA256=" + stage_sha +
                  " CANDIDATE_SHA256=" + candidate_sha)
        print("FRONTEND_IMPORTS_OUTSIDE_SRC=" + str(len(outside_src)))
        for source, imported_path in sorted(outside_src):
            print("FRONTEND_IMPORT_OUTSIDE_SRC=" + source +
                  " IMPORT=" + imported_path)
        ensure(not missing_stage and not missing_candidate and
               not mismatches and not outside_src,
               "Unreviewed frontend dependencies: " +
               str(len(missing_stage)) + " missing in stage, " +
               str(len(missing_candidate)) + " missing in candidate, " +
               str(len(mismatches)) + " differing, " +
               str(len(outside_src)) + " imports outside src; no automatic broad copy")
        for path in COMPONENTS:
            ensure(path in candidate_bytes, "Dashboard component not dependency-verified")
            target = scratch / path
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.write_bytes(candidate_bytes[path])
        print("ALL_OTHER_IMPORTS_AND_LOGIN_UNCHANGED=PASS")
        return {p: digest(candidate_bytes[p]) for p in COMPONENTS}
    finally:
        run("docker", "rm", cid, check=False)

def build(scratch):
    rules = ["FROM " + BEFORE, "WORKDIR /app"]
    for path in COMPONENTS:
        rules.append("COPY --chmod=0644 " + path + " /app/" + path)
    rules.append("RUN npm run build")
    (scratch / "Dockerfile").write_text("\n".join(rules) + "\n")
    result = run("docker", "build", "--network", "none", "--pull=false",
                 "-t", AFTER, str(scratch), check=False)
    ensure(result.returncode == 0,
           "Stage-only frontend build failed (nothing deployed): " +
           (result.stderr or result.stdout)[-1600:])
    return inspect(AFTER, "image")["Id"]

def checkpoint(compose):
    folder = ROOT / "checkpoints"
    folder.mkdir(mode=0o700, exist_ok=True)
    ensure(not folder.is_symlink() and stat.S_IMODE(folder.stat().st_mode) == 0o700,
           "Staging checkpoint directory not owner-private")
    dest = folder / ("before-dashboard-ui-" +
                     datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    dest.mkdir(mode=0o700)
    shutil.copytree(ROOT / "data", dest / "data")
    fd = os.open(dest / "compose.yml", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(compose)
    return dest

def save_compose(data):
    target = ROOT / "compose.yml"
    temp = ROOT / "compose.yml.dashboard.tmp"
    ensure(not temp.exists() and not temp.is_symlink(),
           "Stale staging Compose temporary file")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)
    os.replace(temp, target)
    os.chmod(target, 0o600)

def restart():
    cmd = run("docker", "compose", "--env-file", ".env", "-f", "compose.yml",
              "up", "-d", "--no-deps", "--force-recreate", "--wait", "hub",
              cwd=ROOT, check=False)
    ensure(cmd.returncode == 0,
           "Stage-only Hub recreate/health failed: " + cmd.stderr[-1500:])

def verify_after(stage, live, stage_pos, live_pos, image_id, hashes):
    new = inspect(STAGE_NAME)
    ensure(new["Config"]["Image"] == AFTER and new["Image"] == image_id and
           new["State"].get("Health", {}).get("Status") == "healthy",
           "Updated private Hub is not healthy on pinned dashboard image")
    ensure(env_map(new) == env_map(stage) and
           new["Config"]["User"] == stage["Config"]["User"],
           "Stage auth/MFA or runtime account changed")
    port_check(new)
    ensure(set(new["NetworkSettings"]["Networks"]) == {STAGE_NET} and
           inspect(LIVE_NAME)["Id"] == live["Id"] and
           inspect(LIVE_POS_NAME)["Id"] == live_pos["Id"] and
           inspect(POS_NAME)["Id"] == stage_pos["Id"],
           "Production or private POS/network isolation changed")
    for path, expected in hashes.items():
        actual = run("docker", "exec", STAGE_NAME, "sha256sum",
                     "/app/" + path).stdout.split()[0]
        ensure(actual == expected, "Stage dashboard file fingerprint differs: " + path)
    url = "http://" + ip_of(new) + ":3040"
    ensure(get(url + "/api/health")[0] == 200, "Aligned Hub health failed")
    for name in PRODUCTS:
        status, mime, body = get(url + "/assets/login-products/" + name + ".png", 8)
        ensure(status == 200 and mime.startswith("image/png") and body == PNG,
               "Hub login icon regression: " + name)
    css_code, css_mime, _ = get(url + "/src/index.css?direct")
    ensure(css_code == 200 and css_mime.startswith("text/css"),
           "Hub approved login stylesheet missing after alignment")
    pos_url = "http://" + ip_of(inspect(POS_NAME)) + ":8080"
    ensure(get(pos_url + "/ready")[0] == 200 and
           get(pos_url + "/v1/me")[0] == 401,
           "Stage POS health or anonymous access regressed")
    print("STAGING_UPDATED_DASHBOARD_FILES=PASS")
    print("STAGING_LOGIN_ICONS_AND_CSS=PASS")
    print("STAGING_MFA_AND_POS_RUNTIME_PRESERVED=PASS")
    print("PRODUCTION_AND_STAGE_POS_UNCHANGED=PASS")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Build image and recreate only private staging Hub")
    args = parser.parse_args()
    stage, live, stage_pos, live_pos, compose, previous = check_preflight()
    print("PRIVATE_STAGE_DASHBOARD_PREFLIGHT=PASS")
    with tempfile.TemporaryDirectory(prefix="v79-dashboard-",
                                     dir=ROOT) as d:
        scratch = Path(d)
        hashes = verify_candidate_dependency_parity(scratch)
        if not args.apply:
            print("STAGING_DASHBOARD_DRY_RUN=PASS")
            return
        image_id = build(scratch)
        backup = checkpoint(compose)
        print("PRIVATE_DASHBOARD_CHECKPOINT=" + str(backup))
        save_compose(compose.replace("    image: " + BEFORE + "\n",
                                    "    image: " + AFTER + "\n", 1))
        try:
            run("docker", "compose", "--env-file", ".env", "-f", "compose.yml",
                "config", "--quiet", cwd=ROOT)
            restart()
            verify_after(stage, live, stage_pos, live_pos, image_id, hashes)
        except Exception:
            print("STAGING_DASHBOARD_FAILED_ROLLBACK_ATTEMPT", flush=True)
            save_compose(compose)
            try:
                restart()
                print("PREVIOUS_HEALTHY_STAGE_RESTORED=PASS", flush=True)
            except Exception as e:
                print("STAGING_DASHBOARD_ROLLBACK_FAILED=" + str(e), flush=True)
            print("DASHBOARD_CHECKPOINT_RETAINED=" + str(backup), flush=True)
            raise
        record = {
            "dashboard_image": AFTER,
            "image_id": image_id,
            "base_stage_image": BEFORE,
            "base_stage_image_id": stage["Image"],
            "dashboard_source_image": CANDIDATE,
            "dashboard_source_image_id": inspect(CANDIDATE, "image")["Id"],
            "changed_files_sha256": hashes,
            "checkpoint": str(backup),
            "applied_utc": datetime.now(timezone.utc).isoformat(),
        }
        fd = os.open(PIN, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        print("PRIVATE_STAGING_DASHBOARD_ALIGNED=PASS")
        print("STAGING_MFA_AND_POS_BROWSER_RETEST=NOT_YET_VERIFIED")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, UnicodeError,
            subprocess.CalledProcessError, KeyError) as error:
        raise SystemExit(str(error)) from None
