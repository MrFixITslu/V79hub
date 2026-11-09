#!/usr/bin/env python3
"""Repair ONLY an inaccessible public image directory in the private Hub stage.

Dry-run by default. The original staging image, private data and keys stay intact.
No live container, production source or existing Docker image is modified.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path("/home/firelion/v79-hub-pos-hubqa-20261109")
CHECK = ROOT / "source/staging/pos-hubqa/check.py"
LIVE = "v79-hub"
STAGE = "v79-hub-pos-hubqa"
STAGE_OLD = "v79hub:pos-hubqa-ui-v3-20261109"
BROKEN = "v79hub:pos-hubqa-ui-v3-styled-20261109"
FIXED = "v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1"
STAGE_NETWORK = "v79pos-hubqa-20261109_stage_internal"
CSS_HASH = "ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c"
LOGIN_HASH = "cb250f00742c5bc3f40f119cbc51f626a1fb94f542f254e27b0d3c6884b4c49b"
PRODUCTS = ("academy", "ffpro", "marketing", "pos", "tiquet")
PNG = b"\x89PNG\r\n\x1a\n"

def ensure(ok, reason):
    if not ok:
        raise RuntimeError("STAGE_ICON_PERMISSION_BLOCKED: " + reason)

def run(*cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)

def inspect(name, what="container"):
    return json.loads(run("docker", what, "inspect", name).stdout)[0]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read_image_files(tag):
    # Use a non-running disposable container; no image start, no live mounts.
    cid = run("docker", "create", "--network", "none", "--entrypoint", "sh",
              tag, "-c", ":").stdout.strip()
    ensure(re.fullmatch("[a-f0-9]{64}", cid) is not None, "Disposable inspection failed")
    try:
        with tempfile.TemporaryDirectory(prefix="v79-icons-read-") as d:
            base = Path(d)
            selected = {}
            files = [
                "src/index.css", "src/components/Login.tsx",
                *(f"public/assets/login-products/{name}.png" for name in PRODUCTS),
            ]
            for name in files:
                target = base / name
                target.parent.mkdir(parents=True, exist_ok=True)
                result = run("docker", "cp", cid + ":/app/" + name,
                             str(target), check=False)
                ensure(result.returncode == 0 and target.is_file() and
                       not target.is_symlink() and target.stat().st_size < 2_000_000,
                       "Expected approved frontend file unavailable: " + name)
                selected[name] = target.read_bytes()
            return selected
    finally:
        run("docker", "rm", cid, check=False)

def check():
    ensure(os.geteuid() != 0, "Do not run stage maintenance as root")
    ensure(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.resolve() == ROOT,
           "Unexpected staging root")
    for filename in (ROOT / ".env", ROOT / "compose.yml"):
        ensure(filename.is_file() and not filename.is_symlink() and
               stat.S_IMODE(filename.stat().st_mode) == 0o600,
               "Staging configuration is not owner-only")
    data = ROOT / "data"
    ensure(data.is_dir() and not data.is_symlink() and
           data.stat().st_uid == os.getuid() and
           stat.S_IMODE(data.stat().st_mode) == 0o700 and
           not any(entry.is_symlink() for entry in data.rglob("*")),
           "Private staging data not safe for checkpoint")
    ensure(not (ROOT / "approved-login-style.json").exists() and
           not (ROOT / "approved-login-assets-perms.json").exists() and
           (ROOT / "approved-login-overlay.json").is_file(),
           "Existing staging promotion state differs; do not repeat")
    ensure(CHECK.is_file() and not CHECK.is_symlink(), "Stage verifier missing")
    # Existing read-only verification checks: stage-only key separation, MFA,
    # signed private POS routing, loopback declarations, health and anonymous 401.
    result = run(sys.executable, str(CHECK), check=False)
    ensure(result.returncode == 0 and
           "STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS" in result.stdout,
           "Existing staging acceptance failed: " + result.stderr[-500:])
    stage = inspect(STAGE)
    live = inspect(LIVE)
    pos = inspect("v79-pos")
    ensure(stage["Config"]["Image"] == STAGE_OLD and
           stage["Image"] == inspect(STAGE_OLD, "image")["Id"] and
           stage["State"]["Health"]["Status"] == "healthy",
           "Stage no longer runs the original healthy login overlay")
    ensure(live["State"]["Health"]["Status"] == "healthy" and
           pos["State"]["Health"]["Status"] == "healthy" and
           pos["Config"]["Image"] == "localhost/v79-brand-pos:20261106-r1",
           "Production health/image unexpected")
    net = stage["NetworkSettings"]["Networks"]
    ensure(set(net) == {STAGE_NETWORK} and
           inspect(STAGE_NETWORK, "network")["Internal"] is True,
           "Stage lost private Docker network isolation")
    paths = stage["HostConfig"].get("PortBindings") or {}
    ensure(paths.get("3040/tcp") == [{"HostIp": "127.0.0.1", "HostPort": "18082"}],
           "Stage Hub is not configured for localhost-only access")
    compose = (ROOT / "compose.yml").read_text()
    old_ref = "    image: " + STAGE_OLD + "\n"
    ensure(compose.count(old_ref) == 1 and
           "container_name: v79-hub-pos-hubqa" in compose and
           "POS_BASE_URL: http://v79-pos-hubqa-api:8080" in compose and
           'V79_REQUIRE_ADMIN_MFA: "1"' in compose and
           'WIPAY_ENABLED: "0"' in compose and
           'RESEND_API_KEY: ""' in compose and
           "proxy_network" not in compose,
           "Unexpected staging Compose settings")
    broken = inspect(BROKEN, "image")
    baseline = inspect(STAGE_OLD, "image")
    layers = broken.get("RootFS", {}).get("Layers") or []
    parents = baseline.get("RootFS", {}).get("Layers") or []
    ensure(len(layers) > len(parents) and layers[:len(parents)] == parents,
           "Broken styled image does not derive from approved staging image")
    selected = read_image_files(BROKEN)
    ensure(sha(selected["src/index.css"]) == CSS_HASH and
           sha(selected["src/components/Login.tsx"]) == LOGIN_HASH,
           "Candidate CSS/login revision does not match owner-verified source")
    ensure(all(selected["public/assets/login-products/" + n + ".png"].startswith(PNG)
               for n in PRODUCTS), "Product image bytes are not PNG")
    return compose, stage, live, pos, broken

def verify_prebuilt_image(broken):
    """Reuse only the exact already-built, owner-observed image, never overwrite it."""
    if run("docker", "image", "inspect", FIXED, check=False).returncode != 0:
        return None
    built = inspect(FIXED, "image")
    ensure(built["Id"] ==
           "sha256:30ee063ae29b77ab09629ae09a361fa80ba78bd5e773c3d97064ed1a557706bf",
           "Existing corrected image differs from owner-observed immutable image ID")
    base_layers = broken.get("RootFS", {}).get("Layers") or []
    new_layers = built.get("RootFS", {}).get("Layers") or []
    ensure(len(new_layers) == len(base_layers) + 1 and
           new_layers[:len(base_layers)] == base_layers,
           "Prebuilt correction is not a single filesystem layer on the approved styled image")
    for key in ("Env", "Entrypoint", "Cmd", "WorkingDir", "User"):
        ensure(built.get("Config", {}).get(key) == broken.get("Config", {}).get(key),
               "Prebuilt image changed runtime setting: " + key)
    history = run("docker", "history", "--no-trunc", "--format",
                  "{{.CreatedBy}}", FIXED).stdout.splitlines()
    ensure(bool(history) and
           "chmod 0755 /app/public/assets/login-products" in history[0] and
           "test -d /app/public/assets/login-products" in history[0],
           "Prebuilt image does not show the approved single-directory chmod operation")
    return built["Id"]

def build():
    with tempfile.TemporaryDirectory(prefix="v79-stage-icon-fix-") as folder:
        dockerfile = Path(folder) / "Dockerfile"
        dockerfile.write_text(
            "FROM " + BROKEN + "\n"
            "RUN test -d /app/public/assets/login-products && "
            "chmod 0755 /app/public/assets/login-products && "
            "test \"$(stat -c %a /app/public/assets/login-products)\" = 755\n"
        )
        out = run("docker", "build", "--network", "none", "--pull=false",
                  "-t", FIXED, folder, check=False)
        ensure(out.returncode == 0,
               "Stage-only permissions image build failed: " + (out.stderr or out.stdout)[-800:])
    return inspect(FIXED, "image")["Id"]

def probe_nonroot_image():
    # No ports, network or running Hub: verify PNG bytes accessible by UID 1000.
    js = (
        "const fs=require('fs');"
        "const ns=['academy','ffpro','marketing','pos','tiquet'];"
        "for(const n of ns){"
        "const p='/app/public/assets/login-products/'+n+'.png';"
        "const b=fs.readFileSync(p);"
        "if(b.length<8||b.subarray(0,8).toString('hex')!=='89504e470d0a1a0a')process.exit(9);"
        "} console.log('NONROOT_PNG_READ=PASS');"
    )
    result = run("docker", "run", "--rm", "--network", "none",
                 "--read-only", "--user", "1000:1000",
                 "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                 "--entrypoint", "node", FIXED, "-e", js, check=False)
    ensure(result.returncode == 0 and "NONROOT_PNG_READ=PASS" in result.stdout,
           "Non-root staging image cannot traverse product image directory")

def checkpoint(compose):
    home = ROOT / "checkpoints"
    home.mkdir(mode=0o700, exist_ok=True)
    ensure(not home.is_symlink() and stat.S_IMODE(home.stat().st_mode) == 0o700,
           "Stage checkpoint directory not private")
    target = home / ("before-product-icon-permissions-" +
                     datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    target.mkdir(mode=0o700)
    shutil.copytree(ROOT / "data", target / "data")
    f = target / "compose.yml"
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(compose)
    return str(target)

def save_compose(body):
    p = ROOT / "compose.yml"
    tmp = ROOT / "compose.yml.icon-fix.tmp"
    ensure(not tmp.exists() and not tmp.is_symlink(), "Stale compose temporary file")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(body)
    os.replace(tmp, p)
    os.chmod(p, 0o600)

def restart_only_stage():
    result = run("docker", "compose", "--env-file", ".env",
                 "-f", "compose.yml", "up", "-d", "--no-deps",
                 "--force-recreate", "--wait", "hub", cwd=ROOT, check=False)
    ensure(result.returncode == 0,
           "Private Hub stage failed to become healthy: " + result.stderr[-700:])

def env_map(container):
    """Compare actual key/value pairs, not Docker's unstable array ordering.

    Never print any environment values; stage secrets are always private.
    """
    rows = container["Config"].get("Env") or []
    result = {}
    for row in rows:
        ensure("=" in row, "Stage runtime has a malformed environment entry")
        name, value = row.split("=", 1)
        ensure(name.isidentifier() and name not in result,
               "Stage runtime environment contains duplicate or invalid keys")
        result[name] = value
    return result


def verified_loopback_binding(container):
    """Require EXACTLY one 3040/TCP binding, to Acer-tunnel-only localhost."""
    bindings = container["HostConfig"].get("PortBindings") or {}
    ensure(set(bindings) == {"3040/tcp"},
           "Staging Hub has an additional or missing published TCP port")
    ports = bindings["3040/tcp"]
    ensure(isinstance(ports, list) and len(ports) == 1 and
           ports[0].get("HostIp") == "127.0.0.1" and
           ports[0].get("HostPort") == "18082",
           "Staging Hub is not restricted to 127.0.0.1:18082")
    effective = (container["NetworkSettings"].get("Ports") or {}).get("3040/tcp") or []
    ensure(all(item.get("HostIp") == "127.0.0.1" and
               item.get("HostPort") == "18082" for item in effective),
           "Effective published stage port differs from loopback-only declaration")


def verify(old, live, pos, new_id):
    after = inspect(STAGE)
    ensure(after["Config"]["Image"] == FIXED and after["Image"] == new_id and
           after["State"]["Health"]["Status"] == "healthy",
           "Stage is not running the approved fixed image")
    before_env = env_map(old)
    after_env = env_map(after)
    if before_env != after_env:
        changed = sorted(k for k in set(before_env) | set(after_env)
                         if before_env.get(k) != after_env.get(k))
        ensure(False, "Stage environment keys changed (values suppressed): " +
               ",".join(changed[:25]))
    print("STAGE_AUTH_AND_SERVICE_ENV_SEMANTICALLY_IDENTICAL=PASS")
    ensure(after["Config"]["User"] == old["Config"]["User"] and
           after["Config"]["User"] == "1000:1000",
           "Stage container no longer uses the same non-root account")
    verified_loopback_binding(old)
    verified_loopback_binding(after)
    print("STAGE_NONROOT_USER_AND_LOOPBACK_BINDING=PASS")
    ensure(set(after["NetworkSettings"]["Networks"]) == {STAGE_NETWORK},
           "Stage network unexpectedly changed")
    ensure(inspect(LIVE)["Id"] == live["Id"] and
           inspect("v79-pos")["Id"] == pos["Id"],
           "Production containers changed")
    # Use container private IP: host Docker port publisher is unreliable.
    addr = after["NetworkSettings"]["Networks"][STAGE_NETWORK]["IPAddress"]
    import urllib.request
    with urllib.request.urlopen("http://" + addr + ":3040/api/health", timeout=8) as r:
        ensure(r.status == 200, "Stage Hub health endpoint not ready")
    for n in PRODUCTS:
        with urllib.request.urlopen(
            "http://" + addr + ":3040/assets/login-products/" + n + ".png",
            timeout=8
        ) as r:
            ensure(r.status == 200 and
                   r.headers.get("Content-Type", "").startswith("image/png") and
                   r.read(8) == PNG,
                   "Staging image response not real PNG: " + n)
    with urllib.request.urlopen("http://" + addr + ":3040/src/index.css?direct",
                               timeout=8) as r:
        ensure(r.status == 200 and
               r.headers.get("Content-Type", "").startswith("text/css"),
               "Approved stylesheet unavailable")
    result = run("docker", "exec", STAGE, "sha256sum", "/app/src/index.css")
    ensure(result.stdout.split()[0] == CSS_HASH, "Approved CSS fingerprint changed")
    print("STAGE_LOGIN_PRODUCT_PNG_HTTP=PASS")
    print("STAGE_LOGIN_CSS=PASS")
    print("STAGE_KEYS_MFA_AND_POS_BACKEND_PRESERVED=PASS")
    print("PRODUCTION_CONTAINERS_UNCHANGED=PASS")

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--apply", action="store_true", help="Recreate only the private Hub stage")
    args = a.parse_args()
    compose, stage, live, pos, broken = check()
    print("STAGING_SAFETY_PREFLIGHT=PASS")
    print("BROKEN_STYLED_IMAGE_ID=" + broken["Id"])
    print("ICON_DIRECTORY_FIX=0755 (only this directory)")
    existing_id = verify_prebuilt_image(broken)
    if existing_id:
        probe_nonroot_image()
        print("EXISTING_CORRECTED_IMAGE_PROVENANCE=PASS")
        print("EXISTING_NONROOT_PRODUCT_IMAGE_READ=PASS")
    if not args.apply:
        print("DRY_RUN_ONLY=PASS")
        return
    new_id = existing_id if existing_id else build()
    probe_nonroot_image()
    print("NONROOT_PRODUCT_IMAGE_READ=PASS")
    dest = checkpoint(compose)
    print("STAGING_PRIVATE_CHECKPOINT=" + dest)
    save_compose(compose.replace("    image: " + STAGE_OLD + "\n",
                                "    image: " + FIXED + "\n", 1))
    try:
        run("docker", "compose", "--env-file", ".env", "-f", "compose.yml",
            "config", "--quiet", cwd=ROOT)
        restart_only_stage()
        verify(stage, live, pos, new_id)
    except Exception:
        print("ICON_STAGE_FIX_FAILED_ATTEMPTING_STAGE_ONLY_ROLLBACK", flush=True)
        save_compose(compose)
        try:
            restart_only_stage()
            print("OLD_STAGE_HUB_IMAGE_RESTORED=PASS", flush=True)
        except Exception as e:
            print("STAGE_ROLLBACK_FAILED=" + str(e), flush=True)
        print("CHECKPOINT_RETAINED=" + dest, flush=True)
        raise
    record = {
        "image": FIXED,
        "image_id": new_id,
        "derived_from": BROKEN,
        "derived_from_id": broken["Id"],
        "previous_staging_image": STAGE_OLD,
        "previous_staging_image_id": stage["Image"],
        "approved_css_sha256": CSS_HASH,
        "approved_login_sha256": LOGIN_HASH,
        "checkpoint": dest,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    pin = ROOT / "approved-login-assets-perms.json"
    fd = os.open(pin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print("STAGING_LOGIN_ASSETS_FIXED=PASS")
    print("STAGING_HUB_HEALTH=PASS")
    print("PRODUCTION_UNCHANGED=PASS")
    print("VERSION3_VISUAL_AND_MFA_SSO=NOT_YET_VERIFIED")

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, AssertionError,
            KeyError, subprocess.CalledProcessError) as err:
        raise SystemExit(str(err)) from None
