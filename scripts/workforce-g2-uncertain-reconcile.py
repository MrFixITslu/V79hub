#!/usr/bin/env python3
"""Read-only reconciliation of existing G2 uncertain marker, journal and signed ledger.

Never clears marker, performs POST, creates a task, starts a timer or reads
private task content into stdout. Proof of a completed external effect is NOT
possible from a journal, so outcome is always reserved for owner review.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys

ROOT = Path.home() / ".local/share/v79-approved-task-worker"
UNIT = "v79-g2-approved-task-worker.service"
BEFORE = dt.timedelta(minutes=5)
AFTER = dt.timedelta(minutes=5)
UTC = dt.timezone.utc

LEDGER_READER = r"""
import {createWorkActionStore} from './server/workforce-action-store.mjs';
const marker=Number(process.argv[1]);
if(!Number.isFinite(marker)||marker<=0)throw Error('Bad audit marker');
const store=createWorkActionStore({
 file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',
 secret:process.env.V79_WORKFORCE_AUDIT_KEY,
 backend:process.env.V79_HUB_STORE_BACKEND||'json',
 databaseUrl:process.env.DATABASE_URL||''
});
const validTime=(v)=>Number.isFinite(Date.parse(v))?Date.parse(v):NaN;
const inRange=(t,delta)=>Number.isFinite(t)&&Math.abs(t-marker)<=delta;
try{
 const v=await store.read(); // HMAC verification; never transact().
 const jobs=v.jobs.filter(j=>j.operation==='create_work_item');
 const matchingEvents=v.events.filter(e=>e.type==='work_item_created'&&
   e.actor==='coo-worker'&&inRange(validTime(e.at),300000));
 const nearbyTasks=v.tasks.filter(t=>inRange(validTime(t.createdAt),300000));
 const after=v.events.filter(e=>e.type==='work_item_created'&&
   e.actor==='coo-worker'&&validTime(e.at)>=marker);
 const active=jobs.filter(j=>['approved','running','uncertain'].includes(j.status));
 const approvedCount=jobs.filter(j=>j.status==='approved').length;
 const statuses={};
 for(const j of jobs){
  const status=['pending','approved','running','uncertain','succeeded','failed',
                'rejected','expired','cancelled'].includes(j.status)?j.status:'other';
  statuses[status]=(statuses[status]||0)+1;
 }
 const eventTimes=v.events.filter(e=>e.type==='work_item_created'&&e.actor==='coo-worker')
   .map(e=>validTime(e.at)).filter(Number.isFinite);
 const latest=eventTimes.length?Math.max(...eventTimes):NaN;
 const nearSuccess=jobs.filter(j=>j.status==='succeeded'&&
   inRange(validTime(j.result?.at),300000)).length;
 console.log('LEDGER_SIGNATURE=VALIDATED_BY_EXISTING_STORE');
 console.log('SIGNED_LEDGER_PAUSED='+v.paused);
 console.log('SIGNED_CREATE_WORK_ITEM_STATUS_COUNTS='+JSON.stringify(statuses));
 console.log('SIGNED_WORKER_CREATED_WITHIN_5_MIN='+matchingEvents.length);
 console.log('SIGNED_ALL_TASKS_CREATED_WITHIN_5_MIN='+nearbyTasks.length);
 console.log('SIGNED_SUCCESSFUL_WORK_ITEMS_WITHIN_5_MIN='+nearSuccess);
 console.log('SIGNED_WORKER_CREATED_AFTER_MARKER='+after.length);
 console.log('SIGNED_UNRESOLVED_CREATE_WORK_ITEMS='+active.length);
 console.log('SIGNED_LAST_WORKER_TASK_AT='+(
   Number.isFinite(latest)?new Date(latest).toISOString():'NONE'));
}finally{await store.close();}
"""


def run(args, timeout=20):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode or len(result.stdout) > 1_000_000:
        return None
    try:
        return result.stdout.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return None


def private_file(path):
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                             getattr(os, "O_NONBLOCK", 0))
        s = os.fstat(descriptor)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or
                s.st_mode & 0o077 or s.st_size > 4096):
            return None
        with os.fdopen(descriptor, "rb") as f:
            descriptor = None
            return f.read(4097)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def marker_information():
    try:
        root = ROOT.lstat()
        if (not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid() or
                root.st_mode & 0o077 or ROOT.is_symlink()):
            raise ValueError()
        marker = ROOT / "uncertain.json"
        state = marker.lstat()
        raw = private_file(marker)
        if raw is None or len(raw) > 4096:
            raise ValueError()
        value = json.loads(raw)
        if value != {"state": "uncertain",
                     "action": "inspect_signed_queue_before_reset"}:
            raise ValueError()
        recorded = dt.datetime.fromtimestamp(state.st_mtime, UTC)
        print("MARKER=EXPECTED_PRIVATE_UNCERTAIN_SCHEMA")
        print("MARKER_LAST_MODIFIED_UTC=" + recorded.isoformat())
        print("MARKER_CHANGE_UTC=" +
              dt.datetime.fromtimestamp(state.st_ctime, UTC).isoformat())
        print("MARKER_AGE_SECONDS=" +
              str(max(0, int((dt.datetime.now(UTC)-recorded).total_seconds()))))
        return recorded
    except (OSError, ValueError, TypeError):
        print("MARKER=ABSENT_UNSAFE_OR_UNEXPECTED")
        return None


def known_message(message):
    if message == "TASK_WORKER=UNCERTAIN_RECONCILIATION_REQUIRED":
        return "UNCERTAIN"
    if message == "TASK_WORKER=BLOCKED_PENDING_OPERATOR_RECONCILIATION":
        return "BLOCKED"
    if message == "TASK_WORKER=IDLE":
        return "IDLE"
    if message == "TASK_WORKER=SUCCEEDED":
        return "SUCCEEDED"
    return None


def journal(marker):
    begin = (marker - BEFORE).strftime("%Y-%m-%d %H:%M:%S UTC")
    raw = run(["journalctl", "--user", "-u", UNIT, "--since", begin,
               "--output=json", "--no-pager", "-n", "600"], timeout=25)
    if raw is None:
        print("JOURNAL=UNAVAILABLE")
        return
    counts = {label:0 for label in ("UNCERTAIN", "BLOCKED", "IDLE", "SUCCEEDED")}
    nearest = None
    first = None
    last = None
    parsed = 0
    for line in raw.splitlines():
        try:
            event = json.loads(line)
            micros = int(event.get("__REALTIME_TIMESTAMP", "-1"))
            kind = known_message(event.get("MESSAGE"))
            time = dt.datetime.fromtimestamp(micros / 1e6, UTC)
            if kind is None or time < marker - BEFORE:
                continue
            parsed += 1
            counts[kind] += 1
            first = min(first, time) if first else time
            last = max(last, time) if last else time
            if kind == "UNCERTAIN":
                distance = abs((time - marker).total_seconds())
                nearest = min(nearest, distance) if nearest is not None else distance
        except (TypeError, ValueError, OverflowError):
            continue
    print("JOURNAL_KNOWN_WORKER_EVENTS=" + str(parsed))
    print("JOURNAL_KNOWN_EVENT_COUNTS=" + json.dumps(counts, sort_keys=True))
    print("JOURNAL_FIRST_KNOWN_AT=" + (first.isoformat() if first else "NONE"))
    print("JOURNAL_LAST_KNOWN_AT=" + (last.isoformat() if last else "NONE"))
    print("JOURNAL_NEAREST_UNCERTAIN_SECONDS=" +
          (str(int(nearest)) if nearest is not None else "UNAVAILABLE"))


def ledger(marker):
    result = run(["docker", "exec", "v79-hub", "node", "--input-type=module",
                  "-e", LEDGER_READER, str(int(marker.timestamp()*1000))],
                 timeout=25)
    if result is None:
        print("SIGNED_LEDGER=UNAVAILABLE_NO_NEGATIVE_PROOF")
    else:
        # The fixed reader outputs only counters, booleans and UTC times.
        print(result.strip())


def status_file(marker):
    raw = private_file(ROOT / "status.json")
    if raw is None:
        print("STORED_RECEIPT=UNAVAILABLE")
        return
    try:
        item = json.loads(raw)
        state = item.get("state")
        if state not in ("idle", "succeeded"):
            raise ValueError()
        s = (ROOT / "status.json").lstat()
        when = dt.datetime.fromtimestamp(s.st_mtime, UTC)
        print("STORED_RECEIPT_STATE=" + state.upper())
        print("STORED_RECEIPT_BEFORE_MARKER=" + str(when < marker).lower())
        print("STORED_RECEIPT_MODIFIED_AT=" + when.isoformat())
        print("STORED_RECEIPT_CAUTION=NOT_PROOF_OF_FAILED_OR_SUCCEEDED_UNKNOWN_POST")
    except (ValueError, TypeError, AttributeError, OSError):
        print("STORED_RECEIPT=INVALID")


def main():
    if len(sys.argv) != 1 or socket.gethostname() != "v79sl":
        raise SystemExit("STOP=OWNER_SERVER_ONLY")
    print("G2_RECONCILIATION=READ_ONLY")
    print("NO_POST_NO_APPROVAL_NO_RESET_NO_TIMER_CHANGE=TRUE")
    marker = marker_information()
    if marker:
        status_file(marker)
        journal(marker)
        ledger(marker)
    print("OPERATOR_DECISION=HOLD_UNTIL_SIGNED_QUEUE_AND_JOURNAL_REVIEWED")
    print("UNSAFE_AUTOMATIC_MARKER_CLEAR=NEVER")
    print("PRODUCTION_CHANGES=NONE")


if __name__ == "__main__":
    main()
