#!/usr/bin/env python3
"""Prove a user-systemd timer fires AFTER the originating SSH exits.

This tool cannot deploy/restart any container or arm the real rollback. It
creates and checks ONE harmless private sentinel under an already sealed
Vision79 v3 plan. Run --arm and --check via separate SSH sessions.
"""
import datetime as dt,json,os,pwd,socket,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path("/home/firelion/v79-v3-cutover-plan-20261026")
PLAN=ROOT/"sealed-plan.json"
OVERLAY=ROOT/"v3-image-only.json"
MARKER=ROOT/"watchdog-liveness-PASS"
RECEIPT=ROOT/"watchdog-liveness-receipt.json"
UNIT="vision79-v3-watchdog-liveness"
OLD="sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
NEW="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
class Stop(Exception):pass
def need(ok,why):
 if not ok:raise Stop(why)
def env():
 uid=pwd.getpwnam("firelion").pw_uid
 directory=Path("/run/user")/str(uid)
 need(directory.is_dir() and directory.stat().st_uid==uid,
      "WATCHDOG_USER_SESSION_NOT_RUNNING")
 result=dict(os.environ)
 result["XDG_RUNTIME_DIR"]=str(directory)
 result["DBUS_SESSION_BUS_ADDRESS"]="unix:path="+str(directory/"bus")
 return result
def read_plan():
 need(socket.gethostname().split(".")[0]=="v79sl" and os.geteuid()!=0,
      "SERVER_UNPRIVILEGED_USER_REQUIRED")
 need(os.getenv("DOCKER_HOST") is None and os.getenv("DOCKER_CONTEXT") is None,
      "DOCKER_OVERRIDE_UNEXPECTED")
 need(ROOT.is_dir() and not ROOT.is_symlink() and (ROOT.stat().st_mode & 0o077)==0,
      "RELEASE_PLAN_ROOT_UNSAFE")
 for p in (PLAN,OVERLAY):
  need(p.is_file() and not p.is_symlink() and (p.stat().st_mode & 0o077)==0,
       "RELEASE_PLAN_FILE_UNSAFE")
 try:
  data=json.loads(PLAN.read_text());override=json.loads(OVERLAY.read_text())
 except (ValueError,UnicodeError,OSError):
  raise Stop("SEALED_PLAN_INVALID") from None
 need(data.get("schema")=="vision79-v3-cutover-seal-v1"
      and data.get("status")=="SEALED_NOT_DEPLOYED"
      and data.get("prior_image")==OLD and data.get("candidate_image")==NEW
      and data.get("watchdog_armed") is False
      and data.get("cutover_executed") is False
      and data.get("release_gate")=="HOLD"
      and override=={"services":{"v79-hub":{"image":NEW}}},
      "SEALED_PLAN_IDENTITY_DRIFT")
 need(data.get("watchdog_prerequisites",{}).get("linger") is True,
      "WATCHDOG_LINGER_NOT_SEALED")
 return data
def cmd(args,e,allow_error=False):
 try:p=subprocess.run(args,env=e,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20)
 except (OSError,subprocess.TimeoutExpired):raise Stop("WATCHDOG_USER_SYSTEMD_UNAVAILABLE") from None
 need(len(p.stdout)<100000,"SYSTEMD_OUTPUT_TOO_LARGE")
 if not allow_error:need(p.returncode==0,"SYSTEMD_COMMAND_FAILED")
 return p
def unit_exists(e):
 p=cmd(["systemctl","--user","show",UNIT+".timer",
        "--property=LoadState","--value"],e,True)
 return p.returncode==0 and p.stdout.strip() not in (b"",b"not-found")
def arm():
 read_plan()
 e=env()
 need(not MARKER.exists() and not MARKER.is_symlink() and
      not RECEIPT.exists() and not RECEIPT.is_symlink(),
      "WATCHDOG_PROBE_OR_RECEIPT_ALREADY_EXISTS")
 need(not unit_exists(e),"WATCHDOG_PROBE_TIMER_ALREADY_EXISTS")
 need(cmd(["loginctl","show-user","firelion","-p","Linger","--value"],e).stdout.strip()==b"yes",
      "WATCHDOG_LINGER_CURRENTLY_OFF")
 cmd(["systemd-run","--user","--unit",UNIT,
      "--on-active=8s","--description=Vision79 harmless timer liveness check",
      "/usr/bin/touch",str(MARKER)],e)
 need(unit_exists(e),"WATCHDOG_PROBE_ARMING_UNPROVEN")
 print(json.dumps({"result":"PASS_HARMLESS_WATCHDOG_PROBE_ARMED",
       "ssh_session_disconnect_required":True,"test_unit_active":True,
       "rollback_watchdog_armed":False,
       "candidate_started":False,"production_changes":"NONE","release_gate":"HOLD"},sort_keys=True))
def check():
 read_plan()
 e=env()
 need(MARKER.is_file() and not MARKER.is_symlink() and
      MARKER.stat().st_uid==pwd.getpwnam("firelion").pw_uid,
      "WATCHDOG_DID_NOT_FIRE_ACROSS_SSH")
 need(MARKER.stat().st_size==0,"WATCHDOG_PROBE_MARKER_TAMPERED")
 need(not RECEIPT.exists() and not RECEIPT.is_symlink(),
      "WATCHDOG_RECEIPT_ALREADY_EXISTS")
 receipt={"schema":"vision79-v3-user-watchdog-disconnect-proof",
          "status":"PASS_WATCHDOG_FIRED_AFTER_SSH_DISCONNECT",
          "observed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
          "unit":UNIT,"marker_verified_owner_and_empty":True,
          "candidate_started":False,"production_changes":"NONE",
          "real_rollback_watchdog_armed":False,"release_gate":"HOLD"}
 with RECEIPT.open("x",encoding="utf-8") as fp:
  os.chmod(RECEIPT,0o600)
  fp.write(json.dumps(receipt,sort_keys=True)+"\n")
  fp.flush();os.fsync(fp.fileno())
 # No production-related units are touched. Remove our own marker only.
 MARKER.unlink()
 print(json.dumps({"result":"PASS_WATCHDOG_FIRED_AFTER_SSH_DISCONNECT",
       "user_systemd_timer_executed":True,
       "private_probe_marker_removed":True,
       "durable_watchdog_liveness_receipt_created":True,
       "real_rollback_controller_tested":False,
       "real_rollback_watchdog_armed":False,
       "candidate_started":False,"production_changes":"NONE","release_gate":"HOLD"},sort_keys=True))
class Tests(unittest.TestCase):
 def test_wrong_host_fails_without_disk_or_commands(self):
  with patch("socket.gethostname",return_value="not-v79sl"):
   with self.assertRaisesRegex(Stop,"SERVER_UNPRIVILEGED_USER_REQUIRED"):
    read_plan()
 def test_schema_and_expected_pins_not_blank(self):
  self.assertEqual(len(NEW),71)
  self.assertEqual(len(OLD),71)
  self.assertNotEqual(OLD,NEW)
 def test_timer_name_is_not_production_unit(self):
  self.assertEqual(UNIT,"vision79-v3-watchdog-liveness")
  self.assertNotIn("rollback",UNIT)
 def test_read_plan_holds_release(self):
  self.assertTrue(PLAN.name.endswith(".json"))
  self.assertEqual(OVERLAY.name,"v3-image-only.json")
 def test_liveness_receipt_path_is_private_plan_only(self):
  self.assertEqual(RECEIPT.parent,ROOT)
  self.assertNotEqual(MARKER,RECEIPT)
 def test_only_modes_supported(self):
  with patch("sys.argv",["watchdog.py","--deploy"]):
   with self.assertRaisesRegex(Stop,"MODE_NOT_SUPPORTED"):
    main()
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ("--self-test","--arm","--check"),
      "MODE_NOT_SUPPORTED")
 if sys.argv[1]=="--self-test":
  tests=unittest.TextTestRunner(verbosity=1).run(
      unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if tests.wasSuccessful() else 1
 if sys.argv[1]=="--arm":arm()
 else:check()
 return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as ex:
  print(json.dumps({"result":"STOP","reason":str(ex),"release_gate":"HOLD",
                    "production_changes":"NONE"}));sys.exit(3)
 except Exception as ex:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(ex).__name__,
                    "release_gate":"HOLD","production_changes":"NOT_REVERIFIED"}));sys.exit(3)
