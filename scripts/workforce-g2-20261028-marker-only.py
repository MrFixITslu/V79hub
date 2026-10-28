#!/usr/bin/env python3
"""Owner-only, exact-state G2 uncertainty evidence review and optional archival.

--review never modifies any file, timer, task, credential or service.
--archive only after a separate explicit owner run. It archives (never deletes)
the precise marker, without replacing source, sending a POST or touching Hub.
A stale or ambiguous state fails closed.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys

ROOT = Path.home() / ".local/share/v79-approved-task-worker"
MARKER = ROOT / "uncertain.json"
ARCHIVE = ROOT / "uncertain.20261028T153212142639Z.reviewed.json"
MARKER_UTC = dt.datetime.fromisoformat("2026-10-28T15:32:12.142639+00:00")
RECEIPT_UTC = dt.datetime.fromisoformat("2026-10-28T15:31:11.366584+00:00")
WORKER_SHA256 = "5f629915d7715620fdd17ac0fed80cf595e65dab0035d0739a53c9bc5984fb3d"
HUB_IMAGE = "sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec"
TIMER = "v79-g2-approved-task-worker.timer"
SERVICE = "v79-g2-approved-task-worker.service"
STAMP = "2026-10-28T15:32:12.142639Z"
MARKER_PAYLOAD = {"state": "uncertain", "action": "inspect_signed_queue_before_reset"}
RECEIPT_PAYLOAD = {"state": "idle", "operation": "create_work_item"}

# This is Hub's EXISTING HMAC-authenticated store reader. Read only; no POST.
READER = r"""
import {createWorkActionStore} from './server/workforce-action-store.mjs';
const cutoff=Date.parse(process.argv[1]);
const store=createWorkActionStore({
 file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',
 secret:process.env.V79_WORKFORCE_AUDIT_KEY,
 backend:process.env.V79_HUB_STORE_BACKEND||'json',
 databaseUrl:process.env.DATABASE_URL||''
});
try{
 const v=await store.read();
 const jobs=v.jobs.filter(j=>j.operation==='create_work_item');
 const good=jobs.filter(j=>j.status==='succeeded');
 const bad=jobs.filter(j=>j.status==='rejected');
 const events=v.events.filter(e=>e.type==='work_item_created'&&e.actor==='coo-worker');
 const tasks=v.tasks.filter(t=>t.system==='hub'&&t.jobId);
 const inFlight=jobs.filter(j=>['approved','running','uncertain'].includes(j.status));
 const timeOf=x=>Date.parse(x);
 const before=items=>items.every(x=>Number.isFinite(x)&&x<cutoff);
 const linked=good.every(j=>tasks.filter(t=>t.jobId===j.id&&t.id===j.result?.taskId&&
   t.organizationId===j.organizationId).length===1 &&
   events.filter(e=>e.jobId===j.id&&e.digest===j.digest).length===1);
 const taskIds=tasks.map(t=>t.id);
 const jobIds=jobs.map(j=>j.id);
 const eventJobs=events.map(e=>e.jobId);
 const valid=Number.isFinite(cutoff)&&v.paused===false&&
   jobs.length===6&&good.length===5&&bad.length===1&&inFlight.length===0&&
   tasks.length===5&&events.length===5&&linked&&
   new Set(taskIds).size===5&&new Set(jobIds).size===6&&
   new Set(eventJobs).size===5&&
   before(tasks.map(t=>timeOf(t.createdAt)))&&
   before(events.map(e=>timeOf(e.at)))&&
   before(good.map(j=>timeOf(j.result?.at)))&&
   before(jobs.map(j=>timeOf(j.createdAt)));
 console.log(JSON.stringify({signature:'HMAC_STORE_VALIDATED',safe:valid,
   jobs:jobs.length,succeeded:good.length,rejected:bad.length,
   tasks:tasks.length,createdEvents:events.length,
   inFlight:inFlight.length,postMarkerTaskCount:events.filter(e=>timeOf(e.at)>=cutoff).length,
   paused:v.paused,linked,allEffectsBeforeMarker:
   before(tasks.map(t=>timeOf(t.createdAt)))&&before(events.map(e=>timeOf(e.at)))}));
}finally{await store.close()}
"""


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def safe_file(path, max_bytes=100_000):
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
            and st.st_nlink == 1 and st.st_mode & 0o077 == 0
            and st.st_size <= max_bytes and not path.is_symlink(),
            "PRIVATE_FILE_CHANGED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st2 = os.fstat(fd)
        require(st2.st_ino == st.st_ino and st2.st_dev == st.st_dev
                and st2.st_size == st.st_size, "PRIVATE_FILE_RACED")
        return os.read(fd, max_bytes + 1), st
    finally:
        os.close(fd)


def cmd(args, timeout=20):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("REQUIRED_READONLY_CHECK_UNAVAILABLE")
    require(p.returncode == 0 and len(p.stdout) <= 500_000,
            "REQUIRED_READONLY_CHECK_FAILED")
    return p.stdout.decode("utf8", "strict").strip()


def unit(name):
    raw = cmd(["systemctl", "--user", "show", name, "--property=ActiveState",
               "--property=UnitFileState", "--property=Result"])
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def sync_parent():
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def check_files():
    require(socket.gethostname() == "v79sl" and os.getuid() == os.geteuid(),
            "EXPECTED_OWNER_HOST_ONLY")
    st = ROOT.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()
            and st.st_mode & 0o077 == 0 and not ROOT.is_symlink(),
            "PRIVATE_WORKER_ROOT_CHANGED")
    require(not ARCHIVE.exists() and not ARCHIVE.is_symlink(),
            "INCIDENT_ALREADY_ARCHIVED_OR_COLLISION")
    m, mstat = safe_file(MARKER, 4096)
    require(json.loads(m) == MARKER_PAYLOAD and
            abs(mstat.st_mtime - MARKER_UTC.timestamp()) < 0.005,
            "EXACT_20261028_MARKER_CHANGED")
    data, rst = safe_file(ROOT / "status.json", 4096)
    require(json.loads(data) == RECEIPT_PAYLOAD and
            abs(rst.st_mtime - RECEIPT_UTC.timestamp()) < 0.005
            and rst.st_mtime < mstat.st_mtime,
            "PRE_MARKER_IDLE_RECEIPT_CHANGED")
    for name in ("status.tmp", "worker.py.candidate"):
        p = ROOT / name
        require(not p.exists() and not p.is_symlink(),
                "UNRECONCILED_STAGING_FILE_PRESENT")
    worker, _ = safe_file(ROOT / "worker.py", 45_000)
    require(hashlib.sha256(worker).hexdigest() == WORKER_SHA256,
            "INSTALLED_CRASH_SAFE_WORKER_CHANGED")
    configuration, _ = safe_file(ROOT / "config.json", 5000)
    obj = json.loads(configuration)
    require(set(obj) == {"schema", "tokenFile"} and obj["schema"] == 1,
            "WORKER_CONFIG_SCHEMA_CHANGED")
    key = Path(obj["tokenFile"])
    require(key.is_absolute() and not key.is_symlink(), "WORKER_KEY_LOCATION_CHANGED")
    key_stat = key.lstat()
    require(stat.S_ISREG(key_stat.st_mode) and key_stat.st_mode & 0o077 == 0
            and 32 <= key_stat.st_size <= 512, "WORKER_KEY_PERMISSIONS_CHANGED")
    service_file, _ = safe_file(Path.home() / ".config/systemd/user" / SERVICE, 12_000)
    expected = ("ExecStart=/usr/bin/python3 -I " + str(ROOT / "worker.py") +
                " " + str(ROOT / "config.json"))
    require(expected.encode() in service_file, "WORKER_SERVICE_TARGET_CHANGED")


def check_runtime():
    timer = unit(TIMER)
    service = unit(SERVICE)
    require(timer.get("ActiveState") == "active" and
            timer.get("UnitFileState") in ("enabled", "enabled-runtime")
            and service.get("ActiveState") == "inactive",
            "WORKER_TIMER_OR_SERVICE_NOT_IDLE")
    row = json.loads(cmd(["docker", "inspect", "v79-hub"]))[0]
    require(row.get("Image") == HUB_IMAGE and
            row.get("State", {}).get("Running") is True and
            row.get("State", {}).get("Health", {}).get("Status") == "healthy",
            "ACCEPTED_HUB_IMAGE_OR_HEALTH_CHANGED")
    values = {v.split("=", 1)[0]: v.split("=", 1)[1]
              for v in row.get("Config", {}).get("Env", []) if "=" in v}
    require(values.get("V79_WORKFORCE_ACTIONS_ENABLED") == "1",
            "WORKFORCE_ACTIONS_NOT_ENABLED")
    data = json.loads(cmd(["docker", "exec", "v79-hub", "node",
                           "--input-type=module", "-e", READER, STAMP], timeout=25))
    require(data == {
        "signature": "HMAC_STORE_VALIDATED", "safe": True,
        "jobs": 6, "succeeded": 5, "rejected": 1, "tasks": 5,
        "createdEvents": 5, "inFlight": 0, "postMarkerTaskCount": 0,
        "paused": False, "linked": True, "allEffectsBeforeMarker": True
    }, "SIGNED_LEDGER_NOT_EXACT_CURRENT_SAFE_STATE")


def report(state):
    print(json.dumps({"result": state,
                      "marker": "2026-10-28T15:32:12.142639Z",
                      "worker": "ALREADY_HARDENED_EXACT_SOURCE",
                      "signed_ledger": "MATCHED_SIX_JOBS_FIVE_TASKS",
                      "effects_after_marker": 0,
                      "prior_incident_proven_absENT": False,
                      "production_containers_changed": False},
                     sort_keys=True), flush=True)


def archive():
    # A founder must separately invoke --archive; no automatic clearing/replay.
    check_files()
    check_runtime()
    subprocess.run(["systemctl", "--user", "stop", TIMER],
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=20)
    try:
        require(unit(SERVICE).get("ActiveState") == "inactive",
                "SERVICE_NOT_IDLE_AFTER_TIMER_STOP")
        check_files()
        # check_runtime needs an active timer; verify just the signed queue and
        # exact live Hub separately while stopped through a narrow override.
        # Move marker only after strict fresh file+ledger recheck.
        row = json.loads(cmd(["docker", "inspect", "v79-hub"]))[0]
        require(row["Image"] == HUB_IMAGE and
                row["State"].get("Health", {}).get("Status") == "healthy",
                "HUB_CHANGED_WHILE_TIMER_STOPPED")
        v = json.loads(cmd(["docker", "exec", "v79-hub", "node",
                            "--input-type=module", "-e", READER, STAMP], timeout=25))
        require(v.get("safe") is True and v.get("signature") == "HMAC_STORE_VALIDATED"
                and v.get("inFlight") == 0 and v.get("postMarkerTaskCount") == 0,
                "SIGNED_LEDGER_CHANGED_WHILE_TIMER_STOPPED")
        os.rename(MARKER, ARCHIVE)
        sync_parent()
        try:
            subprocess.run(["systemctl", "--user", "start", TIMER],
                           check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
            require(unit(TIMER).get("ActiveState") == "active",
                    "TIMER_NOT_ACTIVE_AFTER_RECONCILIATION")
            report("PASS_G2_20261028_MARKER_ARCHIVED_WORKER_ACTIVE")
        except BaseException:
            if not MARKER.exists() and ARCHIVE.exists():
                os.rename(ARCHIVE, MARKER)
                sync_parent()
            raise
    except BaseException:
        # If no archive was taken, the original marker remains fail-closed.
        # If there was a newer uncertain marker, never overwrite it.
        if not MARKER.exists() and ARCHIVE.exists():
            os.rename(ARCHIVE, MARKER)
            sync_parent()
        raise
    finally:
        # Do not silently start worker after an ambiguous failure. A timer
        # must be operator-reviewed if its state did not return to ACTIVE.
        pass


def main():
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--review", action="store_true")
    mode.add_argument("--archive", action="store_true")
    args = p.parse_args()
    os.umask(0o077)
    if args.review:
        check_files()
        check_runtime()
        report("PASS_G2_20261028_MARKER_REVIEW_ONLY")
    else:
        archive()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        reason = str(error).split(":", 1)[0]
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", reason):
            reason = type(error).__name__
        print(json.dumps({"result": "STOP_G2_20261028_MARKER_RECONCILE",
                          "reason": reason, "operator_review_required": True}),
              flush=True)
        raise SystemExit(1)
