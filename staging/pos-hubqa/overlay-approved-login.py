#!/usr/bin/env python3
"""Overlay the 9 Nov Hub Connected Login frontend onto the private Hub stage.

Read-only preflight is default. --apply builds a NEW stage-only image, then
recreates ONLY the private Hub stage with a rollback checkpoint.
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
STAGE_BASE = "v79hub:pos-hubqa-20261109"
CANDIDATE = "localhost/v79-hub-login-connected:20261109-r1"
ALIAS = "localhost/v79-hub-sales-review:20261107-r1"
OUTPUT = "v79hub:pos-hubqa-ui-v3-20261109"
PRIVATE_NET = "v79pos-hubqa-20261109_stage_internal"
COMPOSE_OLD = "    image: " + STAGE_BASE + "\n"
COMPOSE_NEW = "    image: " + OUTPUT + "\n"
STAGE = "v79-hub-pos-hubqa"
PRODUCTION = "v79-hub"
STAGE_POS = "v79-pos-hubqa-api"
STAGE_DB = "v79-pos-hubqa-db"

def require(condition, reason):
    if not condition:
        raise RuntimeError("STAGING_LOGIN_OVERLAY_BLOCKED: " + reason)

def run(*cmd, check=True, cwd=None):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=cwd, check=check)

def inspect(name, kind="container"):
    return json.loads(run("docker", kind, "inspect", name).stdout)[0]

def container_env(container):
    return dict(row.split("=", 1) for row in container["Config"]["Env"] if "=" in row)

def private_ip(container):
    networks = container["NetworkSettings"]["Networks"]
    require(set(networks) == {PRIVATE_NET}, "Stage connected to another network")
    ip = networks[PRIVATE_NET].get("IPAddress", "")
    require(ip and ipaddress.ip_address(ip).version == 4 and
            ipaddress.ip_address(ip).is_private, "Invalid private Docker IP")
    return ip

def healthcode(url):
    try:
        with urllib.request.urlopen(url, timeout=8) as result:
            return result.status
    except urllib.error.HTTPError as e:
        return e.code

def atomic_write(path, content):
    require(not path.is_symlink(), "Symlink target")
    temp = path.with_name(path.name + ".overlay.tmp")
    require(not temp.exists() and not temp.is_symlink(), "Stale temporary file")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    os.replace(temp, path)
    os.chmod(path, 0o600)

def check_stage():
    require(os.geteuid() != 0, "Must run as stage owner, not root")
    require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.resolve() == ROOT,
            "Unexpected stage directory")
    data = ROOT / "data"
    require(data.is_dir() and not data.is_symlink() and
            data.stat().st_uid == os.getuid() and
            stat.S_IMODE(data.stat().st_mode) == 0o700,
            "Stage private store owner/permissions changed")
    for path in data.rglob("*"):
        require(not path.is_symlink(), "Symlink in stage data")
    for path in (ROOT / ".env", ROOT / "compose.yml"):
        require(path.is_file() and not path.is_symlink() and
                stat.S_IMODE(path.stat().st_mode) == 0o600,
                "Stage config missing or not private")
    env_text = (ROOT / ".env").read_text()
    private_env = {}
    for line in env_text.splitlines():
        if not line or line.startswith("#"):
            continue
        require("=" in line, "Unexpected environment format")
        k, v = line.split("=", 1)
        require(k.isidentifier() and k not in private_env,
                "Invalid or duplicate stage env key")
        private_env[k] = v
    require(private_env.get("V79_REQUIRE_ADMIN_MFA") == "1" and
            len(private_env.get("V79_HUB_SECURITY_KEY", "")) >= 32 and
            len(private_env.get("V79_PLATFORM_SHARED_SECRET", "")) >= 32 and
            private_env["V79_PLATFORM_SHARED_SECRET"] != private_env["V79_HUB_SECURITY_KEY"],
            "Stage MFA or service keys missing")
    require(private_env.get("V79_HUB_STAGE_UID") == str(os.getuid()) and
            private_env.get("V79_HUB_STAGE_GID") == str(os.getgid()),
            "Stage non-root identity mapping changed")
    require(not (ROOT / "approved-login-overlay.json").exists() and
            not (ROOT / "approved-live-image.json").exists(),
            "Stage image already pinned; refuse to overwrite")
    old_compose = (ROOT / "source" / "staging" / "pos-hubqa" / "hub-compose.yml").read_text()
    compose = (ROOT / "compose.yml").read_text()
    require(compose == old_compose and compose.count(COMPOSE_OLD) == 1,
            "Stage Compose has unreviewed changes")
    require("127.0.0.1:18082:3040" in compose and
            "POS_BASE_URL: http://v79-pos-hubqa-api:8080" in compose and
            "POS_PUBLIC_URL: http://127.0.0.1:18081" in compose and
            "V79_REQUIRE_ADMIN_MFA: \"1\"" in compose and
            "V79_WORKFORCE_ACTIONS_ENABLED: \"0\"" in compose and
            "WIPAY_ENABLED: \"0\"" in compose and
            "RESEND_API_KEY: \"\"" in compose and
            "proxy_network" not in compose,
            "Unsafe staging Compose")
    prod_hub = inspect(PRODUCTION)
    prod_pos = inspect("v79-pos")
    stage_hub = inspect(STAGE)
    pos = inspect(STAGE_POS)
    db = inspect(STAGE_DB)
    for c in (prod_hub, prod_pos, stage_hub, pos, db):
        require(c["State"].get("Health", {}).get("Status") == "healthy",
                "A production or stage dependency is not healthy")
    require(prod_pos["Config"]["Image"] == "localhost/v79-brand-pos:20261106-r1",
            "Unexpected live POS image")
    require(stage_hub["Config"]["Image"] == STAGE_BASE,
            "Old stage image was already replaced")
    require(stage_hub["Image"] == inspect(STAGE_BASE, "image")["Id"],
            "Old stage image was retagged unexpectedly")
    require(inspect(PRIVATE_NET, "network")["Internal"] is True,
            "Private staging bridge not isolated")
    private_ip(stage_hub)
    private_ip(pos)
    private_ip(db)
    require(container_env(db).get("POSTGRES_DB") == "v79pos_hubqa",
            "Stage DB name differs")
    for c, port, published in ((stage_hub, "3040/tcp", "18082"),
                                (pos, "8080/tcp", "18081")):
        b = (c["HostConfig"].get("PortBindings") or {}).get(port) or []
        require(len(b) == 1 and b[0].get("HostIp") == "127.0.0.1"
                and b[0].get("HostPort") == published,
                "A staging port is not configured for loopback only")
    se = container_env(stage_hub)
    require(se.get("NODE_ENV") == "development" and
            se.get("V79_HUB_STORE_BACKEND") == "json" and
            se.get("POS_BASE_URL") == "http://v79-pos-hubqa-api:8080" and
            se.get("POS_PUBLIC_URL") == "http://127.0.0.1:18081" and
            se.get("APP_URL") == "http://127.0.0.1:18082" and
            se.get("V79_REQUIRE_ADMIN_MFA") == "1" and
            se.get("WIPAY_ENABLED") == "0" and
            se.get("RESEND_API_KEY", "") == "" and
            se.get("V79_WORKFORCE_ACTIONS_ENABLED") == "0",
            "Staging Hub runtime safety settings changed")
    require(healthcode("http://" + private_ip(stage_hub) + ":3040/api/health") == 200 and
            healthcode("http://" + private_ip(pos) + ":8080/ready") == 200 and
            healthcode("http://" + private_ip(pos) + ":8080/v1/me") == 401,
            "Stage health or unauthenticated access check failed")
    return compose, stage_hub, prod_hub, pos

def inspect_image():
    approved = inspect(CANDIDATE, "image")
    alias = inspect(ALIAS, "image")
    require(approved["Id"] == alias["Id"] and
            approved["Id"].startswith("sha256:"),
            "Approved Connected Login image is missing or differs from alias")
    require(approved["Id"] != inspect(STAGE_BASE, "image")["Id"],
            "Candidate is the same as the old staging Hub")
    for row in approved.get("Config", {}).get("Env") or []:
        key = row.split("=", 1)[0].upper()
        require(not (key.startswith(("V79_", "RESEND_", "WIPAY_", "POSTGRES_",
                                     "GOOGLE_", "DATABASE_", "JWT_")) or
                     key in {"API_KEY", "DATABASE_URL", "REDIS_URL"}),
                "Candidate contains baked confidential environment settings")
    return approved["Id"]

def extract_candidate_files(scratch):
    """Extract only the login component and its local imports, never image .env."""
    cid = run("docker", "create", "--network", "none", "--entrypoint", "sh",
              CANDIDATE, "-c", ":").stdout.strip()
    require(bool(re.fullmatch(r"[0-9a-f]{64}", cid)),
            "Could not create temporary image inspection container")
    try:
        def copy_file(path):
            dest = scratch / path
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            result = run("docker", "cp", cid + ":/app/" + path, str(dest),
                         check=False)
            require(result.returncode == 0 and dest.is_file() and
                    not dest.is_symlink() and dest.stat().st_size < 700_000,
                    "Candidate file unavailable or suspicious: " + path)
        copy_file("src/components/Login.tsx")
        base = ROOT / "source"
        stack = ["src/components/Login.tsx"]
        selected = {"src/components/Login.tsx"}
        scanned = set()
        while stack:
            name = stack.pop()
            if name in scanned:
                continue
            scanned.add(name)
            script = (scratch / name).read_text()
            # Only ordinary static JS/TS imports; runtime build will reject
            # missing/invalid imports. No unreviewed source directory copying.
            pattern = r"""(?:from\s*|import\s*\(|import\s*)['"](\.[^'"]+)['"]"""
            for relative in re.findall(pattern, script):
                prefix = PurePosixPath(name).parent
                # Resolve . and .. without escaping src.
                parts = []
                for part in (prefix / relative).parts:
                    if part == "..":
                        require(bool(parts), "Import escaped staging source")
                        parts.pop()
                    elif part != ".":
                        parts.append(part)
                stem = "/".join(parts)
                require(stem.startswith("src/"), "Unexpected import path")
                options = [stem + ext for ext in (".tsx", ".ts", ".jsx", ".js", ".css")]
                if stem.endswith((".tsx", ".ts", ".jsx", ".js", ".css")):
                    options.insert(0, stem)
                target = next((x for x in options if (base / x).is_file()), None)
                if target:
                    # Stage already supplies common app types/helpers.
                    # Only import extra login-owned components from candidate.
                    if target != "src/components/GoogleSignIn.tsx":
                        continue
                else:
                    require(stem.startswith("src/components/"),
                            "Unresolved shared import; check dependency manually: " + stem)
                    target = options[0]
                if target not in selected:
                    copy_file(target)
                    selected.add(target)
                    stack.append(target)
            # Keep only referenced, local, public login assets (no bulk copy).
            for asset in re.findall(
                r"""['"](/(?:brand|assets|images|icons|logos)/[A-Za-z0-9_./-]+\.(?:svg|png|jpg|jpeg|webp|ico))['"]""",
                script, re.I
            ):
                path = "public" + asset
                require(".." not in PurePosixPath(path).parts, "Asset path escape")
                if path not in selected:
                    copy_file(path)
                    selected.add(path)
        return sorted(selected)
    finally:
        run("docker", "rm", "-f", cid, check=False)

def stage_build(files, scratch):
    dockerfile = [
        "FROM " + STAGE_BASE,
        "WORKDIR /app",
    ]
    for name in files:
        dockerfile.append("COPY --chmod=0644 " + name + " /app/" + name)
    dockerfile.append("RUN npm run build")
    (scratch / "Dockerfile").write_text("\n".join(dockerfile) + "\n")
    result = run("docker", "build", "--network", "none", "--pull=false",
                 "-t", OUTPUT, str(scratch), check=False)
    require(result.returncode == 0, "Frontend overlay build failed (no stage changed). "
            + (result.stderr or result.stdout)[-1300:])

def checkpoint(original):
    data = ROOT / "data"
    home = ROOT / "checkpoints"
    home.mkdir(mode=0o700, exist_ok=True)
    require(not home.is_symlink() and stat.S_IMODE(home.stat().st_mode) == 0o700,
            "Unsafe checkpoint directory")
    name = "before-login-v3-ui-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = home / name
    dest.mkdir(mode=0o700)
    shutil.copytree(data, dest / "data", symlinks=False)
    path = dest / "compose.yml"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(original)
    return dest

def up_stage():
    result = run("docker", "compose", "--env-file", ".env",
                 "-f", "compose.yml", "up", "-d", "--no-deps",
                 "--force-recreate", "--wait", "hub", cwd=ROOT,
                 check=False)
    require(result.returncode == 0,
            "Staging Hub did not become healthy: " + (result.stderr or "")[-800:])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Build and apply staging-only login UI overlay")
    args = parser.parse_args()
    original, stage, prod, pos = check_stage()
    src_image_id = inspect_image()
    require(run("docker", "image", "inspect", OUTPUT, check=False).returncode != 0,
            "Overlay image already exists: review rather than overwrite")
    print("APPROVED_CONNECTED_LOGIN_IMAGE=" + CANDIDATE)
    print("CONNECTED_LOGIN_IMAGE_ID=" + src_image_id)
    print("STAGING_ONLY_BACKEND_AND_MFA=PASS")
    print("STAGING_DATA_PRODUCTION_ISOLATION=PASS")

    # Pull only candidate Login.tsx and its required local files into a
    # temporary stage-owned workspace. Dry-run does NOT change stage services.
    with tempfile.TemporaryDirectory(prefix="v79-login-overlay-", dir=ROOT) as temp:
        scratch = Path(temp)
        files = extract_candidate_files(scratch)
        login = (scratch / "src/components/Login.tsx").read_bytes()
        baseline = (ROOT / "source/src/components/Login.tsx").read_bytes()
        require(login != baseline, "Candidate login component matches old staging")
        fingerprint = hashlib.sha256(login).hexdigest()
        print("CANDIDATE_LOGIN_SHA256=" + fingerprint)
        print("UI_OVERLAY_FILE_COUNT=" + str(len(files)))
        print("UI_OVERLAY_FILES=" + ",".join(files))
        if not args.apply:
            print("DRY_RUN_ONLY=PASS")
            return

        # Build first; a failed build never changes Compose or running stage.
        stage_build(files, scratch)
        built_id = inspect(OUTPUT, "image")["Id"]
        snapshot = checkpoint(original)
        print("PRIVATE_STAGE_ROLLBACK_CHECKPOINT=" + str(snapshot))
        atomic_write(ROOT / "compose.yml", original.replace(COMPOSE_OLD, COMPOSE_NEW, 1))
        try:
            run("docker", "compose", "--env-file", ".env",
                "-f", "compose.yml", "config", "--quiet", cwd=ROOT)
            up_stage()
            after = inspect(STAGE)
            current_prod = inspect(PRODUCTION)
            current_pos = inspect(STAGE_POS)
            require(after["Image"] == built_id and
                    after["Config"]["Image"] == OUTPUT,
                    "Stage is not using exact frontend overlay image")
            require(current_prod["Id"] == prod["Id"] and
                    current_pos["Id"] == pos["Id"] and
                    current_prod["State"]["Health"]["Status"] == "healthy" and
                    current_pos["State"]["Health"]["Status"] == "healthy",
                    "Production Hub or staged POS changed")
            require(private_ip(after) and
                    healthcode("http://" + private_ip(after) + ":3040/api/health") == 200,
                    "New stage health unavailable")
        except Exception:
            print("STAGE_UI_OVERLAY_FAILED_ATTEMPTING_STAGE_ONLY_ROLLBACK",
                  flush=True)
            atomic_write(ROOT / "compose.yml", original)
            try:
                up_stage()
                print("OLD_STAGE_HUB_IMAGE_RESTORED=PASS")
            except Exception as error:
                print("OLD_STAGE_HUB_RESTORE_FAILED: " + str(error), flush=True)
            print("STAGE_CHECKPOINT_RETAINED=" + str(snapshot))
            raise

        record = {
            "source_image": CANDIDATE,
            "source_image_id": src_image_id,
            "base_stage_image": STAGE_BASE,
            "overlay_image": OUTPUT,
            "overlay_image_id": built_id,
            "login_sha256": fingerprint,
            "files": files,
            "checkpoint": str(snapshot),
        }
        pin = ROOT / "approved-login-overlay.json"
        fd = os.open(pin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        print("STAGING_LOGIN_OVERLAY=PASS")
        print("PRIVATE_STAGE_HEALTH=PASS")
        print("ORIGINAL_STAGE_BACKEND_PRESERVED=PASS")
        print("PRODUCTION_UNCHANGED=PASS")
        print("VERSION3_VISUAL_AND_MFA_BROWSER_TEST=NOT_YET_VERIFIED")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError,
            KeyError, AssertionError) as exc:
        raise SystemExit(str(exc)) from None
