#!/usr/bin/env python3
"""Pin the private Hub->POS test Hub to the actual running Hub image, not GitHub main.

Dry-run by default. --apply copies no live data or secrets, retains the existing
private stage store and keys, and recreates ONLY v79-hub-pos-hubqa.
"""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import urllib.request

ROOT = Path("/home/firelion/v79-hub-pos-hubqa-20261109")
POS_ROOT = Path("/home/firelion/v79-pos-hubqa-20261109")
STAGE_NET = "v79pos-hubqa-20261109_stage_internal"
OLD_IMAGE = "v79hub:pos-hubqa-20261109"
PROD_POS_IMAGE = "localhost/v79-brand-pos:20261106-r1"
IMAGE_LINE = "    image: " + OLD_IMAGE + "\n"
STAGE_HUB = "v79-hub-pos-hubqa"
LIVE_HUB = "v79-hub"

def guard(ok, message):
    if not ok:
        raise RuntimeError("STAGE_UI_SYNC_BLOCKED: " + message)

def run(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=check)

def inspect(name, kind="container"):
    output = run("docker", kind, "inspect", name)
    return json.loads(output.stdout)[0]

def env(container):
    return dict(s.split("=", 1) for s in container["Config"]["Env"] if "=" in s)

def stage_ip(container):
    networks = container["NetworkSettings"]["Networks"]
    guard(set(networks) == {STAGE_NET}, "Stage container attached to unexpected Docker network")
    addr = networks[STAGE_NET].get("IPAddress", "")
    guard(bool(addr) and ipaddress.ip_address(addr).version == 4,
          "No private staging IPv4 address")
    return addr

def binding(container, internal, port):
    bindings = container["HostConfig"].get("PortBindings") or {}
    one = bindings.get(internal) or []
    guard(len(one) == 1 and one[0].get("HostIp") == "127.0.0.1"
          and one[0].get("HostPort") == str(port),
          "Stage port is not configured to bind loopback only")

def read_private_env(path):
    guard(path.is_file() and not path.is_symlink(), "Staging .env missing or symlinked")
    guard(stat.S_IMODE(path.stat().st_mode) == 0o600, "Stage .env must be private")
    rows = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        guard("=" in line, "Unexpected stage environment format")
        k, v = line.split("=", 1)
        guard(k.isidentifier() and k not in rows, "Invalid stage environment key")
        rows[k] = v
    guard(len(rows.get("V79_HUB_ADMIN_PASSWORD", "")) >= 20 and
          len(rows.get("V79_PLATFORM_SHARED_SECRET", "")) >= 32 and
          len(rows.get("V79_POS_PLATFORM_SHARED_SECRET", "")) >= 32 and
          len(rows.get("V79_HUB_SECURITY_KEY", "")) >= 32,
          "Dedicated staging keys missing or weak")
    guard(rows["V79_HUB_SECURITY_KEY"] != rows["V79_PLATFORM_SHARED_SECRET"],
          "Stage signing/MFA keys must differ")
    guard(rows["V79_PLATFORM_SHARED_SECRET"] == rows["V79_POS_PLATFORM_SHARED_SECRET"],
          "Stage POS signature contract mismatch")
    guard(rows.get("V79_REQUIRE_ADMIN_MFA") == "1",
          "Stage administrator MFA not enabled")
    guard(rows.get("V79_HUB_STAGE_UID") == str(os.getuid()) and
          rows.get("V79_HUB_STAGE_GID") == str(os.getgid()),
          "Stage identity mapping changed")
    return rows

def private_stage_store():
    data = ROOT / "data"
    guard(data.is_dir() and not data.is_symlink(), "Stage data directory missing")
    st = data.stat()
    guard(st.st_uid == os.getuid() and st.st_gid == os.getgid() and
          stat.S_IMODE(st.st_mode) == 0o700,
          "Stage data must retain owner-only 0700 access")
    for entry in data.rglob("*"):
        guard(not entry.is_symlink(), "Symlink in stage data prohibits snapshot")
    return data

def stage_compose():
    path = ROOT / "compose.yml"
    template = ROOT / "source" / "staging" / "pos-hubqa" / "hub-compose.yml"
    guard(path.is_file() and not path.is_symlink() and template.is_file(),
          "Missing trusted staging Compose")
    raw = path.read_text()
    guard(raw == template.read_text(), "Stage Compose differs from approved template")
    guard(raw.count(IMAGE_LINE) == 1, "Stage Compose source image unexpected")
    for required in (
        "container_name: v79-hub-pos-hubqa",
        "127.0.0.1:18082:3040",
        "V79_REQUIRE_ADMIN_MFA: \"1\"",
        "POS_BASE_URL: http://v79-pos-hubqa-api:8080",
        "POS_PUBLIC_URL: http://127.0.0.1:18081",
        "V79_WORKFORCE_ACTIONS_ENABLED: \"0\"",
        "WIPAY_ENABLED: \"0\"",
        "RESEND_API_KEY: \"\"",
        "external: true",
        "name: v79pos-hubqa-20261109_stage_internal",
    ):
        guard(required in raw, "Staging safety setting is missing")
    guard("proxy_network" not in raw, "Stage would gain access to live proxy network")
    return path, raw

def current_runtime():
    live = inspect(LIVE_HUB)
    prod_pos = inspect("v79-pos")
    stage = inspect(STAGE_HUB)
    pos = inspect("v79-pos-hubqa-api")
    db = inspect("v79-pos-hubqa-db")
    net = inspect(STAGE_NET, "network")
    guard(net["Internal"] is True, "Staging bridge is not internal-only")
    for container, label in ((live, "live Hub"), (stage, "staging Hub"),
                             (prod_pos, "live POS"), (pos, "staging POS"),
                             (db, "staging PostgreSQL")):
        guard(container["State"].get("Health", {}).get("Status") == "healthy",
              label + " not healthy")
    guard(live["State"]["Running"], "Live Hub is not running")
    guard(prod_pos["Config"]["Image"] == PROD_POS_IMAGE, "Unexpected live POS image")
    guard(pos["Config"]["Image"] == "v79pos:hubqa-2590623",
          "Unexpected POS stage image")
    guard(stage["Config"]["Image"] == OLD_IMAGE, "Staging Hub already changed; inspect first")
    guard(stage["Image"].startswith("sha256:") and
          live["Image"].startswith("sha256:"), "Missing immutable image ID")
    binding(stage, "3040/tcp", 18082)
    binding(pos, "8080/tcp", 18081)
    stage_ip(stage)
    stage_ip(pos)
    stage_ip(db)
    guard(env(db).get("POSTGRES_DB") == "v79pos_hubqa",
          "Stage database unexpectedly points to a different DB")
    hs = env(stage)
    guard(hs.get("POS_BASE_URL") == "http://v79-pos-hubqa-api:8080"
          and hs.get("POS_PUBLIC_URL") == "http://127.0.0.1:18081"
          and hs.get("APP_URL") == "http://127.0.0.1:18082"
          and hs.get("V79_HUB_STORE_BACKEND") == "json"
          and hs.get("NODE_ENV") == "development"
          and hs.get("V79_REQUIRE_ADMIN_MFA") == "1"
          and hs.get("WIPAY_ENABLED") == "0"
          and hs.get("RESEND_API_KEY", "") == ""
          and hs.get("V79_WORKFORCE_ACTIONS_ENABLED") == "0",
          "Stage runtime isolation or MFA changed")
    guard(not any(m["Type"] == "bind" and m.get("Destination") != "/app/data"
                  for m in stage["Mounts"]), "Unexpected stage Hub host bind")
    mounts = [m for m in stage["Mounts"] if m["Type"] == "bind"]
    guard(len(mounts) == 1 and mounts[0].get("Source") == str(ROOT / "data"),
          "Stage Hub has unexpected data mount")
    return live, prod_pos, stage, pos

def image_check(live):
    info = inspect(live["Image"], "image")
    guard(info["Id"] == live["Image"], "Live Hub image changed during inspection")
    for row in (info.get("Config", {}).get("Env") or []):
        key = row.split("=", 1)[0].upper()
        guard(not (key.startswith(("V79_", "RESEND_", "WIPAY_", "POSTGRES_",
                                   "DATABASE_", "GOOGLE_", "JWT_")) or
                   key in {"API_KEY", "REDIS_URL", "DATABASE_URL"}),
              "Image contains baked-in potentially sensitive setting: " + key)
    return "v79hub:pos-hubqa-live-" + live["Image"][7:19]

def make_checkpoint(data, compose, raw):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    home = ROOT / "checkpoints"
    home.mkdir(mode=0o700, exist_ok=True)
    guard(not home.is_symlink() and stat.S_IMODE(home.stat().st_mode) == 0o700,
          "Stage checkpoint directory is not private")
    dest = home / ("before-live-ui-" + stamp)
    dest.mkdir(mode=0o700)
    shutil.copytree(data, dest / "data", symlinks=False)
    backup = dest / "compose.yml"
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(raw)
    return dest

def write_new_compose(path, raw):
    temp = path.with_name("compose.yml.live-ui.tmp")
    guard(not temp.exists() and not temp.is_symlink(), "Stale Compose temp file")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(raw)
    os.replace(temp, path)
    os.chmod(path, 0o600)

def up_stage():
    result = run("docker", "compose", "--env-file", ".env", "-f", "compose.yml",
                 "up", "-d", "--no-deps", "--force-recreate", "--wait", "hub",
                 cwd=ROOT, check=False)
    if result.returncode:
        print("STAGING_HUB_START_FAILED: " + (result.stderr or "")[-1200:],
              file=sys.stderr)
        raise RuntimeError("Stage Hub did not become healthy")

def health(url):
    with urllib.request.urlopen(url, timeout=8) as response:
        return response.status

def verify_staged_website(source_id, original_production_id, original_pos_id):
    live, _, stage, pos = current_after()
    guard(live["Id"] == original_production_id and
          pos["Id"] == original_pos_id,
          "Non-stage container changed during stage update")
    guard(stage["Image"] == source_id, "Stage Hub is not running exact live Hub image")
    guard(health("http://" + stage_ip(stage) + ":3040/api/health") == 200,
          "Stage Hub health endpoint is failing")

def current_after():
    live, pos, stage, stage_pos = (
        inspect(LIVE_HUB), inspect("v79-pos"),
        inspect(STAGE_HUB), inspect("v79-pos-hubqa-api")
    )
    guard(live["State"].get("Health", {}).get("Status") == "healthy" and
          pos["State"].get("Health", {}).get("Status") == "healthy" and
          stage["State"].get("Health", {}).get("Status") == "healthy" and
          stage_pos["State"].get("Health", {}).get("Status") == "healthy",
          "Hub/POS health is not fully healthy")
    stage_ip(stage)
    stage_ip(stage_pos)
    binding(stage, "3040/tcp", 18082)
    return live, pos, stage, stage_pos

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Change ONLY named private Hub staging image")
    args = parser.parse_args()
    guard(os.geteuid() != 0, "Run as stage directory owner, never root")
    guard(ROOT.is_dir() and ROOT.resolve() == ROOT and not ROOT.is_symlink(),
          "Unexpected staging Hub folder")
    private_stage_store()
    stage_env = read_private_env(ROOT / ".env")
    compose, raw = stage_compose()
    live, prod_pos, stage, pos = current_runtime()
    prod_image_env = env(live)
    for key in ("V79_PLATFORM_SHARED_SECRET", "V79_POS_PLATFORM_SHARED_SECRET"):
        if prod_image_env.get(key):
            guard(stage_env[key] != prod_image_env[key],
                  "Stage reuses live signing credentials")
    new_tag = image_check(live)
    guard(live["Image"] != stage["Image"], "Stage already matches live image")
    guard(not (ROOT / "approved-live-image.json").exists(),
          "Already promoted; no automatic re-pin")
    info = run("docker", "image", "inspect", new_tag, check=False)
    if info.returncode == 0:
        img = json.loads(info.stdout)[0]
        guard(img["Id"] == live["Image"], "Staging tag points to a different image")

    print("LIVE_HUB_RUNNING_IMAGE=" + live["Config"]["Image"])
    print("LIVE_HUB_IMAGE_ID=" + live["Image"])
    print("PRIVATE_HUB_STAGE_OLD_IMAGE=" + stage["Config"]["Image"])
    print("PRIVATE_HUB_STAGE_NEW_IMAGE=" + new_tag)
    print("PRODUCTION_AND_STAGE_ISOLATION_PREFLIGHT=PASS")
    print("STAGING_KEYS_AND_DATA_PRESERVED=PASS")

    if not args.apply:
        print("DRY_RUN_ONLY=PASS")
        return

    checkpoint = make_checkpoint(ROOT / "data", compose, raw)
    print("PRIVATE_STAGE_ROLLBACK_CHECKPOINT=" + str(checkpoint))
    run("docker", "tag", live["Image"], new_tag)
    new = raw.replace(IMAGE_LINE, "    image: " + new_tag + "\n", 1)
    write_new_compose(compose, new)
    try:
        run("docker", "compose", "--env-file", ".env", "-f", "compose.yml",
            "config", "--quiet", cwd=ROOT)
        up_stage()
        verify_staged_website(live["Image"], live["Id"], pos["Id"])
    except Exception:
        print("STAGE_PROMOTION_FAILED_ATTEMPTING_IMAGE_ONLY_ROLLBACK",
              file=sys.stderr)
        write_new_compose(compose, raw)
        try:
            up_stage()
            print("OLD_STAGE_HUB_IMAGE_RESTORED=PASS", file=sys.stderr)
        except Exception as error:
            print("OLD_STAGE_HUB_RESTORE_FAILED=" + str(error), file=sys.stderr)
        print("STAGE_DATA_CHECKPOINT_RETAINED=" + str(checkpoint),
              file=sys.stderr)
        raise

    note = {
        "source": "exact running production Hub image at staged pin time",
        "production_image_id": live["Image"],
        "production_image_tag": live["Config"]["Image"],
        "stage_image_tag": new_tag,
        "previous_stage_image_tag": OLD_IMAGE,
        "checkpoint": str(checkpoint),
        "pinned_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    pin = ROOT / "approved-live-image.json"
    fd = os.open(pin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(note, stream, indent=2)
        stream.write("\n")
    print("STAGING_HUB_EXACT_LIVE_IMAGE=PASS")
    print("STAGING_HUB_HEALTH=PASS")
    print("STAGING_DATA_AND_KEYS_PRESERVED=PASS")
    print("PRODUCTION_CONTAINERS_NOT_RECREATED=PASS")
    print("BROWSER_VERSION_3_MFA_SSO=NOT_YET_TESTED")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError,
            ValueError, KeyError, AssertionError) as exc:
        raise SystemExit(str(exc)) from None
