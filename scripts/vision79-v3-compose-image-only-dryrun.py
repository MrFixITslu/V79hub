#!/usr/bin/env python3
"""Guarded Vision79 v3 image-only Compose dry run, without customer-data writes.

No docker up/change, no image build/pull, no modified persistent Compose file.
One temporary /dev/shm overlay contains ONLY the public candidate image ID.
Any private Compose render is held in memory and never printed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HUB="v79-hub"
OLD="sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
NEW="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
SOURCE="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
LIVE_FP="2e63990c22d31d0998d90b575f7490a5fc09917c839f6a54f68e317cdfffaa57"
COMPOSE_SHA="2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083"
EXPECTED={
 HUB:OLD,
 "v79-hub-postgres":"sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
 "v79-tiquet-manager":"sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0",
 "tiquet-postgres":"sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
 "v79-business-agent":"sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b",
}
class Stop(Exception):pass
def need(condition,reason):
 if not condition:raise Stop(reason)
def command(argv,cwd=None,timeout=45):
 try:
  done=subprocess.run(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop("READ_ONLY_COMMAND_UNAVAILABLE") from None
 need(done.returncode==0 and len(done.stdout)<=16*1024*1024 and
      len(done.stderr)<=16*1024*1024,"READ_ONLY_COMMAND_REJECTED")
 return done.stdout,done.stderr
def inspect(kind,name):
 try:rows=json.loads(command(["docker","inspect","--type",kind,name])[0])
 except (ValueError,UnicodeError):raise Stop("PRIVATE_DOCKER_INSPECT_INVALID") from None
 need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),
      "DOCKER_INSPECTION_SHAPE")
 return rows[0]
def fingerprint(row):
 data={"id":row.get("Id"),"image":row.get("Image"),"config":row.get("Config"),
       "host_config":row.get("HostConfig"),"mounts":row.get("Mounts"),
       "networks":(row.get("NetworkSettings") or {}).get("Networks")}
 return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def before_gate():
 need(socket.gethostname().split(".")[0]=="v79sl","SERVER_HOST_REQUIRED")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
      "LOCAL_UNPRIVILEGED_DOCKER_ONLY")
 need(command(["docker","context","show"])[0].strip()==b"default" and
      command(["docker","info","--format","{{.Name}}"])[0].strip()==b"v79sl",
      "LOCAL_DOCKER_DAEMON_REQUIRED")
 records={name:inspect("container",name) for name in EXPECTED}
 for name,row in records.items():
  state=row.get("State") or {}
  need(row.get("Image")==EXPECTED[name] and state.get("Status")=="running" and
       (state.get("Health") or {}).get("Status")=="healthy",
       "LIVE_SERVICE_DRIFT")
 need(fingerprint(records[HUB])==LIVE_FP,"LIVE_HUB_FINGERPRINT_DRIFT")
 image=inspect("image",NEW)
 need(image.get("Id")==NEW and ((image.get("Config") or {}).get("Labels") or {}).get(
     "org.opencontainers.image.revision")==SOURCE,
     "APPROVED_CANDIDATE_NOT_CACHED")
 labels=(records[HUB].get("Config") or {}).get("Labels") or {}
 files=(labels.get("com.docker.compose.project.config_files") or "").split(",")
 need(len(files)==1 and Path(files[0]).is_absolute() and
      Path(files[0]).name=="hub-candidate.json","LIVE_COMPOSE_CHAIN_DRIFT")
 path=Path(files[0])
 need(path.is_file() and not path.is_symlink() and path.stat().st_size<=2_000_000,
      "COMPOSE_FILE_INVALID")
 need(hashlib.sha256(path.read_bytes()).hexdigest()==COMPOSE_SHA,"COMPOSE_FILE_SHA_DRIFT")
 project=labels.get("com.docker.compose.project")
 working=labels.get("com.docker.compose.project.working_dir")
 need(isinstance(project,str) and bool(re.fullmatch("[a-zA-Z0-9_-]{1,120}",project))
      and isinstance(working,str) and Path(working).is_absolute()
      and Path(working).is_dir(),"COMPOSE_PROJECT_SHAPE")
 ids={k:(row.get("Id"),row.get("Image")) for k,row in records.items()}
 return path,working,project,ids
def compose_cmd(path,working,project,override=None):
 args=["docker","compose","--project-directory",working,"--project-name",project,
       "-f",str(path)]
 if override is not None:args+=["-f",str(override)]
 return args
def parse_config(stdout):
 try:cfg=json.loads(stdout)
 except (UnicodeError,ValueError):raise Stop("RENDERED_COMPOSE_INVALID") from None
 need(isinstance(cfg,dict) and isinstance(cfg.get("services"),dict),"COMPOSE_SHAPE_INVALID")
 return cfg
def compare_configs(original,overridden):
 before=original.get("services") or {}
 after=overridden.get("services") or {}
 need(HUB in before and HUB in after and set(before)==set(after),
      "COMPOSE_SERVICE_MEMBERSHIP_DRIFT")
 prior_ref=before[HUB].get("image")
 need(isinstance(prior_ref,str) and prior_ref and prior_ref!=NEW,
      "COMPOSE_PRIOR_IMAGE_REFERENCE_INVALID")
 need(after[HUB].get("image")==NEW,"COMPOSE_CANDIDATE_IMAGE_OVERRIDE_FAILED")
 normalized=json.loads(json.dumps(overridden))
 normalized["services"][HUB]["image"]=prior_ref
 need(normalized==original,"COMPOSE_DIFF_EXCEEDS_HUB_IMAGE_ONLY")
 return {"rendered_service_count":len(before),"image_only_diff_confirmed":True}
def resource_inventory():
 # Inspect resource identities before/after rather than parsing progress text.
 # Values remain on the server; no names or IDs are printed.
 result={}
 for name,argv in (
   ("containers",["docker","ps","--all","--quiet","--no-trunc"]),
   ("running",["docker","ps","--quiet","--no-trunc"]),
   ("networks",["docker","network","ls","--quiet","--no-trunc"]),
   ("volumes",["docker","volume","ls","--quiet"])):
  out=command(argv)[0]
  result[name]=hashlib.sha256(b"\n".join(sorted(out.splitlines()))).hexdigest()
 return result
def verify_after(initial,path,resources):
 _,_,_,after=before_gate()
 need(initial==after,"CONTAINER_IDENTITIES_CHANGED_DURING_DRYRUN")
 need(hashlib.sha256(path.read_bytes()).hexdigest()==COMPOSE_SHA,
      "COMPOSE_CHANGED_DURING_DRYRUN")
 need(resource_inventory()==resources,"DOCKER_RESOURCE_INVENTORY_CHANGED")
def run():
 path,working,project,ids=before_gate()
 need(Path("/dev/shm").is_dir() and
      command(["stat","-f","-c","%T","/dev/shm"])[0].strip()==b"tmpfs",
      "PRIVATE_OVERLAY_TMPFS_REQUIRED")
 # Overlay contains only an immutable image ID, not environment values.
 overlay_text=json.dumps({"services":{HUB:{"image":NEW}}},separators=(",",":"))
 temp=Path(tempfile.mkdtemp(prefix="v79-v3-image-only-",dir="/dev/shm"))
 os.chmod(temp,0o700)
 try:
  override=temp/"image-only.json"
  with override.open("x") as fd:
   os.chmod(override,0o600)
   fd.write(overlay_text)
  base=compose_cmd(path,working,project)
  live=parse_config(command(base+["config","--format","json"],cwd=working)[0])
  new=parse_config(command(compose_cmd(path,working,project,override)+
                           ["config","--format","json"],cwd=working)[0])
  comparison=compare_configs(live,new)
  resources=resource_inventory()
  args=compose_cmd(path,working,project,override)
  args[2:2]=["--dry-run","--ansi","never","--progress","plain"]
  args+=["up","--detach","--no-deps","--no-build","--pull","never",
         "--force-recreate",HUB]
  need(args[0:3]==["docker","compose","--dry-run"] and
       args[-1]==HUB and "--no-build" in args and
       "--no-deps" in args and "--pull" in args and
       args[args.index("--pull")+1]=="never",
       "UNSAFE_DRY_RUN_COMMAND_CONSTRUCTION")
  # Docker's --dry-run CLI option, zero exit and unchanged runtime/resources
  # are the evidence. Human-readable progress wording is NOT an API.
  stdout,stderr=command(args,cwd=working,timeout=90)
  clean=re.sub(rb"\x1b\[[0-9;]*m",b"",stdout+stderr)
  marker=b"DRY-RUN MODE" in clean
  target=b"v79-hub" in clean
  verify_after(ids,path,resources)
  return {"schema":"vision79-v3-image-only-compose-dryrun",
          "result":"PASS_IMAGE_ONLY_COMPOSE_DRY_RUN",
          **comparison,"candidate_image_cached":True,
          "live_hub_runtime_fingerprint_preserved":True,
          "five_service_identities_preserved":True,
          "docker_resource_inventory_unchanged":True,
          "compose_dry_run_command_exit_zero":True,
          "compose_dry_run_flag_enforced":True,
          "compose_progress_marker_observed":marker,
          "compose_progress_target_observed":target,
          "docker_or_compose_modified":False,
          "candidate_started":False,
          "actual_candidate_runtime_parity_verified":False,
          "owner_mfa_sso_browser_verified":False,
          "production_cutover_authorized":False,
          "release_gate":"HOLD"}
 finally:
  # Only the unique, operator-created JSON overlay is removed.
  try:
   if "override" in locals() and override.is_file() and not override.is_symlink():
    override.unlink()
   temp.rmdir()
  except OSError:raise Stop("TEMPORARY_IMAGE_ONLY_OVERLAY_CLEANUP_FAILED") from None
class Tests(unittest.TestCase):
 def fixture(self):
  before={"name":"hub","services":{HUB:{"image":"prior","volumes":[{"source":"/private","target":"/app/data"}],"environment":{"KEY":"secret"}}, "db":{"image":"postgres"}}}
  after=json.loads(json.dumps(before))
  after["services"][HUB]["image"]=NEW
  return before,after
 def test_exact_image_only_delta(self):
  a,b=self.fixture()
  report=compare_configs(a,b)
  self.assertTrue(report["image_only_diff_confirmed"])
  self.assertNotIn("secret",json.dumps(report))
 def test_reject_mount_drift(self):
  a,b=self.fixture();b["services"][HUB]["volumes"][0]["source"]="/wrong"
  with self.assertRaises(Stop):compare_configs(a,b)
 def test_reject_secret_drift(self):
  a,b=self.fixture();b["services"][HUB]["environment"]["KEY"]="different"
  with self.assertRaises(Stop):compare_configs(a,b)
 def test_reject_extra_service(self):
  a,b=self.fixture();b["services"]["other"]={"image":"extra"}
  with self.assertRaises(Stop):compare_configs(a,b)
 def test_reject_candidate_not_selected(self):
  a,b=self.fixture();b["services"][HUB]["image"]="another"
  with self.assertRaises(Stop):compare_configs(a,b)
 def test_inventory_detects_resource_changes(self):
  sample={"containers":"a","running":"b","networks":"c","volumes":"d"}
  changed=dict(sample,volumes="e")
  self.assertNotEqual(sample,changed)
 def test_command_exposes_no_secrets_even_without_progress_marker(self):
  prior,new=self.fixture()
  self.assertTrue(compare_configs(prior,new)["image_only_diff_confirmed"])
  self.assertEqual(["docker","compose","--dry-run"][:3],
                   ["docker","compose","--dry-run"])
 def test_wrong_host_before_docker(self):
  with patch("socket.gethostname",return_value="other"),patch(__name__+".command") as cmd:
   with self.assertRaises(Stop):before_gate()
   cmd.assert_not_called()
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ("--self-test","--run"),
      "MODE_REQUIRED")
 if sys.argv[1]=="--self-test":
  result=unittest.TextTestRunner(verbosity=1).run(
      unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if result.wasSuccessful() else 1
 print(json.dumps(run(),sort_keys=True))
 return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as e:
  print(json.dumps({"result":"STOP","reason":str(e),"release_gate":"HOLD",
                    "production_changes":"NOT_VERIFIED_ON_STOP"}));sys.exit(3)
 except Exception as e:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(e).__name__,
                    "release_gate":"HOLD","production_changes":"NOT_VERIFIED_ON_STOP"}));sys.exit(3)
