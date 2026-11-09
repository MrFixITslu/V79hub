#!/usr/bin/env python3
"""Prepare an isolated Hub + POS staging link. Never modifies live Hub/POS.

Default is read-only preflight. --apply changes ONLY the named stage files.
No secrets are printed. Must run on the authorised Ubuntu V79 server.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

POS_ROOT = Path("/home/firelion/v79-pos-hubqa-20261109")
HUB_ROOT = Path("/home/firelion/v79-hub-pos-hubqa-20261109")
STAGE_POS_IMAGE = "v79pos:hubqa-2590623"
STAGE_NET = "v79pos-hubqa-20261109_stage_internal"
STAGE_API_NAME = "v79-pos-hubqa-api"
STAGE_DB_NAME = "v79-pos-hubqa-db"
STAGE_HUB_NAME = "v79-hub-pos-hubqa"
LIVE_POS_IMAGE = "localhost/v79-brand-pos:20261106-r1"

COMPOSE_REPLACEMENTS = {
    "      HUB_INTERNAL_URL: http://v79-hub:3040":
        "      HUB_INTERNAL_URL: http://v79-hub-pos-hubqa:3040",
    "      HUB_JWKS_URL: http://v79-hub:3040/.well-known/jwks.json":
        "      HUB_JWKS_URL: http://v79-hub-pos-hubqa:3040/.well-known/jwks.json",
    "      JWT_ISSUER: https://hub.v79sl.com":
        "      JWT_ISSUER: http://127.0.0.1:18082",
    "      - proxy_network\n": "",
    "  proxy_network:\n    external: true\n    name: proxy_network\n": "",
}

def die(message):
    raise SystemExit("STAGING_PREP_BLOCKED: " + message)

def docker(*args):
    return subprocess.check_output(["docker", *args], text=True)

def assert_stage_only():
    if not POS_ROOT.is_dir():
        die("POS stage directory missing")
    stage_image = json.loads(docker("image", "inspect", STAGE_POS_IMAGE))[0]
    if not stage_image.get("Id", "").startswith("sha256:"):
        die("Staging image ID is missing")
    live = json.loads(docker("inspect", "v79-pos"))[0]
    if live["Config"]["Image"] != LIVE_POS_IMAGE or live["State"]["Health"]["Status"] != "healthy":
        die("Production POS image/health differs; do not alter anything")
    net = json.loads(docker("network", "inspect", STAGE_NET))[0]
    if not net["Internal"]:
        die("POS staging network is not internal")
    names = {entry.get("Name") for entry in net.get("Containers", {}).values()}
    if any(name and not name.startswith("v79-pos-hubqa-") for name in names):
        die("Unexpected container on staging internal network")
    pos = json.loads(docker("inspect", STAGE_API_NAME))[0]
    stage_db = json.loads(docker("inspect", STAGE_DB_NAME))[0]
    if pos["Config"]["Image"] != STAGE_POS_IMAGE:
        die("POS stage container has an unexpected image")
    if stage_db["Config"]["Image"] != "postgres:17-alpine":
        die("POS stage DB image mismatch")
    for key in ("postgres", "v79commerce", "production"):
        if key in stage_db["Name"]:
            die("Unexpected database container name")
    stage_db_env = dict(entry.split("=", 1) for entry in stage_db["Config"]["Env"] if "=" in entry)
    if stage_db_env.get("POSTGRES_DB") != "v79pos_hubqa":
        die("POS stage DB is not the private v79pos_hubqa database")
    publish = pos["NetworkSettings"]["Ports"].get("8080/tcp", [])
    if len(publish) != 1 or publish[0]["HostIp"] != "127.0.0.1" or publish[0]["HostPort"] != "18081":
        die("Staging API publishing is not restricted to loopback")
    try:
        docker("inspect", STAGE_HUB_NAME)
    except subprocess.CalledProcessError:
        pass
    else:
        die("Staging Hub already exists; do not rotate existing keys")

def read_env(path):
    if not path.is_file() or path.is_symlink():
        die("POS stage .env missing or symbolic link")
    rows = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            die("Unexpected POS stage .env format")
        key, value = line.split("=", 1)
        if not key.isidentifier() or key in rows:
            die("Duplicate/invalid POS stage setting")
        rows[key] = value
    for key in ("STAGE_DB_PASSWORD", "ENCRYPTION_KEY",
                "GIFT_CARD_PEPPER", "V79_PLATFORM_SHARED_SECRET",
                "V79_POS_PLATFORM_SHARED_SECRET"):
        if len(rows.get(key, "")) < 32:
            die("Missing or weak POS staging value: " + key)
    if "V79_HUBQA_CONFIG_VERSION" in rows:
        die("Hub stage already prepared; review files instead of rotating keys")
    return rows

def replace_strict(source, old, new):
    if source.count(old) != 1:
        die("Stage Compose expected field is missing or ambiguous: " + repr(old)[:75])
    return source.replace(old, new, 1)

def prepare_compose(path):
    if not path.is_file() or path.is_symlink():
        die("POS staging Compose file missing or symbolic link")
    raw = path.read_text()
    if "name: v79pos-hubqa-20261109" not in raw or \
       'image: v79pos:hubqa-2590623' not in raw or \
       '127.0.0.1:18081:8080' not in raw or \
       'v79pos_hubqa_20261109_db' not in raw:
        die("Unrecognised POS staging Compose; refusing edits")
    merged = raw
    for old, new in COMPOSE_REPLACEMENTS.items():
        merged = replace_strict(merged, old, new)
    if "proxy_network" in merged or "http://v79-hub:3040" in merged:
        die("Production-reachable POS staging network remains")
    return raw, merged

def private_write_new(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(data)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Modify ONLY the stage POS and Hub files")
    args = parser.parse_args()
    assert_stage_only()
    src = HUB_ROOT / "source" / "staging" / "pos-hubqa" / "hub-compose.yml"
    if not src.is_file():
        die("Hub staged source checkout missing")
    if HUB_ROOT.is_symlink() or POS_ROOT.is_symlink() or not HUB_ROOT.is_dir():
        die("Unrecognised Hub stage destination")
    stage_env = POS_ROOT / ".env"
    stage_pos_compose = POS_ROOT / "hubqa.compose.yml"
    pos_values = read_env(stage_env)
    original, patched = prepare_compose(stage_pos_compose)
    if any((HUB_ROOT / file).exists() for file in (".env", "compose.yml", "data")):
        die("Hub stage already initialised; no rotation/overwrite allowed")
    print("ISOLATED_STAGE_PREFLIGHT=PASS")
    print("LIVE_POS_PRESERVED=PASS")
    print("STAGE_POS_IMAGE=" + STAGE_POS_IMAGE)
    print("STAGE_HOST_PORTS=127.0.0.1:18081,127.0.0.1:18082")
    if not args.apply:
        print("DRY_RUN_ONLY=PASS; add --apply to prepare the private stage")
        return
    secret = secrets.token_hex(48)
    pos_values["V79_PLATFORM_SHARED_SECRET"] = secret
    pos_values["V79_POS_PLATFORM_SHARED_SECRET"] = secret
    pos_values["V79_HUBQA_CONFIG_VERSION"] = "1"
    hub_values = {
        "V79_HUB_ADMIN_USERNAME": "admin",
        "V79_HUB_ADMIN_EMAIL": "vision79slu@gmail.com",
        "V79_HUB_ADMIN_PASSWORD": secrets.token_urlsafe(32),
        "V79_PLATFORM_SHARED_SECRET": secret,
        "V79_POS_PLATFORM_SHARED_SECRET": secret,
        "V79_HUB_SECURITY_KEY": secrets.token_hex(48),
        "V79_REQUIRE_ADMIN_MFA": "1",
        "V79_HUB_STORE_BACKEND": "json",
    }
    os.chmod(HUB_ROOT, 0o700)
    private_write_new(HUB_ROOT / ".env", "".join(
        f"{k}={v}\n" for k, v in hub_values.items()))
    private_write_new(HUB_ROOT / "compose.yml", src.read_text())
    (HUB_ROOT / "data").mkdir(mode=0o700)
    private_write_new(POS_ROOT / "hubqa.compose.pre-hubqa.yml", original)
    temp = POS_ROOT / ".env.hubqa.tmp"
    private_write_new(temp, "".join(f"{k}={v}\n" for k, v in pos_values.items()))
    os.replace(temp, stage_env)
    os.chmod(stage_env, 0o600)
    stage_pos_compose.write_text(patched)
    os.chmod(stage_pos_compose, 0o600)
    subprocess.run(["docker", "compose", "-f", str(stage_pos_compose),
                    "--env-file", str(stage_env), "config", "--quiet"], check=True)
    subprocess.run(["docker", "compose", "-f", str(HUB_ROOT / "compose.yml"),
                    "--env-file", str(HUB_ROOT / ".env"), "config", "--quiet"], check=True)
    print("ISOLATED_STAGE_CONFIG=PASS")
    print("FRESH_STAGE_ONLY_KEYS=PASS")
    print("MFA_REQUIRED=PASS")
    print("STAGE_HUB_CREDENTIALS_FILE=private .env (never paste into chat)")
    print("IMPORTANT=Recreate only stage POS api after starting isolated Hub")

if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        die(type(exc).__name__ + " (preflight or Docker check failed)")
