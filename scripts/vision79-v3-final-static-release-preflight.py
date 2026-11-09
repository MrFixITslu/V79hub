#!/usr/bin/env python3
"""Vision79 v3 immutable, server-only read-only replacement *preflight*.

Checks candidate image identity/defaults and the exact pinned current runtime
and its Compose service. No Docker writes, no staging, no release and no
private configuration values emitted. This is NOT actual recreate parity,
MFA/SSO/browser acceptance or permission to deploy.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

PRIOR="sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
CANDIDATE="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
SOURCE="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
COMPOSE_SHA="2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083"
LIVE_FP="2e63990c22d31d0998d90b575f7490a5fc09917c839f6a54f68e317cdfffaa57"
HUB="v79-hub"
SERVICES={
 HUB:PRIOR,
 "v79-hub-postgres":"sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
 "v79-tiquet-manager":"sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0",
 "tiquet-postgres":"sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
 "v79-business-agent":"sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b",
}
class Stop(Exception):pass
def need(ok,reason):
 if not ok:raise Stop(reason)
def cmd(argv,cwd=None):
 try:p=subprocess.run(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=45)
 except (OSError,subprocess.TimeoutExpired):raise Stop("READ_ONLY_DOCKER_UNAVAILABLE") from None
 need(p.returncode==0 and len(p.stdout)<=16*1024*1024,"READ_ONLY_COMMAND_FAILED")
 return p.stdout
def one(kind,name):
 try:rows=json.loads(cmd(["docker","inspect","--type",kind,name]))
 except (ValueError,UnicodeError):raise Stop("PRIVATE_INSPECTION_INVALID") from None
 need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),"DOCKER_INSPECTION_SHAPE")
 return rows[0]
def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def fingerprint(row):
 return digest({"id":row.get("Id"),"image":row.get("Image"),
                "config":row.get("Config"),"host_config":row.get("HostConfig"),
                "mounts":row.get("Mounts"),
                "networks":(row.get("NetworkSettings") or {}).get("Networks")})
def env(rows):
 result={}
 for value in rows or []:
  need(isinstance(value,str) and "=" in value,"ENVIRONMENT_SHAPE_DRIFT")
  k,v=value.split("=",1)
  need(k and k not in result,"DUPLICATE_ENVIRONMENT_KEY")
  result[k]=v
 return result
def mounts(row):
 result={}
 for item in row.get("Mounts") or []:
  dest=item.get("Destination");typ=item.get("Type")
  src=item.get("Name") if typ=="volume" else item.get("Source")
  need(typ in ("bind","volume") and isinstance(dest,str) and dest.startswith("/")
       and isinstance(src,str) and src and dest not in result,"RUNTIME_MOUNT_INVALID")
  result[dest]=(typ,src,bool(item.get("RW")))
 return result
def expected_mounts(service,compose):
 result={}
 for item in service.get("volumes") or []:
  need(isinstance(item,dict),"COMPOSE_MOUNT_INVALID")
  kind=item.get("type");src=item.get("source");target=item.get("target")
  need(kind in ("bind","volume") and isinstance(src,str) and src and
       isinstance(target,str) and target.startswith("/") and target not in result,
       "COMPOSE_MOUNT_SHAPE")
  if kind=="volume":src=((compose.get("volumes") or {}).get(src) or {}).get("name",src)
  result[target]=(kind,src,not bool(item.get("read_only",False)))
 return result
def validate(live,prior,candidate,rendered,others):
 need(set(others)==set(SERVICES)-{HUB},"SERVICE_SET_DRIFT")
 for name,row in [(HUB,live),*others.items()]:
  status=row.get("State") or {}
  need(row.get("Image")==SERVICES[name] and status.get("Status")=="running"
       and (status.get("Health") or {}).get("Status")=="healthy",
       "RUNNING_SERVICE_IDENTITY_OR_HEALTH_DRIFT")
 need(fingerprint(live)==LIVE_FP,"CURRENT_LIVE_RUNTIME_FINGERPRINT_DRIFT")
 need(prior.get("Id")==PRIOR and candidate.get("Id")==CANDIDATE,
      "PRIOR_OR_CANDIDATE_IMAGE_MISSING")
 c_label=((candidate.get("Config") or {}).get("Labels") or {}).get("org.opencontainers.image.revision")
 need(c_label==SOURCE,"APPROVED_CANDIDATE_REVISION_DRIFT")
 current=(live.get("Config") or {})
 service=(rendered.get("services") or {}).get(HUB)
 need(isinstance(service,dict),"COMPOSE_HUB_MISSING")
 tags=[PRIOR]+(prior.get("RepoTags") or [])+(prior.get("RepoDigests") or [])
 need(service.get("image") is None or service.get("image") in tags,
      "COMPOSE_REFERENCE_DRIFT")
 e=env(current.get("Env"))
 cfg_env=service.get("environment") or {}
 need(isinstance(cfg_env,dict),"COMPOSE_ENVIRONMENT_SHAPE")
 expected=env((prior.get("Config") or {}).get("Env"))
 expected.update({k:str(v) for k,v in cfg_env.items() if v is not None})
 need(e==expected and len(e)==85,"LIVE_ENVIRONMENT_COMPOSE_DRIFT")
 need(e.get("V79_REQUIRE_ADMIN_MFA")=="1","OWNER_MFA_CONFIG_DISABLED")
 candidate_env=env((candidate.get("Config") or {}).get("Env"))
 need(set(candidate_env).issubset(e) and
      all(e[k]==v for k,v in candidate_env.items()),"CANDIDATE_DEFAULT_ENVIRONMENT_DRIFT")
 expected_m=expected_mounts(service,rendered)
 actual_m=mounts(live)
 need(actual_m==expected_m and len(actual_m)==7,"EXACT_MOUNT_SOURCE_AND_MODE_DRIFT")
 hc=live.get("HostConfig") or {}
 need(len(hc.get("Binds") or [])==4 and len(hc.get("Mounts") or [])==3,
      "HOST_BIND_AND_MOUNT_SHAPE_DRIFT")
 need(not hc.get("Privileged") and not hc.get("PortBindings"),"UNEXPECTED_PRIVILEGE_OR_PORTS")
 networks=(live.get("NetworkSettings") or {}).get("Networks") or {}
 expected_n=service.get("networks") or {}
 if isinstance(expected_n,list):expected_n={n:{} for n in expected_n}
 need(isinstance(expected_n,dict),"COMPOSE_NETWORKS_SHAPE")
 need(set(networks)=={((rendered.get("networks") or {}).get(n) or {}).get("name",n)
                       for n in expected_n} and len(networks)==2,
      "NETWORK_MEMBERSHIP_DRIFT")
 # The image must preserve the process/working-directory contract; Docker
 # Compose may supply overrides. Do not infer exact recreation from this.
 config_before=prior.get("Config") or {}
 config_after=candidate.get("Config") or {}
 critical=("User","Entrypoint","Cmd","WorkingDir","StopSignal","Healthcheck",
           "ExposedPorts","Volumes")
 changed=[k for k in critical if config_before.get(k)!=config_after.get(k)]
 need(not changed,"CANDIDATE_PROCESS_OR_VOLUME_DEFAULT_DRIFT")
 # Plan an image-only change against the rendered Compose *in memory*.
 # If the original service contains build, forbid Compose rebuilding live.
 need(not service.get("build"),"COMPOSE_BUILD_DIRECTIVE_REQUIRES_REVIEW")
 planned=dict(service, image=CANDIDATE)
 need({k:v for k,v in planned.items() if k!="image"}==
      {k:v for k,v in service.items() if k!="image"},
      "PLANNED_COMPOSE_MUTATION_OUTSIDE_IMAGE")
 before={name:{"id":row.get("Id"),"image":row.get("Image")}
         for name,row in [(HUB,live),*others.items()]}
 return {"schema":"vision79-v3-static-replacement-preflight",
         "result":"PASS_STATIC_REPLACEMENT_CONTRACT",
         "approved_candidate_cached":True,
         "live_runtime_fingerprint_matches":True,
         "current_services_healthy":len(SERVICES),
         "service_identity_sha256":digest(before),
         "runtime_environment_keys":len(e),
         "mount_destinations":len(actual_m),
         "host_bind_entries":len(hc.get("Binds") or []),
         "host_mount_entries":len(hc.get("Mounts") or []),
         "network_count":len(networks),
         "candidate_critical_image_defaults_match":True,
         "rendered_compose_planned_change":"IMAGE_ONLY_IN_MEMORY",
         "live_docker_or_compose_modified":False,
         "candidate_started":False,
         "exact_recreation_parity_proven":False,
         "authenticated_owner_mfa_sso_proven":False,
         "live_cutover_authorized":False,
         "release_gate":"HOLD"}
def collect():
 need(socket.gethostname().split(".")[0]=="v79sl","EXPECTED_SERVER_ONLY")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
      "LOCAL_UNPRIVILEGED_DOCKER_ONLY")
 need(cmd(["docker","context","show"]).strip()==b"default" and
      cmd(["docker","info","--format","{{.Name}}"]).strip()==b"v79sl",
      "LOCAL_DOCKER_DAEMON_REQUIRED")
 services={n:one("container",n) for n in SERVICES}
 hub=services[HUB]
 labels=(hub.get("Config") or {}).get("Labels") or {}
 chain=(labels.get("com.docker.compose.project.config_files") or "").split(",")
 need(len(chain)==1 and Path(chain[0]).is_absolute() and
      Path(chain[0]).name=="hub-candidate.json","COMPOSE_CHAIN_DRIFT")
 path=Path(chain[0])
 need(path.is_file() and not path.is_symlink() and path.stat().st_size<=2_000_000,
      "COMPOSE_FILE_INVALID")
 need(hashlib.sha256(path.read_bytes()).hexdigest()==COMPOSE_SHA,"COMPOSE_FILE_DIGEST_DRIFT")
 project=labels.get("com.docker.compose.project")
 working=labels.get("com.docker.compose.project.working_dir")
 need(isinstance(project,str) and project and isinstance(working,str) and
      Path(working).is_absolute(),"COMPOSE_PROJECT_DRIFT")
 try:rendered=json.loads(cmd(["docker","compose","--project-directory",working,
   "--project-name",project,"-f",str(path),"config","--format","json"],cwd=working))
 except (ValueError,UnicodeError):raise Stop("COMPOSE_RENDER_INVALID") from None
 result=validate(hub,one("image",PRIOR),one("image",CANDIDATE),rendered,
                 {n:r for n,r in services.items() if n!=HUB})
 refreshed={n:one("container",n) for n in SERVICES}
 need(all(services[n].get("Id")==refreshed[n].get("Id") and
          services[n].get("Image")==refreshed[n].get("Image") for n in SERVICES),
      "SERVICE_IDENTITY_CHANGED_DURING_AUDIT")
 need(fingerprint(refreshed[HUB])==LIVE_FP and
      hashlib.sha256(path.read_bytes()).hexdigest()==COMPOSE_SHA,
      "HUB_RUNTIME_CHANGED_DURING_AUDIT")
 return result
class Tests(unittest.TestCase):
 def example(self):
  envs=["V79_REQUIRE_ADMIN_MFA=1"]+["KEY"+str(i)+"=value" for i in range(84)]
  identity=PRIOR
  live={"Image":PRIOR,"State":{"Status":"running","Health":{"Status":"healthy"}},
   "Config":{"Env":envs},
   "HostConfig":{"Binds":["private"]*4,"Mounts":[{}]*3,
                  "Privileged":False,"PortBindings":None},
   "Mounts":[{"Destination":"/app/d"+str(i),"Type":"bind",
              "Source":"/private/d"+str(i),"RW":True} for i in range(7)],
   "NetworkSettings":{"Networks":{"network_a":{},"network_b":{}}}}
  others={n:{"Image":image,"Id":"container-"+str(i),
            "State":{"Status":"running","Health":{"Status":"healthy"}}}
          for i,(n,image) in enumerate(SERVICES.items()) if n!=HUB}
  prior={"Id":PRIOR,"Config":{"Env":[]}, "RepoTags":["hub:prior"]}
  candidate={"Id":CANDIDATE,"Config":{"Env":["V79_REQUIRE_ADMIN_MFA=1"],
     "Labels":{"org.opencontainers.image.revision":SOURCE}}}
  volumes=[{"type":"bind","source":"/private/d"+str(i),"target":"/app/d"+str(i)}
           for i in range(7)]
  rendered={"services":{HUB:{"image":"hub:prior","environment":
             {k:v for k,v in env(x for x in envs).items()},"volumes":volumes,
             "networks":{"a":{},"b":{}}}},
             "networks":{"a":{"name":"network_a"},"b":{"name":"network_b"}}}
  return live,prior,candidate,rendered,others
 def test_healthy_synthetic_static_contract_no_secrets(self):
  live,prior,cand,model,others=self.example()
  live["Config"]["Env"][1]="KEY0=private-secret"
  model["services"][HUB]["environment"]["KEY0"]="private-secret"
  with patch(__name__+".LIVE_FP",fingerprint(live)):
   report=validate(live,prior,cand,model,others)
  self.assertEqual(report["result"],"PASS_STATIC_REPLACEMENT_CONTRACT")
  self.assertNotIn("private-secret",json.dumps(report))
  self.assertFalse(report["live_cutover_authorized"])
 def test_fail_bad_candidate_digest(self):
  vals=self.example();vals[2]["Id"]="sha256:"+"a"*64
  with self.assertRaises(Stop):validate(*vals)
 def test_fail_mutated_mount(self):
  vals=self.example();vals[0]["Mounts"][0]["Source"]="/wrong"
  with patch(__name__+".LIVE_FP",fingerprint(vals[0])):
   with self.assertRaises(Stop):validate(*vals)
 def test_fail_changed_candidate_user(self):
  vals=self.example();vals[2]["Config"]["User"]="appuser"
  with patch(__name__+".LIVE_FP",fingerprint(vals[0])):
   with self.assertRaises(Stop):validate(*vals)
 def test_fail_unexpected_compose_build(self):
  vals=self.example();vals[3]["services"][HUB]["build"]={"context":"."}
  with patch(__name__+".LIVE_FP",fingerprint(vals[0])):
   with self.assertRaises(Stop):validate(*vals)
 def test_wrong_host_does_not_touch_docker(self):
  with patch("socket.gethostname",return_value="other"),patch(__name__+".cmd") as c:
   with self.assertRaises(Stop):collect()
   c.assert_not_called()
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ("--self-test","--run"),
      "SELF_TEST_OR_RUN_REQUIRED")
 if sys.argv[1]=="--self-test":
  r=unittest.TextTestRunner(verbosity=1).run(
      unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 print(json.dumps(collect(),sort_keys=True));return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as exc:
  print(json.dumps({"result":"STOP","reason":str(exc),"release_gate":"HOLD",
                    "production_changes":"NONE"}));sys.exit(3)
 except Exception as exc:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(exc).__name__,
                    "release_gate":"HOLD","production_changes":"NONE"}));sys.exit(3)
