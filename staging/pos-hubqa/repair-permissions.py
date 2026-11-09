#!/usr/bin/env python3
"""One-time, idempotent repair for private Hub staging EACCES, not a production operation.

Default: inspect only. --apply updates ONLY the existing private Hub staging
Compose and .env to run as the stage-data owner. Does not rotate any secret.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT = Path("/home/firelion/v79-hub-pos-hubqa-20261109")
POS_STAGE = Path("/home/firelion/v79-pos-hubqa-20261109")
STAGE_IMAGE = "v79hub:pos-hubqa-20261109"
PROD_IMAGE = "localhost/v79-brand-pos:20261106-r1"

OWNER_DIRECTIVE = """    # Run as the owner of the private stage-only bind mount, not root.
    user: "${V79_HUB_STAGE_UID:?Set staging directory owner UID}:${V79_HUB_STAGE_GID:?Set staging directory owner GID}"
"""
CACHE_DIRECTIVE = """    # Vite development cache writes must also work without root or loosening /app permissions.
    tmpfs:
      - "/app/node_modules/.vite:uid=${V79_HUB_STAGE_UID},gid=${V79_HUB_STAGE_GID},mode=0700"
      - "/app/node_modules/.vite-temp:uid=${V79_HUB_STAGE_UID},gid=${V79_HUB_STAGE_GID},mode=0700"
"""


def check(condition, message):
    if not condition:
        raise SystemExit("STAGE_PERMISSION_REPAIR_BLOCKED: " + message)


def inspect(name):
    result = subprocess.run(["docker", "inspect", name],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, check=True)
    return json.loads(result.stdout)[0]


def envparse(text):
    pairs = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        check("=" in line, "Unexpected environment line")
        key, value = line.split("=", 1)
        check(key.isidentifier() and key not in pairs, "Duplicate/invalid environment key")
        pairs[key] = value
    return pairs


def atomic_save(path, content):
    check(not path.is_symlink() and path.is_file(), "Refusing unsafe target file")
    temp = path.with_name(path.name + ".permissions-repair.tmp")
    check(not temp.exists() and not temp.is_symlink(), "Stale repair temp file exists")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Repair private staging only")
    args = parser.parse_args()

    check(os.geteuid() != 0, "Execute as the owner of the stage directory, not root")
    root = ROOT.resolve(strict=True)
    check(root == ROOT and not ROOT.is_symlink() and ROOT.is_dir(),
          "Unknown staging Hub root")
    data = ROOT / "data"
    check(data.is_dir() and not data.is_symlink(), "Private Hub stage data missing")
    s = data.stat()
    check(s.st_uid == os.getuid() and s.st_gid == os.getgid(),
          "Stage data owner differs from current user")
    check(stat.S_IMODE(s.st_mode) == 0o700,
          "Stage data directory must retain private mode 0700")
    check((POS_STAGE / ".env").is_file(), "Isolated POS stage configuration missing")

    live = inspect("v79-pos")
    check(live["Config"]["Image"] == PROD_IMAGE and
          live["State"]["Health"]["Status"] == "healthy",
          "Production POS image or health changed; halt")

    hub = inspect("v79-hub-pos-hubqa")
    check(hub["Config"]["Image"] == STAGE_IMAGE,
          "Hub stage does not use the expected isolated image")
    check(not hub["State"]["Running"],
          "Stage Hub is running; refusal prevents disruption")
    publish = hub["HostConfig"]["PortBindings"].get("3040/tcp") or []
    check(len(publish) == 1 and publish[0].get("HostIp") == "127.0.0.1" and
          publish[0].get("HostPort") == "18082",
          "Hub stage port binding is not private")

    template = ROOT / "source" / "staging" / "pos-hubqa" / "hub-compose.yml"
    target = ROOT / "compose.yml"
    env_file = ROOT / ".env"
    for path in (template, target, env_file):
        check(path.is_file() and not path.is_symlink(),
              "Required trusted staging file missing or symlinked")
    updated = template.read_text()
    check(updated.count(OWNER_DIRECTIVE) == 1 and
          updated.count(CACHE_DIRECTIVE) == 1,
          "Updated Hub stage Compose source not checked out")
    original = updated.replace(OWNER_DIRECTIVE, "", 1).replace(CACHE_DIRECTIVE, "", 1)
    installed = target.read_text()
    check(installed in (original, updated),
          "Installed Hub stage Compose differs from known safe template")
    old_env = env_file.read_text()
    values = envparse(old_env)
    check(len(values.get("V79_HUB_ADMIN_PASSWORD", "")) >= 20 and
          len(values.get("V79_PLATFORM_SHARED_SECRET", "")) >= 32,
          "Stage Hub credentials absent or too short")
    check(not (ROOT / "data").is_symlink(),
          "Staging data folder must not be a symlink")
    uid, gid = str(os.getuid()), str(os.getgid())
    for key, expected in (("V79_HUB_STAGE_UID", uid), ("V79_HUB_STAGE_GID", gid)):
        check(key not in values or values[key] == expected,
              "Existing stage user mapping conflicts with current data owner")

    check(subprocess.run(
        ["docker", "image", "inspect", STAGE_IMAGE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0, "Prepared staging Hub image missing")
    print("STAGE_PERMISSION_PREFLIGHT=PASS")
    print("PRIVATE_DATA_DIRECTORY_PRESERVED=PASS")
    print("EXISTING_STAGE_KEYS_PRESERVED=PASS")
    print("PRODUCTION_POS_HEALTH=PASS")

    if not args.apply:
        print("DRY_RUN_ONLY=PASS")
        return

    suffix = ""
    if "V79_HUB_STAGE_UID" not in values:
        suffix += f"V79_HUB_STAGE_UID={uid}\n"
    if "V79_HUB_STAGE_GID" not in values:
        suffix += f"V79_HUB_STAGE_GID={gid}\n"
    if suffix:
        atomic_save(env_file, old_env.rstrip("\n") + "\n" + suffix)
    if installed != updated:
        atomic_save(target, updated)
    subprocess.run(["docker", "compose", "--env-file", ".env", "-f", "compose.yml",
                    "config", "--quiet"], cwd=ROOT, check=True)
    print("STAGE_PERMISSION_CONFIGURATION=PASS")
    print("NON_ROOT_STAGE_RUNTIME=CONFIGURED")
    print("NO_IMAGE_REBUILD_OR_KEY_ROTATION=PASS")


if __name__ == "__main__":
    main()
