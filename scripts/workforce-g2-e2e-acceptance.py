#!/usr/bin/env python3
"""Founder-run read-only G2 acceptance verifier: original scheduled worker only.

Checks exact single benign job in HMAC-authenticated Hub ledger, and correlates
the founder approval, worker-actor event, and one matching COO task. No POST,
task creation, approval, timer change, data dump or monitoring probes.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys

ROOT = Path.home() / ".local/share/v79-approved-task-worker"
WORKER_BLOB = "2f956ae6cddd1c480963738cb995856856c009bd"
TITLE = "G2 acceptance dry-run 2026-10-28"
DETAIL = ("Internal acceptance test only. Verify that the approved G2 worker creates "
          "exactly one COO work item. No customer changes, billing, messages, "
          "deployments or external actions.")
TIMER = "v79-g2-approved-task-worker.timer"
LEDGER_READER = r"""
import {createWorkActionStore} from './server/workforce-action-store.mjs';
import {workDigest} from './server/workforce-actions.mjs';
const title=process.argv[1],detail=process.argv[2];
const result={signature:'validated_by_HMAC_store',status:'HOLD',jobCount:0,
              approvedEvents:0,workerEvents:0,linkedTasks:0,sideEffects:'NONE',
              claim:'COO_TASK_CREATION_ONLY_NOT_UNDERLYING_TASK_COMPLETION'};
const store=createWorkActionStore({
 file:(process.env.DATA_DIR||'/app/data')+'/workforce-actions.json',
 secret:process.env.V79_WORKFORCE_AUDIT_KEY,
 backend:process.env.V79_HUB_STORE_BACKEND||'json',
 databaseUrl:process.env.DATABASE_URL||''
});
try {
 const state=await store.read();
 result.paused=state.paused;
 const jobs=state.jobs.filter(j=>j.summary===title);
 result.jobCount=jobs.length;
 if(jobs.length===0)result.status='NOT_STARTED_OWNER_MUST_QUEUE';
 else if(jobs.length!==1)result.status='HOLD_DUPLICATE_JOB_TITLE';
 else {
  const j=jobs[0],s=j.status;
  result.jobStatus=['pending','approved','succeeded','rejected','cancelled','failed','uncertain','running']
      .includes(s)?s:'invalid';
  const payload={operation:j.operation,system:j.system,summary:j.summary,
    payload:j.payload,idempotencyKey:j.idempotencyKey};
  const scope=j.operation==='create_work_item'&&j.system==='hub'&&
    j.payload?.detail===detail&&j.digest===workDigest(payload)&&
    j.createdBy&&j.createdBy!=='coo-worker'&&
    j.organizationId&&j.id;
  const events=state.events.filter(e=>e.jobId===j.id);
  const created=events.filter(e=>e.type==='proposed'&&e.actor===j.createdBy&&
     e.digest===j.digest);
  const approved=events.filter(e=>e.type==='approved'&&e.actor===j.createdBy&&
     e.digest===j.digest);
  const worker=events.filter(e=>e.type==='work_item_created'&&
     e.actor==='coo-worker'&&e.digest===j.digest);
  const tasks=state.tasks.filter(t=>t.jobId===j.id);
  result.approvedEvents=approved.length;
  result.workerEvents=worker.length;
  result.linkedTasks=tasks.length;
  result.scopeExact=Boolean(scope);
  const t=tasks[0];
  const start=Date.parse(j.createdAt),applied=Date.parse(j.approval?.at),
    finish=Date.parse(j.result?.at),expiry=Date.parse(j.approval?.expiresAt);
  const timeline=[start,applied,finish,expiry].every(Number.isFinite)&&
     start<=applied&&applied<=finish&&finish<expiry;
  const taskMatches=t&&t.id===j.result?.taskId&&
    t.organizationId===j.organizationId&&t.system==='hub'&&
    t.title===title&&t.detail===detail&&t.assignedTo==='coo'&&
    t.status==='open'&&Number.isFinite(Date.parse(t.createdAt))&&
    Math.abs(Date.parse(t.createdAt)-finish)<1000;
  const exactJobEvents=events.filter(e=>['proposed','approved','work_item_created']
      .includes(e.type));
  if(!scope)result.status='HOLD_WRONG_SCOPE_OR_DIGEST';
  else if(state.paused)result.status='HOLD_LEDGER_PAUSED';
  else if(s==='pending'&&created.length===1&&approved.length===0&&
      worker.length===0&&tasks.length===0)
    result.status='AWAITING_FOUNDER_MFA_APPROVAL';
  else if(s==='approved'&&created.length===1&&approved.length===1&&
      j.approval?.by===j.createdBy&&worker.length===0&&tasks.length===0)
    result.status='APPROVED_WAIT_FOR_SCHEDULED_WORKER';
  else if(s==='succeeded'&&j.approval?.by===j.createdBy&&
      created.length===1&&approved.length===1&&worker.length===1&&
      tasks.length===1&&exactJobEvents.length===3&&
      timeline&&taskMatches)
    result.status='PASS_CREATED_EXACTLY_ONCE_BY_COO_WORKER';
  else result.status='HOLD_REQUIRES_OPERATOR_REVIEW';
 }
 console.log(JSON.stringify(result));
} finally { await store.close(); }
"""


def run(args, timeout=20):
    try:
        p = subprocess.run(args, capture_output=True, check=False, timeout=timeout)
        if p.returncode or len(p.stdout)>4096:
            return None
        return p.stdout.decode("utf-8", "strict")
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        return None


def private_bytes(path, maximum=50000):
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os,"O_NOFOLLOW",0) |
                     getattr(os,"O_NONBLOCK",0))
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or (
            s.st_mode&0o077) or not 0<s.st_size<=maximum:
            return None
        with os.fdopen(fd,"rb") as f:
            fd=None
            return f.read(maximum+1)
    except OSError:
        return None
    finally:
        if fd is not None: os.close(fd)


def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


def check_host():
    if socket.gethostname()!="v79sl":
        raise SystemExit("STOP=EXPECTED_V79SL_HOST_ONLY")
    parent=ROOT.lstat()
    if ROOT.is_symlink() or not stat.S_ISDIR(parent.st_mode) or (
        parent.st_uid!=os.getuid() or parent.st_mode&0o077):
        raise SystemExit("STOP=PRIVATE_G2_DIRECTORY_UNVERIFIED")
    item=private_bytes(ROOT/"worker.py")
    if item is None or git_blob(item)!=WORKER_BLOB:
        raise SystemExit("STOP=RUNNING_G2_WORKER_BLOB_UNVERIFIED")
    if (ROOT/"uncertain.json").exists() or (ROOT/"uncertain.json").is_symlink():
        raise SystemExit("STOP=G2_WORKER_UNCERTAIN_MANUAL_RECONCILIATION_REQUIRED")
    if (run(["systemctl","--user","is-active",TIMER]) or "").strip()!="active":
        raise SystemExit("STOP=G2_TIMER_NOT_ACTIVE")
    print("G2_RUNTIME_PREFLIGHT=PASS_HARDENED_TIMER_AND_NO_UNCERTAINTY")


def main():
    if len(sys.argv)!=1:
        raise SystemExit("STOP=NO_ARGUMENTS_ALLOWED")
    check_host()
    output=run(["docker","exec","v79-hub","node","--input-type=module",
                "-e",LEDGER_READER,TITLE,DETAIL],timeout=25)
    if output is None:
        raise SystemExit("G2_E2E=UNKNOWN_SIGNED_LEDGER_UNAVAILABLE")
    try:
        data=json.loads(output)
        allowed={"signature","status","jobCount","approvedEvents","workerEvents",
                 "linkedTasks","sideEffects","claim","paused","jobStatus","scopeExact"}
        if (not isinstance(data,dict) or set(data)-allowed or
            data.get("signature")!="validated_by_HMAC_store" or
            data.get("claim")!="COO_TASK_CREATION_ONLY_NOT_UNDERLYING_TASK_COMPLETION" or
            data.get("sideEffects")!="NONE"):
            raise ValueError()
        print("G2_SIGNED_LEDGER=HMAC_VALIDATED")
        for key in ("status","jobCount","jobStatus","scopeExact","paused",
                    "approvedEvents","workerEvents","linkedTasks"):
            value=data.get(key,"NOT_APPLICABLE")
            if type(value) is bool or (type(value) is int and 0<=value<=2000) or (
                isinstance(value,str) and value in {
                    "NOT_STARTED_OWNER_MUST_QUEUE","HOLD_DUPLICATE_JOB_TITLE",
                    "HOLD_WRONG_SCOPE_OR_DIGEST","HOLD_LEDGER_PAUSED",
                    "AWAITING_FOUNDER_MFA_APPROVAL","APPROVED_WAIT_FOR_SCHEDULED_WORKER",
                    "PASS_CREATED_EXACTLY_ONCE_BY_COO_WORKER",
                    "HOLD_REQUIRES_OPERATOR_REVIEW","NOT_APPLICABLE",
                    "pending","approved","succeeded","rejected","cancelled",
                    "failed","uncertain","running","invalid"}):
                print("G2_"+key.upper()+"="+str(value))
            else:
                raise ValueError()
        print("G2_SCOPE=COO_TASK_CREATION_ONLY")
        print("PRODUCTION_CHANGES=NONE")
    except (TypeError, ValueError):
        raise SystemExit("G2_E2E=UNKNOWN_UNEXPECTED_AUDIT_SHAPE")


if __name__=="__main__":
    main()
