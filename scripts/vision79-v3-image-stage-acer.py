#!/usr/bin/env python3
"""Acer-only transfer of approved v3 image into Dell Docker cache, no rollout.

Exports by immutable image ID, refuses archives with tags, verifies SSH
transport and checks five live container identities before and after import.
Never runs/stops/replaces an application, changes Compose or copies secrets.
"""
import hashlib,json,os,re,shlex,shutil,socket,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

IMAGE="sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6"
PRIOR="sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4"
SOURCE="114841271d4f8b9c4b63df6aedfd55bde2e82f40"
GATE_SHA="e2499c7879e1ecb406809c471364eeb8e33f602341d4d24c720de4907e06f9bd"
BUILD=Path("/home/firelion/v79-v3-approved-build.XDA1yD6v/build-receipt.json")
HOST="firelion@192.168.100.163"
SSH=["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=10",HOST]
SCP=["scp","-q","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=10"]
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def run(args,input_data=None,timeout=120):
 try:p=subprocess.run(args,input=input_data,stdout=subprocess.PIPE,
                      stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):raise Stop("COMMAND_UNAVAILABLE_OR_TIMEOUT") from None
 need(p.returncode==0 and len(p.stdout)<4*1024*1024,"LOCAL_OR_SSH_COMMAND_FAILED")
 return p.stdout.strip()
def remote(command,input_data=None,timeout=120):
 return run(SSH+[command],input_data,timeout)
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def validate_archive(archive):
 need(archive.is_file() and not archive.is_symlink() and
      10_000_000 <= archive.stat().st_size <= 4*1024**3,"ARCHIVE_SIZE_INVALID")
 try:
  with tarfile.open(archive,mode="r:") as tar:
   manifest=tar.extractfile("manifest.json")
   need(manifest is not None,"DOCKER_MANIFEST_MISSING")
   data=manifest.read(64*1024)
   entries=json.loads(data)
   need(isinstance(entries,list) and len(entries)==1,"IMAGE_ARCHIVE_COUNT_DRIFT")
   entry=entries[0]
   need(not entry.get("RepoTags"),"IMAGE_ARCHIVE_HAS_MUTABLE_TAGS")
   config=entry.get("Config","")
   need(config==IMAGE.split(":")[1]+".json","IMAGE_ARCHIVE_CONFIG_DRIFT")
 except (tarfile.TarError,ValueError,UnicodeError,OSError):
  raise Stop("IMAGE_ARCHIVE_INVALID") from None
 return digest(archive)
def preflight(gate):
 need(socket.gethostname().split(".")[0]=="firelion-Aspire-A315-51","ACER_REQUIRED")
 need(os.geteuid()!=0 and not os.getenv("DOCKER_HOST") and not os.getenv("DOCKER_CONTEXT"),
      "LOCAL_DOCKER_ONLY")
 need(gate.is_file() and not gate.is_symlink() and digest(gate)==GATE_SHA,
      "SERVER_GATE_SHA_DRIFT")
 need(run(["docker","context","show"])==b"default" and
      run(["docker","info","--format","{{.Name}}"])==b"firelion-Aspire-A315-51",
      "ACER_LOCAL_DOCKER_REQUIRED")
 rows=json.loads(run(["docker","image","inspect",IMAGE]))
 need(len(rows)==1 and rows[0].get("Id")==IMAGE and
      ((rows[0].get("Config") or {}).get("Labels") or {}).get("org.opencontainers.image.revision")==SOURCE,
      "CANDIDATE_IDENTITY_DRIFT")
 need(BUILD.is_file() and not BUILD.is_symlink(),"BUILD_RECEIPT_MISSING")
 receipt=json.loads(BUILD.read_text())
 need(receipt.get("candidate_image_id")==IMAGE and receipt.get("source_commit")==SOURCE
      and receipt.get("production_changes")=="NONE","BUILD_RECEIPT_DRIFT")
 need(shutil.disk_usage(str(Path.home())).free>=6*1024**3,"ACER_DISK_HEADROOM_LOW")
def live_gate(gate,phase):
 need(phase in ("before","after"),"GATE_PHASE_INVALID")
 out=remote("sg docker -c 'python3 -B - --"+phase+"'",gate.read_bytes(),timeout=100)
 try:result=json.loads(out)
 except (ValueError,UnicodeError):raise Stop("SERVER_GATE_RESPONSE_INVALID") from None
 need(result.get("schema")=="vision79-v3-image-only-stage-gate" and
      result.get("phase")==phase and
      result.get("live_hub_fingerprint_match") is True and
      result.get("live_services_healthy")==5 and
      result.get("candidate_present") is (phase=="after") and
      result.get("production_containers_changed") is False and
      result.get("release_gate")=="HOLD" and
      re.fullmatch("[a-f0-9]{64}",result.get("service_identity_sha256","")),
      "SERVER_GATE_REJECTED")
 return result
def remote_directory(path):
 need(bool(re.fullmatch(r"/home/firelion/v79-v3-image-transfer\.[a-zA-Z0-9]{8}",path)),
      "REMOTE_SCRATCH_PATH_UNSAFE")
 return path
def free_bytes(path):
 need(path.startswith("/") and ".." not in Path(path).parts and "\n" not in path,
      "DISK_PATH_INVALID")
 result=remote("df -B1 --output=avail "+shlex.quote(path)+" | tail -n 1")
 need(result.isdigit(),"DISK_HEADROOM_UNAVAILABLE")
 return int(result)
def cleanup(remote_dir):
 remote_directory(remote_dir)
 remote("rm -rf -- "+shlex.quote(remote_dir),timeout=120)
 check=remote("test ! -e "+shlex.quote(remote_dir)+" && printf CLEAN")
 need(check==b"CLEAN","REMOTE_TEMP_CLEANUP_UNVERIFIED")
def stage(gate):
 preflight(gate)
 before=live_gate(gate,"before")
 print("SERVER_LIVE_BASELINE=PASS_BEFORE",flush=True)
 scratch_remote=None;stage_done=False
 try:
  with tempfile.TemporaryDirectory(prefix="v79-v3-image-only-",dir=str(Path.home())) as d:
   archive=Path(d)/"candidate.tar"
   run(["docker","image","save","--output",str(archive),IMAGE],timeout=900)
   sha=validate_archive(archive)
   print("UNTAGGED_CANDIDATE_ARCHIVE=PASS",flush=True)
   docker_root=remote("sg docker -c 'docker info --format {{.DockerRootDir}}'").decode()
   need(docker_root.startswith("/") and ".." not in Path(docker_root).parts and
        not re.search(r"[\n\r'\"]",docker_root),"SERVER_DOCKER_ROOT_INVALID")
   minimum=archive.stat().st_size*3 + 4*1024**3
   need(free_bytes("/home/firelion")>=minimum and free_bytes(docker_root)>=minimum,
        "SERVER_DISK_HEADROOM_LOW")
   scratch_remote=remote_directory(remote("umask 077; mktemp -d /home/firelion/v79-v3-image-transfer.XXXXXXXX").decode())
   remote_archive=scratch_remote+"/candidate.tar"
   transfer=run(SCP+[str(archive),HOST+":"+remote_archive],timeout=1200)
   check=remote("sha256sum "+shlex.quote(remote_archive))
   need(check.decode().split()[0]==sha,"SSH_ARCHIVE_CHECKSUM_MISMATCH")
   need(live_gate(gate,"before")["service_identity_sha256"]==before["service_identity_sha256"],
        "SERVER_CHANGED_DURING_TRANSFER")
   # Loading the no-tag image can alter only image cache, never containers.
   remote("sg docker -c "+shlex.quote("docker image load --quiet --input "+shlex.quote(remote_archive)),
          timeout=1200)
   after=live_gate(gate,"after")
   need(after["service_identity_sha256"]==before["service_identity_sha256"],
        "SERVER_CONTAINER_IDENTITY_CHANGED")
   stage_done=True
 finally:
  if scratch_remote is not None:
   cleanup(scratch_remote)
 need(stage_done,"IMAGE_STAGE_INCOMPLETE")
 print(json.dumps({"schema":"vision79-v3-approved-image-only-stage",
        "candidate_image":IMAGE,"source_commit":SOURCE,
        "five_running_container_identities_unchanged":True,
        "live_runtime_fingerprint_unchanged":True,
        "candidate_image_in_dell_cache":True,
        "production_containers_changed":False,
        "image_cache_changed":True,
        "candidate_started":False,"mfa_sso_verified":False,
        "full_replacement_parity_verified":False,"release_gate":"HOLD"},sort_keys=True))
class Tests(unittest.TestCase):
 def test_remote_directory_refuses_injection(self):
  for bad in ("/","/home/firelion","/home/firelion/v79-v3-image-transfer.x;rm",
              "/home/firelion/v79-v3-image-transfer.123/../../"):
   with self.assertRaises(Stop):remote_directory(bad)
 def test_remote_directory_unique(self):
  self.assertEqual(remote_directory("/home/firelion/v79-v3-image-transfer.ab12CD34"),
                   "/home/firelion/v79-v3-image-transfer.ab12CD34")
 def test_wrong_host_before_docker(self):
  with patch("socket.gethostname",return_value="other"),patch(__name__+".run") as c:
   with self.assertRaises(Stop):preflight(Path("/missing"))
   c.assert_not_called()
 def test_invalid_archive_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"bad.tar";p.write_bytes(b"not a tar")
   with self.assertRaises(Stop):validate_archive(p)
def main():
 need(len(sys.argv) in (2,3) and sys.argv[1] in ("--self-test","--stage"),"MODE_REQUIRED")
 if sys.argv[1]=="--self-test":
  r=unittest.TextTestRunner(verbosity=1).run(
      unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
  return 0 if r.wasSuccessful() else 1
 need(len(sys.argv)==3,"SERVER_GATE_PATH_REQUIRED")
 stage(Path(sys.argv[2]));return 0
if __name__=="__main__":
 try:sys.exit(main())
 except Stop as e:
  print(json.dumps({"result":"STOP","reason":str(e),
                    "production_containers_changed":"NOT_PROVEN",
                    "release_gate":"HOLD"}));sys.exit(3)
 except Exception as e:
  print(json.dumps({"result":"STOP","reason":"REDACTED_"+type(e).__name__,
                    "production_containers_changed":"NOT_PROVEN",
                    "release_gate":"HOLD"}));sys.exit(3)
