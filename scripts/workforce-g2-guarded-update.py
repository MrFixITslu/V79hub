#!/usr/bin/env python3
"""Guarded *owner-run* upgrade of the existing 60s G2 create-work-item worker only.

Default --check is strictly read-only. --apply changes one private worker source
file and its user timer, only after exact installed-image/queue/source checks.
No task proposals, approved task execution, DB changes, container changes or releases.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import urllib.request

OLD_BLOB = "948745fcf4e9a4709f586570cea1df417a8654a4"
NEW_BLOB = "2f956ae6cddd1c480963738cb995856856c009bd"
HUB_IMAGE = "sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
HUB_REVISION = "114841271d4f8b9c4b63df6aedfd55bde2e82f40"
CANDIDATE_URL = ("https://raw.githubusercontent.com/MrFixITslu/V79hub/"
                 "e52cb3bcc2f0c25bc79f205af4c6c7b881c2ff22/"
                 "scripts/workforce-approved-task-worker.py")
SERVICE = "v79-g2-approved-task-worker.service"
TIMER = "v79-g2-approved-task-worker.timer"
ROOT = Path.home() / ".local/share/v79-approved-task-worker"

# Trusted Hub code's private and authenticated state-reader, no transact().
LEDGER_READ = r"""
import {createWorkActionStore} from './server/workforce-action-store.mjs';
const s=createWorkActionStore({
  file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',
  secret:process.env.V79_WORKFORCE_AUDIT_KEY,
  backend:process.env.V79_HUB_STORE_BACKEND||'json',
  databaseUrl:process.env.DATABASE_URL||''
});
try {
 const v=await s.read();
 const inFlight=v.jobs.filter(j=>['approved','running','uncertain'].includes(j.status));
 console.log(JSON.stringify({paused:v.paused,unreconciled:inFlight.length}));
} finally {await s.close()}
"""


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def command(args, timeout=20):
    p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if p.returncode != 0 or len(p.stdout) > 400_000:
        raise RuntimeError("Required private runtime check failed")
    return p.stdout.decode("utf-8", "strict")


def private(path):
    if path.is_symlink():
        raise RuntimeError("Symlink rejected")
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or (s.st_mode & 0o077) or s.st_uid != os.getuid():
        raise RuntimeError("Unsafe owner-private file")
    return path.read_bytes()


def fixed_files():
    d = ROOT.lstat()
    if not stat.S_ISDIR(d.st_mode) or d.st_uid != os.getuid() or d.st_mode & 0o077:
        raise RuntimeError("Unsafe worker directory")
    old = ROOT / "worker.py"
    original = private(old)
    if blob(original) not in (OLD_BLOB, NEW_BLOB):
        raise RuntimeError("Installed worker differs from both reviewed versions")
    config = json.loads(private(ROOT / "config.json"))
    if set(config) != {"schema", "tokenFile"} or config["schema"] != 1:
        raise RuntimeError("Worker configuration changed")
    token = Path(config["tokenFile"])
    if not token.is_absolute() or not token.is_file() or token.is_symlink():
        raise RuntimeError("Worker credential path unsafe")
    st = token.lstat()
    if st.st_mode & 0o077 or st.st_size < 32 or st.st_size > 512:
        raise RuntimeError("Worker credential permissions unavailable")
    unit = private(Path.home() / ".config/systemd/user" / SERVICE)
    required = "ExecStart=/usr/bin/python3 -I " + str(old) + " " + str(ROOT / "config.json")
    if required.encode() not in unit:
        raise RuntimeError("Unexpected installed unit execution path")
    if (ROOT / "uncertain.json").exists() or (ROOT / "uncertain.json").is_symlink():
        raise RuntimeError("Uncertain G2 result must be manually reconciled")
    return old, original


def unit_state(name):
    output = command(["systemctl", "--user", "show", name,
                      "--property=ActiveState", "--property=UnitFileState",
                      "--property=Result"])
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def pinned_hub():
    row = json.loads(command(["docker", "inspect", "v79-hub"]))[0]
    if row.get("Image") != HUB_IMAGE or (
            row.get("State", {}).get("Health", {}).get("Status") != "healthy"):
        raise RuntimeError("Installed Hub image or health differs from owner audit")
    label = row.get("Config", {}).get("Labels", {}).get("org.opencontainers.image.revision")
    # Image label is only a guard, not proof that all source files match.
    if label != HUB_REVISION:
        raise RuntimeError("Installed Hub revision changed")
    env = {x.split("=", 1)[0]: x.split("=", 1)[1]
           for x in row.get("Config", {}).get("Env", []) if "=" in x}
    if env.get("V79_WORKFORCE_ACTIONS_ENABLED") != "1":
        raise RuntimeError("Owner-approved G2 disabled")
    state = json.loads(command(["docker", "exec", "v79-hub", "node",
                                "--input-type=module", "-e", LEDGER_READ]))
    if state.get("unreconciled") != 0 or state.get("paused") is not False:
        raise RuntimeError("Pending/running/uncertain G2 work or pause in effect")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("Unexpected candidate redirect")


def candidate():
    request = urllib.request.Request(CANDIDATE_URL, headers={"Accept": "text/plain"})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=18) as response:
        if response.status != 200:
            raise RuntimeError("Candidate source unavailable")
        data = response.read(40001)
    if len(data) > 40000 or blob(data) != NEW_BLOB:
        raise RuntimeError("Candidate source does not match reviewed blob")
    compile(data, "<v79-reviewed-worker>", "exec")
    return data


def fsync_dir():
    fd = os.open(ROOT, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def apply(old, original, replacement):
    # Do not patch/restart the entire Hub, DB, Agent, Tiquet or Sentinel.
    timer = unit_state(TIMER)
    service = unit_state(SERVICE)
    if timer.get("ActiveState") != "active" or timer.get("UnitFileState") not in (
            "enabled", "enabled-runtime") or service.get("ActiveState") != "inactive":
        raise RuntimeError("Worker timer/service not in expected idle state")
    if blob(original) == NEW_BLOB:
        print("G2_WORKER=ALREADY_REVIEWED_VERSION")
        return
    saved = ROOT / ("worker.py.precrashfix." + OLD_BLOB[:12])
    staged = ROOT / "worker.py.candidate"
    if saved.exists() or staged.exists() or saved.is_symlink() or staged.is_symlink():
        raise RuntimeError("Existing patch artifacts need operator reconciliation")
    command(["systemctl", "--user", "stop", TIMER])
    changed = False
    try:
        if unit_state(SERVICE).get("ActiveState") != "inactive":
            raise RuntimeError("Worker was running after timer stop")
        pinned_hub()  # Fresh signed-queue check while timer is stopped.
        if private(old) != original:
            raise RuntimeError("Worker source raced before patch")
        with saved.open("xb") as f:
            os.chmod(saved, 0o600)
            f.write(original)
            f.flush()
            os.fsync(f.fileno())
        with staged.open("xb") as f:
            os.chmod(staged, 0o600)
            f.write(replacement)
            f.flush()
            os.fsync(f.fileno())
        fsync_dir()
        os.replace(staged, old)
        changed = True
        fsync_dir()
        if blob(private(old)) != NEW_BLOB:
            raise RuntimeError("Postreplace worker identity drift")
        command(["systemctl", "--user", "start", TIMER])
        if unit_state(TIMER).get("ActiveState") != "active":
            raise RuntimeError("Timer did not resume")
        print("G2_WORKER_PATCH=REVIEWED_CRASH_LATCH_INSTALLED")
        print("G2_TIMER=ACTIVE")
        print("OWNER_APPROVED_QUEUE_ACTIONS=UNCHANGED")
        print("CONTAINERS_AND_DATA=NOT_MODIFIED")
        print("G2_E2E_TASK_DELIVERY=NOT_TESTED")
    except Exception:
        if changed:
            # Revert only this worker file if restart/check fails.
            if blob(private(saved)) != OLD_BLOB:
                raise RuntimeError("STOP_WORKER_BACKUP_INTEGRITY_FAILURE_MANUAL_RECOVERY")
            with old.open("wb") as f:
                os.chmod(old, 0o600)
                f.write(original)
                f.flush()
                os.fsync(f.fileno())
            fsync_dir()
        try:
            command(["systemctl", "--user", "start", TIMER])
        except Exception:
            raise RuntimeError("STOP_TIMER_RECOVERY_UNVERIFIED_MANUAL_INTERVENTION")
        raise


def main():
    parser = argparse.ArgumentParser()
    x = parser.add_mutually_exclusive_group(required=True)
    x.add_argument("--check", action="store_true")
    x.add_argument("--apply", action="store_true")
    options = parser.parse_args()
    os.umask(0o077)
    if socket.gethostname() != "v79sl":
        raise RuntimeError("Only approved v79sl owner session can run this")
    old, data = fixed_files()
    pinned_hub()
    worker = unit_state(SERVICE)
    timer = unit_state(TIMER)
    if timer.get("ActiveState") != "active" or worker.get("ActiveState") != "inactive":
        raise RuntimeError("Unexpected live timer/service state")
    new = candidate()
    print("G2_WORKER_INSTALLED_GIT_BLOB=" + blob(data))
    print("G2_GUARDED_CANDIDATE_GIT_BLOB=" + blob(new))
    print("G2_UNRECONCILED_APPROVED_RUNNING_UNCERTAIN=0")
    print("G2_TIMER=ACTIVE_AND_WORKER_IDLE")
    if options.check:
        print("G2_PATCH=SAFE_CANDIDATE_NOT_APPLIED")
        print("PRODUCTION_CHANGES=NONE")
    else:
        apply(old, data, new)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("G2_PATCH=STOPPED")
        print("G2_REASON=" + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__))
        raise SystemExit(1)
