#!/usr/bin/env python3
"""Stage-only fix: align Connected Login stylesheet and referenced public assets.

No production Docker or data writes. Dry-run first; --apply builds from the
already healthy front-end-only stage image, checkpoints private stage settings,
and replaces ONLY the private staging Hub with image-only rollback on failure.
"""
import argparse
from datetime import datetime, timezone
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

ROOT = Path("/home/firelion/v79-hub-pos-hubqa-20261109")
NET = "v79pos-hubqa-20261109_stage_internal"
STAGE_NAME = "v79-hub-pos-hubqa"
POS_NAME = "v79-pos-hubqa-api"
DB_NAME = "v79-pos-hubqa-db"
PROD_NAME = "v79-hub"
PROD_POS_NAME = "v79-pos"
CURRENT = "v79hub:pos-hubqa-ui-v3-20261109"
CANDIDATE = "localhost/v79-hub-login-connected:20261109-r1"
OUTPUT = "v79hub:pos-hubqa-ui-v3-styled-20261109"
CSS_SHA = "ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c"
OLD_CSS_SHA = "cb3417cc160bc3f8edcd3c444e22dd51af781918b065956182fa44d3b9907145"
LOGIN_SHA = "cb250f00742c5bc3f40f119cbc51f626a1fb94f542f254e27b0d3c6884b4c49b"
OLD_LINE = "    image: " + CURRENT + "\n"
NEW_LINE = "    image: " + OUTPUT + "\n"
ASSET_RE = re.compile(
    r"""(?<![\w/])/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_.@-]+\.(?:svg|png|webp|jpg|jpeg|gif|ico|woff2?|ttf)\b""",
    re.I
)

def require(ok, why):
    if not ok:
        raise RuntimeError("STAGE_PRESENTATION_BLOCKED: " + why)

def command(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, check=check)

def docker_inspect(name, kind="container"):
    return json.loads(command("docker", kind, "inspect", name).stdout)[0]

def digest(filename):
    return hashlib.sha256(Path(filename).read_bytes()).hexdigest()

def env_from(container):
    return dict(s.split("=", 1) for s in container["Config"]["Env"] if "=" in s)

def stage_ip(container):
    networks = container["NetworkSettings"]["Networks"]
    require(set(networks) == {NET}, "Stage container has an unexpected network")
    address = networks[NET].get("IPAddress", "")
    try:
        parsed = ipaddress.ip_address(address)
        require(parsed.version == 4 and parsed.is_private, "Stage IPv4 is not private")
    except ValueError:
        require(False, "Stage IPv4 address invalid")
    return address

def http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=9) as response:
            return response.status, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", "")

def check_port(container, internal, published):
    published_ports = (container["HostConfig"].get("PortBindings") or {}).get(internal) or []
    require(len(published_ports) == 1 and
            published_ports[0].get("HostIp") == "127.0.0.1" and
            published_ports[0].get("HostPort") == str(published),
            "Stage published-port declaration is not restricted to localhost")

def check_preflight():
    require(os.geteuid() != 0, "Run as normal stage owner, not root")
    require(ROOT.is_dir() and ROOT.resolve() == ROOT and not ROOT.is_symlink(),
            "Unexpected Hub staging directory")
    data = ROOT / "data"
    require(data.is_dir() and not data.is_symlink() and
            data.stat().st_uid == os.getuid() and
            stat.S_IMODE(data.stat().st_mode) == 0o700,
            "Stage store is not private and owner-controlled")
    require(not any(p.is_symlink() for p in data.rglob("*")),
            "Stage data contains a symlink")
    stage_env = ROOT / ".env"
    compose = ROOT / "compose.yml"
    for file in (stage_env, compose):
        require(file.is_file() and not file.is_symlink() and
                stat.S_IMODE(file.stat().st_mode) == 0o600,
                "Stage .env/Compose is missing or not owner-only")
    require(not (ROOT / "approved-login-style.json").exists(),
            "Presentation fix already applied: verify instead of repeating")
    pin = ROOT / "approved-login-overlay.json"
    require(pin.is_file() and not pin.is_symlink() and
            stat.S_IMODE(pin.stat().st_mode) == 0o600,
            "Staging login image pin missing or unsafe")
    record = json.loads(pin.read_text())
    require(record.get("overlay_image") == CURRENT and
            record.get("source_image") == CANDIDATE,
            "Staging login image source not recognised")
    values = {}
    for row in stage_env.read_text().splitlines():
        if not row or row.startswith("#"):
            continue
        require("=" in row, "Malformed staging-only environment")
        key, value = row.split("=", 1)
        require(key.isidentifier() and key not in values,
                "Duplicate/malformed stage environment key")
        values[key] = value
    require(values.get("V79_HUB_STAGE_UID") == str(os.getuid()) and
            values.get("V79_HUB_STAGE_GID") == str(os.getgid()) and
            values.get("V79_REQUIRE_ADMIN_MFA") == "1" and
            len(values.get("V79_PLATFORM_SHARED_SECRET", "")) >= 32 and
            len(values.get("V79_HUB_SECURITY_KEY", "")) >= 32 and
            values["V79_PLATFORM_SHARED_SECRET"] != values["V79_HUB_SECURITY_KEY"],
            "Stage UID, MFA or keys unexpectedly changed")

    live_hub = docker_inspect(PROD_NAME)
    live_pos = docker_inspect(PROD_POS_NAME)
    stage_hub = docker_inspect(STAGE_NAME)
    stage_pos = docker_inspect(POS_NAME)
    db = docker_inspect(DB_NAME)
    for label, container in [
        ("Live Hub", live_hub), ("Live POS", live_pos),
        ("Stage Hub", stage_hub), ("Stage POS", stage_pos),
        ("Stage PostgreSQL", db),
    ]:
        require(container["State"].get("Health", {}).get("Status") == "healthy",
                label + " is not healthy")
    require(live_pos["Config"]["Image"] == "localhost/v79-brand-pos:20261106-r1",
            "Production POS image unexpected")
    require(docker_inspect(NET, "network")["Internal"] is True,
            "Stage Docker network is not internal")
    for item in (stage_hub, stage_pos, db):
        stage_ip(item)
    require(env_from(db).get("POSTGRES_DB") == "v79pos_hubqa",
            "Staging database name unexpected")
    require(stage_hub["Config"]["Image"] == CURRENT and
            stage_hub["Image"] == record.get("overlay_image_id") and
            stage_hub["Image"] == docker_inspect(CURRENT, "image")["Id"],
            "Stage Hub is not on the owner-verified frontend-only image")
    require(docker_inspect(CANDIDATE, "image")["Id"] ==
            record.get("source_image_id"),
            "Approved 9 Nov Connected Login source image changed")
    runtime = env_from(stage_hub)
    require(runtime.get("V79_HUB_STORE_BACKEND") == "json" and
            runtime.get("NODE_ENV") == "development" and
            runtime.get("V79_REQUIRE_ADMIN_MFA") == "1" and
            runtime.get("POS_BASE_URL") == "http://v79-pos-hubqa-api:8080" and
            runtime.get("POS_PUBLIC_URL") == "http://127.0.0.1:18081" and
            runtime.get("APP_URL") == "http://127.0.0.1:18082" and
            runtime.get("WIPAY_ENABLED") == "0" and
            runtime.get("RESEND_API_KEY", "") == "" and
            runtime.get("V79_WORKFORCE_ACTIONS_ENABLED") == "0",
            "Stage auth, billing, or integration safety settings changed")
    check_port(stage_hub, "3040/tcp", 18082)
    check_port(stage_pos, "8080/tcp", 18081)
    require(http_get("http://" + stage_ip(stage_hub) + ":3040/api/health")[0] == 200 and
            http_get("http://" + stage_ip(stage_pos) + ":8080/ready")[0] == 200 and
            http_get("http://" + stage_ip(stage_pos) + ":8080/v1/me")[0] == 401,
            "Existing stage health or POS anonymous denial unexpectedly changed")
    raw_compose = compose.read_text()
    require(raw_compose.count(OLD_LINE) == 1 and
            raw_compose.count("container_name: v79-hub-pos-hubqa") == 1 and
            "127.0.0.1:18082:3040" in raw_compose and
            "POS_BASE_URL: http://v79-pos-hubqa-api:8080" in raw_compose and
            'V79_REQUIRE_ADMIN_MFA: "1"' in raw_compose and
            'WIPAY_ENABLED: "0"' in raw_compose and
            'RESEND_API_KEY: ""' in raw_compose and
            "proxy_network" not in raw_compose,
            "Unexpected stage Compose topology")
    require(command("docker", "image", "inspect", OUTPUT, check=False).returncode != 0,
            "Styled image tag already exists; do not overwrite")
    return raw_compose, live_hub, live_pos, stage_hub, stage_pos, record

def extract(candidate, scratch):
    cid = command("docker", "create", "--network", "none",
                  "--entrypoint", "sh", candidate, "-c", ":").stdout.strip()
    require(re.fullmatch(r"[a-f0-9]{64}", cid) is not None,
            "Disposable candidate inspection container not created")
    selected = []
    try:
        def copy_source(name, required=True):
            dest = scratch / name
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            result = command("docker", "cp", cid + ":/app/" + name, str(dest),
                             check=False)
            if result.returncode != 0:
                require(not required,
                        "Candidate lacks required frontend file: " + name)
                return False
            require(dest.is_file() and not dest.is_symlink() and
                    dest.stat().st_size < 2_000_000,
                    "Candidate frontend file unsafe/oversized: " + name)
            selected.append(name)
            return True

        copy_source("src/index.css")
        copy_source("src/components/Login.tsx")
        copy_source("index.html")
        require(digest(scratch / "src/index.css") == CSS_SHA,
                "9 Nov Connected Login stylesheet hash changed")
        require(digest(scratch / "src/components/Login.tsx") == LOGIN_SHA,
                "9 Nov Connected Login component changed")
        require(digest(scratch / "index.html") ==
                "6ea202201b5d07d5592417d41933d6a277899e1544437888bc8946fd8f8da4f3",
                "9 Nov frontend HTML changed")
        # All static references in the login component, styles and HTML.
        text = "\n".join(
            (scratch / file).read_text()
            for file in ("src/index.css", "src/components/Login.tsx", "index.html")
        )
        assets = sorted({m.group() for m in ASSET_RE.finditer(text)})
        require(len(assets) <= 90, "Too many candidate public assets")
        for asset in assets:
            rel = PurePosixPath(asset.lstrip("/"))
            require(".." not in rel.parts and
                    all(re.fullmatch(r"[A-Za-z0-9_.@-]+", s) for s in rel.parts),
                    "Invalid candidate asset path")
            copy_source("public/" + str(rel), required=False)
        return sorted(set(selected)), assets
    finally:
        command("docker", "rm", "-f", cid, check=False)

def stage_build(scratch, files):
    # The current login component and HTML are already correct. Copy only CSS
    # plus public images/fonts discovered in the immutable 9 Nov candidate.
    keep = [f for f in files if f == "src/index.css" or f.startswith("public/")]
    lines = ["FROM " + CURRENT, "WORKDIR /app"]
    for name in keep:
        lines.append("COPY --chmod=0644 " + name + " /app/" + name)
    lines.append("RUN npm run build")
    (scratch / "Dockerfile").write_text("\n".join(lines) + "\n")
    result = command("docker", "build", "--network", "none", "--pull=false",
                     "-t", OUTPUT, str(scratch), check=False)
    require(result.returncode == 0,
            "Offline stage CSS/asset image build failed (no service changed): "
            + (result.stderr or result.stdout)[-1100:])
    return docker_inspect(OUTPUT, "image")["Id"]

def checkpoint(compose):
    base = ROOT / "checkpoints"
    base.mkdir(mode=0o700, exist_ok=True)
    require(not base.is_symlink() and stat.S_IMODE(base.stat().st_mode) == 0o700,
            "Private checkpoint directory permissions changed")
    name = "before-v3-style-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    location = base / name
    location.mkdir(mode=0o700)
    shutil.copytree(ROOT / "data", location / "data")
    fd = os.open(location / "compose.yml", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(compose)
    return location

def save_compose(text):
    path = ROOT / "compose.yml"
    tmp = ROOT / "compose.yml.style.tmp"
    require(not tmp.exists() and not tmp.is_symlink(), "Stale Compose temp file")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    os.chmod(path, 0o600)

def restart_stage():
    result = command("docker", "compose", "--env-file", ".env",
                     "-f", "compose.yml", "up", "-d", "--no-deps",
                     "--force-recreate", "--wait", "hub", cwd=ROOT, check=False)
    require(result.returncode == 0,
            "Staging Hub did not become healthy: " + (result.stderr or "")[-1000:])

def verify(built_id, live_hub, live_pos, stage_pos, public_assets):
    hub = docker_inspect(STAGE_NAME)
    require(hub["Config"]["Image"] == OUTPUT and hub["Image"] == built_id and
            hub["State"]["Health"]["Status"] == "healthy",
            "Styled Hub image was not started or is unhealthy")
    require(docker_inspect(PROD_NAME)["Id"] == live_hub["Id"] and
            docker_inspect(PROD_POS_NAME)["Id"] == live_pos["Id"] and
            docker_inspect(POS_NAME)["Id"] == stage_pos["Id"],
            "Unexpected replacement of production or POS staging container")
    base_url = "http://" + stage_ip(hub) + ":3040"
    require(http_get(base_url + "/api/health")[0] == 200,
            "Styled Hub API health endpoint unavailable")
    body = command("docker", "exec", STAGE_NAME, "sha256sum",
                   "/app/src/index.css").stdout.split()[0]
    require(body == CSS_SHA, "Styled Hub did not contain 9 Nov CSS source")
    css_code, css_type = http_get(base_url + "/src/index.css?direct")
    require(css_code == 200 and css_type.startswith("text/css"),
            "Vite did not serve a stylesheet after the overlay")
    missing = []
    for asset in public_assets:
        if not asset.endswith((".svg", ".png", ".webp", ".jpg", ".jpeg", ".gif", ".ico")):
            continue
        status, media_type = http_get(base_url + asset)
        if status != 200 or not media_type.startswith("image/"):
            missing.append(asset)
    require(not missing, "Login images still missing: " + ", ".join(missing[:10]))
    pos = docker_inspect(POS_NAME)
    url = "http://" + stage_ip(pos) + ":8080"
    require(http_get(url + "/ready")[0] == 200 and
            http_get(url + "/v1/me")[0] == 401,
            "POS staging readiness/anonymous-denial regression")
    require(docker_inspect(PROD_NAME)["State"]["Health"]["Status"] == "healthy"
            and docker_inspect(PROD_POS_NAME)["State"]["Health"]["Status"] == "healthy",
            "Live Hub/POS health changed")
    print("V3_STAGING_STYLESHEET=PASS")
    print("V3_STAGING_ASSETS=PASS")
    print("STAGING_HUB_AND_POS_HEALTH=PASS")
    print("STAGING_POS_ANONYMOUS_DENIAL=PASS")
    print("PRODUCTION_UNCHANGED=PASS")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Apply CSS/assets to only the private staging Hub")
    args = parser.parse_args()
    compose, live_hub, live_pos, stage_hub, stage_pos, pin = check_preflight()
    print("PRIVATE_STAGING_AND_PRODUCTION_PREFLIGHT=PASS")
    with tempfile.TemporaryDirectory(prefix="v79-ui-style-", dir=ROOT) as folder:
        scratch = Path(folder)
        files, paths = extract(CANDIDATE, scratch)
        require(digest(scratch / "src/index.css") == CSS_SHA,
                "Approved candidate CSS unavailable")
        print("CANDIDATE_CSS_SHA256=" + CSS_SHA)
        print("FRONTEND_PUBLIC_ASSET_PATHS=" + str(len(paths)))
        print("COPIED_CANDIDATE_ASSETS=" +
              ",".join(x.removeprefix("public/") for x in files if x.startswith("public/")))
        if not args.apply:
            print("DRY_RUN_ONLY=PASS")
            return
        image_id = stage_build(scratch, files)
        snapshot = checkpoint(compose)
        print("PRIVATE_STAGE_ROLLBACK_CHECKPOINT=" + str(snapshot))
        save_compose(compose.replace(OLD_LINE, NEW_LINE, 1))
        try:
            command("docker", "compose", "--env-file", ".env",
                    "-f", "compose.yml", "config", "--quiet", cwd=ROOT)
            restart_stage()
            verify(image_id, live_hub, live_pos, stage_pos, paths)
        except Exception:
            print("STAGE_CSS_FIX_FAILED_ATTEMPTING_STAGE_ONLY_ROLLBACK", flush=True)
            save_compose(compose)
            try:
                restart_stage()
                print("OLD_STAGE_HUB_IMAGE_RESTORED=PASS", flush=True)
            except Exception as error:
                print("STAGING_ROLLBACK_FAILED=" + str(error), flush=True)
            print("STAGING_CHECKPOINT_RETAINED=" + str(snapshot), flush=True)
            raise
        record = {
            "source_image": CANDIDATE,
            "source_image_id": pin["source_image_id"],
            "previous_image": CURRENT,
            "previous_image_id": stage_hub["Image"],
            "styled_image": OUTPUT,
            "styled_image_id": image_id,
            "stylesheet_sha256": CSS_SHA,
            "asset_paths": paths,
            "checkpoint": str(snapshot),
            "applied_utc": datetime.now(timezone.utc).isoformat()
        }
        target = ROOT / "approved-login-style.json"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        print("STAGING_LOGIN_STYLE_AND_ASSETS=PASS")
        print("STAGING_BACKEND_AND_MFA_PRESERVED=PASS")
        print("VERSION3_VISUAL_AND_MFA_BROWSER_TEST=NOT_YET_VERIFIED")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, AssertionError,
            subprocess.CalledProcessError, KeyError, TypeError) as exc:
        raise SystemExit(str(exc)) from None
