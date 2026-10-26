#!/usr/bin/env python3
"""Read-only live identity checks around a separately controlled image-only import.

Never starts/stops containers, changes Compose, or reports raw private metadata.
The --before gate requires the candidate image absent. --after requires it present.
"""
import hashlib,json,os,socket,subprocess,sys,unittest
from unittest.mock import patch
EXPECTED={
 "v79-hub":"sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4",
 "v79-hub-postgres":"sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
 "v79-tiquet-manager":"sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0",
 "tiquet-postgres":"sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685",
 "v79-business-agent":"sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b"}
CANDIDATE="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
SOURCE="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
AUDIT="2e63990c22d31d0998d90b575f7490a5fc09917c839f6a54f68e317cdfffaa57"
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def command(args):
 try:p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=45)
 except (OSError,subprocess.TimeoutExpired):raise Stop("READ_ONLY_DOCKER_UNAVAILABLE") from None
 need(p.returncode==0 and len(p.stdout)<16*1024*1024,"READ_ONLY_DOCKER_FAILED")
 return p.stdout
def inspect(kind,name):
 try:rows=json.loads(command(["docker","inspect","--type",kind,name]))
 except (ValueError,UnicodeError):raise Stop("INSPECTION_JSON_INVALID") from None
 need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),"INSPECTION_SHAPE_INVALID")
 return rows[0]
def fingerprint(row):
 data={"id":row.get("Id"),"image":row.get("Image"),"config":row.get("Config"),
       "host_config":row.get("HostConfig"),"mounts":row.get("Mounts"),
       "networks":(row.get("NetworkSettings") or {}).get("Networks")}
 return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def validate(services,candidate=None,phase="before"):
 need(set(services)==set(EXPECTED),"LIVE_SERVICE_SET_DRIFT")
 for name,row in services.items():
  state=row.get("State") or {}
  need(row.get("Image")==EXPECTED[name] and state.get("Status")=="running" and
       (state.get("Health") or {}).get("Status")=="healthy","LIVE_IMAGE_OR_HEALTH_DRIFT")
 need(fingerprint(services["v79-hub"])==AUDIT,"LIVE_HUB_RUNTIME_FINGERPRINT_DRIFT")
 if phase=="before":
  need(candidate is None,"CANDIDATE_ALREADY_IN_DOCKER_STORE")
 else:
  need(isinstance(candidate,dict) and candidate.get("Id")==CANDIDATE and
       ((candidate.get("Config") or {}).get("Labels") or {}).get("org.opencontainers.image.revision")==SOURCE,
       "STAGED_IMAGE_ID_OR_REVISION_DRIFT")
 return {"schema":"vision79-v3-image-only-stage-gate","phase":phase,
         "live_hub_fingerprint_match":True,"live_services_healthy":5,
         "candidate_present":phase=="after",
         "production_containers_changed":False,"release_gate":"HOLD"}
def collect(phase):
 need(socket.gethostname().split(".")[0]=="v79sl","SERVER_REQUIRED")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
      "LOCAL_DOCKER_REQUIRED")
 need(command(["docker","context","show"]).strip()==b"default" and
      command(["docker","info","--format","{{.Name}}"]).strip()==b"v79sl",
      "SERVER_DOCKER_DAEMON_REQUIRED")
 services={name:inspect("container",name) for name in EXPECTED}
 candidate=None
 try:
  raw=subprocess.run(["docker","image","inspect",CANDIDATE],stdout=subprocess.PIPE,
      stderr=subprocess.DEVNULL,timeout=30)
  need(len(raw.stdout)<16*1024*1024,"IMAGE_INSPECT_TOO_LARGE")
  if raw.returncode==0:
   rows=json.loads(raw.stdout)
   need(isinstance(rows,list) and len(rows)==1,"CANDIDATE_INSPECT_SHAPE")
   candidate=rows[0]
 except (OSError,subprocess.TimeoutExpired,ValueError,UnicodeDecodeError):
  raise Stop("CANDIDATE_INSPECT_UNAVAILABLE") from None
 result=validate(services,candidate,phase)
 again=inspect("container","v79-hub")
 need(fingerprint(again)==AUDIT and again.get("Id")==services["v79-hub"].get("Id"),
      "BASELINE_CHANGED_DURING_GATE")
 return result
class Tests(unittest.TestCase):
 def fixture(self):
  rows={n:{"Image":image,"State":{"Status":"running","Health":{"Status":"healthy"}}}
        for n,image in EXPECTED.items()}
  return rows
 def test_reject_wrong_image(self):
  rows=self.fixture();rows["v79-hub"]["Image"]="sha256:"+"a"*64
  with self.assertRaises(Stop):validate(rows,None,"before")
 def test_reject_bad_health(self):
  rows=self.fixture();rows["tiquet-postgres"]["State"]["Health"]["Status"]="unhealthy"
  with self.assertRaises(Stop):validate(rows,None,"before")
 def test_reject_fingerprint_drift(self):
  with self.assertRaises(Stop):validate(self.fixture(),None,"before")
 def test_reject_candidate_before_staging(self):
  rows=self.fixture()
  with patch(__name__+".AUDIT",fingerprint(rows["v79-hub"])):
   with self.assertRaises(Stop):validate(rows,{"Id":CANDIDATE},"before")
 def test_validate_after_source_pin_and_secret_free_output(self):
  rows=self.fixture()
  candidate={"Id":CANDIDATE,"Config":{"Labels":{"org.opencontainers.image.revision":SOURCE,
             "secret":"not_for_output"}}}
  with patch(__name__+".AUDIT",fingerprint(rows["v79-hub"])):
   report=validate(rows,candidate,"after")
  self.assertNotIn("not_for_output",json.dumps(report))
  self.assertEqual(report["candidate_present"],True)
 def test_wrong_host_before_docker(self):
  with patch("socket.gethostname",return_value="other"),patch(__name__+".command") as c:
   with self.assertRaises(Stop):collect("before")
   c.assert_not_called()
def main():
 need(len(sys.argv)==2 and sys.argv[1] in ("--before","--after","--self-test"),"MODE_REQUIRED")
 if sys.argv[1]=="--self-test":
  r=unittest.TextTestRunner(verbosity=1).run(
       unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 print(json.dumps(collect(sys.argv[1][2:]),sort_keys=True));return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as e:
  print(json.dumps({"result":"STOP","reason":str(e),"release_gate":"HOLD"}));sys.exit(3)
 except Exception as e:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(e).__name__,
                    "release_gate":"HOLD"}));sys.exit(3)
