#!/usr/bin/env python3
"""V79 Vision79 v3: SEAL A RELEASE PLAN ONLY. NEVER DEPLOY.

Creates one private receipt and one durable IMAGE-ONLY Compose overlay.
NO docker up/stop/create, data access, user authentication, secrets export,
timer changes, service restarts or production deployment capability.

A sealed plan is NOT a GO. It must be consumed by a separately reviewed,
supervised rollback-watched release controller after explicit acceptance.
"""
import grp,hashlib,json,os,pwd,re,shutil,socket,stat,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

HUB="v79-hub"
BEFORE="sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
AFTER="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
SOURCE="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
LIVE_FP="2e63990c22d31d0998d90b575f7490a5fc09917c839f6a54f68e317cdfffaa57"
CONFIG_SHA="2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083"
BASE_DIR=Path("/home/firelion/v79-v3-cutover-plan-20261026")
OTHER={
 "v79-hub-postgres":"sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
 "v79-tiquet-manager":"sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0",
 "tiquet-postgres":"sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
 "v79-business-agent":"sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b",
}
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def run(args,env=None,cwd=None,timeout=35):
 try:
  p=subprocess.run(args,cwd=cwd,env=env,stdout=subprocess.PIPE,
                   stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):
  raise Stop("READ_ONLY_COMMAND_UNAVAILABLE") from None
 need(p.returncode==0 and len(p.stdout)<16*1024*1024,
      "READ_ONLY_COMMAND_FAILED")
 return p.stdout
def docker(kind,name):
 try:rows=json.loads(run(["docker","inspect","--type",kind,name]))
 except (ValueError,UnicodeError):raise Stop("DOCKER_INSPECTION_JSON_INVALID") from None
 need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),
      "DOCKER_INSPECTION_SHAPE")
 return rows[0]
def sha(data):
 return hashlib.sha256(data).hexdigest()
def fingerprint(row):
 obj={"id":row.get("Id"),"image":row.get("Image"),"config":row.get("Config"),
      "host_config":row.get("HostConfig"),"mounts":row.get("Mounts"),
      "networks":(row.get("NetworkSettings") or {}).get("Networks")}
 return sha(json.dumps(obj,sort_keys=True,separators=(",",":")).encode())
def user_manager_env():
 uid=pwd.getpwnam("firelion").pw_uid
 runtime=Path("/run/user")/str(uid)
 need(runtime.is_dir() and runtime.stat().st_uid==uid,
      "SYSTEMD_USER_RUNTIME_DIRECTORY_MISSING")
 custom=dict(os.environ)
 custom["XDG_RUNTIME_DIR"]=str(runtime)
 return custom
def watchdog_prerequisites():
 need(run(["loginctl","show-user","firelion","-p","Linger","--value"]).strip()==b"yes",
      "WATCHDOG_LINGER_DISABLED")
 need(shutil.which("systemd-run") and shutil.which("systemctl") and
      shutil.which("sg"),"WATCHDOG_SYSTEMD_COMMAND_MISSING")
 try: group=grp.getgrnam("docker")
 except KeyError:raise Stop("DOCKER_GROUP_MISSING") from None
 account=pwd.getpwnam("firelion")
 need("firelion" in group.gr_mem or account.pw_gid==group.gr_gid,
      "WATCHDOG_USER_NOT_IN_DOCKER_GROUP")
 environment=user_manager_env()
 # Observation only: installing/scheduling a watchdog is NOT done here.
 run(["systemctl","--user","list-timers","--all","--no-pager","--no-legend"],
     env=environment)
 return {"linger":True,"user_systemd_query":True,
         "docker_group_membership":True,
         "timer_was_armed":False,"rollback_transaction_tested":False}
def validate_rows(hub,others,prior,candidate,rendered,compose_path):
 expected={HUB:BEFORE,**OTHER}
 need(set(others)==set(OTHER),"SERVICE_SET_DRIFT")
 for name,row in [(HUB,hub),*others.items()]:
  status=row.get("State") or {}
  need(row.get("Image")==expected[name] and status.get("Status")=="running" and
       (status.get("Health") or {}).get("Status")=="healthy",
       "SERVICE_IMAGE_OR_HEALTH_DRIFT")
 need(fingerprint(hub)==LIVE_FP,"HUB_RUNTIME_FINGERPRINT_DRIFT")
 need(prior.get("Id")==BEFORE and candidate.get("Id")==AFTER and
      ((candidate.get("Config") or {}).get("Labels") or {}).get(
      "org.opencontainers.image.revision")==SOURCE,
      "IMAGE_ID_OR_SOURCE_DRIFT")
 need(sha(compose_path.read_bytes())==CONFIG_SHA,"COMPOSE_DIGEST_DRIFT")
 services=rendered.get("services") or {}
 need(isinstance(services,dict) and HUB in services,"COMPOSE_SERVICE_MISSING")
 before=services[HUB]
 need(not before.get("build"),"COMPOSE_BUILD_DIRECTIVE")
 old_refs={BEFORE,*(prior.get("RepoTags") or []),*(prior.get("RepoDigests") or [])}
 need(before.get("image") in old_refs,"OLD_COMPOSE_IMAGE_REFERENCE_DRIFT")
 need(len((hub.get("Config") or {}).get("Env") or [])==85 and
      len(hub.get("Mounts") or [])==7 and
      len((hub.get("HostConfig") or {}).get("Binds") or [])==4 and
      len((hub.get("HostConfig") or {}).get("Mounts") or [])==3 and
      len(((hub.get("NetworkSettings") or {}).get("Networks") or {}))==2,
      "RUNTIME_COUNT_DRIFT")
 return {"services":len(services),"image_before":BEFORE,"image_after":AFTER}
def preflight():
 need(socket.gethostname().split(".")[0]=="v79sl","EXPECTED_SERVER_REQUIRED")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and
      not os.getenv("DOCKER_CONTEXT"),"LOCAL_DOCKER_ONLY")
 need(run(["docker","context","show"]).strip()==b"default" and
      run(["docker","info","--format","{{.Name}}"]).strip()==b"v79sl",
      "SERVER_DOCKER_REQUIRED")
 hub=docker("container",HUB)
 labels=(hub.get("Config") or {}).get("Labels") or {}
 files=(labels.get("com.docker.compose.project.config_files") or "").split(",")
 need(len(files)==1 and Path(files[0]).is_absolute() and
      Path(files[0]).name=="hub-candidate.json",
      "ORIGINAL_COMPOSE_CHAIN_DRIFT")
 compose=Path(files[0])
 need(compose.is_file() and not compose.is_symlink()
      and 0<compose.stat().st_size<2_000_000,
      "COMPOSE_SOURCE_FILE_INVALID")
 working=labels.get("com.docker.compose.project.working_dir")
 project=labels.get("com.docker.compose.project")
 need(isinstance(working,str) and Path(working).is_absolute()
      and Path(working).is_dir() and isinstance(project,str)
      and re.fullmatch(r"[a-zA-Z0-9_-]{1,120}",project),
      "COMPOSE_PROJECT_INVALID")
 base=["docker","compose","--project-directory",working,
       "--project-name",project,"-f",str(compose)]
 try:rendered=json.loads(run(base+["config","--format","json"],cwd=working))
 except (ValueError,UnicodeError):raise Stop("RENDERED_COMPOSE_INVALID") from None
 others={n:docker("container",n) for n in OTHER}
 result=validate_rows(hub,others,docker("image",BEFORE),docker("image",AFTER),
                      rendered,compose)
 identity=sha(json.dumps({n:{"id":r.get("Id"),"image":r.get("Image")}
                for n,r in [(HUB,hub),*others.items()]},
               sort_keys=True,separators=(",",":")).encode())
 need(identity=="fc96149b9d17077a6bb263835e5f043ce3465b95ad958a2fb64e08107d5535b3","FIVE_SERVICE_IDENTITY_DRIFT")
 watchdog=watchdog_prerequisites()
 # Avoid checks passing if live containers changed while watching systemd.
 need(fingerprint(docker("container",HUB))==LIVE_FP,
      "HUB_CHANGED_DURING_WATCHDOG_PREFLIGHT")
 for name,row in others.items():
  latest=docker("container",name)
  need(latest.get("Id")==row.get("Id") and latest.get("Image")==row.get("Image"),
       "OTHER_SERVICE_CHANGED_DURING_PREFLIGHT")
 return {"project":project,"working":working,"base_path":str(compose),
         "hub_id":hub.get("Id"),"service_identity_sha256":sha(
            json.dumps({n:{"id":r.get("Id"),"image":r.get("Image")}
                for n,r in [(HUB,hub),*others.items()]},
               sort_keys=True,separators=(",",":")).encode()),
         "service_count":result["services"],"watchdog":watchdog}
def private_file(path,data):
 with path.open("x",encoding="utf-8") as f:
  os.chmod(path,0o600)
  f.write(data)
  f.flush();os.fsync(f.fileno())
def create(plan):
 need(not BASE_DIR.exists() and not BASE_DIR.is_symlink(),
      "RELEASE_PLAN_ALREADY_EXISTS_STOP")
 os.umask(0o077)
 BASE_DIR.mkdir(mode=0o700)
 try:
  override={"services":{HUB:{"image":AFTER}}}
  encoded=json.dumps(override,sort_keys=True,separators=(",",":"))+"\n"
  private_file(BASE_DIR/"v3-image-only.json",encoded)
  receipt={"schema":"vision79-v3-cutover-seal-v1","status":"SEALED_NOT_DEPLOYED",
    "originating_approved_source":SOURCE,
    "candidate_image":AFTER,"prior_image":BEFORE,
    "base_compose_sha256":CONFIG_SHA,"baseline_live_fingerprint":LIVE_FP,
    "approved_static_preflight":"PASS_STATIC_REPLACEMENT_CONTRACT",
    "approved_compose_dryrun":"PASS_IMAGE_ONLY_COMPOSE_DRY_RUN",
    "five_service_identity_sha256":plan["service_identity_sha256"],
    "compose_project":plan["project"],
    "compose_project_directory":plan["working"],
    "base_compose_path":plan["base_path"],
    "overlay_path":str(BASE_DIR/"v3-image-only.json"),
    "overlay_sha256":sha(encoded.encode()),
    "exact_old_hub_container_id":plan["hub_id"],
    "rollback_command_plan_only":["docker","compose","--project-directory",
        plan["working"],"--project-name",plan["project"],"-f",plan["base_path"],
        "up","--detach","--no-deps","--no-build","--pull","never",
        "--force-recreate",HUB],
    "watchdog_prerequisites":plan["watchdog"],
    "watchdog_armed":False,"watchdog_timer_verified":False,
    "cutover_executed":False,"owner_mfa_sso_accepted":False,
    "reversible_production_transaction_tested":False,
    "release_gate":"HOLD"}
  private_file(BASE_DIR/"sealed-plan.json",
               json.dumps(receipt,sort_keys=True,indent=2)+"\n")
  return {"result":"PASS_RELEASE_PLAN_SEALED_NOT_DEPLOYED",
    "plan_root":str(BASE_DIR),"durable_override_created":True,
    "original_compose_unchanged":True,
    "watchdog_preconditions_verified":True,
    "rollback_command_prepared_not_executed":True,
    "watchdog_timer_armed":False,"candidate_started":False,
    "production_changes":"NONE","release_gate":"HOLD"}
 except Exception:
  for filename in ("sealed-plan.json","v3-image-only.json"):
   p=BASE_DIR/filename
   if p.is_file() and not p.is_symlink():p.unlink()
  BASE_DIR.rmdir()
  raise
class Tests(unittest.TestCase):
 def test_release_verb_not_supported(self):
  with patch("sys.argv",["seal.py","--deploy"]),patch(__name__+".preflight") as fn:
   with self.assertRaises(Stop):main()
   fn.assert_not_called()
 def test_private_plan_pins_only_approved_image_and_retains_base(self):
  with tempfile.TemporaryDirectory() as tmp:
   planroot=Path(tmp)/"sealed"
   fixture={"project":"demo","working":"/opt/synthetic",
      "base_path":"/opt/synthetic/hub-candidate.json",
      "hub_id":"original-container-id","service_count":3,
      "service_identity_sha256":"a"*64,
      "watchdog":{"linger":True,"timer_was_armed":False}}
   with patch(__name__+".BASE_DIR",planroot):
    output=create(fixture)
   self.assertEqual(output["result"],"PASS_RELEASE_PLAN_SEALED_NOT_DEPLOYED")
   data=json.loads((planroot/"sealed-plan.json").read_text())
   overlay=json.loads((planroot/"v3-image-only.json").read_text())
   self.assertEqual(overlay,{"services":{HUB:{"image":AFTER}}})
   self.assertEqual(data["prior_image"],BEFORE)
   self.assertEqual(data["release_gate"],"HOLD")
   self.assertFalse(data["watchdog_armed"])
   self.assertFalse(data["cutover_executed"])
   self.assertEqual(data["rollback_command_plan_only"][-1],HUB)
   self.assertEqual(data["rollback_command_plan_only"][
     data["rollback_command_plan_only"].index("-f")+1],fixture["base_path"])
   self.assertEqual(stat.S_IMODE(planroot.stat().st_mode),0o700)
   self.assertEqual(stat.S_IMODE((planroot/"sealed-plan.json").stat().st_mode),0o600)
   self.assertEqual(stat.S_IMODE((planroot/"v3-image-only.json").stat().st_mode),0o600)
   self.assertNotIn("secret",str(data).lower())
 def test_wrong_host_before_docker(self):
  with patch("socket.gethostname",return_value="other"),patch(__name__+".run") as fn:
   with self.assertRaises(Stop):preflight()
   fn.assert_not_called()
 def test_refuses_duplicate_seal(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch(__name__+".BASE_DIR",Path(tmp)):
    with self.assertRaisesRegex(Stop,"RELEASE_PLAN_ALREADY_EXISTS_STOP"):
     create({"watchdog":{}})
 def test_linger_missing_denies_watchdog_readiness(self):
  with patch(__name__+".run",return_value=b"no\n") as fn:
   with self.assertRaisesRegex(Stop,"WATCHDOG_LINGER_DISABLED"):
    watchdog_prerequisites()
   self.assertEqual(fn.call_count,1)

def main():
 need(len(sys.argv)==2 and sys.argv[1] in ("--self-test","--seal"),
      "NO_RELEASE_OPERATION_SUPPORTED")
 if sys.argv[1]=="--self-test":
  tests=unittest.TextTestRunner(verbosity=1).run(
   unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if tests.wasSuccessful() else 1
 plan=preflight()
 print(json.dumps(create(plan),sort_keys=True))
 return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as exc:
  print(json.dumps({"result":"STOP","reason":str(exc),
        "production_runtime_changed":False,"release_gate":"HOLD"}))
  sys.exit(3)
 except Exception as exc:
  print(json.dumps({"result":"STOP",
        "reason":"REDACTED_"+type(exc).__name__,
        "production_runtime_changed":"NOT_REVERIFIED",
        "release_gate":"HOLD"}))
  sys.exit(3)
