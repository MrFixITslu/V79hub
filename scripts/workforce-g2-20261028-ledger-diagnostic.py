#!/usr/bin/env python3
"""Diagnostic only: identify G2 signed-ledger guard mismatch without ledger disclosure.
No timer changes, marker archival, writes, POSTs, replay, or production probes.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess

ROOT = Path.home() / ".local/share/v79-approved-task-worker"
IMAGE = "sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec"
WORKER_SHA = "5f629915d7715620fdd17ac0fed80cf595e65dab0035d0739a53c9bc5984fb3d"
MARKER = 1793201532.142639  # 2026-10-28 15:32:12.142639 UTC

READER = r"""
import {createWorkActionStore} from './server/workforce-action-store.mjs';
const limit=Date.parse('2026-10-28T15:32:12.142639Z');
const store=createWorkActionStore({
 file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',
 secret:process.env.V79_WORKFORCE_AUDIT_KEY,
 backend:process.env.V79_HUB_STORE_BACKEND||'json',
 databaseUrl:process.env.DATABASE_URL||''
});
try {
 const v=await store.read(); // authentication of entire state, no mutation
 const jobs=v.jobs.filter(j=>j.operation==='create_work_item');
 const ok=jobs.filter(j=>j.status==='succeeded');
 const rejected=jobs.filter(j=>j.status==='rejected');
 const open=jobs.filter(j=>['approved','running','uncertain'].includes(j.status));
 const allTasks=v.tasks.filter(t=>t.jobId);
 const hubTasks=allTasks.filter(t=>t.system==='hub');
 const allEvents=v.events.filter(e=>e.type==='work_item_created');
 const workerEvents=allEvents.filter(e=>e.actor==='coo-worker');
 const ms=x=>Date.parse(x);
 const isBefore=x=>Number.isFinite(ms(x))&&ms(x)<limit;
 const oneTask=ok.every(j=>allTasks.filter(t=>
   t.jobId===j.id && t.id===j.result?.taskId &&
   t.organizationId===j.organizationId && t.system===j.system).length===1);
 const oneWorkerEvent=ok.every(j=>workerEvents.filter(e=>
   e.jobId===j.id && e.digest===j.digest).length===1);
 const oneAnyEvent=ok.every(j=>allEvents.filter(e=>
   e.jobId===j.id && e.digest===j.digest).length===1);
 const unique=x=>new Set(x).size===x.length;
 const checks={
   pausedFalse:v.paused===false,
   jobCountSix:jobs.length===6,
   fiveSucceeded:ok.length===5,
   oneRejected:rejected.length===1,
   noInFlight:open.length===0,
   allTasksFive:allTasks.length===5,
   hubTasksFive:hubTasks.length===5,
   allCreateEventsFive:allEvents.length===5,
   workerCreateEventsFive:workerEvents.length===5,
   perSuccessTaskLinked:oneTask,
   perSuccessWorkerEventLinked:oneWorkerEvent,
   perSuccessAnyActorEventLinked:oneAnyEvent,
   uniqueJobIds:unique(jobs.map(j=>j.id)),
   uniqueTaskIds:unique(allTasks.map(t=>t.id)),
   uniqueWorkerEventJobIds:unique(workerEvents.map(e=>e.jobId)),
   allTaskTimesBeforeMarker:allTasks.every(t=>isBefore(t.createdAt)),
   allCreateEventTimesBeforeMarker:allEvents.every(e=>isBefore(e.at)),
   allSucceededResultTimesBeforeMarker:ok.every(j=>isBefore(j.result?.at)),
   allJobCreatedTimesBeforeMarker:jobs.every(j=>isBefore(j.createdAt)),
   rejectedJobCreatedBeforeMarker:rejected.every(j=>isBefore(j.createdAt)),
   validMarkerTime:Number.isFinite(limit)
 };
 const counters={
   jobs:jobs.length,succeeded:ok.length,rejected:rejected.length,
   unresolved:open.length,tasksWithJob:allTasks.length,
   hubTasks:hubTasks.length,allCreatedEvents:allEvents.length,
   workerCreatedEvents:workerEvents.length,
   tasksAfterMarker:allTasks.filter(t=>Number.isFinite(ms(t.createdAt))&&ms(t.createdAt)>=limit).length,
   createEventsAfterMarker:allEvents.filter(e=>Number.isFinite(ms(e.at))&&ms(e.at)>=limit).length
 };
 // Keys/values are fixed, bounded, and contain no task, identity, secret or detail.
 console.log(JSON.stringify({result:'READ_ONLY_HMAC_LEDGER_DIAGNOSTIC',
   hmacValidated:true,checks,counters}));
}finally{await store.close();}
"""


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def run(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       timeout=25, check=False)
    require(p.returncode == 0 and len(p.stdout) < 12000, "REDACTED_READ_FAILED")
    return p.stdout.decode("utf8", "strict")


def private(path, limit):
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and not path.is_symlink()
            and st.st_uid == os.getuid() and st.st_nlink == 1
            and st.st_mode & 0o077 == 0 and st.st_size <= limit,
            "LOCAL_EVIDENCE_CHANGED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(os.fstat(fd).st_ino == st.st_ino, "EVIDENCE_RACE")
        return os.read(fd, limit + 1), st
    finally:
        os.close(fd)


def main():
    require(socket.gethostname() == "v79sl", "EXPECTED_OWNER_HOST_ONLY")
    root = ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and not ROOT.is_symlink()
            and root.st_uid == os.getuid() and root.st_mode & 0o077 == 0,
            "PRIVATE_ROOT_CHANGED")
    marker, meta = private(ROOT / "uncertain.json", 4096)
    require(json.loads(marker) == {"state":"uncertain",
            "action":"inspect_signed_queue_before_reset"} and
            abs(meta.st_mtime - MARKER) < 0.005,
            "20261028_MARKER_CHANGED")
    worker, _ = private(ROOT / "worker.py", 45000)
    require(hashlib.sha256(worker).hexdigest() == WORKER_SHA,
            "INSTALLED_WORKER_CHANGED")
    row = json.loads(run(["docker", "inspect", "v79-hub"]))[0]
    require(row.get("Image") == IMAGE and
            row.get("State", {}).get("Health", {}).get("Status") == "healthy",
            "HUB_IDENTITY_OR_HEALTH_CHANGED")
    raw = json.loads(run(["docker", "exec", "v79-hub", "node", "--input-type=module",
                          "-e", READER]))
    require(raw.get("result") == "READ_ONLY_HMAC_LEDGER_DIAGNOSTIC" and
            raw.get("hmacValidated") is True and
            set(raw) == {"result","hmacValidated","checks","counters"} and
            set(raw["checks"]) == {
              "pausedFalse","jobCountSix","fiveSucceeded","oneRejected","noInFlight",
              "allTasksFive","hubTasksFive","allCreateEventsFive",
              "workerCreateEventsFive","perSuccessTaskLinked",
              "perSuccessWorkerEventLinked","perSuccessAnyActorEventLinked",
              "uniqueJobIds","uniqueTaskIds","uniqueWorkerEventJobIds",
              "allTaskTimesBeforeMarker","allCreateEventTimesBeforeMarker",
              "allSucceededResultTimesBeforeMarker","allJobCreatedTimesBeforeMarker",
              "rejectedJobCreatedBeforeMarker","validMarkerTime"} and
            all(isinstance(x, bool) for x in raw["checks"].values()) and
            all(type(x) is int and 0 <= x <= 10000 for x in raw["counters"].values()),
            "LEDGER_DIAGNOSTIC_INVALID")
    print(json.dumps(raw, sort_keys=True), flush=True)
    print("MARKER_UNCHANGED=true", flush=True)
    print("POST_OR_TASK_EXECUTED=false", flush=True)
    print("PRODUCTION_CHANGES=NONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        code = str(e)
        if not re.fullmatch(r"[A-Z0-9_]+", code):
            code = type(e).__name__
        print(json.dumps({"result": "STOP_G2_BOUNDED_LEDGER_DIAGNOSTIC",
                          "reason": code}), flush=True)
        raise SystemExit(1)
