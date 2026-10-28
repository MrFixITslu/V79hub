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
 const otherTasks=allTasks.filter(t=>t.system!=='hub');
 const otherEvents=allEvents.filter(e=>e.actor!=='coo-worker');
 const otherSucceeded=ok.filter(j=>j.system!=='hub');
 const hubSucceeded=ok.filter(j=>j.system==='hub');
 const approvedEvents=v.events.filter(e=>e.type==='approved');
 const oneOther=otherTasks.length===1 && otherEvents.length===1 &&
   otherSucceeded.length===1;
 const outside=otherSucceeded[0], task=otherTasks[0], event=otherEvents[0];
 const oneOtherLinked=Boolean(oneOther && task.jobId===outside.id &&
   task.id===outside.result?.taskId && task.system===outside.system &&
   task.organizationId===outside.organizationId &&
   event.jobId===outside.id && event.digest===outside.digest &&
   event.actor===outside.approval?.by && event.actor!=='coo-worker');
 const oneOtherApproved=Boolean(oneOtherLinked &&
   outside.approval?.digest===outside.digest &&
   approvedEvents.filter(e=>e.jobId===outside.id &&
     e.actor===outside.approval.by && e.digest===outside.digest).length===1);
 const oneOtherChronology=Boolean(oneOtherApproved &&
   [outside.createdAt,outside.approval.at,event.at,task.createdAt,
    outside.result?.at,outside.approval.expiresAt].every(x=>Number.isFinite(ms(x))) &&
   ms(outside.createdAt)<=ms(outside.approval.at) &&
   ms(outside.approval.at)<=ms(event.at) &&
   ms(event.at)<ms(outside.approval.expiresAt) &&
   ms(event.at)===ms(task.createdAt) &&
   ms(task.createdAt)===ms(outside.result.at) &&
   ms(event.at)<limit);
 const hubWorkerCohort=hubSucceeded.length===4 &&
   hubSucceeded.every(j=>allTasks.filter(t=>t.jobId===j.id &&
     t.id===j.result?.taskId && t.organizationId===j.organizationId &&
     t.system==='hub').length===1 &&
     workerEvents.filter(e=>e.jobId===j.id && e.digest===j.digest).length===1);
 const exactTwoCohorts=oneOtherChronology && hubWorkerCohort &&
   allTasks.length===5 && allEvents.length===5 && ok.length===5 &&
   allTasks.every(t=>ok.some(j=>j.id===t.jobId)) &&
   allEvents.every(e=>ok.some(j=>j.id===e.jobId));
 const cohort={
   exactlyOneOtherSystemJob:oneOther,
   otherSystemTaskEventSameJob:oneOtherLinked,
   otherSystemApprovalActorMatches:oneOtherApproved,
   otherSystemTimelineWithinApproval:oneOtherChronology,
   fourHubWorkerTasksLinked:hubWorkerCohort,
   allFiveEffectsBelongToFiveSuccesses:exactTwoCohorts,
   otherSystemInitiatedByExecutingActor:Boolean(oneOther &&
     outside.createdBy===event.actor)
 };
 const cohortCounts={
   otherSystemTasks:otherTasks.length,otherActorCreateEvents:otherEvents.length,
   otherSystemSuccessfulJobs:otherSucceeded.length,
   hubSuccessfulJobs:hubSucceeded.length
 };

 // Analyse actual job→task→creation-event links, not coincidental cohorts.
 // Both actor-bound paths are valid in the installed Hub: credential-bound
 // coo-worker and MFA-verified owner's explicit execute action.
 const createdEvents=v.events.filter(e=>e.type==='work_item_created');
 const allApprovedEvents=v.events.filter(e=>e.type==='approved');
 const allProposedEvents=v.events.filter(e=>e.type==='proposed');
 const profiles=ok.map(j=>{
   const taskMatches=allTasks.filter(t=>t.jobId===j.id &&
     t.id===j.result?.taskId && t.organizationId===j.organizationId &&
     t.system===j.system);
   const creationMatches=createdEvents.filter(e=>e.jobId===j.id &&
     e.digest===j.digest);
   const approvedMatches=allApprovedEvents.filter(e=>e.jobId===j.id &&
     e.digest===j.digest && e.actor===j.approval?.by);
   const proposalMatches=allProposedEvents.filter(e=>e.jobId===j.id &&
     e.digest===j.digest && e.actor===j.createdBy);
   const e=creationMatches[0],t=taskMatches[0],a=approvedMatches[0],p=proposalMatches[0];
   const validDates=[j.createdAt,j.approval?.at,j.approval?.expiresAt,
     e?.at,t?.createdAt,j.result?.at,a?.at,p?.at].every(x=>Number.isFinite(ms(x)));
   const actorClass=e?.actor==='coo-worker'?'worker':
     (e?.actor===j.approval?.by && e?.actor!=='coo-worker'?'owner':'unexpected');
   const chronology=Boolean(validDates &&
     ms(p.at)===ms(j.createdAt) &&
     ms(a.at)===ms(j.approval.at) &&
     ms(j.createdAt)<=ms(j.approval.at) &&
     ms(j.approval.at)<=ms(e.at) &&
     ms(e.at)<ms(j.approval.expiresAt) &&
     ms(e.at)===ms(t.createdAt) &&
     ms(t.createdAt)===ms(j.result.at) &&
     ms(e.at)<limit);
   return {system:j.system==='hub'?'hub':'other',actorClass,
     taskMatch:taskMatches.length===1, eventMatch:creationMatches.length===1,
     approvedMatch:approvedMatches.length===1,
     proposedMatch:proposalMatches.length===1,
     approvalDigest:j.approval?.digest===j.digest,
     chronology};
 });
 const groups={hubWorker:0,hubOwner:0,otherWorker:0,otherOwner:0,unexpectedActor:0};
 for(const p of profiles){
   const key=p.actorClass==='unexpected'?'unexpectedActor':
     p.system+(p.actorClass==='worker'?'Worker':'Owner');
   groups[key]++;
 }
 const fixedTotal=jobs.length===6 && ok.length===5 && rejected.length===1 &&
   open.length===0 && v.paused===false && allTasks.length===5 &&
   createdEvents.length===5 && profiles.length===5;
 const provenanceChecks={
   fixedCurrentCounts:fixedTotal,
   allFiveTasksMatch:profiles.every(p=>p.taskMatch),
   allFiveCreateEventsMatch:profiles.every(p=>p.eventMatch),
   allFiveApprovedEventsMatch:profiles.every(p=>p.approvedMatch),
   allFiveProposalEventsMatch:profiles.every(p=>p.proposedMatch),
   allFiveApprovalDigestsMatch:profiles.every(p=>p.approvalDigest),
   allFiveActorsRecognised:profiles.every(p=>p.actorClass!=='unexpected'),
   allFiveChronologiesValid:profiles.every(p=>p.chronology),
   noOrphanTasks:allTasks.every(t=>ok.some(j=>j.id===t.jobId)),
   noOrphanCreationEvents:createdEvents.every(e=>ok.some(j=>j.id===e.jobId)),
   noEventsOrTasksAfterMarker:
     counters.createEventsAfterMarker===0 && counters.tasksAfterMarker===0,
   distinctTaskIds:unique(allTasks.map(t=>t.id)),
   distinctCreationEventIds:unique(createdEvents.map(e=>e.id)),
   exactlyOneFounderExecution:
     groups.hubOwner+groups.otherOwner===1 &&
     groups.unexpectedActor===0,
   exactlyFourWorkerExecutions:
     groups.hubWorker+groups.otherWorker===4
 };

 // Keys/values are fixed, bounded, and contain no task, identity, secret or detail.
 console.log(JSON.stringify({result:'READ_ONLY_HMAC_LEDGER_DIAGNOSTIC',
   hmacValidated:true,checks,counters,cohort,cohortCounts,provenanceChecks,groups}));
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
    # Project only image and health: full Docker inspect includes unrelated secrets.
    fmt = "{{json .Image}}|{{json .State.Running}}|{{json .State.Health.Status}}"
    projected = run(["docker", "inspect", "--format", fmt, "v79-hub"])
    values = projected.strip().split("|")
    require(len(values) == 3, "HUB_IDENTITY_PROJECTION_INVALID")
    image, running, health = (json.loads(x) for x in values)
    require(image == IMAGE and running is True and health == "healthy",
            "HUB_IDENTITY_OR_HEALTH_CHANGED")
    raw = json.loads(run(["docker", "exec", "v79-hub", "node", "--input-type=module",
                          "-e", READER]))
    require(raw.get("result") == "READ_ONLY_HMAC_LEDGER_DIAGNOSTIC" and
            raw.get("hmacValidated") is True and
            set(raw) == {"result","hmacValidated","checks","counters","cohort","cohortCounts","provenanceChecks","groups"} and
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
            all(type(x) is int and 0 <= x <= 10000 for x in raw["counters"].values()) and
            set(raw["cohort"]) == {"exactlyOneOtherSystemJob","otherSystemTaskEventSameJob",
             "otherSystemApprovalActorMatches","otherSystemTimelineWithinApproval",
             "fourHubWorkerTasksLinked","allFiveEffectsBelongToFiveSuccesses",
             "otherSystemInitiatedByExecutingActor"} and
            all(isinstance(x, bool) for x in raw["cohort"].values()) and
            set(raw["cohortCounts"]) == {"otherSystemTasks","otherActorCreateEvents",
              "otherSystemSuccessfulJobs","hubSuccessfulJobs"} and
            all(type(x) is int and 0 <= x <= 10000 for x in raw["cohortCounts"].values()) and
            set(raw["provenanceChecks"]) == {
             "fixedCurrentCounts","allFiveTasksMatch","allFiveCreateEventsMatch",
             "allFiveApprovedEventsMatch","allFiveProposalEventsMatch",
             "allFiveApprovalDigestsMatch","allFiveActorsRecognised",
             "allFiveChronologiesValid","noOrphanTasks","noOrphanCreationEvents",
             "noEventsOrTasksAfterMarker","distinctTaskIds",
             "distinctCreationEventIds","exactlyOneFounderExecution",
             "exactlyFourWorkerExecutions"} and
            all(type(x) is bool for x in raw["provenanceChecks"].values()) and
            set(raw["groups"]) == {"hubWorker","hubOwner","otherWorker",
                                  "otherOwner","unexpectedActor"} and
            all(type(x) is int and 0 <= x <= 5 for x in raw["groups"].values()) and
            sum(raw["groups"].values()) == 5,
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
