#!/usr/bin/env python3
"""Vision79 v3 supervised Hub-only release with persistent watchdog.

NO use without independent owner verification, the sealed private plan, and
the recorded after-SSH watchdog probe. Never writes customer data or secrets.
--self-test and --verify make no production changes. --execute is deliberately
gated and changes the live Hub ONLY after a persistent rollback timer is active.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path("/home/firelion/v79-v3-cutover-plan-20261026")
PLAN=ROOT/"sealed-plan.json"
OVERLAY=ROOT/"v3-image-only.json"
PROBE=ROOT/"watchdog-liveness-receipt.json"
STATE=ROOT/"release-state.json"
LOCK=ROOT/"release.lock"
INSTALLED=ROOT/"vision79-v3-supervised-cutover.py"
USER_UNITS=Path("/home/firelion/.config/systemd/user")
TIMER="vision79-v3-automatic-rollback.timer"
SERVICE="vision79-v3-automatic-rollback.service"
PRIOR="sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
CANDIDATE="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
SOURCE="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
BASE_SHA="2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083"
PRIOR_FP="2e63990c22d31d0998d90b575f7490a5fc09917c839f6a54f68e317cdfffaa57"
FIVE_SHA="fc96149b9d17077a6bb263835e5f043ce3465b95ad958a2fb64e08107d5535b3"
OTHER={
 "v79-hub-postgres":"sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
 "v79-tiquet-manager":"sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0",
 "tiquet-postgres":"sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
 "v79-business-agent":"sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b",
}
WINDOW_SECONDS=1200
class Stop(Exception):pass
def need(ok,reason):
 if not ok:raise Stop(reason)
def sha(value):
 if isinstance(value,str):value=value.encode()
 return hashlib.sha256(value).hexdigest()
def canon(obj):
 return json.dumps(obj,sort_keys=True,separators=(",",":"))
def call(args,env=None,cwd=None,timeout=60,permit_failure=False):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                      cwd=cwd,env=env,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):
  raise Stop("GUARDED_COMMAND_FAILED_OR_TIMED_OUT") from None
 need(len(p.stdout)<8*1024*1024,"GUARDED_COMMAND_OUTPUT_TOO_LARGE")
 if not permit_failure:need(p.returncode==0,"GUARDED_COMMAND_NONZERO")
 return p
def inspect(kind,name):
 try:items=json.loads(call(["docker","inspect","--type",kind,name]).stdout)
 except (UnicodeError,ValueError):raise Stop("PRIVATE_DOCKER_INSPECT_INVALID") from None
 need(isinstance(items,list) and len(items)==1 and isinstance(items[0],dict),
      "DOCKER_INSPECTION_SHAPE")
 return items[0]
def hub_fingerprint(r):
 return sha(canon({"id":r.get("Id"),"image":r.get("Image"),
   "config":r.get("Config"),"host_config":r.get("HostConfig"),
   "mounts":r.get("Mounts"),
   "networks":(r.get("NetworkSettings") or {}).get("Networks")}))
def contract(r):
 c=r.get("Config") or {};h=r.get("HostConfig") or {}
 return {
  "env":c.get("Env"),"user":c.get("User"),"entrypoint":c.get("Entrypoint"),
  "cmd":c.get("Cmd"),"workdir":c.get("WorkingDir"),
  "healthcheck":c.get("Healthcheck"),"stop_signal":c.get("StopSignal"),
  "binds":h.get("Binds"),"host_mounts":h.get("Mounts"),
  "privileged":h.get("Privileged"),"readonly_rootfs":h.get("ReadonlyRootfs"),
  "port_bindings":h.get("PortBindings"),"restart":h.get("RestartPolicy"),
  "security_opts":h.get("SecurityOpt"),"cap_add":h.get("CapAdd"),
  "cap_drop":h.get("CapDrop"),"network_mode":h.get("NetworkMode"),
  "actual_mounts":sorted([(m.get("Destination"),m.get("Type"),
      m.get("Name") if m.get("Type")=="volume" else m.get("Source"),
      bool(m.get("RW"))) for m in r.get("Mounts") or []]),
  "networks":sorted(((r.get("NetworkSettings") or {}).get("Networks") or {}).keys())
 }
def current_other():
 result={}
 for n,img in OTHER.items():
  r=inspect("container",n);st=r.get("State") or {}
  need(r.get("Image")==img and st.get("Status")=="running" and
       (st.get("Health") or {}).get("Status")=="healthy",
       "OTHER_LIVE_SERVICE_CHANGED")
  result[n]={"id":r.get("Id"),"image":r.get("Image")}
 return result
def read_json(path):
 need(path.is_file() and not path.is_symlink()
      and path.stat().st_uid==pwd.getpwnam("firelion").pw_uid
      and path.stat().st_mode & 0o077==0
      and path.stat().st_size<200_000,"PRIVATE_SEAL_FILE_INVALID")
 try:return json.loads(path.read_bytes())
 except (ValueError,UnicodeError,OSError):
  raise Stop("PRIVATE_SEAL_JSON_INVALID") from None
def load_plan(need_probe=True):
 need(socket.gethostname().split(".")[0]=="v79sl" and os.geteuid()!=0,
      "EXPECTED_LOCAL_SERVER_USER")
 need(not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
      "DOCKER_CONTEXT_OVERRIDE_REFUSED")
 need(ROOT.is_dir() and not ROOT.is_symlink()
      and ROOT.stat().st_mode & 0o077==0,"PRIVATE_RELEASE_ROOT_INVALID")
 p=read_json(PLAN)
 need(p.get("schema")=="vision79-v3-cutover-seal-v1"
      and p.get("status")=="SEALED_NOT_DEPLOYED"
      and p.get("release_gate")=="HOLD"
      and p.get("prior_image")==PRIOR and p.get("candidate_image")==CANDIDATE
      and p.get("originating_approved_source")==SOURCE
      and p.get("base_compose_sha256")==BASE_SHA
      and p.get("baseline_live_fingerprint")==PRIOR_FP
      and p.get("five_service_identity_sha256")==FIVE_SHA
      and p.get("watchdog_armed") is False
      and p.get("cutover_executed") is False
      and p.get("overlay_path")==str(OVERLAY),
      "SEALED_RELEASE_PLAN_MISMATCH")
 need(sha(OVERLAY.read_bytes())==p.get("overlay_sha256") and
      read_json(OVERLAY)=={"services":{"v79-hub":{"image":CANDIDATE}}},
      "DURABLE_OVERRIDE_DRIFT")
 if need_probe:
  proof=read_json(PROBE)
  need(proof.get("schema")=="vision79-v3-user-watchdog-disconnect-proof"
       and proof.get("status")=="PASS_WATCHDOG_FIRED_AFTER_SSH_DISCONNECT"
       and proof.get("marker_verified_owner_and_empty") is True
       and proof.get("production_changes")=="NONE",
       "PERSISTENT_WATCHDOG_PROBE_UNVERIFIED")
 path=Path(p["base_compose_path"])
 need(path.is_absolute() and path.is_file() and
      not path.is_symlink() and sha(path.read_bytes())==BASE_SHA,
      "ORIGINAL_COMPOSE_FILE_DRIFT")
 working=Path(p["compose_project_directory"])
 need(working.is_absolute() and working.is_dir()
      and re.fullmatch(r"[A-Za-z0-9_-]{1,120}",p["compose_project"]),
      "COMPOSE_PROJECT_DRIFT")
 return p
def base_cmd(plan,use_candidate=False):
 args=["docker","compose","--project-directory",plan["compose_project_directory"],
       "--project-name",plan["compose_project"],"-f",plan["base_compose_path"]]
 if use_candidate:args+=["-f",str(OVERLAY)]
 return args
def expected_prior_reference(plan):
 result=call(base_cmd(plan)+["config","--format","json"],
             cwd=plan["compose_project_directory"])
 try:doc=json.loads(result.stdout)
 except (ValueError,UnicodeError):raise Stop("COMPOSE_RENDER_UNAVAILABLE") from None
 ref=((doc.get("services") or {}).get("v79-hub") or {}).get("image")
 need(isinstance(ref,str) and ref and ref!=CANDIDATE,"ORIGINAL_IMAGE_REF_INVALID")
 need(inspect("image",ref).get("Id")==PRIOR,"ORIGINAL_IMAGE_REF_NOT_PRIOR")
 return ref
def verify_live(plan,expect_image):
 hub=inspect("container","v79-hub")
 st=hub.get("State") or {}
 need(hub.get("Image")==expect_image and st.get("Status")=="running"
      and (st.get("Health") or {}).get("Status")=="healthy",
      "HUB_IMAGE_OR_HEALTH_INVALID")
 others=current_other()
 if expect_image==PRIOR:
  need(hub_fingerprint(hub)==PRIOR_FP
      and hub.get("Id")==plan.get("exact_old_hub_container_id"),
      "LIVE_PRIOR_BASELINE_DRIFT")
  ids={"v79-hub":{"id":hub.get("Id"),"image":hub.get("Image")},**others}
  need(sha(canon(ids))==FIVE_SHA,"FIVE_SERVICE_IDENTITY_DRIFT")
 return hub,others
def systemd_env():
 uid=pwd.getpwnam("firelion").pw_uid
 d=Path("/run/user")/str(uid)
 need(d.is_dir() and d.stat().st_uid==uid,"USER_SYSTEMD_RUNTIME_UNAVAILABLE")
 env=dict(os.environ)
 env["XDG_RUNTIME_DIR"]=str(d)
 env["DBUS_SESSION_BUS_ADDRESS"]="unix:path="+str(d/"bus")
 return env
def timer_active():
 r=call(["systemctl","--user","show",TIMER,"--property=ActiveState","--value"],
        env=systemd_env(),permit_failure=True)
 return r.returncode==0 and r.stdout.strip()==b"active"
def locked():
 need(ROOT.is_dir(),"RELEASE_ROOT_MISSING")
 fd=os.open(str(LOCK),os.O_CREAT|os.O_RDWR,0o600)
 fcntl.flock(fd,fcntl.LOCK_EX)
 return fd
def atomic_write(path,data):
 payload=json.dumps(data,sort_keys=True,indent=2)+"\n"
 fd,tmp=tempfile.mkstemp(prefix=".v79-state-",dir=str(ROOT),text=True)
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,"w") as f:
   f.write(payload);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 except Exception:
  try:os.unlink(tmp)
  except OSError:pass
  raise
def state():
 return read_json(STATE) if STATE.exists() else None
def unit_text(deadline):
 date=dt.datetime.fromtimestamp(deadline,dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
 service=f"[Unit]\nDescription=Vision79 v3 automatic rollback\nStartLimitIntervalSec=0\n[Service]\nType=oneshot\nRestart=on-failure\nRestartSec=20s\nExecStart=/usr/bin/python3 -B {INSTALLED} --rollback\n"
 timer=f"[Unit]\nDescription=Vision79 v3 rollback deadline\n[Timer]\nOnCalendar={date}\nPersistent=true\nAccuracySec=1s\nUnit={SERVICE}\n[Install]\nWantedBy=timers.target\n"
 return service,timer
def install_timer(deadline):
 need(INSTALLED.is_file() and not INSTALLED.is_symlink()
      and INSTALLED.stat().st_mode & 0o022==0,"INSTALLED_CONTROLLER_UNSAFE")
 home=Path("/home/firelion")
 need(home.is_dir() and not home.is_symlink()
      and home.stat().st_uid==pwd.getpwnam("firelion").pw_uid,
      "USER_HOME_NOT_TRUSTED")
 if not USER_UNITS.parent.exists():USER_UNITS.parent.mkdir(mode=0o700)
 need(USER_UNITS.parent.is_dir() and not USER_UNITS.parent.is_symlink()
      and USER_UNITS.parent.stat().st_uid==pwd.getpwnam("firelion").pw_uid,
      "USER_SYSTEMD_CONFIG_DIRECTORY_UNAVAILABLE")
 if not USER_UNITS.exists():USER_UNITS.mkdir(mode=0o700)
 need(USER_UNITS.is_dir() and not USER_UNITS.is_symlink()
      and USER_UNITS.stat().st_uid==pwd.getpwnam("firelion").pw_uid,
      "USER_UNIT_DIRECTORY_UNAVAILABLE")
 service=USER_UNITS/SERVICE;timer=USER_UNITS/TIMER
 need(not service.exists() and not timer.exists(),
      "ROLLBACK_UNIT_NAME_ALREADY_OCCUPIED")
 a,b=unit_text(deadline)
 # timer and service are durable on disk and OnCalendar is Persistent,
 # unlike transient systemd-run --on-active timers.
 for path,content in ((service,a),(timer,b)):
  with path.open("x") as f:
   os.fchmod(f.fileno(),0o600)
   f.write(content);f.flush();os.fsync(f.fileno())
 env=systemd_env()
 call(["systemctl","--user","daemon-reload"],env=env)
 call(["systemctl","--user","enable","--now",TIMER],env=env)
 need(timer_active(),"PERSISTENT_ROLLBACK_TIMER_NOT_ACTIVE")
 return True
def compose_up(plan,upgrade):
 args=base_cmd(plan,use_candidate=upgrade)+[
       "up","--detach","--no-deps","--no-build","--pull","never",
       "--force-recreate","v79-hub"]
 call(args,cwd=plan["compose_project_directory"],timeout=240)
def healthy_hub(image,original_contract=None,timeout=120):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  try:r=inspect("container","v79-hub")
  except Stop:r=None
  if (r is not None
      and r.get("Image")==image
      and (r.get("State") or {}).get("Status")=="running"
      and ((r.get("State") or {}).get("Health") or {}).get("Status")=="healthy"):
   if original_contract is not None:
    need(contract(r)==original_contract,"RECREATED_HUB_RUNTIME_CONTRACT_DRIFT")
   return r
  time.sleep(3)
 raise Stop("HUB_HEALTH_WAIT_TIMEOUT")
def verify():
 p=load_plan()
 need(call(["docker","context","show"]).stdout.strip()==b"default" and
      call(["docker","info","--format","{{.Name}}"]).stdout.strip()==b"v79sl",
      "SERVER_DOCKER_CONTEXT_DRIFT")
 verify_live(p,PRIOR)
 need(inspect("image",CANDIDATE).get("Id")==CANDIDATE,
      "CANDIDATE_IMAGE_MISSING")
 expected_prior_reference(p)
 need(call(["loginctl","show-user","firelion","-p","Linger","--value"]).stdout.strip()==b"yes",
      "PERSISTENT_USER_SYSTEMD_DISABLED")
 need(not STATE.exists() and not (USER_UNITS/TIMER).exists()
      and not (USER_UNITS/SERVICE).exists(),
      "RELEASE_ATTEMPT_ALREADY_STARTED")
 return p
def execute():
 need(os.getenv("V79_V3_OWNER_PRESENT")=="I_AM_PRESENT_FOR_MFA_SSO_AND_VISUAL_CHECKS",
      "OWNER_SUPERVISION_REQUIRED")
 p=verify()
 fd=locked()
 try:
  need(state() is None,"RELEASE_STATE_ALREADY_EXISTS")
  old,others=verify_live(p,PRIOR)
  old_contract=contract(old)
  deadline=time.time()+WINDOW_SECONDS
  pending={"schema":"vision79-v3-supervised-cutover","state":"ARMING",
           "planned_deadline_epoch":deadline,"original_contract_sha256":sha(canon(old_contract)),
           "original_hub_container_id":old.get("Id"),
           "other_service_identity_sha256":sha(canon(others)),
           "candidate_image":CANDIDATE,"prior_image":PRIOR,
           "owner_acceptance":False,"release_gate":"HOLD"}
  atomic_write(STATE,pending)
  install_timer(deadline)
  pending["state"]="WATCHDOG_ARMED"
  atomic_write(STATE,pending)
  # No data restoration, database migrations, timer quiesce or dependency starts.
  try:
   compose_up(p,True)
   newer=healthy_hub(CANDIDATE,old_contract,timeout=120)
   need(sha(canon(current_other()))==pending["other_service_identity_sha256"],
        "OTHER_SERVICE_CHANGED_DURING_CUTOVER")
   pending["state"]="REVIEW_PENDING"
   pending["new_hub_container_id"]=newer.get("Id")
   pending["runtime_contract_verified"]=True
   atomic_write(STATE,pending)
  except Exception as exc:
   pending["state"]="ROLLBACK_REQUIRED"
   pending["cutover_failure_code"]=str(exc) if isinstance(exc,Stop) else "REDACTED_EXCEPTION"
   atomic_write(STATE,pending)
   # Restore the original Compose image immediately, with persistent
   # watchdog as a fallback if the foreground operation fails or dies.
   try:
    compose_up(p,False)
    restored=healthy_hub(PRIOR,timeout=120)
    need(sha(canon(contract(restored)))==pending["original_contract_sha256"],
         "IMMEDIATE_ROLLBACK_RUNTIME_MISMATCH")
    need(sha(canon(current_other()))==pending["other_service_identity_sha256"],
         "IMMEDIATE_ROLLBACK_OTHER_SERVICES_DRIFT")
    pending["state"]="ROLLED_BACK"
    atomic_write(STATE,pending)
    raise Stop("CUTOVER_FAILED_PRIOR_HUB_RESTORED") from None
   except Stop as rollback_error:
    if str(rollback_error)=="CUTOVER_FAILED_PRIOR_HUB_RESTORED":raise
    pending["state"]="ROLLBACK_FAILED"
    atomic_write(STATE,pending)
    raise Stop("CUTOVER_FAILED_WATCHDOG_ROLLBACK_PENDING") from None
   except Exception:
    pending["state"]="ROLLBACK_FAILED"
    atomic_write(STATE,pending)
    raise Stop("CUTOVER_FAILED_WATCHDOG_ROLLBACK_PENDING") from None
  return {"result":"V3_LIVE_TEMPORARY_REVIEW_WINDOW",
       "owner_mfa_sso_visual_acceptance":"REQUIRED_BEFORE_DEADLINE",
       "deadline_epoch":int(deadline),
       "rollback_watchdog_armed":timer_active(),
       "candidate_runtime_contract_verified":True,
       "release_gate":"HOLD"}
 finally:
  fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
def hub_for_rollback():
 result=call(["docker","inspect","--type","container","v79-hub"],
             permit_failure=True)
 if result.returncode==0:
  try:items=json.loads(result.stdout)
  except (ValueError,UnicodeError):raise Stop("HUB_INSPECT_INVALID") from None
  need(isinstance(items,list) and len(items)==1 and isinstance(items[0],dict),
       "HUB_INSPECT_SHAPE_DRIFT")
  return items[0]
 # No Hub container can be a recoverable partial recreate, but a failed
 # daemon connection is not. Prove the daemon responds before proceeding.
 call(["docker","info","--format","{{.Name}}"])
 allnames=call(["docker","ps","--all","--format","{{.Names}}"]).stdout.splitlines()
 need(b"v79-hub" not in allnames,"HUB_EXISTS_BUT_INSPECT_FAILED")
 return None
def rollback():
 p=load_plan()
 fd=locked()
 try:
  s=state()
  need(isinstance(s,dict) and s.get("schema")=="vision79-v3-supervised-cutover",
       "NO_VALID_PENDING_ROLLBACK_STATE")
  if s.get("state") in ("ACCEPTED","ROLLED_BACK"):
   return {"result":"ROLLBACK_NOOP_FINAL_STATE","state":s["state"]}
  need(s.get("state") in ("ARMING","WATCHDOG_ARMED","REVIEW_PENDING",
                            "ROLLBACK_REQUIRED","ROLLBACK_FAILED"),
       "ROLLBACK_STATE_INVALID")
  need(expected_prior_reference(p),"PRIOR_IMAGE_REF_UNAVAILABLE")
  hub=hub_for_rollback()
  need(hub is None or hub.get("Image") in (PRIOR,CANDIDATE),
       "UNKNOWN_HUB_IMAGE_REFUSE_REPLACE")
  if hub is None or hub.get("Image")==CANDIDATE or (hub.get("Image")==PRIOR and (
     (hub.get("State") or {}).get("Status")!="running")):
   try:
    compose_up(p,False)
    healthy_hub(PRIOR,timeout=120)
   except Exception:
    s["state"]="ROLLBACK_FAILED"
    atomic_write(STATE,s)
    raise Stop("ROLLBACK_EXECUTION_FAILED_REQUIRES_OPERATOR")
  need(sha(canon(contract(healthy_hub(PRIOR,timeout=45))))==
       s.get("original_contract_sha256"),"RESTORED_PRIOR_RUNTIME_DRIFT")
  need(sha(canon(current_other()))==s.get("other_service_identity_sha256"),
       "OTHER_SERVICES_DRIFT_AFTER_ROLLBACK")
  s["state"]="ROLLED_BACK"
  s["owner_acceptance"]=False
  atomic_write(STATE,s)
  return {"result":"PASS_AUTOMATIC_PRIOR_HUB_RESTORED",
          "prior_image_restored":True,
          "candidate_accepted":False,
          "release_gate":"HOLD"}
 finally:
  fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
def accept(flags):
 need(set(flags)=={"--mfa-ok","--sso-ok","--visual-ok","--tenant-ok"},
      "FOUR_OWNER_ACCEPTANCE_ATTESTATIONS_REQUIRED")
 p=load_plan()
 fd=locked()
 try:
  s=state()
  need(isinstance(s,dict) and s.get("state")=="REVIEW_PENDING",
       "NOT_IN_OWNER_REVIEW_WINDOW")
  need(time.time()<float(s.get("planned_deadline_epoch",0))-15,
       "OWNER_ACCEPTANCE_WINDOW_EXPIRED")
  need(timer_active(),"ROLLBACK_WATCHDOG_INACTIVE")
  hub=healthy_hub(CANDIDATE,timeout=5)
  need(hub.get("Id")==s.get("new_hub_container_id"),
       "HUB_RECREATED_DURING_OWNER_REVIEW")
  need(sha(canon(contract(hub)))==s.get("original_contract_sha256")
       and sha(canon(current_other()))==s.get("other_service_identity_sha256"),
       "POST_ACCEPTANCE_RUNTIME_DRIFT")
  s["state"]="ACCEPTED";s["owner_acceptance"]=True
  s["owner_attested_checks"]=sorted(flags)
  s["accepted_at_utc"]=dt.datetime.now(dt.timezone.utc).isoformat()
  atomic_write(STATE,s)
  # No rollback after acceptance even if stopping timer unexpectedly fails.
  unit=call(["systemctl","--user","disable","--now",TIMER],
            env=systemd_env(),permit_failure=True)
  return {"result":"PASS_OWNER_ATTESTED_V3_ACCEPTANCE",
          "owner_attestation_recorded":True,
          "timer_stopped":unit.returncode==0,
          "candidate_image_live":True}
 finally:
  fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
class Tests(unittest.TestCase):
 def test_contract_fails_closed_on_binds_and_mounts(self):
  a={"Config":{"Env":["A=private"],"Cmd":["node"],"User":""},
     "HostConfig":{"Binds":["/old:/app/data:rw"],"Mounts":[]},
     "Mounts":[{"Destination":"/app/data","Type":"bind","Source":"/old","RW":True}],
     "NetworkSettings":{"Networks":{"a":{}}}}
  b=json.loads(json.dumps(a));b["HostConfig"]["Binds"]=["/wrong:/app/data:rw"]
  self.assertNotEqual(contract(a),contract(b))
  b=json.loads(json.dumps(a));b["Mounts"][0]["Source"]="/wrong"
  self.assertNotEqual(contract(a),contract(b))
 def test_image_only_compose_command_excludes_dependencies(self):
  plan={"compose_project_directory":"/tmp/readonly",
        "compose_project":"v79demo","base_compose_path":"/tmp/config.json"}
  original=base_cmd(plan,False)
  updated=base_cmd(plan,True)
  self.assertEqual(updated[:-2],original)
  self.assertEqual(updated[-2:],["-f",str(OVERLAY)])
 def test_persistent_timer_declaration_has_calendar_and_persistence(self):
  service,timer=unit_text(1793030000)
  self.assertIn("Persistent=true",timer)
  self.assertIn("OnCalendar=",timer)
  self.assertIn(str(INSTALLED),service)
  self.assertNotIn("docker compose",service)
 def test_atomic_state_mode_and_no_private_secrets(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"status.json"
   with patch(__name__+".ROOT",Path(td)):
    atomic_write(path,{"schema":"demo","state":"ARMING"})
   self.assertEqual(json.loads(path.read_text())["state"],"ARMING")
   self.assertEqual(path.stat().st_mode & 0o077,0)
 def test_rollback_missing_hub_allows_safely_recreate_prior(self):
  with patch(__name__+".call") as cmd:
   cmd.side_effect=[
    subprocess.CompletedProcess([],1,b"",b""),
    subprocess.CompletedProcess([],0,b"v79sl",b""),
    subprocess.CompletedProcess([],0,b"other-service\n",b"")]
   self.assertIsNone(hub_for_rollback())
 def test_rollback_refuses_broken_daemon(self):
  with patch(__name__+".call") as cmd:
   cmd.side_effect=[
    subprocess.CompletedProcess([],1,b"",b""),
    Stop("GUARDED_COMMAND_NONZERO")]
   with self.assertRaises(Stop):hub_for_rollback()
 def test_rollback_candidate_uses_original_compose_and_preserves_other_services(self):
  prior_row={"Image":PRIOR,"State":{"Status":"running","Health":{"Status":"healthy"}},
             "Config":{"Env":["PRIVATE=do-not-print"]},
             "HostConfig":{"Binds":["/private:/app/data:rw"],"Mounts":[]},
             "Mounts":[{"Destination":"/app/data","Type":"bind",
                        "Source":"/private","RW":True}],
             "NetworkSettings":{"Networks":{"proxy_network":{}}}}
  other_state={"tiquet":{"id":"id","image":"sha256:prior"}}
  snapshot={"schema":"vision79-v3-supervised-cutover","state":"REVIEW_PENDING",
            "original_contract_sha256":sha(canon(contract(prior_row))),
            "other_service_identity_sha256":sha(canon(other_state))}
  with tempfile.TemporaryDirectory() as td:
   fd=os.open(str(Path(td)/"lock"),os.O_CREAT|os.O_RDWR,0o600)
   with patch(__name__+".load_plan",return_value={"base_compose_path":"/tmp/base.json"}),\
        patch(__name__+".locked",return_value=fd),\
        patch(__name__+".state",return_value=snapshot),\
        patch(__name__+".expected_prior_reference",return_value="prior:tag"),\
        patch(__name__+".hub_for_rollback",return_value={"Image":CANDIDATE}),\
        patch(__name__+".compose_up") as compose,\
        patch(__name__+".healthy_hub",return_value=prior_row),\
        patch(__name__+".current_other",return_value=other_state),\
        patch(__name__+".atomic_write") as save:
    result=rollback()
   self.assertEqual(result["result"],"PASS_AUTOMATIC_PRIOR_HUB_RESTORED")
   compose.assert_called_once_with({"base_compose_path":"/tmp/base.json"},False)
   self.assertEqual(snapshot["state"],"ROLLED_BACK")
   self.assertFalse(snapshot["owner_acceptance"])
   save.assert_called_once()
 def test_execute_requires_owner_presence_before_runtime_access(self):
  with patch.dict(os.environ,{"V79_V3_OWNER_PRESENT":"no"},clear=False),\
       patch(__name__+".verify") as verify_fn:
   with self.assertRaisesRegex(Stop,"OWNER_SUPERVISION_REQUIRED"):
    execute()
   verify_fn.assert_not_called()
 def test_wrong_mode_does_not_execute(self):
  with patch("sys.argv",["release.py","--anything"]):
   with self.assertRaisesRegex(Stop,"UNSUPPORTED_RELEASE_OPERATION"):
    main()
 def test_accept_requires_four_check_flags(self):
  with self.assertRaisesRegex(Stop,"FOUR_OWNER_ACCEPTANCE_ATTESTATIONS_REQUIRED"):
   accept(["--mfa-ok","--sso-ok"])
def main():
 args=sys.argv[1:]
 need(args and args[0] in ("--self-test","--verify","--execute",
                          "--rollback","--accept"),
      "UNSUPPORTED_RELEASE_OPERATION")
 if args[0]=="--self-test":
  need(len(args)==1,"UNSUPPORTED_RELEASE_OPERATION")
  r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 if args[0]=="--verify" and len(args)==1:
  verify()
  print(json.dumps({"result":"PASS_RELEASE_CONTROLLER_PREFLIGHT",
     "durable_watchdog_probe_received":True,
     "prior_hub_baseline_verified":True,
     "production_changes":"NONE","cutover_started":False,
     "release_gate":"HOLD"}))
 elif args[0]=="--execute" and len(args)==1:
  print(json.dumps(execute(),sort_keys=True))
 elif args[0]=="--rollback" and len(args)==1:
  print(json.dumps(rollback(),sort_keys=True))
 elif args[0]=="--accept":
  print(json.dumps(accept(args[1:]),sort_keys=True))
 else:raise Stop("UNSUPPORTED_RELEASE_OPERATION")
 return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as e:
  print(json.dumps({"result":"STOP","reason":str(e),"release_gate":"HOLD",
                    "production_changes":"NOT_REVERIFIED"}));sys.exit(3)
 except Exception as e:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(e).__name__,
                    "release_gate":"HOLD","production_changes":"NOT_REVERIFIED"}));sys.exit(3)
